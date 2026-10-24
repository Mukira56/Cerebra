"""Model profiles: a named provider + model pair the user picks for planning, coding and review."""
from __future__ import annotations

import re

from .agents import valid_model
from .integrations import PROVIDERS
from .models import Metadata, now

PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
BUILT_IN = {
    "codex": {"id": "codex", "provider": "codex", "model": "", "label": "Codex (default model)", "built_in": True},
    "claude": {"id": "claude", "provider": "claude", "model": "", "label": "Claude Code (default model)", "built_in": True},
}
DEFAULT_ROLES = {"planner": "claude", "implementer": "codex", "reviewer": "claude"}


def _stored(session):
    row = session.get(Metadata, "model_profiles")
    return row, dict(row.value) if row else {"profiles": [], "overrides": {}, "roles": {}}


def list_profiles(session):
    _, value = _stored(session)
    profiles = []
    for identifier, base in BUILT_IN.items():
        override = value.get("overrides", {}).get(identifier, {})
        profiles.append({**base, **{key: override[key] for key in ("model", "label") if key in override}})
    profiles.extend({**profile, "built_in": False} for profile in value.get("profiles", []))
    for profile in profiles:
        provider = PROVIDERS.get(profile["provider"], {})
        profile["provider_label"] = provider.get("label", profile["provider"])
        profile["can_run_tasks"] = provider.get("execution", False)
    return profiles


def default_roles(session):
    _, value = _stored(session)
    roles = {**DEFAULT_ROLES, **value.get("roles", {})}
    known = {profile["id"] for profile in list_profiles(session)}
    return {role: identifier if identifier in known else DEFAULT_ROLES[role] for role, identifier in roles.items()}


def get_profile(session, identifier):
    profile = next((item for item in list_profiles(session) if item["id"] == identifier), None)
    if profile is None:
        raise ValueError(f"Unknown model profile: {identifier}")
    return profile


def _save(session, row, value):
    if row:
        row.value = value
    else:
        session.add(Metadata(key="model_profiles", value=value))


def add_profile(session, provider, model, label, identifier=None):
    if provider not in PROVIDERS:
        raise ValueError("Unknown provider")
    model = valid_model(model)
    label = (label or "").strip()[:80] or f"{PROVIDERS[provider]['label']} · {model or 'default model'}"
    identifier = identifier or re.sub(r"[^a-z0-9]+", "-", f"{provider}-{model or 'default'}".lower()).strip("-")[:48]
    if not PROFILE_ID.fullmatch(identifier) or identifier in BUILT_IN:
        raise ValueError("Choose a different profile name")
    row, value = _stored(session)
    profiles = list(value.get("profiles", []))
    if any(item["id"] == identifier for item in profiles):
        raise ValueError("A model profile with that name already exists")
    if len(profiles) >= 50:
        raise ValueError("At most 50 custom model profiles are supported")
    profile = {"id": identifier, "provider": provider, "model": model, "label": label, "created_at": now()}
    profiles.append(profile)
    _save(session, row, {**value, "profiles": profiles})
    return profile


def update_profile(session, identifier, model=None, label=None):
    row, value = _stored(session)
    changes = {}
    if model is not None:
        changes["model"] = valid_model(model)
    if label is not None:
        changes["label"] = label.strip()[:80] or identifier
    if identifier in BUILT_IN:
        overrides = dict(value.get("overrides", {}))
        overrides[identifier] = {**overrides.get(identifier, {}), **changes}
        value = {**value, "overrides": overrides}
    else:
        profiles = [dict(item) for item in value.get("profiles", [])]
        target = next((item for item in profiles if item["id"] == identifier), None)
        if target is None:
            raise ValueError("Unknown model profile")
        target.update(changes)
        value = {**value, "profiles": profiles}
    _save(session, row, value)
    return get_profile(session, identifier)


def delete_profile(session, identifier):
    if identifier in BUILT_IN:
        raise ValueError("Built-in profiles cannot be deleted; change their model instead")
    row, value = _stored(session)
    profiles = [item for item in value.get("profiles", []) if item["id"] != identifier]
    if len(profiles) == len(value.get("profiles", [])):
        raise ValueError("Unknown model profile")
    roles = {role: target for role, target in value.get("roles", {}).items() if target != identifier}
    _save(session, row, {**value, "profiles": profiles, "roles": roles})


def set_default_roles(session, roles):
    known = {profile["id"]: profile for profile in list_profiles(session)}
    for role, identifier in roles.items():
        if role not in DEFAULT_ROLES or identifier not in known:
            raise ValueError("Unknown role or model profile")
        if not known[identifier]["can_run_tasks"]:
            raise ValueError(f"{known[identifier]['provider_label']} cannot run tasks yet")
    row, value = _stored(session)
    _save(session, row, {**value, "roles": {**value.get("roles", {}), **roles}})
    return default_roles(session)
