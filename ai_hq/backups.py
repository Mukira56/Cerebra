"""A verified copy of everything Cerebra records, every day, and a way to go back to one.

The copy uses SQLite's backup API, because a plain file copy of a database in WAL mode can miss recent changes or catch it
half written. Each copy is checked before it counts: one that fails is thrown away and nothing older is pruned, so a damaged
database can't push out the good copies. Each copy is one self-contained file, with no WAL files beside it. KEEP_DAYS days are kept, plus one a week for KEEP_WEEKS more weeks. Only this
module's own hq-daily files are ever pruned. The owner can name a second folder, such as a synced one or an external drive,
because a copy on the same disk doesn't survive that disk.

It runs on its own timer rather than as a Chief of Staff job: a fresh install has every job off until the owner chooses, and
keeping a local copy of their data isn't something they should have to switch on.

Going back can't happen while the app has the database open, so restore() only records the choice and apply_pending() does
it at the next start, before the database is opened. The database being replaced is kept in the backups folder first.

Covers the database only: book files, covers and other documents in the data folder are not included. Saved sign-ins are
protected for this Windows account, so on another computer they need connecting again.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from .models import Event, Metadata, now

KEY = "backup_settings"
KEEP_DAYS, KEEP_WEEKS = 7, 4
FIRST_WAIT, EVERY = 60, 3600  # seconds: soon after opening, then hourly (only one copy a day is made)
DAILY = re.compile(r"^hq-daily-(\d{8})\.sqlite3$")
PENDING = "restore-pending.json"
DATABASE = "hq.sqlite3"


def folder_of(data_dir):
    return Path(data_dir) / "backups"


def verified(path):
    """True when this file is a whole, readable database."""
    try:
        connection = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            return connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def _day(path):
    return datetime.strptime(DAILY.match(path.name).group(1), "%Y%m%d").date()


def label(path):
    day = _day(Path(path))
    return f"{day:%B} {day.day}, {day.year}"


def prune(folder):
    """Remove the daily copies past what's kept. Anything not named like one is left alone."""
    copies = sorted((path for path in Path(folder).iterdir() if DAILY.match(path.name)), key=_day, reverse=True)
    weeks, removed = set(), []
    for path in copies[KEEP_DAYS:]:
        week = _day(path).isocalendar()[:2]
        if week not in weeks and len(weeks) < KEEP_WEEKS:
            weeks.add(week)
            continue
        path.unlink()
        removed.append(path.name)
    return removed


def settings(session):
    row = session.get(Metadata, KEY)
    return dict(row.value) if row else {"folder": ""}


def save_settings(session, folder):
    folder = str(folder or "").strip()
    if folder and not (Path(folder).is_absolute() and Path(folder).is_dir()):
        raise ValueError("Choose a folder that exists, with its full path, such as D:\\Backups")
    row = session.get(Metadata, KEY)
    if row is None:
        session.add(Metadata(key=KEY, value={"folder": folder}))
    else:
        row.value = {"folder": folder}
    return {"folder": folder}


class Backups:
    def __init__(self, db, data_dir, notifier=None, today=None):
        self.db, self.data_dir, self.notifier = db, Path(data_dir), notifier
        self.today = today or date.today
        self.problem = ""
        self._stop, self._thread = threading.Event(), None

    @property
    def folder(self):
        return folder_of(self.data_dir)

    def _fail(self, message):
        self.problem = message
        try:
            with self.db.Session.begin() as session:
                session.add(Event(kind="maintenance", message=message, data={}))
        except SQLAlchemyError:
            pass  # the database itself may be what's damaged: the owner must still hear about it
        if self.notifier:
            self.notifier.send("Backup failed", message, tags="warning")
        return {"error": message}

    def make(self, force=False):
        """Today's copy, unless there is one. Returns what happened in plain fields."""
        self.folder.mkdir(parents=True, exist_ok=True)
        name = f"hq-daily-{self.today().strftime('%Y%m%d')}.sqlite3"
        target = self.folder / name
        if target.exists() and not force:
            return {"skipped": "already backed up today"}
        partial = target.with_suffix(".partial")
        partial.unlink(missing_ok=True)
        try:
            source, copy = sqlite3.connect(self.db.path), sqlite3.connect(partial)
            try:
                source.backup(copy)
                copy.execute("PRAGMA journal_mode=DELETE")
            finally:
                copy.close()
                source.close()
        except (sqlite3.Error, OSError) as exc:
            partial.unlink(missing_ok=True)
            return self._fail(f"Today's backup couldn't be made ({exc}). Your earlier backups are untouched.")
        if not verified(partial):
            partial.unlink(missing_ok=True)
            return self._fail("Today's backup failed its check, so your data may be damaged. Your earlier backups are untouched: see Settings > Backups.")
        partial.replace(target)
        self.problem = ""
        result = {"made": name, "removed": prune(self.folder)}
        with self.db.Session() as session:
            extra = settings(session).get("folder")
        if extra:
            try:
                shutil.copy2(target, Path(extra) / name)
                result["copied"] = extra
                result["removed_there"] = prune(extra)
            except OSError as exc:
                self.problem = f"Backed up here, but not to {extra}: {exc.strerror or exc}"
                result["warning"] = self.problem
        return result

    def tick(self):
        return self.make()

    def _run(self, first, every):
        wait = first
        while not self._stop.wait(wait):
            wait = every
            try:
                self.tick()
            except Exception as exc:  # noqa: BLE001 - this timer must outlive one bad day
                self.problem = f"Today's backup couldn't be made ({exc})."

    def start(self, first=FIRST_WAIT, every=EVERY):
        if self._thread is None:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(first, every), name="backups", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None

    def overview(self, session):
        copies = sorted((path for path in self.folder.iterdir() if DAILY.match(path.name)), key=_day, reverse=True) if self.folder.is_dir() else []
        return {"backups": [{"name": path.name, "date": _day(path).isoformat(), "label": label(path), "bytes": path.stat().st_size} for path in copies],
                "folder": str(self.folder), "extra_folder": settings(session).get("folder", ""), "problem": self.problem,
                "restore_pending": self.pending()}

    def pending(self):
        path = self.folder / PENDING
        try:
            return json.loads(path.read_text(encoding="utf-8")).get("name", "") if path.is_file() else ""
        except (OSError, ValueError):
            return ""

    def restore(self, name):
        """Choose a backup to go back to at the next start. Only a daily copy in the backups folder can be chosen."""
        name = str(name or "")
        path = self.folder / name
        if not DAILY.match(name) or not path.is_file():
            raise LookupError("That backup wasn't found")
        if not verified(path):
            raise ValueError("That backup failed its check, so it can't be used. Choose another.")
        (self.folder / PENDING).write_text(json.dumps({"name": name, "at": now()}), encoding="utf-8")
        with self.db.Session.begin() as session:
            session.add(Event(kind="maintenance", message=f"Going back to {name} at the next start", data={}))
        return {"pending": name, "message": "Close Cerebra completely and open it again to finish going back."}

    def cancel(self):
        (self.folder / PENDING).unlink(missing_ok=True)
        return {"pending": ""}


def apply_pending(data_dir):
    """At start, before the database opens: put the chosen backup in place, keeping the current database. Never raises."""
    data_dir = Path(data_dir)
    folder = folder_of(data_dir)
    marker = folder / PENDING
    if not marker.is_file():
        return None
    try:
        name = json.loads(marker.read_text(encoding="utf-8")).get("name", "")
    except (OSError, ValueError):
        name = ""
    chosen = folder / name
    if not DAILY.match(str(name)) or not chosen.is_file() or not verified(chosen):
        marker.unlink(missing_ok=True)
        return {"error": "The chosen backup couldn't be used; nothing was changed"}
    kept = folder / f"replaced-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    live = [data_dir / (DATABASE + end) for end in ("", "-wal", "-shm")]
    moved = []
    try:
        kept.mkdir(parents=True, exist_ok=True)
        for path in live:
            if path.exists():
                shutil.move(str(path), str(kept / path.name))
                moved.append(path)
        shutil.copy2(chosen, live[0])
    except OSError as exc:  # still open somewhere: put everything back and try again at the next start
        for path in moved:
            if (kept / path.name).exists():
                shutil.move(str(kept / path.name), str(path))
        return {"error": f"Couldn't go back yet: {exc.strerror or exc}. Close every Cerebra window and open it again."}
    marker.unlink(missing_ok=True)
    return {"restored": name, "kept": str(kept)}
