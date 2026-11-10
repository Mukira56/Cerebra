"""A CV as a plain, readable PDF (US Letter, Helvetica), written with no outside library: a name, a headline, then sections
of paragraphs and bullet points, wrapped to the page and continued onto further pages. Text only, which applicant
tracking systems read reliably.
"""
from __future__ import annotations

PAGE_W, PAGE_H, MARGIN = 612, 792, 54  # US Letter in points, 0.75 inch margins
# Helvetica advance widths (per 1000 units) for printable ASCII; anything else counts as an average letter.
_W = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + [278, 278, 584, 584, 584, 556,
      1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611,
      278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556,
      500, 722, 500, 500, 500, 334, 260, 334, 584]


def _width(text, size, bold=False):
    total = sum(_W[ord(char) - 32] if 32 <= ord(char) < 127 else 556 for char in text)
    return total * size / 1000 * (1.06 if bold else 1.0)  # bold runs slightly wider: wrap a little earlier


def wrap(text, size, width, bold=False):
    """Lines of text that fit the width, breaking between words (a word longer than a line is split)."""
    lines, line = [], ""
    for word in str(text).split():
        while _width(word, size, bold) > width:  # a very long word (a URL): split it
            cut = max(1, int(len(word) * width / _width(word, size, bold)) - 1)
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:cut])
            word = word[cut:]
        candidate = f"{line} {word}".strip()
        if _width(candidate, size, bold) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _escape(text):
    raw = str(text).encode("cp1252", "replace")  # Helvetica's WinAnsi encoding: curly quotes, dashes and bullets stay
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def build(name, headline, sections, contact=""):
    """The PDF bytes. sections: [(heading, [block, ...])], where a block is a paragraph string or ("bullet", text)."""
    pages, ops, y = [], [], PAGE_H - MARGIN

    def put(text, size, x, bold=False, gap=None):
        nonlocal ops, y
        if y - size < MARGIN:
            pages.append(ops)
            ops, y = [], PAGE_H - MARGIN
        y -= gap if gap is not None else size * 1.35
        ops.append(b"BT /%s %d Tf %d %d Td (%s) Tj ET" % (b"F2" if bold else b"F1", size, x, round(y), _escape(text)))

    usable = PAGE_W - 2 * MARGIN
    for line in wrap(name, 20, usable, True):
        put(line, 20, MARGIN, True, 22)
    for line in wrap(headline, 11, usable):
        put(line, 11, MARGIN)
    for line in wrap(contact, 9.5, usable):
        put(line, 9, MARGIN)
    for heading, blocks in sections:
        y -= 8
        put(heading.upper(), 10.5, MARGIN, True)
        ops.append(b"0.6 w %d %d m %d %d l S" % (MARGIN, round(y) - 4, PAGE_W - MARGIN, round(y) - 4))
        y -= 4
        for block in blocks:
            if isinstance(block, tuple):
                first = True
                for line in wrap(block[1], 10, usable - 14):
                    put(line, 10, MARGIN + 14)
                    if first:
                        ops.append(b"BT /F1 10 Tf %d %d Td (%s) Tj ET" % (MARGIN + 3, round(y), _escape("•")))
                        first = False
            else:
                for line in wrap(block, 10, usable):
                    put(line, 10, MARGIN)
                y -= 3
    pages.append(ops)

    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"]
    kids = []
    for page_ops in pages:
        stream = b"\n".join(page_ops)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(len(objects) + 1)
        objects.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> >>"
                       % (PAGE_W, PAGE_H, len(objects)))
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % kid for kid in kids), len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    start = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, start)
    return bytes(out)
