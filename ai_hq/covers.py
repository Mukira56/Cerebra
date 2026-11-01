"""Full-wrap paperback covers for KDP low-content books, drawn by code (docs/ETSY_AMAZON_PLAN.md, phase 4).

One PDF page: bleed, back cover, spine, front cover, bleed, sized by books.cover_size from the trim, page count and paper.
The title, subtitle and author are vector strokes (ai_hq/strokefont.py), so the cover has no font to embed and no AI
image: KDP's AI question is No for it. The lower right of the back (where KDP prints the barcode) is left empty, all
text keeps 0.25 in inside the trim, and the spine carries the title only from 79 pages, as KDP allows.
"""
from __future__ import annotations

from . import books, strokefont

POINTS = 72
SAFE = 0.25 + books.COVER_BLEED  # inches from the page edge to any text
SPINE_SAFE = 0.0625  # KDP: spine text keeps this far from the spine's folds
# name: (label, background, panel, ink), colours as 0-1 RGB
PALETTES = {
    "navy": ("Navy and cream", (0.11, 0.17, 0.30), (0.96, 0.93, 0.86), (0.96, 0.93, 0.86)),
    "forest": ("Forest green and cream", (0.13, 0.27, 0.20), (0.95, 0.92, 0.84), (0.95, 0.92, 0.84)),
    "terracotta": ("Terracotta and sand", (0.70, 0.36, 0.25), (0.97, 0.91, 0.82), (0.99, 0.96, 0.91)),
    "charcoal": ("Charcoal and mustard", (0.17, 0.17, 0.18), (0.89, 0.71, 0.24), (0.89, 0.71, 0.24)),
    "blush": ("Blush and plum", (0.93, 0.80, 0.79), (0.42, 0.20, 0.33), (0.42, 0.20, 0.33)),
    "sky": ("Sky blue and navy", (0.71, 0.84, 0.92), (0.11, 0.20, 0.36), (0.11, 0.20, 0.36)),
}


def _n(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _rgb(colour, stroke=False):
    return " ".join(_n(part) for part in colour) + (" RG" if stroke else " rg")


def _lines(text, size, limit, most):
    """Words wrapped to `limit` points at `size`, at most `most` lines (the last one shortened with no ellipsis glyph)."""
    lines, current = [], ""
    for word in str(text or "").upper().split():
        trial = f"{current} {word}".strip()
        if current and strokefont.width(trial, size) > limit:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines[:most]


def _fit(text, size, limit, most, smallest):
    """The largest size up to `size` at which the text fits in `most` lines of `limit` points, and those lines."""
    while size > smallest:
        lines = _lines(text, size, limit, most + 1)
        if len(lines) <= most and all(strokefont.width(line, size) <= limit for line in lines):
            return size, lines
        size -= 1
    return smallest, _lines(text, smallest, limit, most)


def _centred(lines, size, middle, top, gap):
    parts, y = [], top
    for line in lines:
        y -= size
        parts.append(strokefont.draw(line, middle - strokefont.width(line, size) / 2, y, size))
        y -= gap
    return " ".join(parts), y


MOTIFS = ("rules", "dots", "checks", "waves", "bars", "double")  # the pattern under the title: one look per collection


def _motif(motif, x0, x1, top):
    """A band of pattern below the title panel, in the panel's colour (stroke and fill already set)."""
    if motif == "dots":
        return "1 J 3 w " + " ".join(f"{_n(x)} {_n(top - row * 10)} m {_n(x)} {_n(top - row * 10)} l" for row in range(3)
                                     for x in [x0 + step * 12 for step in range(int((x1 - x0) // 12) + 1)]) + " S"
    if motif == "checks":
        size = 8
        return " ".join(f"{_n(x0 + index * size * 2)} {_n(top - size)} {_n(size)} {_n(size)} re" for index in range(int((x1 - x0) // (size * 2)) + 1)
                        if x0 + index * size * 2 + size <= x1) + " f"
    if motif == "waves":
        parts = []
        for row in range(3):
            y, points = top - row * 10, []
            for index in range(int((x1 - x0) // 8) + 1):
                points.append(f"{_n(x0 + index * 8)} {_n(y - (4 if index % 2 else 0))}")
            parts.append(points[0] + " m " + " ".join(point + " l" for point in points[1:]))
        return "1 j 1 w " + " ".join(parts) + " S"
    if motif == "bars":
        return " ".join(f"{_n(x0)} {_n(top - row * 9 - (5 - row))} {_n((x1 - x0) * (1 - row * 0.18))} {_n(5 - row)} re" for row in range(5)) + " f"
    if motif == "double":
        return f"1.5 w {_n(x0)} {_n(top - 22)} {_n(x1 - x0)} 22 re S 0.6 w {_n(x0 + 4)} {_n(top - 18)} {_n(x1 - x0 - 8)} 14 re S"
    return "0.8 w " + " ".join(f"{_n(x0)} {_n(top - row * 9)} m {_n(x1)} {_n(top - row * 9)} l" for row in range(5)) + " S"  # rules, like lined pages


def build(title, subtitle="", author="", trim="6x9", pages=120, paper="white", palette="navy", motif="rules"):
    """The cover PDF (bytes) and its measurements. Raises ValueError for what KDP won't print."""
    if palette not in PALETTES:
        raise ValueError("Choose a palette: " + ", ".join(label for label, *_colours in PALETTES.values()))
    if motif not in MOTIFS:
        raise ValueError("Choose a pattern: " + ", ".join(MOTIFS))
    title = " ".join(str(title or "").split())
    if not strokefont.width(title, 10):
        raise ValueError("Give the book a title")
    pages = int(pages) + int(pages) % 2
    problem = books.check_format(trim, pages, paper)
    if problem:
        raise ValueError(problem)
    size_info = books.cover_size(trim, pages, paper)
    trim_w, trim_h = books.PAPERBACK_TRIMS[trim]
    bleed, spine = books.COVER_BLEED, size_info["spine"]
    page_w, page_h = size_info["width"] * POINTS, size_info["height"] * POINTS
    front_x0 = (bleed + trim_w + spine) * POINTS  # the front cover starts after the back and the spine
    front_x1, middle = page_w - SAFE * POINTS, front_x0 + trim_w * POINTS / 2
    _label, background, panel, ink = PALETTES[palette]

    ops = [_rgb(background), f"0 0 {_n(page_w)} {_n(page_h)} re f"]
    # The front: a light panel inside a thin frame, the title on it, a band of rules below, the author at the foot.
    inset = (SAFE + 0.15) * POINTS
    panel_x0, panel_x1 = front_x0 + inset, page_w - inset
    panel_top, panel_bottom = page_h - (SAFE + 0.55) * POINTS, page_h * 0.42
    ops += [_rgb(panel), f"{_n(panel_x0)} {_n(panel_bottom)} {_n(panel_x1 - panel_x0)} {_n(panel_top - panel_bottom)} re f",
            _rgb(panel, stroke=True), "1.2 w", f"{_n(front_x0 + inset - 6)} {_n(panel_bottom - 6)} {_n(panel_x1 - panel_x0 + 12)} {_n(panel_top - panel_bottom + 12)} re S"]
    width_limit = panel_x1 - panel_x0 - 24
    title_size, title_lines = _fit(title, 34, width_limit, 3, 14)
    subtitle_size, subtitle_lines = _fit(subtitle, 11, width_limit, 3, 7) if subtitle else (0, [])
    block = len(title_lines) * (title_size + title_size * 0.45) + (len(subtitle_lines) * (subtitle_size + 5) + 14 if subtitle_lines else 0)
    top = (panel_top + panel_bottom) / 2 + block / 2
    words, after = _centred(title_lines, title_size, middle, top, title_size * 0.45)
    ops += [_rgb(background, stroke=True), f"{_n(title_size / 7)} w 1 J 1 j", words, "S"]
    if subtitle_lines:
        words, _after = _centred(subtitle_lines, subtitle_size, middle, after - 10, 5)
        ops += [f"{_n(subtitle_size / 9)} w", words, "S"]
    ops += [_rgb(panel, stroke=True), _rgb(panel), _motif(motif, panel_x0, panel_x1, panel_bottom - 0.45 * POINTS)]
    if author:
        author_size, author_lines = _fit(author, 12, width_limit, 1, 7)
        words, _after = _centred(author_lines, author_size, middle, SAFE * POINTS + 0.35 * POINTS + author_size, 0)
        ops += [_rgb(ink, stroke=True), f"{_n(author_size / 8)} w", words, "S"]
    # The spine: the title (and author) reading from top to bottom, as on US books, when the book is thick enough.
    if size_info["spine_text"]:
        spine_x0 = (bleed + trim_w) * POINTS
        spine_size = min(12.0, spine * POINTS - 2 * SPINE_SAFE * POINTS - 2)
        line = title.upper() + (f"  -  {author.upper()}" if author else "")
        run = page_h - 2 * (SAFE + 0.3) * POINTS
        while spine_size > 4 and strokefont.width(line, spine_size) > run:
            spine_size -= 0.5
        if spine_size >= 4:
            centre_x = spine_x0 + spine * POINTS / 2
            start_y = page_h / 2 + strokefont.width(line, spine_size) / 2
            # rotate 90 degrees clockwise about the spine's centre line; the glyphs' baseline runs downwards
            ops += [_rgb(ink, stroke=True), f"{_n(spine_size / 8)} w", f"q 0 -1 1 0 {_n(centre_x - spine_size / 2)} {_n(start_y)} cm",
                    strokefont.draw(line, 0, 0, spine_size), "S Q"]
    stream = "\n".join(ops).encode("ascii")
    media = f"[0 0 {_n(page_w)} {_n(page_h)}]"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [3 0 R] /Count 1 >>".encode("ascii"),
               f"<< /Type /Page /Parent 2 0 R /MediaBox {media} /TrimBox {media} /Contents 4 0 R /Resources << >> >>".encode("ascii"),
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"]
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    out += b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return bytes(out), {**size_info, "trim": trim, "pages": pages, "paper": paper, "palette": palette, "motif": motif, "bytes": len(out)}


def save(folder, name, **fields):
    """Write the cover next to its interior; returns where it is and the KDP settings that go with it."""
    data, info = build(**fields)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}-cover-{info['palette']}.pdf"
    path.write_bytes(data)
    return {**info, "file": path.name, "path": str(path),
            "kdp": [f"Cover: upload {path.name} as a print-ready PDF ({info['width']} × {info['height']} in, spine {info['spine']} in)",
                    "Leave the barcode to KDP: the lower right of the back is kept empty for it",
                    "AI-generated content for the cover: No (it's drawn by code)"]}
