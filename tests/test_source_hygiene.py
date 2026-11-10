"""No invisible control characters in Cerebra's own source: one (a backspace where a regex meant \b) once kept Company
pitches from recognising translator and join-us pages."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_no_control_characters_in_source():
    files = [*ROOT.joinpath("ai_hq").rglob("*.py"), *ROOT.joinpath("ai_hq", "static").glob("*.js"), *ROOT.joinpath("ai_hq", "static").glob("*.css"),
             *ROOT.joinpath("ai_hq", "static").glob("*.html"), *ROOT.joinpath("scripts").glob("*.py"), *ROOT.joinpath("scripts").glob("*.cjs")]
    found = [f"{path.relative_to(ROOT)}:{number}" for path in files
             for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").split("\n"), 1)
             if any(ord(char) < 32 and char not in "\t\r" for char in line)]
    assert found == [], found
