import json
import sys
import os
from pathlib import Path
import pytest
from ai_hq.config import Settings
from ai_hq.manage import process_identity, owned_process

def test_process_identity_matches_current_process(tmp_path):
    identity=process_identity(os.getpid())
    assert identity["pid"]==os.getpid()
    assert Path(identity["image"]).name.lower() in {"python.exe","python","python3","python3.13"}
    settings=Settings(data_dir=tmp_path)
    (tmp_path/"server.json").write_text(json.dumps(identity))
    assert owned_process(settings)["pid"]==os.getpid()

def test_pid_reuse_or_tampering_never_authorizes_stop(tmp_path):
    identity=process_identity(os.getpid())
    identity["created"]=str(identity["created"])+"tampered"
    (tmp_path/"server.json").write_text(json.dumps(identity))
    with pytest.raises(RuntimeError,match="refusing to act"):
        owned_process(Settings(data_dir=tmp_path))

def run_manage(monkeypatch,tmp_path,*args):
    from ai_hq import manage
    monkeypatch.setenv("AIHQ_DATA_DIR",str(tmp_path))
    monkeypatch.setattr(sys,"argv",["manage",*args])
    return manage.main()

def test_cli_confinement_policy_requires_acknowledgement_and_is_revocable(tmp_path,monkeypatch):
    from ai_hq.api import create_app
    with pytest.raises(SystemExit):
        run_manage(monkeypatch,tmp_path,"accept-cli-confinement")
    assert not create_app(Settings(data_dir=tmp_path),start_worker=False).state.supervisor.registry.scope_verified
    run_manage(monkeypatch,tmp_path,"accept-cli-confinement","--acknowledge-residual-read-risk")
    app=create_app(Settings(data_dir=tmp_path),start_worker=False)
    assert app.state.settings.cli_confinement_accepted and app.state.supervisor.registry.confinement_mode == "cli-confinement"
    assert not app.state.supervisor.registry.scope_verified, "Risk acceptance is not verified OS isolation"
    assert not app.state.supervisor.registry.allow_live, "Accepting confinement must not enable live execution"
    run_manage(monkeypatch,tmp_path,"revoke-cli-confinement")
    assert not create_app(Settings(data_dir=tmp_path),start_worker=False).state.supervisor.registry.scope_verified

def test_cli_confinement_policy_refuses_while_server_runs(tmp_path,monkeypatch):
    identity=process_identity(os.getpid())
    (tmp_path/"server.json").write_text(json.dumps(identity))
    with pytest.raises(RuntimeError,match="Stop AI HQ"):
        run_manage(monkeypatch,tmp_path,"accept-cli-confinement","--acknowledge-residual-read-risk")

def test_doctor_records_stored_sandbox_policy_for_dashboard(tmp_path,monkeypatch):
    from ai_hq import doctor
    from ai_hq.agents import _CliAdapter
    monkeypatch.setattr(_CliAdapter,"_find",lambda self: None)
    assert doctor.inspect(Settings(data_dir=tmp_path))["agents"]["codex"]["scope_verified"] is False
    run_manage(monkeypatch,tmp_path,"accept-cli-confinement","--acknowledge-residual-read-risk")
    report=doctor.inspect(Settings(data_dir=tmp_path))
    assert report["agents"]["codex"]["scope_verified"] is False and report["agents"]["claude"]["scope_verified"] is False
    assert report["agents"]["codex"]["confinement_mode"] == "cli-confinement"
    assert report["agents"]["codex"]["live_enabled"] is False
