"""Capital letters, digits and a few signs drawn as vector strokes, for headings on KDP interiors.

KDP rejects an interior whose fonts aren't embedded. Text drawn as plain lines contains no font at all, so the check
can't fail and no font licence is involved. Each glyph is a list of strokes on a 4-wide, 6-high grid (y up); a stroke
of one point is a dot, drawn with a round cap. Lower case is printed as capitals: headings read best that way.
"""
from __future__ import annotations

_O = [[(1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0)]]
_P = [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)]]
GLYPHS = {
    "A": [[(0, 0), (2, 6), (4, 0)], [(0.7, 2), (3.3, 2)]],
    "B": [[(0, 0), (0, 6), (3, 6), (4, 5), (4, 4), (3, 3), (0, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (0, 0)]],
    "C": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1)]],
    "D": [[(0, 0), (0, 6), (2.5, 6), (4, 4.5), (4, 1.5), (2.5, 0), (0, 0)]],
    "E": [[(4, 6), (0, 6), (0, 0), (4, 0)], [(0, 3), (3, 3)]],
    "F": [[(4, 6), (0, 6), (0, 0)], [(0, 3), (3, 3)]],
    "G": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 3), (2, 3)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "I": [[(1, 6), (3, 6)], [(2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "J": [[(4, 6), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "K": [[(0, 0), (0, 6)], [(4, 6), (0, 2)], [(1.3, 3.3), (4, 0)]],
    "L": [[(0, 6), (0, 0), (4, 0)]],
    "M": [[(0, 0), (0, 6), (2, 3), (4, 6), (4, 0)]],
    "N": [[(0, 0), (0, 6), (4, 0), (4, 6)]],
    "O": _O,
    "P": _P,
    "Q": _O + [[(2.5, 1.5), (4, 0)]],
    "R": _P + [[(2, 3), (4, 0)]],
    "S": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 4), (1, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "T": [[(0, 6), (4, 6)], [(2, 6), (2, 0)]],
    "U": [[(0, 6), (0, 1), (1, 0), (3, 0), (4, 1), (4, 6)]],
    "V": [[(0, 6), (2, 0), (4, 6)]],
    "W": [[(0, 6), (1, 0), (2, 4), (3, 0), (4, 6)]],
    "X": [[(0, 6), (4, 0)], [(4, 6), (0, 0)]],
    "Y": [[(0, 6), (2, 3), (4, 6)], [(2, 3), (2, 0)]],
    "Z": [[(0, 6), (4, 6), (0, 0), (4, 0)]],
    "0": _O + [[(0.6, 0.6), (3.4, 5.4)]],
    "1": [[(1, 5), (2, 6), (2, 0)], [(1, 0), (3, 0)]],
    "2": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (0, 0), (4, 0)]],
    "3": [[(0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1.5, 3)], [(3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "4": [[(3, 0), (3, 6), (0, 2), (4, 2)]],
    "5": [[(4, 6), (0, 6), (0, 3), (3, 3), (4, 2), (4, 1), (3, 0), (1, 0), (0, 1)]],
    "6": [[(4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3), (0, 3)]],
    "7": [[(0, 6), (4, 6), (1.5, 0)]],
    "8": [[(1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 4), (3, 3), (1, 3), (0, 2), (0, 1), (1, 0), (3, 0), (4, 1), (4, 2), (3, 3)]],
    "9": [[(4, 3), (1, 3), (0, 4), (0, 5), (1, 6), (3, 6), (4, 5), (4, 1), (3, 0), (1, 0), (0, 1)]],
    ":": [[(2, 1), (2, 1)], [(2, 4), (2, 4)]],
    ".": [[(2, 0), (2, 0)]],
    "/": [[(0, 0), (4, 6)]],
    "-": [[(1, 3), (3, 3)]],
    "#": [[(1.3, 0), (1.7, 6)], [(2.7, 0), (3.1, 6)], [(0.3, 2), (4, 2)], [(0, 4), (3.7, 4)]],
    "'": [[(2, 6), (2, 4.5)]],
    " ": [],
}
ADVANCE, SPACE = 5.6, 4.0  # grid units from one letter to the next; a space is narrower


def _clean(text):
    return "".join(char for char in str(text).upper() if char in GLYPHS)


def width(text, size):
    """The width in points of text whose capitals are `size` points high."""
    text = _clean(text)
    if not text:
        return 0.0
    units = sum(SPACE if char == " " else ADVANCE for char in text) - (ADVANCE - 4)
    return units * size / 6


def draw(text, x, y, size):
    """PDF path operators for the text, its baseline starting at (x, y); stroke them with S (round caps for the dots)."""
    unit, parts, cursor = size / 6, [], x
    for char in _clean(text):
        for stroke in GLYPHS[char]:
            (first_x, first_y), *rest = stroke
            parts.append(f"{cursor + first_x * unit:.2f} {y + first_y * unit:.2f} m")
            parts.extend(f"{cursor + px * unit:.2f} {y + py * unit:.2f} l" for px, py in (rest or [(first_x, first_y)]))
        cursor += (SPACE if char == " " else ADVANCE) * unit
    return " ".join(parts)
