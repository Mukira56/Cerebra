"""Non-destructive Git worktrees and explicitly approved fast-forward integration."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import threading
import time
import uuid

from .agents import _allows
from .processes import ProcessRunner
from .security import canonical, redact, relative_paths


class GitError(RuntimeError):
    pass


class GitManager:
    _locks: dict[str, threading.RLock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, data_dir, runner=None):
        self.data_dir = Path(data_dir).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.worktrees_dir = self.data_dir / "worktrees"
        self.lock_dir = self.data_dir / "locks"
        self.empty_hooks = self.data_dir / "disabled-git-hooks"
        for directory in (self.worktrees_dir, self.lock_dir, self.empty_hooks):
            directory.mkdir(parents=True, exist_ok=True)
        self.runner = runner or ProcessRunner()
        self.executable = shutil.which("git")
        if not self.executable:
            raise GitError("Git executable is unavailable")

    def _git(self, repo, *args, check=True, timeout=60):
        filters = []
        if any(argument in {"add", "commit", "merge", "worktree", "checkout", "diff", "status"} for argument in args):
            # Configured clean/smudge/process filters are arbitrary executables too.
            configured = self._git(repo, "config", "--name-only", "--get-regexp", r"^filter\..*\.(clean|smudge|process|required)$", check=False)
            for key in configured.stdout.splitlines():
                if re.fullmatch(r"filter\..*\.(clean|smudge|process|required)", key):
                    filters += ["-c", key + ("=false" if key.endswith(".required") else "=")]
        result = self.runner.run([self.executable, "-c", f"core.hooksPath={self.empty_hooks}",
                                  "-c", "commit.gpgsign=false", "-c", "core.fsmonitor=false",
                                  "-c", "protocol.ext.allow=never", "-c", "protocol.file.allow=never",
                                  "-c", "core.pager=cat", "-c", "diff.external=", *filters, *map(str, args)], repo, timeout,
                                 redact_output=False)
        # Output is parsed unredacted (a redacted path or SHA would be corrupted); redact what leaves here.
        if result.timed_out or result.cancelled or (check and result.exit_code != 0):
            raise GitError(redact((result.stderr or result.stdout or "Git command failed").strip()))
        if result.output_truncated:
            raise GitError("Git output exceeded the configured limit; operation cannot be validated")
        return result

    def _root(self, repo):
        directory = Path(repo).resolve(strict=True)
        root = Path(self._git(directory, "rev-parse", "--show-toplevel").stdout.strip()).resolve(strict=True)
        if directory != root:
            raise GitError("Register the repository root, rather than a repository subdirectory")
        return root

    @contextmanager
    def _lock(self, repo):
        common = self._git(repo, "rev-parse", "--git-common-dir").stdout.strip()
        common_path = (Path(repo) / common).resolve()
        key = hashlib.sha256(str(common_path).casefold().encode()).hexdigest()
        with self._locks_guard:
            local = self._locks.setdefault(key, threading.RLock())
        with local:
            with (self.lock_dir / f"{key}.lock").open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                deadline = time.monotonic() + 10
                while True:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise GitError("Repository is busy with another managed operation")
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def inspect_repository(self, path):
        root = self._root(path)
        head = self._git(root, "rev-parse", "--verify", "HEAD").stdout.strip()
        current = self._git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip() or None
        remote_default = self._git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD", check=False).stdout.strip()
        configured = self._git(root, "config", "--get", "init.defaultBranch", check=False).stdout.strip()
        default = remote_default.removeprefix("origin/") if remote_default else configured or current
        if default:
            exists = self._git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{default}", check=False)
            if exists.exit_code != 0 and not remote_default:
                default = current
        return {"path": str(root), "head": head, "current_branch": current,
                "default_branch": default, "dirty": bool(self._git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout),
                "bare": False}

    register = inspect_repository
    info = inspect_repository

    def create_worktree(self, repo, task_id, base=None):
        root = self._root(repo)
        if not str(task_id) or len(str(task_id)) > 200:
            raise GitError("Task identifier is invalid")
        with self._lock(root):
            baseline = self._git(root, "rev-parse", "--verify", f"{base or 'HEAD'}^{{commit}}").stdout.strip()
            base_branch = self._git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip() or None
            token = re.sub(r"[^A-Za-z0-9_-]+", "-", str(task_id)).strip("-")[:64] or "task"
            repository_key = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:12]
            suffix = uuid.uuid4().hex[:10]
            branch = f"ai-hq/{token}-{suffix}"
            directory = self.worktrees_dir / repository_key / f"{token}-{suffix}"
            directory.parent.mkdir(parents=True, exist_ok=True)
            canonical(directory, [self.worktrees_dir], must_exist=False)
            self._git(root, "worktree", "add", "-b", branch, str(directory), baseline)
            return {"path": str(directory), "branch": branch, "base_commit": baseline,
                    "repository": str(root), "base_branch": base_branch}

    def _safe_changed_path(self, root, name):
        if not name:
            raise GitError("Empty changed repository path")
        relative_paths([name])
        relative = PurePosixPath(name.replace("\\", "/"))
        if any(part.casefold() == ".git" for part in relative.parts):
            raise GitError("Git metadata paths are not valid task changes")
        cursor = root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.exists() or cursor.is_symlink():
                info = cursor.lstat()
                if cursor.is_symlink() or (getattr(info, "st_file_attributes", 0) & 0x400):
                    raise GitError("Changed paths may not contain symlinks or Windows reparse points")
                if not stat.S_ISREG(info.st_mode) and not stat.S_ISDIR(info.st_mode):
                    raise GitError("Changed paths must be ordinary files or directories")
        canonical(root / Path(*relative.parts), [root], must_exist=False)

    def _new_file_diff(self, root, path):
        file = root / Path(*PurePosixPath(path).parts)
        if not file.is_file():
            raise GitError("Untracked changes must be ordinary files")
        # Never read an arbitrarily large model-created file into memory.
        with file.open("rb") as stream:
            content = stream.read(self.runner.max_output_bytes + 1)
        if b"\x00" in content:
            return f"\nUntracked binary file: {path}\n"
        if len(content) > self.runner.max_output_bytes:
            raise GitError("An untracked text file exceeds the configured inspection limit")
        return f"\n--- /dev/null\n+++ b/{path}\n" + content.decode("utf-8", errors="replace")

    def snapshot(self, workdir):
        root = self._root(workdir)
        with self._lock(root):
            status = self._git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
            changed = self._git(root, "diff", "--no-renames", "--name-only", "-z", "HEAD", "--").stdout.split("\x00")
            untracked = [path for path in self._git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\x00") if path]
            paths = sorted(set(path for path in changed + untracked if path))
            for path in paths:
                self._safe_changed_path(root, path)
            diff = self._git(root, "diff", "--no-ext-diff", "--no-textconv", "HEAD", "--").stdout
            for path in untracked:
                diff += self._new_file_diff(root, path)
                if len(diff.encode("utf-8")) > self.runner.max_output_bytes:
                    raise GitError("Diff is too large to inspect safely")
            return {"diff": redact(diff), "status": redact(status), "untracked": untracked, "changed_paths": paths}

    def candidate_snapshot(self, workdir, base_commit):
        """Include agent-created commits as well as staged, unstaged and new files."""
        root = self._root(workdir)
        with self._lock(root):
            baseline = self._git(root, "rev-parse", "--verify", f"{base_commit}^{{commit}}").stdout.strip()
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()
            if self._git(root, "merge-base", "--is-ancestor", baseline, head, check=False).exit_code != 0:
                raise GitError("Candidate history does not descend from the approved baseline")
            status = self._git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout
            names = self._git(root, "diff", "--no-renames", "--name-only", "-z", baseline, "--").stdout.split("\x00")
            untracked = [p for p in self._git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\x00") if p]
            paths = sorted(set(p for p in names + untracked if p))
            for path in paths:
                self._safe_changed_path(root, path)
            # ls-tree catches a symlink committed by an agent then removed in its working copy.
            for entry in self._git(root, "ls-tree", "-r", "-z", head).stdout.split("\x00"):
                if entry.startswith(("120000 ", "160000 ")):
                    raise GitError("Candidate symlinks and submodules require manual inspection")
            diff = self._git(root, "diff", "--no-ext-diff", "--no-textconv", baseline, "--").stdout
            for path in untracked:
                diff += self._new_file_diff(root, path)
                if len(diff.encode("utf-8")) > self.runner.max_output_bytes:
                    raise GitError("Candidate diff is too large to inspect safely")
            return {"diff": redact(diff), "status": redact(status), "untracked": untracked,
                    "changed_paths": paths, "head": head, "base_commit": baseline}

    def commit(self, workdir, message, allowed_paths=None):
        root = self._root(workdir)
        scopes = relative_paths(allowed_paths if allowed_paths is not None else ["."])
        if not message or len(message) > 1000 or "\x00" in message:
            raise GitError("Commit message is invalid")
        with self._lock(root):
            names = self._git(root, "diff", "--no-renames", "--name-only", "-z", "HEAD", "--").stdout.split("\x00")
            names += self._git(root, "ls-files", "--others", "--exclude-standard", "-z").stdout.split("\x00")
            paths = sorted(set(path for path in names if path))
            for path in paths:
                self._safe_changed_path(root, path)
                if not _allows(path, scopes):
                    raise GitError(redact(f"Changed path is outside this task's allowed paths: {path}"))
            if paths:
                # Explicit pathspecs ensure a filename cannot inject a Git option.
                self._git(root, "add", "--", *paths)
                self._git(root, "-c", "user.name=Cerebra", "-c", "user.email=ai-hq@localhost", "commit", "--no-verify", "-m", message)
            return {"commit": self._git(root, "rev-parse", "HEAD").stdout.strip(), "changed": bool(paths), "changed_paths": paths}

    def integrate(self, repo, branch, expected_base=None, approved=False, expected_branch=None, expected_candidate=None):
        if approved is not True:
            raise GitError("Human approval is required before branch integration")
        root = self._root(repo)
        if not isinstance(branch, str) or not branch.startswith("ai-hq/") or "\x00" in branch or len(branch) > 250:
            raise GitError("Only managed task branches can be integrated")
        with self._lock(root):
            if self._git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout:
                raise GitError("Integration refused: registered repository has user changes")
            head = self._git(root, "rev-parse", "HEAD").stdout.strip()
            current_branch = self._git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False).stdout.strip() or None
            if expected_branch and current_branch != expected_branch:
                raise GitError("Integration refused: target branch differs from the approved branch")
            if expected_base and head != expected_base:
                raise GitError("Integration refused: target branch moved since task creation")
            target = self._git(root, "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}").stdout.strip()
            if expected_candidate and target != expected_candidate:
                raise GitError("Integration refused: candidate changed after approval was requested")
            if self._git(root, "merge-base", "--is-ancestor", head, target, check=False).exit_code != 0:
                raise GitError("Integration refused: branches diverged; manual conflict resolution is required")
            # Check paths again, including tracked symlinks materialized by checkout.
            changes = [p for p in self._git(root, "diff", "--no-renames", "--name-only", "-z", head, target, "--").stdout.split("\x00") if p]
            if changes:
                index_entries = self._git(root, "ls-files", "-v", "-z", "--", *changes).stdout.split("\x00")
                if any(entry and (entry[0] == "S" or entry[0].islower()) for entry in index_entries):
                    raise GitError("Integration refused: assume-unchanged or skip-worktree index flags can hide local user changes")
            for path in changes:
                self._safe_changed_path(root, path)
                if (root / Path(*PurePosixPath(path).parts)).exists():
                    existing = self._git(root, "ls-tree", "HEAD", "--", path).stdout
                    if not existing or existing.startswith("040000 "):
                        raise GitError("Integration refused: a changed path would overwrite an untracked or ignored user path")
            entries = self._git(root, "ls-tree", "-r", "-z", target).stdout.split("\x00")
            for entry in entries:
                if entry.startswith("120000 ") or entry.startswith("160000 "):
                    raise GitError("Integration refused: symlinks and submodules require manual inspection")
            self._git(root, "merge", "--ff-only", "--no-edit", target)
            return {"commit": self._git(root, "rev-parse", "HEAD").stdout.strip(), "branch": branch,
                    "changed_paths": changes}

    merge = integrate
