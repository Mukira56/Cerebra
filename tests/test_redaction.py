"""Targeted tests for secret redaction (ai_hq.security.redact).

These cover formats the first implementation leaked (non-Bearer Authorization schemes,
URL credentials, private keys, several provider token formats), ordinary identifiers
it wrongly mangled (words that merely begin with "sk", "gho" or "ghp"), and hostile input
that makes a regular expression backtrack quadratically (redact() runs on every piece of
untrusted agent output, and the supervisor has a single worker thread).
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

from ai_hq.security import redact

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("header, credential", [
    ("Authorization: Bearer abcdef1234567890abcdef", "abcdef1234567890abcdef"),
    ("Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ1", "dXNlcjpwYXNzd29yZDEyMzQ1"),
    ("Authorization: Token abcdef1234567890abcdef", "abcdef1234567890abcdef"),
    ("Authorization: Digest response=abcdef1234567890", "abcdef1234567890"),
    ("Authorization: CustomScheme abcdef1234567890", "abcdef1234567890"),
    ('{"Authorization": "Basic dXNlcjpwYXNzd29yZDEyMzQ1"}', "dXNlcjpwYXNzd29yZDEyMzQ1"),
])
def test_authorization_values_never_leak_the_credential(header, credential):
    cleaned = redact(header)
    assert credential not in cleaned
    assert "[REDACTED]" in cleaned


def test_known_authorization_scheme_name_is_kept_for_readability():
    assert redact("Authorization: Basic dXNlcjpwYXNz") == "Authorization: Basic [REDACTED]"
    assert redact("Authorization: Bearer abc123def456") == "Authorization: Bearer [REDACTED]"


@pytest.mark.parametrize("secret", [
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "gho_abcdefghijklmnopqrstuvwxyz0123456789",
    "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz",
    "glpat-abcdefghijklmnopqrstu",
    "sk-proj-abcdefghijklmnop1234",
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
    "AKIAIOSFODNN7EXAMPLE",
    "xoxb-123456789012-abcdefghijklmnop",
    "AIza" + "A" * 35,
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuvwxyz",
])
def test_common_provider_token_formats_are_redacted(secret):
    cleaned = redact(f"error while calling the service with {secret} attached")
    assert secret not in cleaned
    assert "[REDACTED]" in cleaned


def test_url_credentials_are_redacted_but_host_and_path_survive():
    cleaned = redact("git clone https://user:hunter2pass@example.com/owner/repo.git")
    assert "hunter2pass" not in cleaned
    assert "example.com/owner/repo.git" in cleaned


def test_private_key_blocks_are_redacted_even_when_truncated():
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7"
    complete = f"before\n-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----\nafter"
    cleaned = redact(complete)
    assert body not in cleaned and cleaned.startswith("before") and cleaned.endswith("after")
    truncated = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n{body}"
    assert body not in redact(truncated)


@pytest.mark.parametrize("text", [
    "ghost_process_cleanup_handles finished",
    "loading skills_directory_listing_module now",
    "tests/test_glpat_parser_module_checks.py::test_ok PASSED",
    "ask-abcdefghijklmnopqrstuvwxyz is a normal word sequence",
    "git clone ssh://git@github.com/owner/repo.git",
    "GET http://127.0.0.1:8765/health -> 200",
    "see https://example.com:443/path for details",
    "max_tokens: 100 and token_count = 5",
    "The quick brown fox: token count, password policy and secret garden.",
])
def test_ordinary_text_is_not_mangled(text):
    assert redact(text) == text


def test_redaction_is_idempotent():
    sample = "\n".join([
        "Authorization: Basic dXNlcjpwYXNzd29yZDEyMzQ1",
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnop1234",
        "https://user:hunter2pass@example.com/repo.git",
        "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----",
        '{"password": "example-secret"}',
    ])
    once = redact(sample)
    assert redact(once) == once


def test_redaction_of_large_output_is_not_pathological():
    # Output is bounded to 256 KiB by default; make sure no pattern backtracks badly on
    # adversarial-looking input (many unterminated markers, long token-like runs).
    chunk = ("-----BEGIN PRIVATE KEY-----\n" + "A" * 200 + "\n"
             + "sk-" + "a" * 5000 + "\n" + "Authorization: " + "x" * 3000 + "\n")
    text = chunk * 40
    started = time.monotonic()
    cleaned = redact(text)
    assert time.monotonic() - started < 10
    assert "A" * 200 not in cleaned


@pytest.mark.parametrize("text", [
    "password: hunter2pass",
    "password = hunter2pass",
    '{"password": "hunter2pass"}',
    '"password" : "hunter2pass"',
    "API_KEY=hunter2pass",
    "api-key: hunter2pass",
    "access_token='hunter2pass'",
    "refresh_token : hunter2pass",
    "secret=hunter2pass&other=1",
])
def test_assignment_style_secrets_are_redacted(text):
    assert "hunter2pass" not in redact(text)


@pytest.mark.parametrize("url, secret", [
    ("postgresql://admin:s3cr3tpw@db.internal:5432/app", "s3cr3tpw"),
    ("git+ssh://deploy:tokenvalue123@example.com/repo.git", "tokenvalue123"),
    ("https://user:pa:ss:word@example.com/", "pa:ss:word"),
])
def test_url_credentials_in_assorted_schemes_are_redacted(url, secret):
    cleaned = redact(f"connecting to {url} now")
    assert secret not in cleaned
    assert cleaned.startswith("connecting to ") and cleaned.endswith(" now") and "@" in cleaned


_N = 262_144  # the default per-run output bound is 256 KiB
HOSTILE_INPUTS = {
    "dash_separated_words": "a-" * (_N // 2),
    "dot_separated_words": "a." * (_N // 2),
    "plus_separated_words": "a+" * (_N // 2),
    "jwt_prefix_repeated": "eyJ-" * (_N // 4),
    "keyword_then_spaces": "token" + " " * _N,
    "keyword_then_spaces_then_text": "password" + " " * _N + "x",
    "keyword_quote_then_spaces": 'secret"' + " " * _N,
    "authorization_then_spaces": "authorization" + " " * _N,
    "url_userinfo_without_at": "x://u:" + "p" * _N,
    "scheme_separator_repeated": "a://" * (_N // 4),
    "private_key_header_repeated": "-----BEGIN PRIVATE KEY-----\n" * (_N // 28),
    "private_key_header_then_run": "-----BEGIN " + "A " * (_N // 2),
    "token_prefixes_repeated": "sk-" * (_N // 6) + "ghp_" * (_N // 8),
    "ordinary_prose_with_keywords": "The quick brown fox: token count, password policy and secret garden.\n" * (_N // 68),
}

_TIMING_CHILD = (
    "import sys, time\n"
    "from ai_hq.security import redact\n"
    "data = sys.stdin.read()\n"
    "started = time.perf_counter()\n"
    "redact(data)\n"
    "print(time.perf_counter() - started)\n"
)


@pytest.mark.parametrize("name", sorted(HOSTILE_INPUTS))
def test_redaction_stays_fast_on_hostile_input(name):
    # Each case runs in its own process so a catastrophic regression fails this test with a clear
    # name instead of hanging the whole suite. A healthy run takes tens of milliseconds; a pattern
    # that backtracks quadratically needs minutes at this size.
    try:
        result = subprocess.run([sys.executable, "-c", _TIMING_CHILD], input=HOSTILE_INPUTS[name],
                                capture_output=True, text=True, cwd=REPO_ROOT, timeout=60)
    except subprocess.TimeoutExpired:
        pytest.fail(f"redact() needed more than 60 s for the {name} input")
    assert result.returncode == 0, result.stderr
    assert float(result.stdout) < 5.0
