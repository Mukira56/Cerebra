"""Low-content book interiors for Amazon KDP: print-ready PDFs of ruled, dot-grid and graph pages (docs/ETSY_AMAZON_PLAN.md,
phase 4).

Drawn by code, not by AI, so Amazon's AI-content disclosure doesn't apply. The pages carry only vector lines and dots, with
no text at all: KDP requires every font in an interior to be embedded, and a font-free interior can't fail that check.
Each page is the trim size exactly (no bleed), the wide gutter margin sits on the binding side (left on right-hand pages,
right on left-hand pages) and grows with the page count as KDP's margin table asks. Pages share two drawing streams (one
per side), so even an 828-page notebook is a few kilobytes.
"""
from __future__ import annotations

from . import books

POINTS = 72  # a PDF point is 1/72 inch
# Each style: (label, kind, spacing in inches). College and wide rule are the US school standards (9/32 and 11/32 inch).
STYLES = {
    "college": ("College-ruled lined pages", "lines", 9 / 32),
    "wide": ("Wide-ruled lined pages", "lines", 11 / 32),
    "dot": ("Dot grid (5 mm)", "dots", 5 / 25.4),
    "graph": ("Graph paper (4 squares per inch)", "grid", 0.25),
    "bordered": ("Bordered pages for sketching", "frame", 0.0),
}
OUTSIDE, TOP, BOTTOM = 0.5, 0.6, 0.5  # inches: generous room so lines stay well inside KDP's safe area
GRAY, WIDTH = 0.6, 0.5  # light grey lines, half a point wide: visible, never louder than the writing


def _number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _page_stream(width, height, left, right, style):
    """Drawing operators for one page, in points, inside the margins."""
    label, kind, spacing = STYLES[style]
    x0, x1, y0, y1 = left * POINTS, (width - right) * POINTS, BOTTOM * POINTS, (height - TOP) * POINTS
    step = spacing * POINTS
    parts = [f"{GRAY} G {WIDTH} w"]
    if kind == "lines":
        y = y1
        while y >= y0:
            parts.append(f"{_number(x0)} {_number(y)} m {_number(x1)} {_number(y)} l")
            y -= step
        parts.append("S")
    elif kind == "dots":  # a zero-length line with a round cap is a dot
        parts = [f"{GRAY - 0.1} G 1.3 w 1 J"]
        y = y1
        while y >= y0:
            x = x0
            while x <= x1:
                parts.append(f"{_number(x)} {_number(y)} m {_number(x)} {_number(y)} l")
                x += step
            y -= step
        parts.append("S")
    elif kind == "grid":
        parts = [f"{GRAY + 0.1} G 0.35 w"]
        count_x, count_y = int((x1 - x0) // step), int((y1 - y0) // step)
        right_edge, bottom_edge = x0 + count_x * step, y1 - count_y * step
        for column in range(count_x + 1):
            x = x0 + column * step
            parts.append(f"{_number(x)} {_number(bottom_edge)} m {_number(x)} {_number(y1)} l")
        for row in range(count_y + 1):
            y = y1 - row * step
            parts.append(f"{_number(x0)} {_number(y)} m {_number(right_edge)} {_number(y)} l")
        parts.append("S")
    else:  # a thin frame around the drawing area
        parts.append(f"{_number(x0)} {_number(y0)} {_number(x1 - x0)} {_number(y1 - y0)} re S")
    return "\n".join(parts).encode("ascii")


def build(style, trim, pages, paper="white"):
    """The interior PDF (bytes) and what it is. Raises ValueError for anything KDP won't print."""
    if style not in STYLES:
        raise ValueError("Choose one of: " + ", ".join(label for label, _kind, _space in STYLES.values()))
    pages = int(pages)
    pages += pages % 2  # KDP prints in leaves: an even page count
    problem = books.check_format(trim, pages, paper)
    if problem:
        raise ValueError(problem)
    width, height = books.PAPERBACK_TRIMS[trim]
    gutter = books.inside_margin(pages)
    right_hand = _page_stream(width, height, gutter, OUTSIDE, style)  # odd pages: binding on the left
    left_hand = _page_stream(width, height, OUTSIDE, gutter, style)  # even pages: binding on the right
    media = f"[0 0 {_number(width * POINTS)} {_number(height * POINTS)}]"

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
               b"<< /Length %d >>\nstream\n" % len(right_hand) + right_hand + b"\nendstream",
               b"<< /Length %d >>\nstream\n" % len(left_hand) + left_hand + b"\nendstream"]
    kids = []
    for number in range(1, pages + 1):
        kids.append(f"{len(objects) + 1} 0 R")
        content = 3 if number % 2 else 4
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox {media} /TrimBox {media} /Contents {content} 0 R /Resources << >> >>".encode("ascii"))
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>".encode("ascii")

    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode("ascii") + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii")
    out += b"".join(f"{offset:010d} 00000 n \n".encode("ascii") for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    return bytes(out), {"style": style, "label": STYLES[style][0], "trim": trim, "pages": pages, "paper": paper,
                        "gutter": gutter, "bytes": len(out)}


def save(folder, style, trim, pages, paper="white"):
    """Write the interior into the owner's books folder; returns where it is and the KDP settings to choose."""
    data, info = build(style, trim, pages, paper)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{style}-{trim}-{info['pages']}p-{paper}.pdf"
    path.write_bytes(data)
    return {**info, "file": path.name, "path": str(path),
            "kdp": [f"Trim size {trim.replace('x', ' × ')} in, no bleed, {paper} paper, black ink",
                    f"Upload {path.name} as the manuscript; {info['pages']} pages",
                    "AI-generated content: No (the pages are drawn by code). Answer for the cover separately"]}
