"""Cerebra's own log: data folder › logs › cerebra.log.

Problems only: failed requests, slow requests, retries, a service switched off for a while after repeated
failures, database upgrades and unexpected errors. The page's routine polling is not written. Every line passes
through security.redact, and query strings are never logged (an OAuth callback carries its code in one).

The file is opened for each line and closed again, so a log never keeps a data folder locked on Windows.
It is kept small: at 1 MB it moves to cerebra.log.1 (up to five old files are kept).
"""
import logging
import threading
import traceback
from pathlib import Path

from .security import redact

LOGGER = "cerebra"
MAX_BYTES = 1_000_000
KEEP = 5


class FileLog(logging.Handler):
    def __init__(self, path):
        super().__init__(logging.INFO)
        self.path = Path(path)
        self.guard = threading.Lock()
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    def _rotate(self):
        if not self.path.is_file() or self.path.stat().st_size < MAX_BYTES:
            return
        for number in range(KEEP - 1, 0, -1):
            older = self.path.with_name(f"{self.path.name}.{number}")
            if older.is_file():
                older.replace(self.path.with_name(f"{self.path.name}.{number + 1}"))
        self.path.replace(self.path.with_name(f"{self.path.name}.1"))

    def emit(self, record):
        try:
            line = redact(self.format(record)).replace("\r", "")
            with self.guard:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._rotate()
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except Exception:  # logging must never break the request or worker that logs
            pass


_lock = threading.Lock()
_handler = None


def setup(data_dir):
    """Point Cerebra's log at this data folder (the latest app wins; tests start many)."""
    global _handler
    logger = logging.getLogger(LOGGER)
    with _lock:
        path = Path(data_dir) / "logs" / "cerebra.log"
        if _handler is not None and _handler.path == path:
            return logger
        if _handler is not None:
            logger.removeHandler(_handler)
        _handler = FileLog(path)
        logger.addHandler(_handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def get(name=""):
    return logging.getLogger(f"{LOGGER}.{name}" if name else LOGGER)


def path():
    return _handler.path if _handler is not None else None


def tail(lines=200):
    """The newest lines of the log, already redacted, for Settings and support reports."""
    current = path()
    if current is None or not current.is_file():
        return []
    with open(current, encoding="utf-8", errors="replace") as handle:
        return [line.rstrip("\n") for line in handle.readlines()[-max(1, min(int(lines), 2000)):]]


def error(logger, message, exc):
    logger.error("%s: %s\n%s", message, exc.__class__.__name__,
                 "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:])
