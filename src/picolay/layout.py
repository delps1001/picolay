from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .nodes import Box, Img, Text
from .style import FIT, Style
from .text import fit_wrapped, font_for, measuring, text_bbox, wrapped_height

Node = Union[Box, Text, Img]


@dataclass
class LayoutBox:
    """Resolved layout information for a node."""
    node: Node
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    children: list[LayoutBox] = None
    resolved_font_size: int | None = None
    # Wrapped text: the exact lines to draw (set when style.wrap is True)
    lines: list[str] | None = None
    # Box: distance from its top edge to the baseline of its first text, if any
    box_baseline: float | None = None
    # Box: size its content needs (used for width/height="fit")
    natural_width: float = 0
    natural_height: float = 0

    def __post_init__(self):
        if self.children is None:
            self.children = []


def _resolve_dimension(value, parent_size: float) -> float | None:
    """Resolve a width/height value. Fractions (0 < v <= 1.0) are relative to parent."""
    if value is None or value == FIT:
        return None
    if isinstance(value, float) and 0.0 < value <= 1.0:
        return value * parent_size
    return float(value)


def _text_intrinsic_size(node: Text, font_size: int | None = None) -> tuple[float, float]:
    """Compute intrinsic (width, height) of a single-line text node."""
    if not node.content:
        return (0, 0)
    font = font_for(node.style, font_size or node.style.font_size)
    bbox = text_bbox(font, node.content)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return (w, h)


def _img_intrinsic_size(node: Img) -> tuple[float, float]:
    """Get intrinsic size of the source image."""
    img = node.load_image()
    if img is None:
        return (0, 0)
    return (float(img.width), float(img.height))


def compute_layout(node: Node, available_w: float, available_h: float, antialias: bool = True) -> LayoutBox:
    """Compute layout for the full node tree, starting at (0, 0).

    Pass antialias=False if the tree will be rendered that way: hard-edged text has
    slightly different widths, which changes where it wraps and how far it shrinks.
    """
    with measuring(antialias):
        return _layout_node(node, available_w, available_h, parent_is_row=True, has_flex_grow=False)


def _clamp(s: Style, w: float, h: float, available_w: float, available_h: float) -> tuple[float, float]:
    if s.max_width is not None:
        w = min(w, _resolve_dimension(s.max_width, available_w))
    if s.max_height is not None:
        h = min(h, _resolve_dimension(s.max_height, available_h))
    if s.min_width is not None:
        w = max(w, float(s.min_width))
    if s.min_height is not None:
        h = max(h, float(s.min_height))
    return w, h


def _fit_text(lb: LayoutBox) -> None:
    """(Re)wrap a wrapped text node to its box, shrinking the font if allowed."""
    s = lb.node.style
    max_w = max(0, lb.width - s.h_padding - s.h_border)
    max_h = max(0, lb.height - s.v_padding - s.v_border)
    size, lines = fit_wrapped(s, lb.node.content, max_w, max_h)
    lb.lines = lines
    lb.resolved_font_size = size if size != s.font_size else None


def baseline_of(lb: LayoutBox) -> float | None:
    """Distance from the top of a laid-out node to its first text baseline (None if no text)."""
    node = lb.node
    s = node.style
    if isinstance(node, Text):
        if not node.content:
            return None
        size = lb.resolved_font_size or s.font_size
        font = font_for(s, size)
        ascent, _ = font.getmetrics()
        top = s.padding_top + s.border_width
        if s.wrap:
            return top + ascent  # lines are drawn from the top of the content box
        bbox = text_bbox(font, node.content)
        ch = max(0, lb.height - s.v_padding - s.v_border)
        # Mirrors render._draw_text: glyph box centered vertically, origin shifted by bbox[1]
        return top + (ch - (bbox[3] - bbox[1])) / 2 - bbox[1] + ascent
    if isinstance(node, Box):
        return lb.box_baseline
    return None


def _layout_node(
    node: Node,
    available_w: float,
    available_h: float,
    parent_is_row: bool = True,
    has_flex_grow: bool = False,
) -> LayoutBox:
    """Layout a single node within available space.

    has_flex_grow: if True and node has no explicit main-axis size, start at 0
    (space will be assigned during flex_grow distribution in the parent).
    """
    s = node.style

    w = _resolve_dimension(s.width, available_w)
    h = _resolve_dimension(s.height, available_h)

    if isinstance(node, Text):
        if s.wrap:
            max_cw = (w if w is not None else available_w) - s.h_padding - s.h_border
            max_ch = (h if h is not None else available_h) - s.v_padding - s.v_border
            font_size, lines = fit_wrapped(s, node.content, max(0, max_cw), max(0, max_ch))
            iw = max(0, max_cw)  # wrapped text is block-like: it takes the full width
            ih = wrapped_height(s, font_size, len(lines)) if node.content else 0
        else:
            lines = None
            font_size = s.font_size
            iw, ih = _text_intrinsic_size(node, font_size)

            # Auto-shrink font to fit available width
            if s.font_shrink:
                if w is not None:
                    max_content_w = w - s.h_padding - s.h_border
                else:
                    max_content_w = available_w - s.h_padding - s.h_border
                floor = max(1, s.min_font_size)
                while font_size > floor and iw > max_content_w:
                    font_size -= 1
                    iw, ih = _text_intrinsic_size(node, font_size)

        if w is None:
            if has_flex_grow and s.flex_grow > 0 and parent_is_row:
                w = 0
            else:
                w = min(iw + s.h_padding + s.h_border, available_w)
        if h is None:
            if has_flex_grow and s.flex_grow > 0 and not parent_is_row:
                h = 0
            else:
                h = min(ih + s.v_padding + s.v_border, available_h)
        w, h = _clamp(s, w, h, available_w, available_h)
        lb = LayoutBox(node=node, width=w, height=h, lines=lines)
        if font_size != s.font_size:
            lb.resolved_font_size = font_size
        return lb

    if isinstance(node, Img):
        iw, ih = _img_intrinsic_size(node)
        if w is None:
            if has_flex_grow and s.flex_grow > 0 and parent_is_row:
                w = 0
            else:
                w = min(iw + s.h_padding + s.h_border, available_w)
        if h is None:
            if has_flex_grow and s.flex_grow > 0 and not parent_is_row:
                h = 0
            else:
                h = min(ih + s.v_padding + s.v_border, available_h)
        w, h = _clamp(s, w, h, available_w, available_h)
        return LayoutBox(node=node, width=w, height=h)

    # Box node
    fit_w = s.width == FIT
    fit_h = s.height == FIT
    if w is None:
        if has_flex_grow and s.flex_grow > 0 and parent_is_row and not fit_w:
            w = 0  # will be filled by flex_grow
        else:
            w = available_w
    if h is None:
        if has_flex_grow and s.flex_grow > 0 and not parent_is_row and not fit_h:
            h = 0  # will be filled by flex_grow
        else:
            h = available_h
    w, h = _box_clamp(s, w, h, available_w, available_h)

    layout = _layout_box(node, w, h)
    if fit_w or fit_h:
        # Shrink-wrap: lay out again at the size the children need
        nw = min(layout.natural_width, available_w) if fit_w else w
        nh = min(layout.natural_height, available_h) if fit_h else h
        nw, nh = _box_clamp(s, nw, nh, available_w, available_h)
        layout = _layout_box(node, nw, nh)
    return layout


def _box_clamp(s: Style, w: float, h: float, available_w: float, available_h: float) -> tuple[float, float]:
    if s.min_width is not None:
        w = max(w, float(s.min_width))
    if s.min_height is not None:
        h = max(h, float(s.min_height))
    if s.max_width is not None:
        w = min(w, _resolve_dimension(s.max_width, available_w))
    if s.max_height is not None:
        h = min(h, _resolve_dimension(s.max_height, available_h))
    # min wins over max
    if s.min_width is not None:
        w = max(w, float(s.min_width))
    if s.min_height is not None:
        h = max(h, float(s.min_height))
    return w, h


def _layout_box(node: Box, w: float, h: float) -> LayoutBox:
    """Lay out a Box of a known size and position its children."""
    s = node.style
    layout = LayoutBox(node=node, width=w, height=h)
    layout.natural_width = s.h_padding + s.h_border
    layout.natural_height = s.v_padding + s.v_border

    if not node.children:
        return layout

    # Content area (inside border + padding)
    content_x = s.padding_left + s.border_width
    content_y = s.padding_top + s.border_width
    content_w = max(0, w - s.h_padding - s.h_border)
    content_h = max(0, h - s.v_padding - s.v_border)

    is_row = s.flex_direction == "row"
    baseline_align = is_row and s.align_items == "baseline"

    # Check if any child has flex_grow
    any_grow = any(c.style.flex_grow > 0 for c in node.children)

    # First pass: layout children to get their sizes
    child_layouts = []
    for child in node.children:
        cs = child.style
        child_avail_w = max(0, content_w - cs.h_margin)
        child_avail_h = max(0, content_h - cs.v_margin)
        cl = _layout_node(child, child_avail_w, child_avail_h, parent_is_row=is_row, has_flex_grow=any_grow)
        child_layouts.append(cl)

    # Calculate total fixed size and flex_grow
    total_fixed = 0
    total_grow = 0.0
    gap = s.gap
    num_children = len(child_layouts)

    for cl in child_layouts:
        cs = cl.node.style
        if is_row:
            total_fixed += cl.width + cs.h_margin
        else:
            total_fixed += cl.height + cs.v_margin
        total_grow += cs.flex_grow

    total_gaps = gap * max(0, num_children - 1)
    main_size = content_w if is_row else content_h
    remaining = max(0, main_size - total_fixed - total_gaps)

    # Natural content size, before any growing or stretching (for width/height="fit")
    natural_main = total_fixed + total_gaps
    if baseline_align:
        natural_cross = _baseline_extent(child_layouts)
    elif is_row:
        natural_cross = max((cl.height + cl.node.style.v_margin for cl in child_layouts), default=0)
    else:
        natural_cross = max((cl.width + cl.node.style.h_margin for cl in child_layouts), default=0)
    if is_row:
        layout.natural_width += natural_main
        layout.natural_height += natural_cross
    else:
        layout.natural_width += natural_cross
        layout.natural_height += natural_main

    # Distribute flex_grow
    if total_grow > 0:
        for cl in child_layouts:
            cs = cl.node.style
            if cs.flex_grow > 0:
                extra = remaining * (cs.flex_grow / total_grow)
                if is_row:
                    cl.width += extra
                else:
                    cl.height += extra
        # Enforce max_width/max_height after flex_grow distribution
        for cl in child_layouts:
            cs = cl.node.style
            if cs.flex_grow > 0:
                child_avail_w = max(0, content_w - cs.h_margin)
                child_avail_h = max(0, content_h - cs.v_margin)
                if cs.max_width is not None:
                    cl.width = min(cl.width, _resolve_dimension(cs.max_width, child_avail_w))
                if cs.max_height is not None:
                    cl.height = min(cl.height, _resolve_dimension(cs.max_height, child_avail_h))
        # After distributing grow, re-layout children that grew (to lay out their children with correct size)
        for cl in child_layouts:
            cs = cl.node.style
            if cs.flex_grow > 0 and isinstance(cl.node, Box) and cl.node.children:
                new_cl = _layout_node(cl.node, cl.width, cl.height, parent_is_row=is_row, has_flex_grow=False)
                cl.children = new_cl.children
                cl.box_baseline = new_cl.box_baseline

    # Handle align_items=stretch
    for cl in child_layouts:
        cs = cl.node.style
        if s.align_items == "stretch":
            if is_row:
                if cl.node.style.height is None:
                    cl.height = max(0, content_h - cs.v_margin)
            else:
                if cl.node.style.width is None:
                    cl.width = max(0, content_w - cs.h_margin)

    # Wrapped text: re-wrap (and re-shrink) to its final size
    for cl in child_layouts:
        if isinstance(cl.node, Text) and cl.node.style.wrap and cl.node.content:
            _fit_text(cl)

    # Compute main-axis sizes for justify
    total_main = 0
    for cl in child_layouts:
        cs = cl.node.style
        if is_row:
            total_main += cl.width + cs.h_margin
        else:
            total_main += cl.height + cs.v_margin

    total_main_with_gap = total_main + total_gaps

    # Justify content
    justify = s.justify_content
    main_offset = 0.0
    extra_gap = 0.0

    if justify == "start":
        main_offset = 0
    elif justify == "center":
        main_offset = (main_size - total_main_with_gap) / 2
    elif justify == "end":
        main_offset = main_size - total_main_with_gap
    elif justify == "space_between":
        if num_children <= 1:
            main_offset = (main_size - total_main) / 2
            extra_gap = 0
        else:
            space = main_size - total_main
            extra_gap = space / (num_children - 1)
            main_offset = 0
    elif justify == "space_around":
        if num_children == 0:
            main_offset = 0
        else:
            space = main_size - total_main
            slot = space / num_children
            main_offset = slot / 2
            extra_gap = slot

    # Baseline alignment: the shared baseline, measured from the top of the content area
    if baseline_align:
        shared_baseline = max((_child_baseline(cl) + cl.node.style.margin_top for cl in child_layouts), default=0)

    # Position children
    cursor = main_offset
    for cl in child_layouts:
        cs = cl.node.style

        if is_row:
            cl.x = content_x + cursor + cs.margin_left
            cursor += cl.width + cs.h_margin
        else:
            cl.y = content_y + cursor + cs.margin_top
            cursor += cl.height + cs.v_margin

        # Add gap/extra_gap
        if justify == "space_between" and num_children > 1:
            cursor += extra_gap
        elif justify == "space_around":
            cursor += extra_gap
        else:
            cursor += gap

        # Cross axis position
        cross_size = content_h if is_row else content_w
        if is_row:
            child_cross = cl.height + cs.v_margin
            if s.align_items == "start":
                cl.y = content_y + cs.margin_top
            elif s.align_items == "center":
                cl.y = content_y + (cross_size - child_cross) / 2 + cs.margin_top
            elif s.align_items == "end":
                cl.y = content_y + cross_size - child_cross + cs.margin_top
            elif s.align_items == "stretch":
                cl.y = content_y + cs.margin_top
            elif baseline_align:
                cl.y = content_y + shared_baseline - _child_baseline(cl)
            else:
                cl.y = content_y + cs.margin_top
        else:
            child_cross = cl.width + cs.h_margin
            if s.align_items == "start":
                cl.x = content_x + cs.margin_left
            elif s.align_items == "center":
                cl.x = content_x + (cross_size - child_cross) / 2 + cs.margin_left
            elif s.align_items == "end":
                cl.x = content_x + cross_size - child_cross + cs.margin_left
            elif s.align_items == "stretch":
                cl.x = content_x + cs.margin_left
            else:
                cl.x = content_x + cs.margin_left

        layout.children.append(cl)

    # This box's baseline is that of its first child that has one (as in CSS flexbox)
    for cl in layout.children:
        b = baseline_of(cl)
        if b is not None:
            layout.box_baseline = cl.y + b
            break

    return layout


def _child_baseline(cl: LayoutBox) -> float:
    """Baseline used for align_items="baseline"; nodes without text align by their bottom edge."""
    b = baseline_of(cl)
    return b if b is not None else cl.height


def _baseline_extent(child_layouts: list[LayoutBox]) -> float:
    """Cross size a baseline-aligned row needs."""
    if not child_layouts:
        return 0
    shared = max(_child_baseline(cl) + cl.node.style.margin_top for cl in child_layouts)
    return max(shared - _child_baseline(cl) + cl.height + cl.node.style.margin_bottom for cl in child_layouts)
