"""The model hub: each kind of work routed to a model, using only what costs the owner nothing extra: their own Claude and
Codex accounts, and free models (docs/MODELS_AND_HIVE.md). Every call is on the record.

The owner (2026-10-30): "Use the free models do not use a route that I will be required to pay for premium services unless it
is for Claude or Codex." So the hub refuses any OpenRouter model with a price, and never uses paid extras such as web search.
Free OpenRouter models are rate limited (about 20 a minute and 50 a day on an account that never bought credits) and come and
go, so each call names fallbacks from the live free list.

OpenRouter (openrouter.ai) serves Claude, GPT, Gemini, Grok, DeepSeek, Qwen, Llama, Mistral and more behind one
OpenAI-compatible API, and publishes its live model list with prices. Cerebra uses it for writing and research turns
(proposals, emails, plans, verification); building code stays with the owner's Codex and Claude Code accounts.
When no key is saved, every writer falls back to those accounts, as before.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from . import vault
from .agents import AgentResult
from .models import Metadata, ModelUsage
from .network import LazyClient
from .security import redact

API = "https://openrouter.ai/api/v1"
KEY = "model_hub"
CATALOG_TTL = 6 * 3600
# A route is "account:claude" or "account:codex" (the owner's own subscriptions, as before) or a free OpenRouter model.
ACCOUNTS = {"account:claude": "Your Claude account", "account:codex": "Your Codex account"}
# Kinds of work, with the default for each: the owner's Claude account where quality matters most (it's already paid for),
# free models for volume and for checking. Checkers come from other companies than the writer, so they don't share its blind spots.
CATEGORIES = {
    "writing": ("Writing in your name", "Proposals, emails to businesses, profiles, posts", "account:claude"),
    "judgment": ("Plans and judgment", "The Chief of Staff's plans, funding answers, final research reports", "account:claude"),
    "bulk": ("High-volume work", "Sorting, summarising, extracting, first drafts", "nvidia/nemotron-3-ultra-550b-a55b:free"),
    "research": ("Research", "The hive's researchers, reading pages Cerebra fetched", "thinkingmachines/inkling:free"),
    "coding": ("Code questions", "Explaining and reviewing code outside a task", "poolside/laguna-s-2.1:free"),
    "verify": ("Checking", "Cross-checking claims against their sources", "google/gemma-4-31b-it:free"),
    "verify_second": ("Second check", "Another company's model, for disputed claims", "nvidia/nemotron-3.5-super-vl:free"),
}
FALLBACK = "openrouter/free"  # OpenRouter's own free router: picks any free model that is up
OLLAMA = "http://127.0.0.1:11434"  # local models on the owner's own computer: free, no daily limit; only this loopback address
LOCAL_TTL = 30  # seconds the list of local models is remembered
LOCAL = "local:"  # a route to one of those local models, e.g. "local:qwen3:14b"
DEFAULTS = {"api_key": "", "routes": {}, "enabled": True}


def settings(session):
    row = session.get(Metadata, KEY)
    value = {**DEFAULTS, **(row.value if row else {})}
    value["routes"] = {**{key: model for key, (_, _, model) in CATEGORIES.items()}, **(value.get("routes") or {})}
    return value


def public(value, spent=0.0):
    return {"connected": bool(value["api_key"]), "enabled": value["enabled"], "spent_this_month": round(spent, 4), "free_only": True,
            "routes": value["routes"], "accounts": ACCOUNTS, "categories": [{"key": key, "label": label, "about": about, "default": model}
                                                                            for key, (label, about, model) in CATEGORIES.items()]}


def save_settings(session, fields):
    value = settings(session)
    if "api_key" in fields:
        key = str(fields["api_key"] or "").strip()
        if key and not key.startswith("sk-or-"):
            raise ValueError("An OpenRouter key starts with sk-or-: copy it from openrouter.ai › Keys")
        value["api_key"] = vault.protect(key) if key else ""
    if "enabled" in fields:
        value["enabled"] = bool(fields["enabled"])
    if "routes" in fields:
        for category, model in (fields["routes"] or {}).items():
            model = str(model or "").strip()
            if category not in CATEGORIES or not model:
                continue
            local = model.startswith(LOCAL) and 1 < len(model) - len(LOCAL) <= 100 and " " not in model
            if model not in ACCOUNTS and not local and not (model.endswith(":free") or model == FALLBACK):
                raise ValueError(f"{model} isn't free: choose a free model (its name ends in :free), a model on this computer, or your Claude or Codex account")
            value["routes"][category] = model
    stored = {**value, "routes": {key: model for key, model in value["routes"].items() if model != CATEGORIES[key][2]}}
    row = session.get(Metadata, KEY)
    if row is None:
        session.add(Metadata(key=KEY, value=stored))
    else:
        row.value = stored
    return value


def month_start(now=None):
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def spent_this_month(session, now=None):
    return float(session.scalar(select(func.coalesce(func.sum(ModelUsage.cost), 0.0)).where(ModelUsage.at >= month_start(now))) or 0.0)


def usage_summary(session, now=None):
    rows = session.execute(select(ModelUsage.category, ModelUsage.model, func.count(), func.sum(ModelUsage.cost))
                           .where(ModelUsage.at >= month_start(now)).group_by(ModelUsage.category, ModelUsage.model)).all()
    return [{"category": category, "model": model, "calls": calls, "cost": round(float(cost or 0), 4)} for category, model, calls, cost in rows]


class Hub:
    def __init__(self, db, client=None):
        self.db = db
        self.client = client or LazyClient(timeout=180, headers={"X-Title": "Cerebra"})
        self._catalog, self._catalog_at, self._lock = [], 0.0, threading.Lock()

    def ready(self):
        with self.db.Session() as session:
            value = settings(session)
            return bool(value["api_key"] and value["enabled"])

    def catalog(self, force=False):
        """OpenRouter's live model list with prices per million tokens (public: no key needed)."""
        with self._lock:
            if self._catalog and not force and time.monotonic() - self._catalog_at < CATALOG_TTL:
                return self._catalog
        response = self.client.get(f"{API}/models")
        response.raise_for_status()
        models = []
        for item in response.json().get("data", []):
            pricing = item.get("pricing") or {}
            try:
                prompt, completion = float(pricing.get("prompt") or 0) * 1e6, float(pricing.get("completion") or 0) * 1e6
            except (TypeError, ValueError):
                continue
            if item.get("id", "").startswith("~") or prompt < 0 or completion < 0:
                continue  # aliases that move under you; negative prices mean "varies"
            models.append({"id": item["id"], "name": item.get("name", item["id"]), "input": round(prompt, 4), "output": round(completion, 4),
                           "context": item.get("context_length") or 0})
        with self._lock:
            self._catalog, self._catalog_at = models, time.monotonic()
        return models

    def price(self, model_id):
        found = next((item for item in (self._catalog or []) if item["id"] == model_id), None)
        return (found["input"], found["output"]) if found else (None, None)

    def catalog_soon(self, wait=1.5):
        """The model list for a page: waits at most `wait` seconds, fetching in the background, so a slow connection never
        blocks the Models page (the first fetch took about 8 s on the owner's connection). None while it's still coming;
        raises httpx.HTTPError when OpenRouter couldn't be reached."""
        with self._lock:
            if self._catalog and time.monotonic() - self._catalog_at < CATALOG_TTL:
                return self._catalog
            fetching = getattr(self, "_fetching", None)
            if fetching is None or not fetching.is_alive():
                outcome = {}

                def fetch():
                    try:
                        outcome["models"] = self.catalog()
                    except httpx.HTTPError as exc:
                        outcome["error"] = exc
                fetching = threading.Thread(target=fetch, name="cerebra-model-list", daemon=True)
                self._fetching, self._outcome = fetching, outcome
                fetching.start()
            outcome = self._outcome
        fetching.join(wait)
        if fetching.is_alive():
            return None
        if "error" in outcome:
            raise outcome["error"]
        return outcome.get("models") or self._catalog

    def free_models(self):
        """Ids of the models that cost nothing right now (from the live list)."""
        try:
            return {item["id"] for item in self.catalog() if item["input"] == 0 and item["output"] == 0}
        except httpx.HTTPError:
            return set()

    def local_models(self):
        """Models pulled into Ollama on this computer (empty when Ollama isn't running). Never starts Ollama or downloads anything.
        Remembered for half a minute, and a closed port is given up on quickly: Windows takes about 2 s to refuse a connection
        to a port nobody listens on, which made the Models page slow whenever Ollama wasn't running."""
        cached = getattr(self, "_local", None)
        if cached is not None and time.monotonic() - cached[0] < LOCAL_TTL:
            return list(cached[1])
        try:
            response = self.client.get(f"{OLLAMA}/api/tags", timeout=httpx.Timeout(3, connect=0.5))
            response.raise_for_status()
            names = sorted(item.get("name", "") for item in response.json().get("models", []) if item.get("name"))
        except (httpx.HTTPError, ValueError):
            names = []
        self._local = (time.monotonic(), names)
        return list(names)

    def chat_local(self, category, model, prompt, max_tokens=4000):
        """One turn with a model on this computer, through Ollama (free; as fast as the computer allows)."""
        name = model[len(LOCAL):]
        started = time.monotonic()
        try:
            response = self.client.post(f"{OLLAMA}/api/chat", timeout=900, json={"model": name, "messages": [{"role": "user", "content": prompt}],
                                                                                "stream": False, "options": {"num_predict": max_tokens, "num_ctx": 16384}})
        except httpx.HTTPError:
            return AgentResult(False, "", error="Ollama isn't running on this computer. Open Ollama, or choose another model on the Models page.")
        if response.status_code >= 400:
            self._record(category, model, {}, 0.0, False, time.monotonic() - started)
            missing = response.status_code == 404
            return AgentResult(False, "", error=(f"{name} isn't on this computer yet: in a terminal run  ollama pull {name}" if missing
                                                 else f"Ollama refused ({response.status_code})"))
        data = response.json()
        text = ((data.get("message") or {}).get("content") or "")
        if "<think>" in text:  # reasoning models (DeepSeek-R1, Qwen3) think aloud first: keep only the answer
            text = text.split("</think>")[-1]
        self._record(category, model, {"prompt_tokens": data.get("prompt_eval_count") or 0, "completion_tokens": data.get("eval_count") or 0},
                     0.0, bool(text.strip()), time.monotonic() - started)
        if not text.strip():
            return AgentResult(False, "", error=f"{name} returned no answer")
        return AgentResult(True, text.strip())

    def route(self, category):
        with self.db.Session() as session:
            return settings(session)["routes"].get(category) or CATEGORIES[category][2]

    def chat(self, category, prompt, max_tokens=4000, model=None):
        """One turn with a free model. Anything with a price is refused: the owner pays only for Claude and Codex."""
        with self.db.Session() as session:
            value = settings(session)
            model = model or value["routes"].get(category) or CATEGORIES.get(category, ("", "", FALLBACK))[2]
            key = vault.unprotect(value["api_key"]) if value["api_key"] else ""
        if model.startswith(LOCAL):
            return self.chat_local(category, model, prompt, max_tokens)
        if not key:
            return AgentResult(False, "", error="Add your free OpenRouter key on the Models page to use free models")
        free = self.free_models()
        if model != FALLBACK and model not in free:
            return AgentResult(False, "", error=f"{model} isn't free right now, so Cerebra won't use it. Choose another free model on the Models page.")
        # Free models are rate limited and come and go: name a few others as fallbacks, ending with OpenRouter's free router.
        backups = [item for item in sorted(free) if item != model and item != FALLBACK][:2] + [FALLBACK]
        body = {"model": model, "models": [model, *backups][:3], "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens,
                "usage": {"include": True}}
        started = time.monotonic()
        try:
            response = self.client.post(f"{API}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})
        except httpx.HTTPError as exc:
            return AgentResult(False, "", error="Couldn't reach OpenRouter: " + redact(str(exc).replace(key, "[key]"))[:200])
        if response.status_code >= 400:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except ValueError:
                detail = response.text[:200]
            self._record(category, model, {}, 0.0, False, time.monotonic() - started)
            hint = " Free models allow about 50 requests a day; try again tomorrow." if response.status_code == 429 else ""
            return AgentResult(False, "", error=f"OpenRouter refused ({response.status_code}): {redact(str(detail).replace(key, '[key]'))[:300]}{hint}")
        data = response.json()
        used = data.get("model") or model
        text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        usage = data.get("usage") or {}
        self._record(category, used, usage, float(usage.get("cost") or 0), bool(text), time.monotonic() - started)
        if not text.strip():
            return AgentResult(False, "", error=f"{used} returned no answer")
        return AgentResult(True, text)

    def _record(self, category, model, usage, cost, ok, seconds):
        with self.db.Session.begin() as session:
            session.add(ModelUsage(category=category, model=model, prompt_tokens=int(usage.get("prompt_tokens") or 0),
                                   completion_tokens=int(usage.get("completion_tokens") or 0), cost=round(cost, 6), ok=ok, seconds=round(seconds, 2)))


def chat_for(hub, category, registry_source, selected, prompt, workdir):
    """What every writer calls. The route for this kind of work decides: the owner's Claude or Codex account, or a free
    model through the hub. Without the hub (no key), it is the owner's chosen account, as before."""
    route = hub.route(category) if hub is not None and category in CATEGORIES else ""
    if route in ACCOUNTS:
        provider = route.split(":", 1)[1]
        model = selected.get("model", "") if selected.get("provider") == provider else ""
        return registry_source().chat(provider, prompt, str(workdir), model)
    if route.startswith(LOCAL) or (route and hub.ready()):
        return hub.chat(category, prompt)
    return registry_source().chat(selected["provider"], prompt, str(workdir), selected.get("model", ""))
