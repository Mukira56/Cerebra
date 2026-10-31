"""KDP low-content interiors: ruled, dot-grid, graph and bordered pages drawn by code, with no fonts and no AI."""
import re

import pytest

from ai_hq import interiors
from test_freelance import client  # noqa: F401  (client is a fixture)


def streams(data):
    return re.findall(rb"stream\n(.*?)\nendstream", data, re.S)


def test_a_notebook_is_the_trim_size_with_the_gutter_on_the_binding_side_and_no_fonts():
    data, info = interiors.build("college", "6x9", 121)
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    assert info["pages"] == 122 and b"/Count 122" in data and data.count(b"/Type /Page ") == 122  # an even page count
    assert b"/MediaBox [0 0 432 648]" in data and b"/TrimBox [0 0 432 648]" in data  # 6 x 9 inches, no bleed
    assert b"/Font" not in data and b" Tj" not in data  # nothing KDP could find unembedded
    right_hand, left_hand = streams(data)
    first_x = lambda stream: float(re.search(rb"(\d+(?:\.\d+)?) [\d.]+ m", stream).group(1))
    assert first_x(right_hand) == pytest.approx(0.375 * 72) and first_x(left_hand) == pytest.approx(0.5 * 72)  # wide margin on the binding side
    assert interiors.build("college", "6x9", 400)[1]["gutter"] == 0.625  # thicker books get a wider gutter (KDP's table)
    xref = int(data.rsplit(b"startxref\n", 1)[1].split()[0])
    assert data[xref:xref + 4] == b"xref"  # a reader can find every object


def test_every_style_draws_and_kdp_limits_are_kept():
    for style in interiors.STYLES:
        data, info = interiors.build(style, "8.5x11", 24)
        assert info["pages"] == 24 and len(streams(data)[0]) > 20
    with pytest.raises(ValueError, match="24 to"):
        interiors.build("college", "6x9", 10)
    with pytest.raises(ValueError, match="590"):
        interiors.build("college", "8.5x11", 600)  # letter size has a lower maximum
    with pytest.raises(ValueError, match="trim size"):
        interiors.build("college", "4x6", 100)
    with pytest.raises(ValueError, match="Choose one of"):
        interiors.build("hexagons", "6x9", 100)


def test_the_books_page_makes_the_file_in_cerebras_folder_and_opens_it(client):  # noqa: F811
    state = client.get("/api/books/interiors").json()
    assert "college" in state["styles"] and "6x9" in state["trims"] and state["files"] == []
    made = client.post("/api/books/interiors", json={"style": "dot", "trim": "6x9", "pages": 120}).json()
    assert made["file"] == "dot-6x9-120p-white.pdf" and any("AI-generated content: No" in line for line in made["kdp"])
    path = client.app.state.settings.data_dir / "books" / "interiors" / made["file"]
    assert path.read_bytes().startswith(b"%PDF") and client.get("/api/books/interiors").json()["files"][0]["file"] == made["file"]
    assert client.post("/api/books/interiors", json={"style": "dot", "trim": "6x9", "pages": 5}).status_code == 400
    client.post("/api/books/interiors/open", json={})
    assert client.app.state.opened[-1].endswith("interiors")
