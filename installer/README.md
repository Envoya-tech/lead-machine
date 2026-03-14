# Lead Machine — Installation Guide

---

## Quick Start

### macOS / Linux
```bash
git clone https://github.com/lennarthanoo/lead-machine.git
cd lead-machine
bash installer/install.sh
```

### macOS (.pkg)
Double-click `lead-machine-VERSION.pkg`. A Terminal window opens automatically
and runs the setup wizard. See "Gatekeeper Warning" below if macOS blocks the package.

### Windows
```bat
installer\install.bat
```
> Run as Administrator. Right-click → "Run as administrator".

### From a tar.gz release
```bash
tar -xzf lead-machine-*.tar.gz
cd lead-machine-*/
bash installer/install.sh          # macOS / Linux
installer\install.bat               # Windows
```

---

## What the Wizard Does

All heavy lifting happens silently with animated spinners. You only see prompts and
checkmarks — no raw CLI output unless something fails.

| Step | Description |
|------|-------------|
| 1 | **System Setup** — installs Node.js, builds frontend if needed |
| 2 | **License activation** — validates your key (online or offline fallback) |
| 3 | **Database** — PostgreSQL (recommended) or SQLite; auto-installs PG if missing |
| 4 | **API keys** — LLM provider, Apollo, Brave Search (required); Telegram (optional) |
| 5 | **Admin account** — name, email, username, password |
| 6 | **Domain / URL** — CORS config + Caddyfile generation; auto-installs Caddy if missing |
| 7 | **Write config** — generates `backend/.env` |
| 8 | **Python venv + DB init** — creates virtualenv, installs packages, creates tables, seeds admin |
| 9 | **Start services** — launchd (macOS) / systemd (Linux) / NSSM (Windows) |
| 10 | **Done** — opens browser |

**Estimated time on a fresh machine: 15–20 minutes** (mostly package downloads).

---

## Platform Support

| Platform | Service manager | Auto-install packages |
|----------|-----------------|-----------------------|
| macOS 12+ (Homebrew) | launchd | PostgreSQL, Caddy, Node, Python 3.11 |
| Ubuntu 22.04 / 24.04 | systemd (user) | PostgreSQL, Caddy, Node, python3.11-venv |
| Windows 10/11 | NSSM | PostgreSQL, Caddy via winget/choco |

### Windows Notes

- Run the installer as **Administrator** (required for NSSM service registration)
- NSSM is installed automatically via winget or Chocolatey if not present
- If neither winget nor choco is available: download [NSSM](https://nssm.cc/release/nssm-2.24.zip)
  and place `nssm.exe` in your PATH before running the wizard
- PostgreSQL is installed via `winget install PostgreSQL.PostgreSQL`
- Caddy is installed via `winget install CaddyServer.Caddy`
- **WSL2** is a simpler alternative for Windows users comfortable with Linux:
  install Ubuntu from the Microsoft Store and follow the Linux instructions

---

## install.sh Bootstrap

`install.sh` handles the pre-wizard bootstrap on macOS and Linux:

- **macOS**: installs Homebrew (if missing), then Python 3.11+ via Homebrew
- **Linux**: installs Python 3.11 + python3-venv via apt (if missing)
- Then calls `python3.11 installer/wizard.py`

The wizard itself handles all remaining dependencies (Node, PostgreSQL, Caddy, pip packages).

---

## API Keys

Prepare these before running the wizard:

| Key | Where to get it | Required |
|-----|-----------------|----------|
| Anthropic API key | https://console.anthropic.com/settings/keys | ✅ (or OpenAI) |
| OpenAI API key | https://platform.openai.com/api-keys | ✅ (or Anthropic) |
| Apollo.io API key | https://developer.apollo.io | ✅ |
| Brave Search API key | https://api.search.brave.com/app/keys | ✅ |
| Telegram bot token | https://t.me/BotFather | Optional |

---

## macOS .pkg Notes

- The `.pkg` installer places Lead Machine in `/Applications/LeadMachine/`
- After install, a Terminal window opens automatically and runs `installer/install.sh`
- The wizard's `ROOT` resolves correctly from `/Applications/LeadMachine/installer/wizard.py`
  to `/Applications/LeadMachine/`

**Gatekeeper warning** ("unidentified developer"): right-click the .pkg → **Open**.  
This is expected for unsigned packages. Signing with an Apple Developer ID ($99/yr) removes this warning:
```bash
productsign --sign "Developer ID Installer: Envoya" \
    lead-machine-VERSION.pkg lead-machine-VERSION-signed.pkg
```

---

## Re-running the Wizard

Safe to re-run at any time — existing `.env` files are backed up first:
```bash
bash installer/install.sh
```

---

## Uninstall

**macOS:**
```bash
launchctl unload ~/Library/LaunchAgents/com.leadmachine.backend.plist
launchctl unload ~/Library/LaunchAgents/com.leadmachine.caddy.plist
rm ~/Library/LaunchAgents/com.leadmachine.*.plist
rm -rf /Applications/LeadMachine/   # if installed via .pkg
```

**Linux:**
```bash
systemctl --user stop leadmachine-backend leadmachine-caddy
systemctl --user disable leadmachine-backend leadmachine-caddy
rm ~/.config/systemd/user/leadmachine-*.service
systemctl --user daemon-reload
```

**Windows:**
```bat
nssm stop LeadMachineBackend
nssm remove LeadMachineBackend confirm
nssm stop LeadMachineCaddy
nssm remove LeadMachineCaddy confirm
```

---

## Troubleshooting

**Backend not responding:**
```bash
# macOS
tail -50 ~/Library/Logs/LeadMachine/backend-error.log
# Linux
journalctl --user -u leadmachine-backend -n 50
```

**Database connection error:**
```bash
psql postgresql://leadmachine:PASSWORD@localhost:5432/leadmachine
```

**Re-initialise the database manually:**
```bash
cd backend
source .venv/bin/activate
python3 -m app.core.init_db
```

**Reset admin password:**
```bash
cd backend && source .venv/bin/activate
python seed_admin.py myusername mynewpassword123 email@example.com
```

---

*Lead Machine — built by Envoya.*
