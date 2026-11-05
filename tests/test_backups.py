"""Daily verified backups, what's kept, a second folder, and going back at the next start. All on throwaway databases."""
import sqlite3
from datetime import date, timedelta

import pytest

from ai_hq import backups
from ai_hq.backups import Backups, apply_pending, prune, verified
from ai_hq.db import Database
from ai_hq.models import Event, Metadata
from test_freelance import client  # noqa: F401  (client is a fixture)


def database(tmp_path):
    db = Database(tmp_path / "hq.sqlite3")
    db.init()
    return db


def note(db, value):
    with db.Session.begin() as session:
        session.merge(Metadata(key="note", value={"text": value}))


def read(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute("select value from configuration_metadata where key='note'").fetchone()
    finally:
        connection.close()


def touch(folder, day):
    path = folder / f"hq-daily-{day.strftime('%Y%m%d')}.sqlite3"
    path.write_bytes(b"x")
    return path


def test_a_copy_is_made_once_a_day_and_holds_changes_still_in_the_wal(tmp_path):
    db = database(tmp_path)
    note(db, "recent")
    days = iter([date(2026, 11, 5)] * 2 + [date(2026, 11, 6)])
    robot = Backups(db, tmp_path, today=lambda: next(days))
    assert robot.tick()["made"] == "hq-daily-20261105.sqlite3"
    assert robot.tick() == {"skipped": "already backed up today"}
    copy = tmp_path / "backups" / "hq-daily-20261105.sqlite3"
    assert verified(copy) and "recent" in read(copy)[0]
    assert robot.tick()["made"] == "hq-daily-20261106.sqlite3"
    assert not list((tmp_path / "backups").glob("*.partial"))
    db.close()


def test_seven_days_and_four_weeks_are_kept_and_nothing_else_is_touched(tmp_path):
    start = date(2026, 11, 5)
    for number in range(60):
        touch(tmp_path, start - timedelta(days=number))
    (tmp_path / "hq-before-deleting-tasks-20261026-181711.sqlite3").write_bytes(b"x")
    (tmp_path / "replaced-20261101-120000").mkdir()
    prune(tmp_path)
    kept = sorted(path.name for path in tmp_path.iterdir() if path.name.startswith("hq-daily"))
    assert len(kept) == 11
    assert kept[-1] == "hq-daily-20261105.sqlite3" and "hq-daily-20261030.sqlite3" in kept  # the newest seven days
    assert (tmp_path / "hq-before-deleting-tasks-20261026-181711.sqlite3").exists() and (tmp_path / "replaced-20261101-120000").is_dir()


def test_a_copy_that_fails_its_check_is_dropped_and_old_copies_survive(tmp_path, monkeypatch):
    told = []

    class Phone:
        def send(self, title, text, tags=""):
            told.append(title)

    db = database(tmp_path)
    robot = Backups(db, tmp_path, Phone(), today=lambda: date(2026, 11, 5))
    (tmp_path / "backups").mkdir()
    olds = [touch(tmp_path / "backups", date(2026, 10, 1) + timedelta(days=number)) for number in range(20)]
    monkeypatch.setattr(backups, "verified", lambda path: False)
    result = robot.tick()
    assert "failed its check" in result["error"] and robot.problem and told == ["Backup failed"]
    assert all(path.exists() for path in olds)  # nothing pruned
    assert not (tmp_path / "backups" / "hq-daily-20261105.sqlite3").exists() and not list((tmp_path / "backups").glob("*.partial"))
    monkeypatch.undo()
    assert "made" in robot.tick() and robot.problem == ""
    db.close()


def test_damaged_files_do_not_pass_the_check(tmp_path):
    db = database(tmp_path)
    robot = Backups(db, tmp_path, today=lambda: date(2026, 11, 5))
    robot.tick()
    good = tmp_path / "backups" / "hq-daily-20261105.sqlite3"
    assert verified(good)
    data = bytearray(good.read_bytes())
    data[4096:8192] = b"\xff" * 4096
    bad = tmp_path / "bad.sqlite3"
    bad.write_bytes(bytes(data))
    (tmp_path / "text.sqlite3").write_bytes(b"not a database at all, just some words here" * 50)
    assert not verified(bad) and not verified(tmp_path / "text.sqlite3") and not verified(tmp_path / "missing.sqlite3")
    db.close()


def test_the_second_folder_gets_a_copy_and_a_lost_folder_only_warns(tmp_path):
    db = database(tmp_path / "data")
    extra = tmp_path / "usb"
    extra.mkdir()
    with db.Session.begin() as session:
        backups.save_settings(session, str(extra))
    robot = Backups(db, tmp_path / "data", today=lambda: date(2026, 11, 5))
    assert robot.tick()["copied"] == str(extra) and verified(extra / "hq-daily-20261105.sqlite3")
    extra.rename(tmp_path / "unplugged")
    result = Backups(db, tmp_path / "data", today=lambda: date(2026, 11, 6)).tick()
    assert result["made"] and "not to" in result["warning"]
    db.close()


def test_the_second_folder_must_be_a_real_full_path(tmp_path):
    db = database(tmp_path)
    with db.Session.begin() as session:
        for bad in ("relative\\folder", str(tmp_path / "missing")):
            with pytest.raises(ValueError, match="full path"):
                backups.save_settings(session, bad)
        assert backups.save_settings(session, "") == {"folder": ""}
    db.close()


def test_going_back_happens_at_the_next_start_and_keeps_what_it_replaced(tmp_path):
    db = database(tmp_path)
    note(db, "before")
    robot = Backups(db, tmp_path, today=lambda: date(2026, 11, 5))
    robot.tick()
    note(db, "after")
    assert robot.restore("hq-daily-20261105.sqlite3")["pending"] == "hq-daily-20261105.sqlite3"
    assert robot.pending() == "hq-daily-20261105.sqlite3" and "after" in read(tmp_path / "hq.sqlite3")[0]  # nothing changes yet
    db.close()
    result = apply_pending(tmp_path)
    assert result["restored"] == "hq-daily-20261105.sqlite3" and "before" in read(tmp_path / "hq.sqlite3")[0]
    from pathlib import Path
    assert "after" in read(Path(result["kept"]) / "hq.sqlite3")[0]
    assert apply_pending(tmp_path) is None  # done once
    again = Database(tmp_path / "hq.sqlite3")
    again.init()
    again.close()


def test_only_a_daily_copy_in_the_folder_can_be_chosen(tmp_path):
    db = database(tmp_path)
    robot = Backups(db, tmp_path, today=lambda: date(2026, 11, 5))
    robot.tick()
    (tmp_path / "backups" / "hq-daily-20261001.sqlite3").write_bytes(b"not a database" * 100)
    for bad in ("../hq.sqlite3", "..\\hq.sqlite3", "C:\\Windows\\win.ini", "", None, "hq-before-x.sqlite3", "hq-daily-20200101.sqlite3"):
        with pytest.raises(LookupError):
            robot.restore(bad)
    with pytest.raises(ValueError, match="failed its check"):
        robot.restore("hq-daily-20261001.sqlite3")
    assert robot.pending() == ""
    db.close()


def test_a_bad_choice_at_start_changes_nothing_and_can_be_cancelled(tmp_path):
    db = database(tmp_path)
    note(db, "current")
    robot = Backups(db, tmp_path, today=lambda: date(2026, 11, 5))
    robot.tick()
    robot.restore("hq-daily-20261105.sqlite3")
    assert robot.cancel() == {"pending": ""} and apply_pending(tmp_path) is None
    robot.restore("hq-daily-20261105.sqlite3")
    (tmp_path / "backups" / "hq-daily-20261105.sqlite3").write_bytes(b"ruined" * 100)
    db.close()
    assert "error" in apply_pending(tmp_path) and "current" in read(tmp_path / "hq.sqlite3")[0]
    assert not (tmp_path / "backups" / "restore-pending.json").exists()


def test_a_database_still_in_use_is_put_back_and_tried_again(tmp_path, monkeypatch):
    db = database(tmp_path)
    note(db, "current")
    Backups(db, tmp_path, today=lambda: date(2026, 11, 5)).tick()
    Backups(db, tmp_path).restore("hq-daily-20261105.sqlite3")
    db.close()
    real = backups.shutil.copy2
    monkeypatch.setattr(backups.shutil, "copy2", lambda *args: (_ for _ in ()).throw(PermissionError(13, "in use")))
    assert "Close every Cerebra window" in apply_pending(tmp_path)["error"]
    assert (tmp_path / "hq.sqlite3").exists() and "current" in read(tmp_path / "hq.sqlite3")[0]
    monkeypatch.setattr(backups.shutil, "copy2", real)
    assert apply_pending(tmp_path)["restored"]


def test_the_app_backs_up_on_its_schedule_and_answers_over_the_api(client):  # noqa: F811
    assert client.post("/api/backups/run").json()["made"].startswith("hq-daily-")
    state = client.get("/api/backups").json()
    assert len(state["backups"]) == 1 and state["backups"][0]["bytes"] > 0 and state["problem"] == ""
    assert backups.label("hq-daily-20261105.sqlite3") == "November 5, 2026"
    name = state["backups"][0]["name"]
    assert client.post("/api/backups/restore", json={"name": "../hq.sqlite3"}).status_code == 404
    assert client.post("/api/backups/restore", json={"name": name}).json()["pending"] == name
    assert client.get("/api/backups").json()["restore_pending"] == name
    assert client.delete("/api/backups/restore").json() == {"pending": ""}
    assert client.put("/api/backups/settings", json={"folder": "nowhere"}).status_code == 400
    assert "backups" not in {job["id"] for job in client.get("/api/chief").json()["jobs"]}  # a fresh install still has every job off


def test_a_copy_is_one_file_with_nothing_beside_it(tmp_path):
    db = database(tmp_path)
    note(db, "x")
    Backups(db, tmp_path, today=lambda: date(2026, 11, 5)).tick()
    assert sorted(path.name for path in (tmp_path / "backups").iterdir()) == ["hq-daily-20261105.sqlite3"]
    db.close()


def test_the_timer_backs_up_on_its_own_and_stops(tmp_path):
    import time
    db = database(tmp_path)
    robot = Backups(db, tmp_path, today=lambda: date(2026, 11, 5))
    robot.start(first=0.01, every=0.01)
    robot.start(first=0.01, every=0.01)  # asking twice starts one timer
    copy = tmp_path / "backups" / "hq-daily-20261105.sqlite3"
    for _ in range(300):
        if copy.exists():
            break
        time.sleep(0.01)
    robot.stop()
    assert copy.exists() and robot._thread is None
    db.close()


def test_one_bad_run_does_not_end_the_timer(tmp_path, monkeypatch):
    import time
    db = database(tmp_path)
    robot = Backups(db, tmp_path, today=lambda: date(2026, 11, 5))
    runs = []
    monkeypatch.setattr(robot, "tick", lambda: runs.append(1) or (_ for _ in ()).throw(RuntimeError("disk gone")))
    robot.start(first=0.01, every=0.01)
    for _ in range(300):
        if len(runs) >= 2:
            break
        time.sleep(0.01)
    robot.stop()
    assert len(runs) >= 2 and "disk gone" in robot.problem
    db.close()


def test_the_owner_still_hears_when_the_database_itself_is_broken(tmp_path, monkeypatch):
    from sqlalchemy.exc import OperationalError
    told = []

    class Phone:
        def send(self, title, text, tags=""):
            told.append(title)

    db = database(tmp_path)
    robot = Backups(db, tmp_path, Phone(), today=lambda: date(2026, 11, 5))
    monkeypatch.setattr(db.Session, "begin", lambda: (_ for _ in ()).throw(OperationalError("x", {}, Exception("malformed"))))
    assert robot._fail("broken") == {"error": "broken"} and told == ["Backup failed"]
    db.close()


def test_restarting_the_app_finishes_going_back(tmp_path):
    from ai_hq.api import create_app
    from ai_hq.config import Settings
    settings = Settings(data_dir=tmp_path / "data")
    first = create_app(settings, bootstrap_key="k" * 40, start_worker=False)
    with first.state.db.Session.begin() as session:
        session.merge(Metadata(key="note", value={"text": "before"}))
    first.state.backups.make()
    name = next((tmp_path / "data" / "backups").glob("hq-daily-*")).name
    with first.state.db.Session.begin() as session:
        session.merge(Metadata(key="note", value={"text": "after"}))
    first.state.backups.restore(name)
    first.state.db.close()
    second = create_app(settings, bootstrap_key="k" * 40, start_worker=False)
    with second.state.db.Session() as session:
        assert session.get(Metadata, "note").value == {"text": "before"}
    assert second.state.backups.pending() == ""
    second.state.db.close()


def test_the_events_table_is_not_needed_for_a_copy_to_count(tmp_path):
    db = database(tmp_path)
    Backups(db, tmp_path, today=lambda: date(2026, 11, 5)).tick()
    with db.Session() as session:
        assert session.query(Event).count() == 0  # a normal day leaves no noise in the activity log
    db.close()
