"""Real payload audit adversarial fixtures; no owner folders or real secrets are used."""
import importlib.util
from pathlib import Path
import py_compile
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from release_privacy import audit, copy_app, copy_dependencies  # noqa: E402


@pytest.mark.parametrize('name', ['data/hq.sqlite3', 'ai_hq/session.db', 'ai_hq/.env', '.git/config', 'ai_hq/debug.log', 'runtime/user.key'])
def test_rejects_private_files(tmp_path, name):
    file = tmp_path / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text('fixture', encoding='utf-8')
    with pytest.raises(ValueError, match='Private runtime artifact'):
        audit(tmp_path)


@pytest.mark.parametrize('content', ['C:/Users/ADMIN/fixture', 'Godfrey Mukira', 'ghp_' + 'x' * 35])
def test_rejects_embedded_identity_and_possible_credentials(tmp_path, content):
    (tmp_path / 'app.py').write_text(content, encoding='utf-8')
    with pytest.raises(ValueError):
        audit(tmp_path)


def test_rejects_nested_absolute_bytecode_paths_and_accepts_relative_ones(tmp_path):
    source = tmp_path / 'app.py'
    source.write_text('def nested():\n    return 1\n', encoding='utf-8')
    compiled = importlib.util.cache_from_source(str(source))
    py_compile.compile(str(source), cfile=compiled, dfile='Z:/private-builder/app.py')
    with pytest.raises(ValueError, match='Absolute build path'):
        audit(tmp_path)
    py_compile.compile(str(source), cfile=compiled, dfile='ai_hq/app.py')
    files = audit(tmp_path)
    assert 'app.py' in files and len(files) == 2


def test_app_inventory_does_not_copy_untracked_local_files(tmp_path):
    import subprocess
    root = tmp_path / 'source'
    app = root / 'ai_hq'
    app.mkdir(parents=True)
    for name in ('api.py', 'onboarding.py'):
        (app / name).write_text('# customer code\n', encoding='utf-8')
    subprocess.run(['git', 'init', str(root)], check=True, capture_output=True)
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
    (app / 'private-notes.txt').write_text('private fixture', encoding='utf-8')
    target = tmp_path / 'payload'
    copy_app(root, target)
    assert (target / 'ai_hq/api.py').is_file()
    assert not (target / 'ai_hq/private-notes.txt').exists()


def test_dependency_inventory_excludes_unrelated_packages_and_local_metadata(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import release_privacy
    site = tmp_path / 'site'
    site.mkdir()
    for name in ('needed.py', 'private.py', 'direct_url.json'):
        (site / name).write_text('fixture', encoding='utf-8')
    wanted = SimpleNamespace(metadata={'Name': 'wanted'}, version='1.0', requires=[],
                             files=[Path('needed.py'), Path('direct_url.json')])
    unrelated = SimpleNamespace(metadata={'Name': 'unrelated'}, version='1.0', requires=[], files=[Path('private.py')])
    monkeypatch.setattr(release_privacy.metadata, 'distributions', lambda **kw: [wanted, unrelated])
    target = tmp_path / 'customer-site'
    assert copy_dependencies(site, target, ['wanted>=1']) == [('wanted', '1.0')]
    assert sorted(path.name for path in target.iterdir()) == ['needed.py']


def test_public_certificate_exception_still_rejects_private_key_material(tmp_path):
    ca = tmp_path / 'runtime/Lib/site-packages/certifi/cacert.pem'
    ca.parent.mkdir(parents=True)
    ca.write_text('-----BEGIN CERTIFICATE-----\npublic fixture\n', encoding='ascii')
    assert audit(tmp_path)
    ca.write_text('-----BEGIN PRIVATE KEY-----\nprivate fixture\n', encoding='ascii')
    with pytest.raises(ValueError, match='credential'):
        audit(tmp_path)
