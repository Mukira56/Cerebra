"""Secrets the user gives Cerebra (Gmail sign-in, Telegram bot token), encrypted with Windows DPAPI.

DPAPI ties the ciphertext to the user's Windows account: another account, or a copy of the database on
another computer, cannot decrypt it. Secrets are never returned by the API, written to logs, or put in
a prompt; only the module that talks to the service decrypts them, just before use.
"""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

PREFIX = "dpapi:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _call(function, data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Protected secrets need Windows (DPAPI)")
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


def protect(value: str) -> str:
    crypt = ctypes.windll.crypt32
    return PREFIX + base64.b64encode(_call(lambda *a: crypt.CryptProtectData(a[0], "Cerebra", *a[2:]), value.encode("utf-8"))).decode("ascii")


def unprotect(value: str) -> str:
    if not value or not value.startswith(PREFIX):
        raise ValueError("Not a protected secret")
    crypt = ctypes.windll.crypt32
    return _call(lambda *a: crypt.CryptUnprotectData(a[0], None, *a[2:]), base64.b64decode(value[len(PREFIX):])).decode("utf-8")
