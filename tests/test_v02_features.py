"""Tests for the 0.2 features: font_path, wrapped text, baseline alignment,
fit-to-content boxes, object_fit="none" and non-antialiased rendering."""
from pathlib import Path

from PIL import Image

from picolay import Box, Img, Style, Text, compute_layout, render
from picolay.layout import baseline_of
from picolay.text import font_for, wrap_lines

BUNDLED = str(Path(__file__).parent.parent / "src" / "picolay" / "DejaVuSans.ttf")
LOREM = "Spits fire that is hot enough to melt boulders. Known to cause forest fires unintentionally."


# --- font_path ---------------------------------------------------------------

def test_font_path_is_used():
    assert font_for(Style(font_path=BUNDLED, font_size=20)).path == BUNDLED


def test_font_path_none_uses_bundled_font():
    assert Path(font_for(Style(font_size=20)).path).name == "DejaVuSans.ttf"


# --- wrapping ----------------------------------------------------------------

def test_wrap_lines_fit_width():
    font = font_for(Style(font_size=20))
    lines = wrap_lines(LOREM, font, 200)
    assert len(lines) > 1
    assert " ".join(lines) == LOREM
    for line in lines:
        bbox = font.getbbox(line)
        assert bbox[2] - bbox[0] <= 200


def test_wrap_hyphenates_word_longer_than_line():
    font = font_for(Style(font_size=20))
    lines = wrap_lines("Supercalifragilistic", font, 80)
    assert len(lines) > 1
    assert all(line.endswith("-") for line in lines[:-1])
    assert "".join(line.rstrip("-") for line in lines) == "Supercalifragilistic"


def test_wrapped_text_height_is_lines_times_pitch():
    text = Text(LOREM, style=Style(wrap=True, font_size=20, line_spacing=4))
    root = Box(style=Style(width=200, height=400, flex_direction="column"), children=[text])
    lb = compute_layout(root, 200, 400).children[0]
    assert lb.lines and len(lb.lines) > 1
    assert lb.height == len(lb.lines) * 24
    assert lb.width == 200  # block-like: full width


def test_wrapped_text_shrinks_to_fit_height():
    text = Text(LOREM, style=Style(wrap=True, font_shrink=True, font_size=40, line_spacing=4))
    root = Box(style=Style(width=200, height=80, flex_direction="column"), children=[text])
    lb = compute_layout(root, 200, 80).children[0]
    size = lb.resolved_font_size
    assert size is not None and size < 40
    assert len(lb.lines) * (size + 4) <= 80


def test_wrapped_text_stops_at_min_font_size():
    text = Text(LOREM * 4, style=Style(wrap=True, font_shrink=True, font_size=30, min_font_size=12))
    root = Box(style=Style(width=200, height=40, flex_direction="column"), children=[text])
    lb = compute_layout(root, 200, 40).children[0]
    assert lb.resolved_font_size == 12


def test_wrapped_text_refits_after_flex_grow():
    """A growing wrapped text is shrunk against its final height, not the first-pass one."""
    root = Box(
        style=Style(width=200, height=200, flex_direction="column"),
        children=[
            Box(style=Style(height=120)),
            Text(LOREM, style=Style(wrap=True, font_shrink=True, font_size=40, flex_grow=1)),
        ],
    )
    lb = compute_layout(root, 200, 200).children[1]
    assert lb.height == 80
    assert len(lb.lines) * (lb.resolved_font_size + 4) <= 80


def test_wrapped_text_renders_inside_its_box():
    root = Box(
        style=Style(width=200, height=100, padding=10, background=(255, 255, 255)),
        children=[Text(LOREM, style=Style(wrap=True, font_shrink=True, font_size=30, flex_grow=1))],
    )
    img = render(root, 200, 100)
    dark = [(x, y) for x in range(200) for y in range(100) if img.getpixel((x, y))[0] < 128]
    assert dark
    assert all(10 <= x < 190 and 10 <= y < 90 for x, y in dark)


# --- baseline alignment -----------------------------------------------------

def test_baseline_aligns_text_of_different_sizes():
    row = Box(
        style=Style(width=400, height=100, align_items="baseline", gap=10),
        children=[Text("#006", style=Style(font_size=20)), Text("Pidgey", style=Style(font_size=50))],
    )
    small, big = compute_layout(row, 400, 100).children
    assert abs((small.y + baseline_of(small)) - (big.y + baseline_of(big))) < 1


def test_baseline_of_box_comes_from_first_text():
    inner = Box(style=Style(width="fit", height="fit", padding=(7, 0)), children=[Text("Ab", style=Style(font_size=30))])
    row = Box(
        style=Style(width=400, height=100, align_items="baseline"),
        children=[Text("#1", style=Style(font_size=14)), inner],
    )
    small, box = compute_layout(row, 400, 100).children
    text = box.children[0]
    assert abs((small.y + baseline_of(small)) - (box.y + text.y + baseline_of(text))) < 1


def test_baseline_row_fit_height_holds_both_texts():
    row = Box(
        style=Style(width=400, height="fit", align_items="baseline"),
        children=[Text("#006", style=Style(font_size=20)), Text("Pidgey", style=Style(font_size=50))],
    )
    lb = compute_layout(row, 400, 300)
    assert lb.height < 300
    for c in lb.children:
        assert c.y >= 0 and c.y + c.height <= lb.height + 0.01


# --- fit-to-content boxes ---------------------------------------------------

def test_fit_height_box_in_column_hugs_children():
    root = Box(
        style=Style(width=300, height=300, flex_direction="column"),
        children=[
            Box(style=Style(height="fit", padding=5, gap=4, flex_direction="column"),
                children=[Box(style=Style(width=50, height=20)), Box(style=Style(width=50, height=30))]),
            Box(style=Style(height=10)),
        ],
    )
    fit, after = compute_layout(root, 300, 300).children
    assert fit.height == 5 + 20 + 4 + 30 + 5
    assert fit.width == 300  # width still fills
    assert after.y == fit.height


def test_fit_width_box_can_be_centered():
    root = Box(
        style=Style(width=300, height=100, justify_content="center"),
        children=[Box(style=Style(width="fit", height=40, gap=8),
                      children=[Box(style=Style(width=50, height=40)), Box(style=Style(width=30, height=40))])],
    )
    fit = compute_layout(root, 300, 100).children[0]
    assert fit.width == 88
    assert fit.x == (300 - 88) / 2


def test_default_box_still_fills_available_space():
    root = Box(style=Style(width=300, height=300, flex_direction="column"), children=[Box(style=Style())])
    assert compute_layout(root, 300, 300).children[0].height == 300


# --- object_fit="none" --------------------------------------------------------

def test_object_fit_none_does_not_resample():
    src = Image.new("RGB", (7, 5))
    for x in range(7):
        for y in range(5):
            src.putpixel((x, y), (x * 30, y * 50, 100))
    root = Box(style=Style(width=21, height=15), children=[Img(src, style=Style(width=21, height=15, object_fit="none"))])
    out = render(root, 21, 15)
    assert out.crop((7, 5, 14, 10)).tobytes() == src.tobytes()


def test_object_fit_none_clips_large_image_centered():
    src = Image.new("RGB", (20, 20), (255, 0, 0))
    src.paste((0, 0, 255), (5, 5, 15, 15))
    root = Box(style=Style(width=10, height=10), children=[Img(src, style=Style(width=10, height=10, object_fit="none"))])
    out = render(root, 10, 10)
    assert all(p == (0, 0, 255) for p in out.getdata())


# --- antialias ----------------------------------------------------------------

def test_antialias_false_draws_only_pure_colors():
    root = Box(
        style=Style(width=300, height=200, flex_direction="column"),
        children=[
            Text("Charizard", style=Style(font_size=40)),
            Text(LOREM, style=Style(wrap=True, font_size=18, flex_grow=1)),
        ],
    )
    colors = set(render(root, 300, 200, antialias=False).getdata())
    assert colors == {(0, 0, 0), (255, 255, 255)}
    assert len(set(render(root, 300, 200).getdata())) > 2  # antialiased by default


def test_hard_edged_text_is_measured_as_it_is_drawn():
    """Hard-edged glyphs are hinted wider or narrower than smooth ones, so wrapping has to
    measure in the same mode; otherwise lines overflow their box and get clipped."""
    from PIL import ImageFont

    from picolay.fonts import _BUNDLED_FONT

    content = ("SHEDINJA's hard body doesn't move - not even a twitch. In fact, its body appears "
               "to be merely a hollow shell. It is believed that this POKeMON will steal the spirit "
               "of anyone peering into its hollow body from its back.")
    font = ImageFont.truetype(_BUNDLED_FONT, 12)

    def drawn_width(line):
        bbox = font.getbbox(line, mode="1")
        return bbox[2] - bbox[0]

    def widest_line(width, antialias):
        lb = compute_layout(Text(content, style=Style(wrap=True, font_size=12)), width, 400, antialias=antialias)
        return max(drawn_width(line) for line in lb.lines)

    widths = range(200, 320)
    assert all(widest_line(w, antialias=False) <= w for w in widths)
    # Laid out for smooth text, the same lines would not all fit when drawn hard-edged
    assert any(widest_line(w, antialias=True) > w for w in widths)
