"""Models the owner signs in to with their own account, like Claude and ChatGPT: Google's Gemini CLI (a Google account,
with Google's free daily allowance) and Qwen Code (a Qwen account, with Qwen's free daily allowance).

They answer writing, research and checking turns only. Building code stays with Claude in its task worktree. Each turn runs
the tool's own headless mode (-p) with JSON output, in plan (read-only) approval mode, inside Cerebra's empty chat folder:
the tool sees the prompt Cerebra gives it, not the owner's projects. Signing in happens in the tool's own window (AI
accounts › Sign in); Cerebra never sees or stores the sign-in. When a tool isn't installed or isn't signed in, the turn
says so plainly and the caller falls back to the owner's chosen account.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .agents import AgentResult
from .processes import ProcessRunner
from .security import redact

PROVIDERS = {
    "gemini": {"label": "Gemini", "tool": "Gemini CLI", "account": "your Google account", "command": "gemini", "package": ("@google", "gemini-cli")},
    "qwen": {"label": "Qwen", "tool": "Qwen Code", "account": "your Qwen account", "command": "qwen", "package": ("@qwen-code", "qwen-code")},
}
ASK = "Follow the instructions above and reply with the answer only."
TIMEOUT = 300
SIGN_IN = re.compile(r"auth|login|log in|sign in|credential|unauthori[sz]ed|api key|GEMINI_API_KEY|oauth", re.I)
LIMIT = re.compile(r"quota|rate limit|429|resource.?exhausted|too many requests|daily limit", re.I)


def command(name):
    """How to start the tool: its Node script with node (npm's .cmd shim needs a shell, which Cerebra never uses), or the
    executable itself. None when it isn't installed."""
    found = shutil.which(PROVIDERS[name]["command"])
    if not found:
        return None
    path = Path(found)
    if path.suffix.lower() in {".cmd", ".ps1", ".bat"} or not path.suffix:
        scope, package = PROVIDERS[name]["package"]
        root = path.parent / "node_modules" / scope / package
        try:
            manifest = json.loads((root / "package.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        binary = manifest.get("bin")
        script = binary.get(PROVIDERS[name]["command"]) if isinstance(binary, dict) else binary
        node = shutil.which("node")
        if not script or not node or not (root / script).is_file():
            return None
        return [node, str(root / script)]
    return [str(path)]


def answer_text(output):
    """The answer from the tool's JSON output ({"response": ...}), or the plain text when it printed text."""
    text = str(output or "").strip()
    for match in reversed(list(re.finditer(r"\{.*\}", text, re.S))):
        try:
            data = json.loads(match.group(0))
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("response"), str):
            return data["response"]
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            raise ValueError(str(data["error"].get("message") or data["error"]))
    return text


def chat(name, prompt, workdir, model="", runner=None, allowed=True):
    """One read-only turn with a signed-in model. Returns an AgentResult; never raises for an expected problem."""
    info = PROVIDERS.get(name)
    if info is None:
        return AgentResult(False, "", error=f"Unknown model account: {name}")
    if not allowed:
        return AgentResult(False, "", error="AI agents are switched off. Turn them on in Settings > Agent permissions.")
    start = command(name)
    if start is None:
        return AgentResult(False, "", error=f"not installed: {info['tool']} isn't installed. Install it on Install tools, then sign in on AI accounts.")
    args = [*start, "-p", ASK, "-o", "json", "--approval-mode", "plan", *(["-m", model] if model else [])]
    directory = Path(workdir)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        result = (runner or ProcessRunner()).run(args, directory, TIMEOUT, None, prompt, redact_output=False)
    except (OSError, ValueError, RuntimeError) as exc:
        return AgentResult(False, "", error=redact(str(exc)))
    detail = (result.stderr or "") + "\n" + (result.stdout or "")
    if result.timed_out:
        return AgentResult(False, "", error=f"{info['tool']} took longer than {TIMEOUT // 60} minutes")
    try:
        text = answer_text(result.stdout) if result.exit_code == 0 else ""
    except ValueError as exc:
        detail, text = str(exc), ""
    if not text.strip():
        if LIMIT.search(detail):
            return AgentResult(False, "", error=f"usage limit: {info['tool']} has used today's free allowance; it resets tomorrow.")
        if SIGN_IN.search(detail):
            return AgentResult(False, "", error=f"not signed in: sign in to {info['tool']} with {info['account']} on AI accounts.")
        return AgentResult(False, "", error=redact(f"{info['tool']} gave no answer: {detail.strip()[-400:]}"))
    return AgentResult(True, redact(text.strip()))
