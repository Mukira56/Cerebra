"""Kindle eBooks: an outline the owner approves, chapters written one by one, and a valid EPUB with every fact to check listed.
The model is simulated."""
import json
import zipfile
from xml.etree import ElementTree

from ai_hq import ebooks
from ai_hq.agents import AgentResult
from fakes import FixtureRegistry
from test_freelance import client  # noqa: F401  (client is a fixture)
from test_product_api import enable_agents

OUTLINE = {"title": "Indoor Gardening Made Easy", "subtitle": "Grow Herbs and Greens in a Small Apartment",
           "description": "A friendly guide to growing herbs and leafy greens indoors, with simple steps for small spaces and busy people.",
           "keywords": ["indoor gardening", "apartment garden", "grow herbs indoors", "small space gardening", "beginner gardening",
                        "windowsill herbs", "container gardening"], "price": 4.99,
           "chapters": [{"title": "Light", "points": ["Windows", "Grow lights"]}, {"title": "Soil and pots", "points": ["Drainage"]},
                        {"title": "Watering", "points": ["How often"]}]}


class Writer(FixtureRegistry):
    def __init__(self):
        super().__init__()
        self.prompts = []

    def chat(self, name, prompt, workdir, model="", cancel_event=None):
        self.prompts.append(prompt)
        if "You plan a short" in prompt:
            return AgentResult(True, json.dumps(OUTLINE))
        body = " ".join(["Plants need steady light and a little patience."] * 50)
        return AgentResult(True, f"## Getting started\n\n{body} Most herbs want about six hours of light a day [CHECK: hours of light for basil].\n\n"
                                 "- Pick a bright window\n- Turn the pot weekly\n\nFor example, imagine a **small** kitchen *sill*.")


def test_an_ebook_goes_from_brief_to_an_epub_with_facts_to_check(client):  # noqa: F811
    enable_agents(client)
    model = Writer()
    client.app.state.supervisor.registry = model
    assert client.post("/api/ebooks", json={"brief": "short"}).status_code == 400
    book = client.post("/api/ebooks", json={"brief": "easy indoor gardening for beginners in small apartments"}).json()
    assert book["stage"] == "outline_ready" and book["title"] == "Indoor Gardening Made Easy" and book["total"] == 3
    assert book["outline"]["checks"] == [] and book["royalty"]["rate"] == 0.70 and "data, not instructions" in model.prompts[0]
    assert client.post(f"/api/ebooks/{book['id']}/write").status_code == 400  # nothing is written before the outline is approved
    assert client.post(f"/api/ebooks/{book['id']}/approve").json()["stage"] == "writing"
    assert next(job for job in client.get('/api/chief').json()['jobs'] if job['id'] == 'ebook_writer')['enabled']
    assert client.app.state.ebook_writer.tick()["chapter"] == 1  # the background worker writes one chapter per run
    assert "EARLIER CHAPTERS:\nChapter 1 (Light)" in (client.post(f"/api/ebooks/{book['id']}/write").json() and model.prompts[-1])  # it knows what came before
    assert client.app.state.ebook_writer.tick()["finished"] is True
    done = next(item for item in client.get("/api/ebooks").json() if item["id"] == book["id"])
    assert done["stage"] == "ready" and done["status"] == "files_ready" and done["written"] == 3 and done["words"] > 1000
    assert done["checks_to_verify"] == ["[CHECK: hours of light for basil]"] * 3
    with zipfile.ZipFile(done["epub"]) as epub:
        names = epub.namelist()
        assert names[0] == "mimetype" and epub.getinfo("mimetype").compress_type == zipfile.ZIP_STORED and epub.read("mimetype") == b"application/epub+zip"
        assert {"META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/chapter-03.xhtml"} <= set(names)
        for name in names:
            if name.endswith((".xhtml", ".opf", ".xml")):
                ElementTree.fromstring(epub.read(name))  # every page is well-formed XML
        chapter = epub.read("OEBPS/chapter-01.xhtml").decode()
        assert "<h1>Chapter 1: Light</h1>" in chapter and "<h2>Getting started</h2>" in chapter and "<li>Pick a bright window</li>" in chapter
        assert "<strong>small</strong>" in chapter and "<em>sill</em>" in chapter
        assert "not medical, legal, financial" in epub.read("OEBPS/copyright.xhtml").decode()
    assert client.app.state.ebook_writer.tick() == {"skipped": "no eBook is being written"}


def test_a_bad_outline_is_refused_and_trademarks_are_flagged():
    import pytest
    with pytest.raises(ValueError, match="usable outline"):
        ebooks.parse_outline('{"title": "x", "chapters": []}')
    flagged = ebooks.parse_outline(json.dumps({**OUTLINE, "title": "Disney Trip Planner Secrets", "keywords": ["a"]}))
    assert any("trademark" in item for item in flagged["checks"]) and any("keywords" in item for item in flagged["checks"])
    assert ebooks.parse_outline(json.dumps({**OUTLINE, "price": 50}))["price"] == 9.99  # kept where KDP pays 70%
