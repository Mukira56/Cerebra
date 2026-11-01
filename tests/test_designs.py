"""Text designs for print-on-demand: a transparent 4500 x 5400 PNG at 300 DPI, drawn by code, with trademarks refused."""
import struct
import zlib

from ai_hq import designs
from test_freelance import client  # noqa: F401  (client is a fixture)


def chunks(data):
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    position, found = 8, {}
    while position < len(data):
        size = struct.unpack(">I", data[position:position + 4])[0]
        kind, body = data[position + 4:position + 8], data[position + 8:position + 8 + size]
        assert struct.unpack(">I", data[position + 8 + size:position + 12 + size])[0] == zlib.crc32(kind + body) & 0xFFFFFFFF  # every chunk intact
        found[kind] = found.get(kind, b"") + body
        position += 12 + size
    return found


def test_a_phrase_becomes_a_merch_sized_transparent_png():
    found = chunks(designs.render("Dog Mom", "pink"))
    width, height, depth, colour_type = struct.unpack(">IIBB", found[b"IHDR"][:10])
    assert (width, height, depth, colour_type) == (4500, 5400, 8, 6)  # RGBA
    per_metre = struct.unpack(">II", found[b"pHYs"][:8])
    assert per_metre == (11811, 11811)  # 300 DPI
    raw = zlib.decompress(found[b"IDAT"])
    stride = 1 + width * 4
    assert len(raw) == height * stride
    alphas = [raw[row * stride + 4:(row + 1) * stride:4] for row in (0, height // 2, height - 1)]
    assert set(alphas[0]) == {0} and set(alphas[2]) == {0}  # transparent around the print
    inked = sum(1 for row in range(0, height, 25) if any(raw[row * stride + 4:(row + 1) * stride:4]))
    assert inked > 10  # the phrase is drawn
    assert raw[height // 2 * stride + 1:height // 2 * stride + 4] == bytes(designs.COLOURS["pink"])


def test_trademarks_and_bad_input_are_refused(client):  # noqa: F811
    assert "disney" in designs.check("Disney Mom")[0]
    assert designs.check("x") and designs.check("Tea ☃ time")  # too short; a character the alphabet can't draw
    made = client.post("/api/designs", json={"text": "Powered by coffee", "colour": "navy"}).json()
    assert made["file"] == "powered-by-coffee-navy.png" and made["width"] == 4500
    assert client.get("/api/designs").json()["files"][0]["file"] == made["file"]
    assert client.post("/api/designs", json={"text": "Starbucks lover"}).status_code == 400
    assert client.post("/api/designs", json={"text": "Coffee", "colour": "plaid"}).status_code == 400
