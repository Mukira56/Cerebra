"""Deliverable checker for Business Studio jobs. Runs as the job's registered test command.

Standalone on purpose (standard library only, no Cerebra imports): the supervisor runs it inside the job's
working copy exactly like a project's own tests, so a "pass" means real files met real rules. It reads
cerebra-brief.json, which Cerebra wrote when the job was created and which the task may not change.

Exit code 0 = every check passed; 1 = at least one check failed (each problem is printed).
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ElementTree
from html.parser import HTMLParser
from pathlib import Path

LIMIT = 5 * 1024 * 1024
UNSAFE_SVG = re.compile(r"<\s*script|\bon[a-z]+\s*=|javascript:|<\s*foreignObject|xlink:href\s*=\s*[\"'](?!#)|href\s*=\s*[\"'](?:https?:|//)", re.I)


class _Html(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.title = set(), ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        self._in_title = tag == "title"

    def handle_endtag(self, tag):
        self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()


def check_svg(path, problems):
    text = path.read_text(encoding="utf-8", errors="replace")
    if UNSAFE_SVG.search(text):
        problems.append(f"{path.name}: contains scripts, event handlers or external links; a design file must be self-contained")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        problems.append(f"{path.name}: not valid SVG/XML ({exc})")
        return
    if not root.tag.endswith("svg"):
        problems.append(f"{path.name}: the root element is not <svg>")
    if not (root.get("viewBox") or (root.get("width") and root.get("height"))):
        problems.append(f"{path.name}: needs a viewBox (or width and height) so it scales correctly")
    if len(list(root.iter())) < 3:
        problems.append(f"{path.name}: looks empty (fewer than two drawn elements)")


def check_html(path, problems):
    parser = _Html()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    for tag in ("html", "head", "body"):
        if tag not in parser.tags:
            problems.append(f"{path.name}: missing <{tag}>")
    if not parser.title:
        problems.append(f"{path.name}: missing a <title>")
    if "meta" not in parser.tags:
        problems.append(f"{path.name}: missing <meta> tags (charset/viewport)")


def check_listing(path, problems, rules):
    text = path.read_text(encoding="utf-8", errors="replace")
    sections = {match.group(1).strip().lower(): match.group(2).strip() for match in re.finditer(r"^##\s*(.+?)\s*$\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)}
    for name in ("title", "description", "tags"):
        if not sections.get(name):
            problems.append(f"{path.name}: needs a '## {name.title()}' section with content")
    title = sections.get("title", "")
    if title and len(title.splitlines()[0]) > rules.get("title_max", 140):
        problems.append(f"{path.name}: title is longer than {rules.get('title_max', 140)} characters")
    tags = [tag.strip() for tag in re.split(r"[,\n]", sections.get("tags", "")) if tag.strip().strip("-* ")]
    if tags and len(tags) > rules.get("tags_max", 13):
        problems.append(f"{path.name}: {len(tags)} tags; at most {rules.get('tags_max', 13)} allowed")
    if any(len(tag.strip("-* ")) > rules.get("tag_length_max", 20) for tag in tags):
        problems.append(f"{path.name}: a tag is longer than {rules.get('tag_length_max', 20)} characters")


def main(root="."):
    root = Path(root).resolve()
    problems, checked = [], []
    try:
        brief = json.loads((root / "cerebra-brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL cerebra-brief.json is missing or unreadable: {exc}")
        return 1
    for name in brief.get("required_files", []):
        path = (root / name).resolve()
        if root not in path.parents:
            problems.append(f"{name}: outside the job folder")
            continue
        if not path.is_file():
            problems.append(f"{name}: required file is missing")
            continue
        size = path.stat().st_size
        if size == 0:
            problems.append(f"{name}: is empty")
            continue
        if size > LIMIT:
            problems.append(f"{name}: larger than 5 MB")
            continue
        suffix = path.suffix.lower()
        if suffix == ".svg":
            check_svg(path, problems)
        elif suffix in {".html", ".htm"}:
            check_html(path, problems)
        elif name.lower().startswith("listing") and suffix == ".md":
            check_listing(path, problems, brief.get("rules", {}))
        checked.append(name)
    text = " ".join((root / name).read_text(encoding="utf-8", errors="replace").lower() for name in checked if (root / name).suffix.lower() in {".md", ".html", ".htm", ".txt"})
    for phrase in brief.get("must_mention", []):
        if phrase.lower() not in text:
            problems.append(f"The deliverables never mention “{phrase}”, which the brief requires")
    for line in problems:
        print("FAIL", line)
    print(f"{len(checked)} file(s) checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
