"""Local boundaries; Git worktrees are not an operating-system sandbox."""
from pathlib import Path
import re

SECRET_PATTERNS = [
    # Private key blocks, including output that was truncated before the END line.
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\Z)"), "[REDACTED PRIVATE KEY]"),
    # Credentials embedded in a URL: scheme://user:password@host. The match is anchored on the literal
    # "://" rather than on a scheme name, so a long run such as "a-a-a-..." is not rescanned from every
    # word boundary (that made the first version of this rule quadratic).
    (re.compile(r"(://)[^\s/@:]+:[^\s/@]+@"), r"\1[REDACTED]@"),
    # Provider tokens with distinctive prefixes. The prefix must include its delimiter so
    # ordinary identifiers such as "skills_directory_listing" are not mistaken for secrets.
    (re.compile(r"(?i)\b(?:sk-|gh[pousr]_|github_pat_|glpat-)[A-Za-z0-9_\-]{16,}"), "[REDACTED]"),
    (re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), "[REDACTED]"),
    # The lookbehind (not \b) allows a start only at the beginning of a base64url run, so input such as
    # "eyJ-eyJ-eyJ-..." is scanned once instead of once per "eyJ".
    (re.compile(r"(?<![A-Za-z0-9_\-])eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[REDACTED]"),
    # Authorization values: keep a recognised scheme name, but redact the credential after it.
    (re.compile(r"(?i)([\"']?authorization[\"']?\s*[:=]\s*[\"']?(?:(?:bearer|basic|token|digest|negotiate|ntlm)\s+)?)[^\r\n\"',}]+"), r"\1[REDACTED]"),
    # No whitespace is allowed before the optional closing quote: two adjacent \s* around an optional quote
    # can split a long run of spaces in many ways and backtrack quadratically (the original rule did).
    (re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret)[\"']?\s*[:=]\s*[\"']?)[^\s,\"'}]+"), r"\1[REDACTED]"),
]

def redact(value: str) -> str:
    value = str(value)
    for pattern, replacement in SECRET_PATTERNS:
        value = pattern.sub(replacement, value)
    return value

def canonical(path, roots, must_exist=True) -> Path:
    candidate = Path(path).expanduser().resolve(strict=must_exist)
    allowed = [Path(root).resolve() for root in roots]
    if not any(candidate == root or candidate.is_relative_to(root) for root in allowed):
        raise ValueError("Path is outside the explicitly authorized project directories")
    return candidate

def relative_paths(paths):
    for path in paths:
        normalized = path.replace("\\", "/")
        parts = normalized.split("/")
        aliases = [part.rstrip(" .").casefold() for part in parts]
        reserved = re.compile(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?$")
        if not normalized or normalized.startswith(("/", "-")) or ":" in normalized or ".." in parts or ".git" in aliases or any(re.fullmatch(r"git~[1-9][0-9]*", part, re.I) or reserved.fullmatch(part) for part in aliases) or any(part not in {".", ""} and part != part.rstrip(" .") for part in parts):
            raise ValueError("Allowed paths must be relative repository paths without traversal or .git")
    return paths
