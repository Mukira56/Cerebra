import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from ai_hq.db import Database
from ai_hq.models import Project, Task, Metadata
from ai_hq.security import canonical, redact, relative_paths
from ai_hq.schemas import ProjectCreate, TaskCreate

def test_persistence_and_foreign_keys(tmp_path):
    db = Database(tmp_path/"hq.db"); db.init()
    with db.Session.begin() as session:
        project=Project(name="Local",path=str(tmp_path),default_branch="trunk")
        session.add(project);session.flush()
        session.add(Task(project_id=project.id,description="Persist this task"))
    db.close()
    reopened=Database(tmp_path/"hq.db");reopened.init()
    with reopened.Session() as session:
        assert session.scalar(select(Task)).description == "Persist this task"
        assert session.get(Metadata,"schema_version").value == {"version":1}
    with pytest.raises(IntegrityError):
        with reopened.Session.begin() as session: session.add(Task(project_id="missing",description="Bad FK"))
    reopened.close()

def test_canonical_rejects_traversal(tmp_path):
    root=tmp_path/"repo";root.mkdir()
    assert canonical(root,[root]) == root
    with pytest.raises(ValueError): canonical(root/"..",[root])
    with pytest.raises(ValueError): relative_paths(["../private"])
    with pytest.raises(ValueError): relative_paths([".git/config"])
    with pytest.raises(ValueError): relative_paths([".GIT/config"])
    with pytest.raises(ValueError): relative_paths([".git./config"])
    with pytest.raises(ValueError): relative_paths(["GIT~1/config"])
    with pytest.raises(ValueError): relative_paths(["aux.txt"])

def test_redaction_and_strict_records():
    assert "abcdef0123456789" not in redact("api_key=abcdef0123456789")
    assert "fixture-only-token-123456789" not in redact('{"authorization": "Bearer fixture-only-token-123456789"}')
    with pytest.raises(ValueError): ProjectCreate(name="No consent",path="x")
    with pytest.raises(ValueError): TaskCreate(project_id="x",description="Valid task",allowed_paths=["C:/Users"])
    with pytest.raises(ValueError): ProjectCreate(name="Private",authorize=True,test_commands=[["tool","--password","fixture-password"]])

def test_unknown_schema_refused(tmp_path):
    db=Database(tmp_path/"db");db.init()
    with db.Session.begin() as session: session.get(Metadata,"schema_version").value={"version":99}
    with pytest.raises(RuntimeError): db.init()
    db.close()
