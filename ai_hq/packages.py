"""Install a JavaScript project's packages before its tests run (or before it is viewed).

A task works in a fresh Git working copy, and installed packages (`node_modules`) are never in Git, so `npm test`
would fail with "'vitest' is not recognized" before testing anything. Cerebra installs them itself, as the
project's lockfile says, with the same package tool the test command uses (including `node …/pnpm.mjs`):
npm ci / pnpm install --frozen-lockfile / yarn install --frozen-lockfile. If the lockfile doesn't match
package.json (the coder added a package), it installs without reading or writing the lockfile, so the working
copy stays clean. It runs again only when package.json or the lockfile change.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

LOCKS = {"pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock", "npm": "package-lock.json"}
SCRIPT = re.compile(r"(pnpm|yarn|npm-cli)\.(?:m?js|cjs)$", re.I)
INSTALL_SECONDS = 20 * 60


def plan(workdir, commands=()):
    """{"prefix", "manager", "steps": [first, fallback], "fingerprint"} for a JavaScript project, else None."""
    root = Path(workdir)
    package = root / "package.json"
    if not package.is_file():
        return None
    manager = next((name for name, lock in LOCKS.items() if (root / lock).is_file()), "npm")
    prefix = [manager]
    for command in commands or ():
        if not command:
            continue
        stem = Path(str(command[0])).stem.lower()
        if stem in LOCKS:
            prefix, manager = [command[0]], stem
            break
        if stem == "node" and len(command) > 1 and SCRIPT.search(str(command[1])):
            name = SCRIPT.search(str(command[1])).group(1).lower()
            prefix, manager = [command[0], command[1]], "npm" if name == "npm-cli" else name
            break
    locked = (root / LOCKS[manager]).is_file()
    first = {"npm": ["ci"] if locked else ["install", "--no-package-lock"],
             "pnpm": ["install", "--frozen-lockfile"] if locked else ["install", "--no-lockfile"],
             "yarn": ["install", "--frozen-lockfile"] if locked else ["install", "--no-lockfile"]}[manager]
    fallback = {"npm": ["install", "--no-package-lock"], "pnpm": ["install", "--no-lockfile"], "yarn": ["install", "--no-lockfile"]}[manager]
    digest = hashlib.sha256()
    for name in ("package.json", LOCKS[manager]):
        path = root / name
        digest.update(path.read_bytes() if path.is_file() else b"-")
    return {"prefix": prefix, "manager": manager, "steps": [first] if first == fallback else [first, fallback],
            "fingerprint": digest.hexdigest()[:16], "installed": (root / "node_modules").is_dir()}


def needed(info, recorded):
    """Whether to install: packages missing, or package.json/lockfile changed since the last install."""
    return info is not None and (not info["installed"] or recorded != info["fingerprint"])
