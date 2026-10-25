"""In-app updates (fake GitHub CLI, no download or install) and the Business connections setup helpers."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from ai_hq import updater as updates
from ai_hq.api import create_app
from ai_hq.config import Settings
from test_product_api import KEY

INSTALLER = b"MZ fixture installer bytes"


class FakeGh:
    """Answers `gh release view/download` like GitHub would, from fixture data."""
    def __init__(self, tag="v99.0.0", assets=True, corrupt=False):
        self.tag, self.assets, self.corrupt, self.calls = tag, assets, corrupt, []

    def run(self, args, cwd, timeout=None):
        args = [str(arg) for arg in args]; self.calls.append(args)
        name = f"Cerebra-Setup-{self.tag[1:]}-Windows-x64.exe"
        if args[1:3] == ["release", "view"]:
            assets = [{"name": name}, {"name": name + ".sha256"}] if self.assets else []
            return SimpleNamespace(exit_code=0, stdout=json.dumps({"tagName": self.tag, "name": f"Cerebra {self.tag}", "body": "## New\n- Faster", "publishedAt": "2026-10-25T10:00:00Z", "assets": assets}), stderr="")
        if args[1:3] == ["release", "download"]:
            target = Path(args[args.index("--dir") + 1])
            (target / name).write_bytes(INSTALLER)
            digest = hashlib.sha256(b"something else" if self.corrupt else INSTALLER).hexdigest()
            (target / (name + ".sha256")).write_text(f"{digest}  {name}\n", encoding="utf-8")
            return SimpleNamespace(exit_code=0, stdout="", stderr="")
        return SimpleNamespace(exit_code=1, stdout="", stderr="unexpected")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.shutil, "which", lambda name: "C:/tools/gh.exe")
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)
    spawned = []
    app.state.updater.runner = FakeGh()
    app.state.updater.spawn = spawned.append
    app.state.spawned = spawned
    with TestClient(app) as client:
        client.headers["X-CSRF-Token"] = client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield client


def test_check_download_verify_and_install_plan(client, tmp_path, monkeypatch):
    info = client.get("/api/updates").json()
    assert info["available"] and info["latest"] == "99.0.0" and "Faster" in info["notes"] and not info["downloaded"]
    assert client.post("/api/updates/install").status_code == 400  # nothing downloaded yet
    result = client.post("/api/updates/download", json={"tag": "v99.0.0"}).json()
    assert result["downloaded"] and result["sha256"] == hashlib.sha256(INSTALLER).hexdigest()
    assert client.get("/api/updates").json()["downloaded"]
    # Running from source: installing is refused (use git pull).
    assert "git pull" in client.post("/api/updates/install").json()["detail"]
    root = tmp_path / "install"; (root / "runtime").mkdir(parents=True)
    for name in ("desktop-settings.json", "AIHQ.exe", "runtime/python.exe"): (root / name).write_text("x", encoding="utf-8")
    monkeypatch.setattr(updates, "ROOT", root)
    started = client.post("/api/updates/install").json()
    assert started["restarting"] and client.app.state.spawned
    folder = tmp_path / "data" / "updates"
    plan = json.loads((folder / "update-plan.json").read_text(encoding="utf-8"))
    assert plan["to"] == "99.0.0" and plan["root"] == str(root) and plan["sha256"] == result["sha256"] and plan["data"] == str(tmp_path / "data")
    script = (folder / "apply-update.ps1").read_text(encoding="utf-8-sig")
    assert "manage stop" in script and "Get-FileHash" in script and "--quiet" in script and "AIHQ.exe" in script


def test_tampered_or_old_releases_are_refused(client):
    client.app.state.updater.runner = FakeGh(corrupt=True)
    response = client.post("/api/updates/download", json={"tag": "v99.0.0"})
    assert response.status_code == 400 and "does not match" in response.json()["detail"]
    assert not list((client.app.state.settings.data_dir / "updates" / "v99.0.0").glob("*.exe"))  # deleted
    assert client.post("/api/updates/download", json={"tag": "v0.0.1"}).status_code == 400
    assert client.post("/api/updates/download", json={"tag": "latest; rm"}).status_code == 422
    client.app.state.updater.runner = FakeGh(assets=False)
    info = client.get("/api/updates").json()
    assert not info["available"] and "no Windows installer" in info["message"]
    client.app.state.updater.runner = FakeGh(tag="v0.1.0")
    assert client.get("/api/updates").json()["message"] == "You have the latest version."


def test_open_link_allows_only_fixed_official_pages(client, monkeypatch):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert client.post("/api/open-link/etsy_apps").json()["opened"] == "https://www.etsy.com/developers/your-apps"
    assert client.post("/api/open-link/https%3A%2F%2Fevil.example").status_code == 404
    assert opened == ["https://www.etsy.com/developers/your-apps"]


def transport(client, handler):
    client.app.state.commerce.client.close()
    client.app.state.commerce.client = httpx.Client(transport=httpx.MockTransport(handler))


def test_etsy_shop_id_is_found_after_authorization(client):
    from ai_hq import commerce, vault
    import time
    with client.app.state.db.Session.begin() as session:
        commerce.store(session, {"etsy": {"api_key": vault.protect("fixturekeystring"), "shared_secret": vault.protect("fixturesecret"),
                                          "access_token": vault.protect("12345678.fixture-access"), "refresh_token": vault.protect("r"), "expires_at": time.time() + 3600}})
    seen = []
    def handle(request):
        seen.append(request.url.path)
        if request.url.path == "/v3/application/users/12345678/shops": return httpx.Response(200, json={"shop_id": 4242, "shop_name": "SunriseStudio"})
        return httpx.Response(200, json={"shop_id": 4242, "shop_name": "SunriseStudio"})
    transport(client, handle)
    result = client.post("/api/business/connections/etsy/check").json()
    assert result["shop_id"] == "4242" and "SunriseStudio" in result["message"]
    assert seen == ["/v3/application/users/12345678/shops", "/v3/application/shops/4242"]
    assert client.get("/api/business/connections").json()["etsy"]["shop_id"] == "4242"
    transport(client, lambda request: httpx.Response(404, json={"error": "no shop"}))
    with client.app.state.db.Session.begin() as session:
        value = commerce.load(session); value["etsy"].pop("shop_id"); commerce.store(session, value)
    assert "no shop yet" in client.post("/api/business/connections/etsy/check").json()["detail"]


def test_printify_single_store_is_selected_automatically(client):
    client.put("/api/business/connections/printify", json={"values": {"api_key": "fixture-printify-token"}})
    transport(client, lambda request: httpx.Response(200, json=[{"id": 777, "title": "My POD store"}]))
    result = client.post("/api/business/connections/printify/check").json()
    assert result["shop_id"] == "777" and "My POD store" in result["message"]
    transport(client, lambda request: httpx.Response(200, json=[]))
    client.put("/api/business/connections/printify", json={"values": {"api_key": "another-fixture-token"}})
    assert "no store yet" in client.post("/api/business/connections/printify/check").json()["detail"]
