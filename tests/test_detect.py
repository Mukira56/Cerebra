"""Project type detection suggests how a project is tested, from its top-level files."""
import json

import pytest

from ai_hq.detect import detect


@pytest.mark.parametrize("files,key", [
    ({"package.json": json.dumps({"scripts": {"test": "vitest run"}})}, "npm"),
    ({"package.json": json.dumps({"scripts": {"test": "jest"}}), "pnpm-lock.yaml": ""}, "pnpm"),
    ({"package.json": json.dumps({"scripts": {"test": "echo \"Error: no test specified\" && exit 1"}})}, "none"),
    ({"App.sln": ""}, "dotnet"),
    ({"go.mod": "module x"}, "go"),
    ({"Cargo.toml": "[package]"}, "cargo"),
    ({"pyproject.toml": "[tool.pytest.ini_options]"}, "pytest"),
    ({"tests/test_app.py": "import unittest"}, "unittest"),
    ({"README.md": "hello"}, "none"),
])
def test_detects_project_type(tmp_path, files, key):
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text, encoding="utf-8")
    result = detect(str(tmp_path))
    assert result["key"] == key, result
    assert (result["test_commands"] == []) is (key == "none")


def test_rejects_missing_or_relative_folders(tmp_path):
    for bad in (str(tmp_path / "missing"), "relative/folder"):
        with pytest.raises(ValueError):
            detect(bad)
