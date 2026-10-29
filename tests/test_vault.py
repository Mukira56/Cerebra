"""Secrets on Windows (DPAPI), macOS (Keychain) and Linux (Secret Service). The macOS and Linux stores are simulated:
the same calls Cerebra makes, answered by a fake library and a fake secret-tool."""
import ctypes
import os
import subprocess

import pytest

from ai_hq import vault


@pytest.mark.skipif(os.name != "nt", reason="DPAPI is Windows-only")
def test_windows_secrets_round_trip_and_hold_no_plain_text():
    sealed = vault.protect("sk_test_123")
    assert sealed.startswith(vault.PREFIX) and "sk_test_123" not in sealed and vault.unprotect(sealed) == "sk_test_123"


class FakeSecurity:
    """The three Security.framework calls Cerebra uses, over a dictionary."""
    def __init__(self):
        self.items, self.freed = {}, 0

    def SecKeychainAddGenericPassword(self, keychain, service_length, service, name_length, name, length, data, item):
        if (service, name) in self.items:
            return -25299  # errSecDuplicateItem
        self.items[(service, name)] = ctypes.create_string_buffer(data, length)
        return 0

    def SecKeychainFindGenericPassword(self, keychain, service_length, service, name_length, name, length, data, item):
        found = self.items.get((service, name))
        if found is None:
            return -25300  # errSecItemNotFound
        ctypes.cast(length, ctypes.POINTER(ctypes.c_uint32)).contents.value = len(found)
        ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p)).contents.value = ctypes.addressof(found)
        return 0

    def SecKeychainItemFreeContent(self, attributes, data):
        self.freed += 1
        return 0


def off_windows(monkeypatch, store):
    monkeypatch.setattr(vault, "_windows", lambda: False)
    monkeypatch.setattr(vault, "_store", store)


def test_macos_keeps_the_secret_in_the_keychain_and_only_a_reference_in_the_database(monkeypatch):
    security = FakeSecurity()
    off_windows(monkeypatch, vault.MacKeychain(security))
    sealed = vault.protect("xoxb-secret ünïcode")
    assert sealed.startswith(vault.KEYCHAIN) and "secret" not in sealed
    assert vault.unprotect(sealed) == "xoxb-secret ünïcode" and security.freed == 1
    assert [service for service, _ in security.items] == [b"Cerebra"]
    with pytest.raises(ValueError, match="Enter it again"):
        vault.unprotect(vault.KEYCHAIN + "missing")


class FakeSecretTool:
    def __init__(self):
        self.items, self.calls = {}, []

    def __call__(self, command, input=None, **kwargs):
        self.calls.append((command, input))
        action, account = command[1], command[-1]
        if action == "store":
            self.items[account] = input
            return subprocess.CompletedProcess(command, 0, "", "")
        if account in self.items:
            return subprocess.CompletedProcess(command, 0, self.items[account], "")
        return subprocess.CompletedProcess(command, 1, "", "")


def test_linux_uses_the_secret_service_and_never_puts_the_secret_on_a_command_line(monkeypatch):
    tool = FakeSecretTool()
    off_windows(monkeypatch, vault.SecretService("/usr/bin/secret-tool", tool))
    sealed = vault.protect("EAAB-page-token")
    assert vault.unprotect(sealed) == "EAAB-page-token"
    assert all("EAAB-page-token" not in " ".join(command) for command, _ in tool.calls)
    assert tool.calls[0][1] == "EAAB-page-token"  # given on stdin


def test_without_a_secret_store_saving_fails_plainly_instead_of_storing_plain_text(monkeypatch):
    store = vault.SecretService.__new__(vault.SecretService)  # no secret-tool on this machine
    store.tool, store.run = None, None
    off_windows(monkeypatch, store)
    with pytest.raises(ValueError, match="install libsecret-tools"):
        vault.protect("token")


def test_a_windows_secret_on_another_system_asks_to_enter_it_again(monkeypatch):
    off_windows(monkeypatch, None)
    with pytest.raises(ValueError, match="Enter it again on this computer"):
        vault.unprotect(vault.PREFIX + "AAAA")
