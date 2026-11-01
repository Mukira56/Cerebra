"""Text designs for shirts, mugs and other print-on-demand products, drawn by code.

A short phrase in the stroke alphabet (ai_hq/strokefont.py), rendered to a transparent PNG at 4500 x 5400 pixels and 300 DPI:
the size Amazon Merch on Demand asks for, which Printify and other print providers accept too. Pure Python, no image
library: thick strokes are stamped as filled discs into an alpha mask, then written as an RGBA PNG. No AI is involved, so
there's nothing to disclose; trademarks are refused, since print providers and marketplaces take those designs down.
"""
from __future__ import annotations

import re
import struct
import zlib

from . import strokefont
from .etsy import TRADEMARKS

WIDTH, HEIGHT, DPI = 4500, 5400, 300
MARGIN = 250
COLOURS = {"white": (255, 255, 255), "black": (17, 17, 17), "navy": (24, 40, 80), "red": (190, 30, 45), "gold": (230, 175, 40),
           "forest": (30, 90, 55), "pink": (235, 120, 160), "sky": (110, 170, 220)}


def check(text):
    """Problems with the phrase, in plain words: an empty list means it can be made."""
    text = " ".join(str(text or "").split())
    problems = []
    if not 2 <= len(text) <= 80:
        problems.append("Write a short phrase: 2 to 80 characters")
    lowered = text.lower()
    marks = sorted({mark for mark in TRADEMARKS if re.search(r"\b" + re.escape(mark) + r"\b", lowered)})
    if marks:
        problems.append("Remove trademarked names (print providers and marketplaces take these designs down): " + ", ".join(marks))
    missing = sorted({char for char in text.upper() if char not in strokefont.GLYPHS})
    if missing:
        problems.append("These characters can't be drawn yet: " + " ".join(missing))
    return problems


def _layout(text):
    """Lines and a cap height that fill the print area's width, up to four lines."""
    words, usable = text.upper().split(), WIDTH - 2 * MARGIN
    best = None
    for count in range(1, min(4, len(words)) + 1):
        lines, per = [], -(-len(words) // count)
        for start in range(0, len(words), per):
            lines.append(" ".join(words[start:start + per]))
        widest = max(strokefont.width(line, 100) for line in lines)
        size = min(900, usable / widest * 100, (HEIGHT * 0.62) / (len(lines) * 1.5))
        if best is None or size * (1 if count == 1 else 0.97) > best[0]:  # fewer lines win a tie: they read faster
            best = (size, lines)
    return best


def _stamp(mask, x, y, radius):
    """A filled disc of the given radius at (x, y): one slice assignment per row."""
    top, bottom = max(0, int(y - radius)), min(HEIGHT - 1, int(y + radius))
    for row in range(top, bottom + 1):
        half = max(0.0, radius * radius - (row - y) ** 2) ** 0.5
        left, right = max(0, int(x - half)), min(WIDTH, int(x + half) + 1)
        if right > left:
            mask[row * WIDTH + left:row * WIDTH + right] = b"\xff" * (right - left)


def render(text, colour="white"):
    """The design as PNG bytes. Raises ValueError with the problems when the phrase can't be made."""
    problems = check(text)
    if colour not in COLOURS:
        problems.append("Choose a colour: " + ", ".join(COLOURS))
    if problems:
        raise ValueError("; ".join(problems))
    size, lines = _layout(" ".join(text.split()))
    radius, unit, gap = max(6.0, size / 13), size / 6, size * 0.5
    mask = bytearray(WIDTH * HEIGHT)
    block = len(lines) * size + (len(lines) - 1) * gap
    baseline = HEIGHT * 0.42 + block / 2  # centred a little above the middle, where a print sits on the chest
    for index, line in enumerate(lines):
        y0 = baseline - (len(lines) - 1 - index) * (size + gap)
        cursor = (WIDTH - strokefont.width(line, size)) / 2
        for char in line:
            for stroke in strokefont.GLYPHS[char]:
                points = [(cursor + px * unit, y0 - py * unit) for px, py in stroke]  # image rows grow downwards
                if len(points) == 1:
                    points = points * 2
                for (ax, ay), (bx, by) in zip(points, points[1:]):
                    steps = max(1, int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / (radius / 2)))
                    for step in range(steps + 1):
                        _stamp(mask, ax + (bx - ax) * step / steps, ay + (by - ay) * step / steps, radius)
            cursor += (strokefont.SPACE if char == " " else strokefont.ADVANCE) * unit
    red, green, blue = COLOURS[colour]
    row, raw = bytearray(bytes((red, green, blue, 0)) * WIDTH), bytearray()
    for line_start in range(0, WIDTH * HEIGHT, WIDTH):
        row[3::4] = mask[line_start:line_start + WIDTH]
        raw += b"\x00" + row
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    per_metre = round(DPI / 0.0254)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 6, 0, 0, 0))
            + chunk(b"pHYs", struct.pack(">IIB", per_metre, per_metre, 1)) + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def save(folder, text, colour="white"):
    data = render(text, colour)
    folder.mkdir(parents=True, exist_ok=True)
    slug = "-".join(re.findall(r"[a-z0-9]+", text.lower()))[:60] or "design"
    path = folder / f"{slug}-{colour}.png"
    path.write_bytes(data)
    return {"file": path.name, "path": str(path), "bytes": len(data), "width": WIDTH, "height": HEIGHT, "dpi": DPI,
            "use": ["Amazon Merch on Demand: upload as the design (4500 × 5400 px, 300 DPI, transparent PNG)",
                    "Printify: upload it in the product's design step, or in Image / marketplace draft from a Business job",
                    f"Pick shirt colours that contrast with {colour} text"]}


def made(folder):
    files = sorted(folder.glob("*.png"), key=lambda path: path.stat().st_mtime, reverse=True) if folder.is_dir() else []
    return [{"file": path.name, "bytes": path.stat().st_size} for path in files[:30]]
