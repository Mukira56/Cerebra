"""A project's local settings files (.env, .env.local…) for its tests, without showing them to the AI.

Settings files hold the owner's own database URLs and secrets, so projects keep them out of Git, and a task's fresh
working copy never has them: EstatePilot's sign-up returned 503 in every test run for that reason. Cerebra lends the
project's settings files to the working copy only while its own test run happens, then removes them again, so the
coding and reviewing models never see them. When a project only has an example file (.env.example) and no real
settings, Cerebra lists the setting names the owner needs to fill in (never values).
"""
from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath

PATTERN = re.compile(r"^\.env(\.[\w-]+)*$")
EXAMPLES = re.compile(r"\.(example|sample|template|dist|defaults)$", re.I)
SKIP = {"node_modules", ".git", ".venv", "venv", "__pycache__", "dist", "build", ".next"}
DEPTH = 3
NAME = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", re.M)
# "# Copy to apps/web/.env.local" in the example says where the real file belongs (EstatePilot's web app reads it there).
TARGET = re.compile(r"copy\s+(?:this\s+file\s+|it\s+)?to\s+[`'\"]?((?:[\w.-]+[\\/])*\.env(?:\.[\w-]+)*)", re.I)


def _walk(root, depth=DEPTH):
    root = Path(root)
    stack = [(root, 0)]
    while stack:
        folder, level = stack.pop()
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir() and not entry.is_symlink():
                if level < depth and entry.name not in SKIP:
                    stack.append((entry, level + 1))
            elif entry.is_file() and PATTERN.match(entry.name):
                yield entry


def settings_files(project):
    """The project's real settings files (not examples), as paths relative to the project."""
    root = Path(project)
    return sorted(path.relative_to(root).as_posix() for path in _walk(root) if not EXAMPLES.search(path.name))


def missing(project):
    """{"example": path, "names": [...]} when the project has an example settings file but no real one, else None."""
    root = Path(project)
    if settings_files(root):
        return None
    examples = sorted(path for path in _walk(root) if EXAMPLES.search(path.name))
    if not examples:
        return None
    example = examples[0].relative_to(root).as_posix()
    try:
        text = examples[0].read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    names = list(dict.fromkeys(NAME.findall(text)))[:30]
    return {"example": example, "names": names, "target": _target(example, text)}


def _target(example, text):
    """Where the real settings file goes: the path the example names, else .env beside it (read by dotenv in Node,
    Python and Next.js alike)."""
    found = TARGET.search(text)
    if found:
        relative = PurePosixPath(found.group(1).replace("\\", "/").removeprefix("./"))
        if not relative.is_absolute() and ".." not in relative.parts and PATTERN.match(relative.name) and not EXAMPLES.search(relative.name):
            return relative.as_posix()
    return (PurePosixPath(example).parent / ".env").as_posix()


def create(project):
    """The owner's "Create the settings file": copy the example to where the real file goes, for the owner to fill
    in. Only when Git ignores that path, so the owner's secrets can never be committed. Returns the path created."""
    root = Path(project)
    needed = missing(root)
    if not needed:
        raise ValueError("This project already has a settings file, or no example to start from")
    target = (root / needed["target"]).resolve()
    if not target.is_relative_to(root.resolve()) or target.exists():
        raise ValueError(f"{needed['target']} already exists or is outside the project")
    ignored = subprocess.run(["git", "check-ignore", "-q", needed["target"]], cwd=root, capture_output=True, timeout=30)
    if ignored.returncode != 0:
        raise ValueError(f"Git doesn't ignore {needed['target']} in this project, so your secrets could be committed. "
                         f"Add {needed['target']} to the project's .gitignore first.")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / needed["example"], target)
    return needed["target"]


@contextlib.contextmanager
def lent(project, workdir):
    """Copy the project's settings files into the working copy for the duration of a test run, then remove them.
    Files the working copy already has are left alone."""
    root, target, copied = Path(project), Path(workdir), []
    try:
        if root.resolve() != target.resolve():
            for relative in settings_files(root):
                destination = target / relative
                if destination.exists() or not destination.parent.is_dir():
                    continue
                shutil.copy2(root / relative, destination)
                copied.append(destination)
        yield [path.relative_to(target).as_posix() for path in copied]
    finally:
        for path in copied:
            try:
                path.unlink()
            except OSError:
                pass
