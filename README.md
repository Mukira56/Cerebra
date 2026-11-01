<img src="ai_hq/static/logo.svg" width="96" alt="Cerebra logo">

# Cerebra

Cerebra is a desktop app that puts the best AI models to work in one place. I connected Claude, ChatGPT (Codex), a set of free open models and the local models on your own computer, and gave them one job: build software properly and help run a small online business, with you deciding every step.

**What it does**

- **Builds software with a real review process.** One model plans the work, another writes the code, and a model from a different company reviews it. Cerebra runs your project's own tests, sends failures back to be fixed, and only merges when you say yes. The code is written in a separate copy of your project, so nothing touches your work until you approve it.
- **Uses the right model for each job.** Claude and ChatGPT through your own accounts, free models through OpenRouter, and local models through Ollama, at no cost. Hard work goes to the strongest models and quick jobs to the fast ones, or you choose yourself.
- **Finds and wins work.** It finds freelance jobs and local businesses that need a website, reads what they actually need, drafts proposals and emails in your voice, and follows up. You can send each one with a click, or let it run on its own within limits you set.
- **Makes things to sell.** Amazon KDP notebooks, logbooks and planners with their covers and listings, Etsy printables, and print-ready designs for shirts and mugs, all made on your computer.
- **Keeps the money straight.** Quotes, invoices with payment links, and orders and sales from Etsy, Shopify and Printify, in one place.
- **Shows you what's happening.** A live view of every part at work, and a plain-English report for every task: what was asked, who did what, and whether the tests passed.

Everything runs on your own computer. Your data stays in a local database, and the only things that leave it are the requests you send to the AI models and the services you connect.

## Install (Windows 10/11 x64)

Run `Cerebra-Setup-<version>-Windows-x64.exe`. Setup installs for your account only, without administrator rights. It bundles its own Python runtime, needs Microsoft Edge WebView2 (preinstalled on Windows 11), and opens Cerebra in its own window. See [docs/WINDOWS_INSTALLER.md](docs/WINDOWS_INSTALLER.md).

Then follow the *Get started* checklist on the Overview page, or read [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

## Run from source

```powershell
.\scripts\setup.ps1          # creates .venv from requirements.lock
.\scripts\start.ps1          # opens the dashboard with a private one-time session link
.\scripts\stop.ps1
```

Python 3.13+ and Git are required.

## macOS and Linux

```bash
git clone https://github.com/Mukira56/Cerebra.git && cd Cerebra
./scripts/setup.sh           # creates .venv and checks the computer
./scripts/start.sh           # opens the dashboard in your browser with a private one-time session link
./scripts/stop.sh
```

Cerebra runs in your browser there (no installer yet). Secrets go into the macOS Keychain, or into the Secret Service (GNOME Keyring, KWallet) on Linux through `secret-tool`. See [docs/MAC_LINUX.md](docs/MAC_LINUX.md).

## Build the installer

```powershell
.\.venv\Scripts\python.exe scripts\build_windows.py --output dist
.\.venv\Scripts\python.exe scripts\test_windows_installer.py dist\Cerebra-Setup-<version>-Windows-x64.exe --test-root <empty folder>
```

The builder uses the project's Python environment and the Windows .NET Framework C# compiler, and downloads nothing. The installer is unsigned until you add a code-signing certificate.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests never launch a real AI CLI. They use the fixture agent in `tests/fakes.py`. The dashboard has a headless Edge test in `scripts/test_dashboard.cjs`.

## Documentation

- [User guide](docs/USER_GUIDE.md): setup, tasks, chat, models, GitHub, and where results are saved
- [Security boundaries](docs/SECURITY.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Windows installer](docs/WINDOWS_INSTALLER.md)
- [Development](docs/DEVELOPMENT.md)
- [Progress record](docs/progress.md)

## License

Copyright (c) 2026 Godfrey Mukira. All rights reserved. The code is public to read, not to use or copy: see [LICENSE](LICENSE).
