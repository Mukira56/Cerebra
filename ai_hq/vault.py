"""Secrets the user gives Cerebra (Gmail sign-in, Telegram bot token, Stripe and platform keys), kept by the system's own
secret store: Windows DPAPI, the macOS Keychain, or the Secret Service (GNOME Keyring, KWallet) on Linux.

DPAPI ties the ciphertext to the user's Windows account: another account, or a copy of the database on another computer,
cannot decrypt it. On macOS and Linux the secret itself lives in the keychain and the database keeps only a reference to
it, so a copy of the database holds no secret at all. Secrets are never returned by the API, written to logs, or put in a
prompt; only the module that talks to the service decrypts them, just before use. Without a secret store (a Linux machine
with no Secret Service), saving a secret fails with a clear message instead of keeping it in plain text.
"""
from __future__ import annotations

import base64
import ctypes
import os
import shutil
import subprocess
import sys
import uuid

PREFIX = "dpapi:"
KEYCHAIN = "keychain:"
SERVICE = "Cerebra"


class VaultError(OSError, ValueError):
    """The system secret store is missing, locked or refused: shown to the owner as a plain message (a 400, not a crash)."""


# ---- Windows: DPAPI ----
def _call(function, data: bytes) -> bytes:
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    source = _Blob(len(data), ctypes.cast(ctypes.create_string_buffer(data, len(data)), ctypes.POINTER(ctypes.c_char)))
    target = _Blob()
    entropy = b"Cerebra secret v1"
    extra = _Blob(len(entropy), ctypes.cast(ctypes.create_string_buffer(entropy, len(entropy)), ctypes.POINTER(ctypes.c_char)))
    if not function(ctypes.byref(source), None, ctypes.byref(extra), None, None, 0x1, ctypes.byref(target)):  # UI_FORBIDDEN
        raise OSError("Windows could not protect or read this secret")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(target.pbData)


def _dpapi_protect(value: str) -> str:
    crypt = ctypes.windll.crypt32
    return PREFIX + base64.b64encode(_call(lambda *a: crypt.CryptProtectData(a[0], "Cerebra", *a[2:]), value.encode("utf-8"))).decode("ascii")


def _dpapi_unprotect(value: str) -> str:
    if not _windows():
        raise VaultError("This secret was saved on Windows and can only be read there. Enter it again on this computer.")
    crypt = ctypes.windll.crypt32
    return _call(lambda *a: crypt.CryptUnprotectData(a[0], None, *a[2:]), base64.b64decode(value[len(PREFIX):])).decode("utf-8")


# ---- macOS: the login Keychain, through the Security framework (no secret ever on a command line) ----
class MacKeychain:
    def __init__(self, library=None):
        self.lib = library or ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Security.framework/Security")

    def store(self, account: str, secret: str):
        service, name, data = SERVICE.encode(), account.encode(), secret.encode("utf-8")
        status = self.lib.SecKeychainAddGenericPassword(None, len(service), service, len(name), name, len(data), data, None)
        if status:
            raise VaultError(f"The macOS Keychain could not save this secret (error {status})")

    def load(self, account: str) -> str:
        service, name = SERVICE.encode(), account.encode()
        length, data = ctypes.c_uint32(), ctypes.c_void_p()
        status = self.lib.SecKeychainFindGenericPassword(None, len(service), service, len(name), name, ctypes.byref(length), ctypes.byref(data), None)
        if status:
            raise VaultError(f"The macOS Keychain has no such Cerebra secret (error {status}). Enter it again.")
        try:
            return ctypes.string_at(data, length.value).decode("utf-8")
        finally:
            self.lib.SecKeychainItemFreeContent(None, data)


# ---- Linux: the Secret Service, through libsecret's secret-tool (the secret goes in on stdin) ----
class SecretService:
    def __init__(self, tool=None, run=subprocess.run):
        self.tool, self.run = tool or shutil.which("secret-tool"), run

    def _require(self):
        if not self.tool:
            raise VaultError("Saving secrets on Linux needs the Secret Service (GNOME Keyring or KWallet) and secret-tool: "
                               "install libsecret-tools (Debian, Ubuntu) or libsecret (Fedora, Arch), then try again.")

    def store(self, account: str, secret: str):
        self._require()
        result = self.run([self.tool, "store", f"--label={SERVICE} secret", "service", SERVICE, "account", account],
                          input=secret, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise VaultError(f"The Secret Service could not save this secret: {(result.stderr or '').strip()[:200] or 'is the keyring unlocked?'}")

    def load(self, account: str) -> str:
        self._require()
        result = self.run([self.tool, "lookup", "service", SERVICE, "account", account], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise VaultError("The Secret Service has no such Cerebra secret, or the keyring is locked. Unlock it, or enter the secret again.")
        return result.stdout


_store = None


def keychain():
    """The system secret store for macOS or Linux (made once; tests replace it)."""
    global _store
    if _store is None:
        _store = MacKeychain() if sys.platform == "darwin" else SecretService()
    return _store


def _windows():
    return os.name == "nt"


def protect(value: str) -> str:
    if _windows():
        return _dpapi_protect(value)
    account = uuid.uuid4().hex
    keychain().store(account, value)
    return KEYCHAIN + account


def unprotect(value: str) -> str:
    if value and value.startswith(PREFIX):
        return _dpapi_unprotect(value)
    if value and value.startswith(KEYCHAIN):
        return keychain().load(value[len(KEYCHAIN):])
    raise ValueError("Not a protected secret")
