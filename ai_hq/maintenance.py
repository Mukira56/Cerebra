"""Retire simulated demo records left by versions before 0.5.0. Runs only when the user asks."""
from __future__ import annotations

from datetime import datetime
import os
import stat
from pathlib import Path
import shutil
import sqlite3
import subprocess

from sqlalchemy import select

from .models import Approval, BusinessJob, Dependency, Event, Finding, PlanItem, Project, Review, Run, Task, Worktree

DELETABLE = {"FAILED", "CANCELLED", "BLOCKED"}


def _inside(path, root):
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except OSError:
        return False


def _make_writable(function, path, _error):
    # Git marks object files read-only, which stops Windows from deleting them.
    os.chmod(path, stat.S_IWRITE)
    function(path)


def preview(db, data_dir):
    with db.Session() as session:
        tasks = session.scalars(select(Task).where(Task.mode == "mock")).all()
        removable = _removable_projects(session, data_dir, {task.id for task in tasks})
        return {"tasks": len(tasks), "projects": [project.name for project in removable]}


def _removable_projects(session, data_dir, removed_tasks):
    projects = []
    for project in session.scalars(select(Project)).all():
        remaining = [task for task in session.scalars(select(Task).where(Task.project_id == project.id)).all() if task.id not in removed_tasks]
        demo_folder = Path(project.path).name.startswith("demo-") and _inside(project.path, Path(data_dir) / "projects")
        if not remaining and project.mode == "mock" and demo_folder:
            projects.append(project)
    return projects


def _backup(db, data_dir, label):
    backups = Path(data_dir) / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"hq-before-{label}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    source = sqlite3.connect(db.path)
    try:
        with sqlite3.connect(backup) as target:
            source.backup(target)
    finally:
        source.close()
    return backup


def delete_tasks(db, data_dir, task_ids):
    """Delete failed, cancelled or paused tasks the owner chose, after backing up the database.
    Their records and working copies go; their Git branches stay in the project, and Activity keeps the history."""
    data_dir, task_ids = Path(data_dir), list(dict.fromkeys(task_ids))
    with db.Session() as session:
        tasks = [session.get(Task, task_id) for task_id in task_ids]
        if any(task is None for task in tasks):
            raise LookupError("Task not found")
        for task in tasks:
            if task.state not in DELETABLE or (task.results or {}).get("integration_in_progress"):
                raise ValueError(f"Task {task.id[:8]} is {task.state.replace('_', ' ').lower()}; only failed, cancelled or paused tasks can be deleted")
        dependents = session.scalars(select(Dependency).where(Dependency.depends_on.in_(task_ids), Dependency.task_id.not_in(task_ids))).all()
        if dependents:
            raise ValueError(f"Task {dependents[0].task_id[:8]} depends on task {dependents[0].depends_on[:8]}; delete them together or cancel it first")
    backup = _backup(db, data_dir, "deleting-tasks")
    folders = []
    with db.Session.begin() as session:
        tasks = [session.get(Task, task_id) for task_id in task_ids]
        for task in tasks:
            for worktree in session.scalars(select(Worktree).where(Worktree.task_id == task.id)).all():
                folders.append(worktree.path)
                session.delete(worktree)
            for review in session.scalars(select(Review).where(Review.task_id == task.id)).all():
                for finding in session.scalars(select(Finding).where(Finding.review_id == review.id)).all():
                    session.delete(finding)
                session.delete(review)
            for model in (Run, Approval):
                for row in session.scalars(select(model).where(model.task_id == task.id)).all():
                    session.delete(row)
            for row in session.scalars(select(Event).where(Event.task_id == task.id)).all():
                row.task_id = None  # Activity keeps the history
            for row in session.scalars(select(Dependency).where((Dependency.task_id == task.id) | (Dependency.depends_on == task.id))).all():
                session.delete(row)
            for row in session.scalars(select(BusinessJob).where(BusinessJob.task_id == task.id)).all():
                row.task_id = None
            for row in session.scalars(select(PlanItem).where(PlanItem.task_id == task.id)).all():
                row.task_id, row.status = None, "proposed"  # the plan item can get a new task later
            if task.worktree_path:
                folders.append(task.worktree_path)
        session.flush()
        projects = {task.project_id for task in tasks}
        for task in tasks:
            session.add(Event(kind="maintenance", message=f"Owner deleted task {task.id[:8]}: {task.description[:120]}", data={"backup": str(backup), "branch": task.branch}))
            session.delete(task)
        session.flush()
        paths = [session.get(Project, identifier).path for identifier in projects if session.get(Project, identifier)]
    removed = 0
    for folder in dict.fromkeys(folders):
        # Only ever delete inside Cerebra's own worktrees folder.
        if folder and Path(folder).is_dir() and _inside(folder, data_dir / "worktrees") and not Path(folder).is_symlink():
            shutil.rmtree(folder, onexc=_make_writable)
            removed += 1
    git = shutil.which("git")
    for path in paths:  # the projects forget the deleted working copies; branches are kept
        if git and Path(path).is_dir():
            subprocess.run([git, "worktree", "prune"], cwd=path, capture_output=True, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"deleted": task_ids, "folders_removed": removed, "backup": str(backup)}


def remove_demo_data(db, data_dir):
    """Delete simulated tasks and demo-only projects, after backing up the database."""
    data_dir = Path(data_dir)
    backups = data_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    backup = backups / f"hq-before-demo-cleanup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite3"
    source = sqlite3.connect(db.path)
    try:
        with sqlite3.connect(backup) as target:
            source.backup(target)
    finally:
        source.close()
    folders = []
    with db.Session.begin() as session:
        tasks = session.scalars(select(Task).where(Task.mode == "mock")).all()
        task_ids = {task.id for task in tasks}
        projects = _removable_projects(session, data_dir, task_ids)
        for task in tasks:
            for worktree in session.scalars(select(Worktree).where(Worktree.task_id == task.id)).all():
                folders.append(worktree.path)
                session.delete(worktree)
            for review in session.scalars(select(Review).where(Review.task_id == task.id)).all():
                for finding in session.scalars(select(Finding).where(Finding.review_id == review.id)).all():
                    session.delete(finding)
                session.delete(review)
            for model in (Run, Approval, Event):
                for row in session.scalars(select(model).where(model.task_id == task.id)).all():
                    session.delete(row)
            for row in session.scalars(select(Dependency).where((Dependency.task_id == task.id) | (Dependency.depends_on == task.id))).all():
                session.delete(row)
            if task.worktree_path:
                folders.append(task.worktree_path)
        session.flush()
        for task in tasks:
            session.delete(task)
        session.flush()
        for project in projects:
            folders.append(project.path)
            session.delete(project)
        # Remaining projects are real work; the old per-project mode flag no longer means anything.
        for project in session.scalars(select(Project)).all():
            project.mode = "live"
        session.add(Event(kind="maintenance", message=f"Removed {len(tasks)} simulated demo tasks and {len(projects)} demo projects; database backed up first",
                          data={"backup": str(backup), "projects": [project.name for project in projects]}))
    removed = 0
    affected = {project.path for project in projects}
    for folder in dict.fromkeys(folders):
        # Only ever delete inside AI HQ's own projects/worktrees folders.
        if folder and Path(folder).is_dir() and (_inside(folder, data_dir / "worktrees") or _inside(folder, data_dir / "projects")) and not Path(folder).is_symlink():
            shutil.rmtree(folder, onexc=_make_writable)
            removed += 1
    # Kept repositories forget the deleted task worktrees.
    git = shutil.which("git")
    with db.Session() as session:
        for project in session.scalars(select(Project)).all():
            if git and project.path not in affected and Path(project.path).is_dir():
                subprocess.run([git, "worktree", "prune"], cwd=project.path, capture_output=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"tasks_removed": len(task_ids), "projects_removed": [project.name for project in projects], "folders_removed": removed, "backup": str(backup)}
