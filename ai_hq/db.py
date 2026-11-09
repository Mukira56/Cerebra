import json
from pathlib import Path
from sqlalchemy import JSON, create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker
from . import logs
from .models import Base, Metadata

log = logs.get("database")


def _literal(column):
    """The SQL default for a column added to an older database, so existing rows get the model's default value."""
    default = column.default
    if default is None or getattr(default, "is_sequence", False):
        return None
    value = default.arg
    if callable(value):
        try:
            value = value(None)
        except Exception:
            return None
    if isinstance(column.type, JSON):
        value = json.dumps(value)
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _quote(name):
    return '"' + str(name).replace('"', '""') + '"'


def upgrade(connection):
    """Bring an older database up to the current models without losing anything: add missing columns (with their
    defaults) and missing indexes. Names come only from Cerebra's own models, never from input. Runs in the caller's
    transaction, so a failure leaves the database as it was. Returns what changed, for the log."""
    changes = []
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or column.primary_key:
                continue
            kind = column.type.compile(dialect=connection.dialect)
            default = _literal(column)
            connection.execute(text(f"ALTER TABLE {_quote(table.name)} ADD COLUMN {_quote(column.name)} {kind}"
                                    + (f" DEFAULT {default}" if default is not None else "")))
            changes.append(f"added column {table.name}.{column.name}")
        indexes = {index["name"] for index in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in indexes:
                index.create(connection, checkfirst=True)
                changes.append(f"added index {index.name}")
    return changes

SCHEMA_VERSION = 1
class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.path.as_posix()}", connect_args={"check_same_thread":False,"timeout":30})
        @event.listens_for(self.engine, "connect")
        def pragmas(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    def init(self):
        # Version one is the initial additive migration. Refuse unknown future schemas.
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            changes = upgrade(connection)
        if changes:
            log.info("Database upgraded: %s", "; ".join(changes))
        with self.Session.begin() as session:
            version = session.get(Metadata, "schema_version")
            if version and version.value.get("version") != SCHEMA_VERSION:
                raise RuntimeError("Unsupported schema version. Back up the database before migration.")
            if not version:
                session.add(Metadata(key="schema_version", value={"version":SCHEMA_VERSION}))

    def close(self): self.engine.dispose()
