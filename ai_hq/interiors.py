"""Low-content book interiors for Amazon KDP: print-ready PDFs of ruled, dot-grid and graph pages (docs/ETSY_AMAZON_PLAN.md,
phase 4).

Drawn by code, not by AI, so Amazon's AI-content disclosure doesn't apply. The pages carry only vector lines and dots:
KDP requires every font in an interior to be embedded, and a font-free interior can't fail that check. Logbooks and the
weekly planner print their headings as strokes too (ai_hq/strokefont.py), so they contain no font either.
Each page is the trim size exactly (no bleed), the wide gutter margin sits on the binding side (left on right-hand pages,
right on left-hand pages) and grows with the page count as KDP's margin table asks. Pages share two drawing streams (one
per side), so even an 828-page notebook is a few kilobytes.
"""
from __future__ import annotations

from . import books, strokefont

POINTS = 72  # a PDF point is 1/72 inch
# Each style: (label, kind, spacing in inches). College and wide rule are the US school standards (9/32 and 11/32 inch).
STYLES = {
    "college": ("College-ruled lined pages", "lines", 9 / 32),
    "wide": ("Wide-ruled lined pages", "lines", 11 / 32),
    "dot": ("Dot grid (5 mm)", "dots", 5 / 25.4),
    "graph": ("Graph paper (4 squares per inch)", "grid", 0.25),
    "bordered": ("Bordered pages for sketching", "frame", 0.0),
    "mileage": ("Mileage log (date, odometer start and end, miles, purpose)", "table", 0.3),
    "reading": ("Reading log (date, title, author, pages, rating)", "table", 0.3),
    "workout": ("Workout log (date, exercise, sets, reps, weight)", "table", 0.3),
    "blood_pressure": ("Blood pressure log (date, time, systolic, diastolic, pulse)", "table", 0.3),
    "weekly": ("Undated weekly planner (seven days and notes)", "week", 9 / 32),
}
# Logbooks: the title printed on each page and the columns, with their relative widths. The mileage log keeps what the
# IRS asks a business-mileage record to show: the date, the miles and the business purpose.
TABLES = {
    "mileage": ("MILEAGE LOG", [("DATE", 1), ("START", 1), ("END", 1), ("MILES", 0.8), ("PURPOSE / DESTINATION", 2.8)]),
    "reading": ("READING LOG", [("DATE", 1), ("TITLE", 2.5), ("AUTHOR", 1.7), ("PAGES", 0.8), ("RATING", 0.9)]),
    "workout": ("WORKOUT LOG", [("DATE", 1), ("EXERCISE", 2.6), ("SETS", 0.7), ("REPS", 0.7), ("WEIGHT", 1)]),
    "blood_pressure": ("BLOOD PRESSURE LOG", [("DATE", 1), ("TIME", 0.9), ("SYS", 0.7), ("DIA", 0.7), ("PULSE", 0.8), ("NOTES", 2)]),
}
DAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY", "NOTES")
INK = 0.2  # headings: near black, so they print crisply
OUTSIDE, TOP, BOTTOM = 0.5, 0.6, 0.5  # inches: generous room so lines stay well inside KDP's safe area
GRAY, WIDTH = 0.6, 0.5  # light grey lines, half a point wide: visible, never louder than the writing


def _number(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _text(text, x, y, size, limit=None):
    """Stroked heading text; shrunk to fit `limit` points of width when given."""
    if limit:
        size = max(4.5, min(size, size * limit / max(strokefont.width(text, size), 0.1)))
    return f"{INK} G {size / 9:.2f} w 1 J 1 j " + strokefont.draw(text, x, y, size) + " S"


def _table(x0, x1, y0, y1, step, style):
    title, columns = TABLES[style]
    title_size = 9
    parts = [_text(title, (x0 + x1 - strokefont.width(title, title_size)) / 2, y1 - title_size, title_size)]
    top = y1 - title_size - 10
    head = 16
    rows = int((top - head - y0) // step)
    bottom = top - head - rows * step
    total = sum(share for _name, share in columns)
    edges, x = [x0], x0
    for _name, share in columns:
        x += (x1 - x0) * share / total
        edges.append(x)
    for (name, _share), left, right in zip(columns, edges, edges[1:]):
        parts.append(_text(name, left + 3, top - head + 5, 6, limit=right - left - 6))
    lines = [f"{_number(GRAY - 0.15)} G 0.75 w {_number(x0)} {_number(bottom)} {_number(x1 - x0)} {_number(top - bottom)} re S",
             f"{_number(x0)} {_number(top - head)} m {_number(x1)} {_number(top - head)} l S", f"{GRAY} G {WIDTH} w"]
    for row in range(1, rows):
        y = top - head - row * step
        lines.append(f"{_number(x0)} {_number(y)} m {_number(x1)} {_number(y)} l")
    for x in edges[1:-1]:
        lines.append(f"{_number(x)} {_number(bottom)} m {_number(x)} {_number(top)} l")
    lines.append("S")
    return "\n".join(lines + parts)


def _week(x0, x1, y0, y1, step):
    """An undated week: "WEEK OF" with a line to write the date, then the seven days and notes in two columns."""
    size = 8
    label = "WEEK OF"
    parts = [_text(label, x0, y1 - size, size),
             f"{GRAY} G {WIDTH} w {_number(x0 + strokefont.width(label, size) + 6)} {_number(y1 - size)} m {_number(x0 + (x1 - x0) * 0.6)} {_number(y1 - size)} l S"]
    top, gap = y1 - size - 14, 10
    box_w, box_h = (x1 - x0 - gap) / 2, (top - y0 - 3 * gap) / 4
    for index, day in enumerate(DAYS):
        left = x0 + (index % 2) * (box_w + gap)
        box_top = top - (index // 2) * (box_h + gap)
        parts.append(f"{_number(GRAY - 0.15)} G 0.75 w {_number(left)} {_number(box_top - box_h)} {_number(box_w)} {_number(box_h)} re S")
        parts.append(_text(day, left + 5, box_top - 11, 6.5))
        rules, y = [f"{GRAY} G {WIDTH} w"], box_top - 16 - step
        while y > box_top - box_h + 4:
            rules.append(f"{_number(left + 5)} {_number(y)} m {_number(left + box_w - 5)} {_number(y)} l")
            y -= step
        parts.append(" ".join(rules) + " S")
    return "\n".join(parts)


def _page_stream(width, height, left, right, style):
    """Drawing operators for one page, in points, inside the margins."""
    label, kind, spacing = STYLES[style]
    x0, x1, y0, y1 = left * POINTS, (width - right) * POINTS, BOTTOM * POINTS, (height - TOP) * POINTS
    step = spacing * POINTS
    if kind == "table":
        return _table(x0, x1, y0, y1, step, style).encode("ascii")
    if kind == "week":
        return _week(x0, x1, y0, y1, step).encode("ascii")
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
