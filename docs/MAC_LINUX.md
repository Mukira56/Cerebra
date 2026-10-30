# Cerebra on macOS and Linux

Cerebra's server, dashboard, agents, Business Studio, Money, Freelance and Marketing are the same on every system. On macOS and Linux it runs from its folder and opens in your browser; the Windows installer, its own window and the one-click updater are Windows-only.

## Install and run

You need Python 3.13 or newer and Git. Codex and Claude Code CLIs are installed the same way as on Windows (see the Toolchain page).

```bash
git clone https://github.com/Mukira56/Cerebra.git && cd Cerebra
./scripts/setup.sh
./scripts/start.sh            # or ./scripts/start.sh 8800 for another port
./scripts/stop.sh
```

`start.sh` opens the dashboard with a private, one-time session link. Your data stays in the `data` folder next to Cerebra, or in `AIHQ_DATA_DIR` when you set it.

## Updating

Settings → Updates tells you when a new version is out. To update: stop Cerebra, then in its folder run

```bash
git pull && ./scripts/setup.sh && ./scripts/start.sh
```

## Secrets

The keys and tokens you give Cerebra (Gmail, Stripe, Freelancer.com, X, Meta, Telegram and others) are kept by the system's own secret store. The database holds only a reference:

- **macOS:** your login Keychain (service "Cerebra"), through the Security framework.
- **Linux:** the Secret Service (GNOME Keyring or KWallet), through `secret-tool`. Install it with `sudo apt install libsecret-tools` (Debian, Ubuntu), `sudo dnf install libsecret` (Fedora) or `sudo pacman -S libsecret` (Arch). Without it, Cerebra refuses to save a secret instead of keeping it in plain text. The secret goes to `secret-tool` on its input, never on a command line.

A secret saved on Windows (DPAPI) can't be read on another computer: enter it again there.

## Opening things

- **Files and folders** open with `open` (macOS) or `xdg-open` (Linux).
- **Text files** such as a project's `.env` open in TextEdit (macOS) or your default editor (Linux).
- **The folder chooser** uses the system dialog: macOS's own, or `zenity` or `kdialog` on Linux. Without either, type the folder.
- **Sign-ins** such as `gh auth login` open in Terminal (macOS) or your terminal app: GNOME Terminal, Konsole, xfce4-terminal, kitty, Alacritty or xterm. Every argument is quoted, so nothing in a path or name can run as a command.

## What has been checked

These macOS and Linux paths are covered by tests that simulate each system's secret store, terminal and dialogs (`tests/test_vault.py`, `tests/test_desktop.py`).

**Linux, checked on a real machine (2026-10-30).** The whole test suite runs on GitHub's Ubuntu machines through `.github/workflows/tests.yml`: setup with `scripts/setup.sh`, then every test, and all of them pass.
- **How it runs:** it's started by hand, from the Actions tab or with `gh workflow run tests.yml`, so the free Actions minutes last.
- **What the first run found:** the tests assumed Windows in a few places (a secret store, a fake Git, paths). They now work on every system.
- **On a Linux computer without a keyring** (a server or a minimal desktop), saving a key fails with a message saying to install `libsecret-tools` (Debian, Ubuntu) or `libsecret` (Fedora, Arch). Cerebra never stores the key in plain text instead.

**macOS, checked on a real machine (2026-10-30).** The same workflow runs there when started with `-f macos=true`. On GitHub's Apple-silicon Mac, setup worked and 502 of 503 tests passed. The one failure was a Windows-only test that assumed an Intel processor; it now follows the machine's processor. A macOS run takes about 20 minutes, and macOS minutes count ten times against the free allowance.

Still to come: a `.dmg`/`.app` for macOS and an AppImage or `.deb` for Linux, with checksums.
