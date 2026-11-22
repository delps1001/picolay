# picolay

A tiny flexbox-style layout engine that renders straight to a [Pillow](https://python-pillow.org/) image. It was built for e-ink picture frames, where you want CSS-like layout without a browser.

![The bird frame's field-guide layout, rendered with picolay](docs/fieldguide-example.png)

*The field-guide layout from an 800×480 bird-sighting e-ink frame, rendered with picolay.*

The only dependency is Pillow. DejaVu Sans is bundled as the default font.

## Install

```bash
pip install "picolay @ git+https://github.com/delps1001/picolay@v0.1.1"
```

## Example

```python
from picolay import Box, Img, Style, Text, render

card = Box(
    style=Style(width=200, height=300, flex_direction="column", background=(255, 255, 255)),
    children=[
        Img(src="sprite.png", style=Style(flex_grow=0.7, object_fit="contain", image_rendering="pixelated")),
        Box(
            style=Style(flex_grow=0.3, align_items="center", justify_content="center"),
            children=[Text("House Finch", style=Style(font_size=14, text_align="center"))],
        ),
    ],
)

image = render(card, 200, 300)          # white background
overlay = render(card, 200, 300, background=None)  # transparent RGBA
```

## Building blocks

- `Box(style, children)`: a flex container.
- `Text(content, style=...)`: wrapped text. `font_shrink=True` shrinks the font to fit.
- `Img(src, style=...)`: a PIL image, or a path to one.
- `Style(...)`: `width`/`height` (pixels, or a float between 0 and 1.0 for a fraction of the parent), `min_*`/`max_*`, `padding`, `margin`, `border`, `background`, `flex_direction`, `justify_content`, `align_items`, `gap`, `flex_grow`, `object_fit`, `image_rendering`, `font_size`, `font_color`, `text_align`, `font_shrink`, `overflow`.
- `compute_layout(node, width, height)`: the layout tree without rendering, handy for tests.

## Development

```bash
uv run --extra dev pytest
```

## License

picolay is released into the public domain under [the Unlicense](LICENSE). Do whatever you like with it.

The bundled DejaVu Sans font (`src/picolay/DejaVuSans.ttf`) keeps its own permissive [DejaVu Fonts license](https://dejavu-fonts.github.io/License.html).
