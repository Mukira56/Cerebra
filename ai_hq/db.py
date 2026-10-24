from pathlib import Path
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from .models import Base, Metadata

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
        with self.Session.begin() as session:
            version = session.get(Metadata, "schema_version")
            if version and version.value.get("version") != SCHEMA_VERSION:
                raise RuntimeError("Unsupported schema version. Back up the database before migration.")
            if not version:
                session.add(Metadata(key="schema_version", value={"version":SCHEMA_VERSION}))

    def close(self): self.engine.dispose()
