"""Known models per provider, ranked into tiers the supervisor routes work by.

Claude Code accepts family aliases (opus, sonnet, haiku) that always mean the newest model of that family,
so the catalog uses them. Codex publishes the models the signed-in account may use in its own model cache
(~/.codex/models_cache.json: names and descriptions only, no credentials); Cerebra reads that list so new
OpenAI models appear without an update, and falls back to a built-in list when the cache is missing.
"""
from __future__ import annotations

import json
from pathlib import Path

TIERS = ("frontier", "balanced", "fast")
TIER_LABEL = {"frontier": "Frontier: hardest problems", "balanced": "Balanced: everyday coding", "fast": "Fast: small, simple jobs"}

CLAUDE = [
    {"model": "opus", "label": "Claude Opus 5.5", "full_name": "claude-opus-5-5", "tier": "frontier",
     "strengths": "Deep reasoning, architecture, tricky bugs, security review."},
    {"model": "sonnet", "label": "Claude Sonnet 5.5", "full_name": "claude-sonnet-5-5", "tier": "balanced",
     "strengths": "Strong everyday coding, planning, writing and review at good speed."},
    {"model": "haiku", "label": "Claude Haiku 5.5", "full_name": "claude-haiku-5-5", "tier": "fast",
     "strengths": "Quick, low-cost answers and small edits."},
    {"model": "claude-fable-5-1", "label": "Claude Fable 5.1", "full_name": "claude-fable-5-1", "tier": "",
     "strengths": "Newer Claude model. Not used for automatic routing until you pick it yourself."},
]
CODEX_FALLBACK = [
    {"model": "", "label": "Codex default model", "tier": "balanced", "strengths": "Whatever Codex uses by default for your plan."},
]


def _tier(description):
    text = description.lower()
    if "frontier" in text or "most demanding" in text:
        return "frontier"
    if any(word in text for word in ("fast", "affordable", "efficient", "easier")):
        return "fast"
    return "balanced"


_CACHE: dict = {}


def codex_models(home=None):
    """Codex's model list, re-read only when its cache file changes (the dashboard asks every few seconds)."""
    cache = Path(home or Path.home()) / ".codex" / "models_cache.json"
    try:
        stamp = (str(cache), cache.stat().st_mtime_ns, cache.stat().st_size)
    except OSError:
        stamp = (str(cache), None, None)
    if _CACHE.get("stamp") == stamp:
        return [dict(item) for item in _CACHE["models"]]
    models = _read_codex(cache)
    _CACHE.update(stamp=stamp, models=models)
    return [dict(item) for item in models]


def _read_codex(cache):
    try:
        if cache.stat().st_size > 2_000_000:
            raise ValueError("cache too large")
        entries = json.loads(cache.read_text(encoding="utf-8")).get("models", [])
    except (OSError, ValueError, AttributeError):
        return [dict(item, provider="codex", source="built-in") for item in CODEX_FALLBACK]
    models = []
    for entry in sorted((e for e in entries if isinstance(e, dict)), key=lambda e: e.get("priority", 99)):
        slug, description = str(entry.get("slug", "")), str(entry.get("description", ""))
        if not slug or entry.get("visibility") != "list":
            continue
        older = any(word in description.lower() for word in ("older", "previous"))
        models.append({"provider": "codex", "model": slug, "label": str(entry.get("display_name") or slug)[:80],
                       "tier": "" if older else _tier(description), "strengths": description[:300], "source": "codex"})
    return models or [dict(item, provider="codex", source="built-in") for item in CODEX_FALLBACK]


def catalog(home=None):
    """All known models; `tier` is empty for models automatic routing does not pick on its own."""
    return {"claude": [dict(item, provider="claude", source="built-in") for item in CLAUDE], "codex": codex_models(home)}


def best(models, provider, tier):
    """The highest-ranked model of a tier for a provider, stepping to neighbouring tiers if absent."""
    order = {"frontier": ["frontier", "balanced", "fast"], "balanced": ["balanced", "frontier", "fast"], "fast": ["fast", "balanced", "frontier"]}[tier]
    for wanted in order:
        found = next((item for item in models.get(provider, []) if item["tier"] == wanted), None)
        if found:
            return found
    return {"provider": provider, "model": "", "label": f"{provider.title()} default model", "tier": tier}
