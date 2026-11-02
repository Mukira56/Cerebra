"""Fail-closed customer payload inventory and privacy checks. Never reads owner runtime data."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import marshal
from pathlib import Path
import re
import shutil
import subprocess
import types

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

FORBIDDEN_PARTS = {'.git', '.codex', '.claude', 'data', 'work', 'logs', 'backups', 'sessions', 'node_modules'}
FORBIDDEN_SUFFIXES = {'.db', '.sqlite', '.sqlite3', '.log', '.pem', '.key', '.p12', '.pfx', '.pyo'}
PERSONAL_MARKERS = ('Mukira56', 'Godfrey Mukira', 'EstatePilot', 'C:/Users/ADMIN', 'C:\\Users\\ADMIN')
SECRET = re.compile(rb'(?<![A-Za-z0-9])(?:sk-(?:proj-|live-)?[A-Za-z0-9_-]{24,}|ghp_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def safe_file(path):
    if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
        raise ValueError('Release inputs cannot contain links: ' + path.name)
    return path.is_file()


def copy_app(root, target):
    result = subprocess.run(['git', 'ls-files', '-z', '--', 'ai_hq'], cwd=root, capture_output=True, check=True)
    names = result.stdout.decode('utf-8').split('\0')
    if 'ai_hq/api.py' not in names or 'ai_hq/onboarding.py' not in names:
        raise ValueError('Stage all customer runtime modules in Git before building')
    for name in filter(None, names):
        path = root / name
        if not safe_file(path):
            raise ValueError('Missing inventoried application file: ' + name)
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def copy_dependencies(site, target, requirements):
    """Copy only declared distributions and their transitive dependencies, using RECORD inventories."""
    available = {canonicalize_name(dist.metadata['Name']): dist for dist in metadata.distributions(path=[str(site)])}
    selected = {}
    pending = list(requirements)
    while pending:
        requirement = Requirement(pending.pop())
        if requirement.marker and not requirement.marker.evaluate():
            continue
        name = canonicalize_name(requirement.name)
        if name in selected:
            continue
        dist = available.get(name)
        if dist is None or not dist.files:
            raise ValueError('Missing dependency inventory: ' + name)
        if requirement.specifier and not requirement.specifier.contains(dist.version):
            raise ValueError('Installed dependency does not satisfy release requirements: ' + name)
        selected[name] = dist
        pending.extend(dist.requires or [])
    for dist in selected.values():
        for entry in dist.files:
            relative = Path(str(entry))
            # Console launchers, local editable metadata and caches never belong to the private runtime.
            if relative.is_absolute() or '..' in relative.parts or '__pycache__' in relative.parts:
                continue
            if relative.suffix.lower() in {'.pyc', '.pyo', '.pth'} or relative.name in {'direct_url.json', 'RECORD'}:
                continue
            path = site / relative
            if not safe_file(path):
                raise ValueError('Missing dependency file: ' + str(relative))
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    return sorted((dist.metadata['Name'], dist.version) for dist in selected.values())


def code_filenames(code):
    yield code.co_filename
    for value in code.co_consts:
        if isinstance(value, types.CodeType):
            yield from code_filenames(value)


def audit(stage):
    """Inspect every payload file, including bytecode constants; report names/hashes, never matching secrets."""
    files = {}
    for path in sorted(stage.rglob('*')):
        if not safe_file(path):
            continue
        relative = path.relative_to(stage)
        parts = {part.lower() for part in relative.parts}
        public_ca = relative.as_posix() == 'runtime/Lib/site-packages/certifi/cacert.pem'
        if parts & FORBIDDEN_PARTS or (path.suffix.lower() in FORBIDDEN_SUFFIXES and not public_ca) or path.name.lower().startswith('.env'):
            raise ValueError('Private runtime artifact in customer payload: ' + relative.as_posix())
        raw = path.read_bytes()
        lower = raw.lower()
        if any(marker.lower().encode(encoding) in lower for marker in PERSONAL_MARKERS for encoding in ('utf-8', 'utf-16le')):
            raise ValueError('Developer identity/path in customer payload: ' + relative.as_posix())
        if SECRET.search(raw):
            raise ValueError('Possible credential in customer payload: ' + relative.as_posix())
        if path.suffix.lower() == '.pyc':
            code = marshal.loads(raw[16:])
            if any(re.match(r'^(?:[A-Za-z]:|[/\\])', name) for name in code_filenames(code)):
                raise ValueError('Absolute build path in bytecode: ' + relative.as_posix())
        files[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    return files
