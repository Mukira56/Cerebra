"""How well an Etsy listing's title and tags are built for search, worked out here with no call to Etsy.

This grades structure, not sales. Etsy's Seller Handbook asks for all 13 tags and for phrases rather than single words; the
other points are common seller practice, so they are advice ("improve") and block nothing. A tag that repeats a title phrase
is fine on Etsy, unlike a KDP keyword box, so it isn't flagged. The main keyword is the one the owner researched for this niche.
"""
from __future__ import annotations

from .words import counted
import re
from collections import Counter

from .kdpaudit import FILLER, grade, words

OPENING = 50  # about the first seven words: the part of a title shoppers see and that carries the most weight
STUFFED = 3


def audit(listing, keyword=""):
    """{score, label, reach, summary, fix: [...], improve: [...]} for a listing, with its niche's keyword when it has one."""
    from .etsy import check_listing
    title, tags = str(listing.get("title") or ""), [str(tag) for tag in listing.get("tags") or []]
    fix, improve = check_listing(listing), []
    main = words(keyword)
    if main and not main <= words(title):
        improve.append(f"Your main keyword “{keyword}” isn't in the title: it's what buyers search for")
    elif main and not main <= words(title[:OPENING]):
        improve.append(f"Move “{keyword}” to the start of the title: the opening words matter most")
    counts = Counter(word for word in re.findall(r"[a-z0-9']+", title.lower()) if word not in FILLER)
    improve.extend(f"The title says “{word}” {count} times: say it once and use the space for something new" for word, count in counts.items() if count >= STUFFED)
    seen, covered = [], set()
    for number, tag in enumerate(tags, 1):
        terms = words(tag)
        earlier = next((place for place, other in enumerate(seen, 1) if terms and terms <= other), None)
        if len(tag.split()) == 1:
            improve.append(f"Tag {number} (“{tag}”) is a single word: phrases match more searches")
        elif earlier:
            improve.append(f"Tag {number} (“{tag}”) adds nothing to tag {earlier}: use different words")
        seen.append(terms)
        covered |= terms
    score, label = grade(fix, improve)
    return {"score": score, "label": label, "reach": len(covered), "summary": f"Your tags cover {counted(len(covered), 'different search word', 'different search words')}.", "fix": fix, "improve": improve}
