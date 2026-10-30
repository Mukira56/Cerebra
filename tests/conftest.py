"""Shared test setup. On macOS and Linux, secrets go to the system's secret store (Keychain or Secret Service); a test
machine may have none (a headless Linux server has no keyring), so tests use an in-memory one there. Windows keeps
using DPAPI, as on the owner's computer. tests/test_vault.py checks the real stores' commands separately."""
import os

import pytest

from ai_hq import vault


class MemoryStore:
    def __init__(self):
        self.secrets = {}

    def store(self, account, secret):
        self.secrets[account] = secret

    def load(self, account):
        if account not in self.secrets:
            raise vault.VaultError("That secret is no longer in this computer's secret store. Save it again.")
        return self.secrets[account]


@pytest.fixture(autouse=True)
def secret_store(monkeypatch):
    if os.name != "nt":
        monkeypatch.setattr(vault, "_store", MemoryStore())
    yield
