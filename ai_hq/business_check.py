"""Deliverable checker for Business Studio jobs. Runs as the job's registered test command.

Standalone on purpose (standard library only, no Cerebra imports): the supervisor runs it inside the job's
working copy exactly like a project's own tests, so a "pass" means real files met real rules. It reads
cerebra-brief.json, which Cerebra wrote when the job was created and which the task may not change.

Exit code 0 = every check passed; 1 = at least one check failed (each problem is printed).
"""
from __future__ import annotations

from .words import counted
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
        self.tags, self.title, self.meta, self.stylesheets = set(), "", [], []
        self.links, self.images, self.forms = [], [], []
        self._in_title = self._in_form = False

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag)
        self._in_title = tag == "title"
        values = dict(attrs)
        if tag == "meta": self.meta.append(values)
        if tag == "link" and "stylesheet" in (values.get("rel") or "").split():
            self.stylesheets.append(values.get("href") or "")
        if tag == "a" and values.get("href") is not None: self.links.append(values.get("href") or "")
        if tag == "img": self.images.append(values)
        if tag == "form": self.forms.append({"attrs": values, "fields": [], "submit": False}); self._in_form = True
        if self._in_form and tag in {"input", "select", "textarea", "button"}:
            kind = (values.get("type") or ("submit" if tag == "button" else "text")).lower()
            if kind == "submit": self.forms[-1]["submit"] = True
            elif values.get("name"): self.forms[-1]["fields"].append({"name": values["name"].lower(), "type": kind, "required": "required" in values})

    def handle_endtag(self, tag):
        self._in_title = False
        if tag == "form": self._in_form = False

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
    if not any((meta.get("charset") or "").lower() == "utf-8" for meta in parser.meta):
        problems.append(f"{path.name}: needs <meta charset='utf-8'>")
    if not any((meta.get("name") or "").lower() == "viewport" and
               "width=device-width" in (meta.get("content") or "").replace(" ", "").lower() for meta in parser.meta):
        problems.append(f"{path.name}: needs a viewport with width=device-width for mobile screens")
    if not parser.stylesheets:
        problems.append(f"{path.name}: needs a linked local stylesheet")
    for href in parser.stylesheets:
        linked = (path.parent / href.split("?")[0].split("#")[0]).resolve()
        if not href or ":" in href or href.startswith(("/", "\\")) or path.parent.resolve() not in linked.parents:
            problems.append(f"{path.name}: stylesheet must be inside the website folder")
        elif not linked.is_file() or not linked.stat().st_size:
            problems.append(f"{path.name}: linked stylesheet {href} is missing or empty")


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


FIELD_GROUPS = {"name": ("name",), "phone or email": ("phone", "tel", "email"), "service": ("service",), "address or ZIP code": ("zip", "postal", "address", "area")}


def check_site(root, brief, problems):
    """A small business website: pages link to each other, images are described, the quote form really posts."""
    pages = [name for name in brief.get("required_files", []) if name.lower().endswith((".html", ".htm")) and (root / name).is_file()]
    site = brief.get("site", {})
    for name in pages:
        path = root / name
        parser = _Html(); parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        for href in parser.links:
            target = href.split("#")[0].split("?")[0].strip()
            if not target or href.startswith(("#", "tel:", "mailto:")):
                continue
            if target.startswith("http://"):
                problems.append(f"{name}: link {href} is not secure (use https://)")
            elif target.startswith("https://"):
                continue
            elif ":" in target or target.startswith(("/", "\\")):
                problems.append(f"{name}: link {href} must be a page inside the website")
            elif not (path.parent / target).resolve().is_file() or root not in (path.parent / target).resolve().parents:
                problems.append(f"{name}: broken link to {href}")
        for image in parser.images:
            if "alt" not in image:
                problems.append(f"{name}: an image ({image.get('src', '?')}) has no alt text for screen readers")
        quote = site.get("quote_page", "quote.html")
        if name != quote and pages and quote in pages and not any(link.split("#")[0] == quote for link in parser.links):
            problems.append(f"{name}: has no link to the quote request page ({quote})")
        if name == quote:
            forms = [form for form in parser.forms if (form["attrs"].get("method") or "get").lower() == "post"]
            if not forms:
                problems.append(f"{name}: needs a quote form that sends with method=\"post\"")
                continue
            form = forms[0]
            action = (form["attrs"].get("action") or "").strip()
            endpoint = (site.get("form_endpoint") or "").strip()
            if endpoint and action != endpoint:
                problems.append(f"{name}: the form must send to the agreed address {endpoint} (it sends to {action or 'nowhere'})")
            elif not action.startswith("https://") or re.search(r"your[-_ ]?form|example\.|placeholder", action, re.I):
                problems.append(f"{name}: the form has no real https:// delivery address, so enquiries would be lost")
            names = [field["name"] for field in form["fields"]]
            for label, keys in FIELD_GROUPS.items():
                if not any(any(key in field for key in keys) for field in names):
                    problems.append(f"{name}: the quote form needs a {label} field")
            if not any(field["required"] and any(key in field["name"] for key in ("phone", "tel", "email")) for field in form["fields"]):
                problems.append(f"{name}: a phone or email field must be required, so you can reply")
            if not form["submit"]:
                problems.append(f"{name}: the quote form needs a submit button")
    text = " ".join((root / name).read_text(encoding="utf-8", errors="replace").lower() for name in pages)
    if site.get("phone") and re.sub(r"\D", "", site["phone"]) not in re.sub(r"\D", "", text):
        problems.append(f"The website never shows the business phone number {site['phone']}")


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
    if brief.get("site"):
        check_site(root, brief, problems)
    for line in problems:
        print("FAIL", line)
    print(f"{counted(len(checked), 'file', 'files')} checked, {counted(len(problems), 'problem', 'problems')}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
