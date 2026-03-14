#!/usr/bin/env python3
"""
Lead Machine Installation Wizard v2.0
Usage: python3 installer/wizard.py   (or: bash installer/install.sh)

Supports: macOS (launchd) · Linux (systemd) · Windows (NSSM)
"""
import sys
import os
import subprocess
import shutil
import json
import re
import getpass
import socket
import time
import secrets
import hashlib
import platform
import threading
import itertools
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# ── OS detection ───────────────────────────────────────────────────────────────
OS = platform.system()   # "Darwin" | "Linux" | "Windows"

# ── ANSI colours (empty on Windows unless ANSICON/WT) ─────────────────────────
_USE_ANSI = sys.platform != "win32" or os.environ.get("ANSICON") or os.environ.get("WT_SESSION")
if _USE_ANSI:
    GREEN  = "\033[92m"
    RED    = "\033[91m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"
else:
    GREEN = RED = YELLOW = BLUE = CYAN = BOLD = DIM = RESET = ""

# ── Root paths ─────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).resolve().parent.parent   # repo root / extracted archive
BACKEND = ROOT / "backend"
DEPLOY  = ROOT / "deploy"

# ── Homebrew PATH injection (macOS) ───────────────────────────────────────────
# When launched from a .pkg postinstall via osascript, PATH may not include
# /opt/homebrew/bin. Inject it early so all brew-installed tools are found.
if platform.system() == "Darwin":
    _brew_paths = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
    ]
    _current_path = os.environ.get("PATH", "")
    _extra = ":".join(p for p in _brew_paths if p not in _current_path)
    if _extra:
        os.environ["PATH"] = _extra + ":" + _current_path

# ── Global state ──────────────────────────────────────────────────────────────
CFG: dict = {}
_COMPLETED: list[str] = []   # step summaries shown after screen clear


# ══════════════════════════════════════════════════════════════════════════════
# Output helpers
# ══════════════════════════════════════════════════════════════════════════════

def _clear():
    os.system("cls" if OS == "Windows" else "clear")

def _banner():
    print(f"{BOLD}{BLUE}")
    print("  ██╗     ███╗   ███╗  ")
    print("  ██║     ████╗ ████║  Lead Machine")
    print("  ██║     ██╔████╔██║  Setup Wizard")
    print("  ██║     ██║╚██╔╝██║  ")
    print("  ███████╗██║ ╚═╝ ██║  ")
    print(f"  ╚══════╝╚═╝     ╚═╝  {RESET}")

def _progress_bar(n: int, total: int, width: int = 24) -> str:
    filled = int(width * n / total)
    bar    = "█" * filled + "░" * (width - filled)
    return f"{CYAN}{bar}{RESET} {n}/{total}"

def print_step(n: int, total: int, title: str):
    _clear()
    _banner()
    # Compact list of completed steps
    if _COMPLETED:
        for s in _COMPLETED:
            print(f"  {GREEN}✓{RESET}  {s}")
        print()
    # Progress
    print(f"  {_progress_bar(n - 1, total)}")
    print(f"\n{BOLD}{CYAN}── Step {n}/{total}: {title}{RESET}")
    print(f"  {DIM}{'─' * 52}{RESET}\n")

def ok(msg: str):
    print(f"  {GREEN}✓{RESET}  {msg}")

def fail(msg: str):
    print(f"  {RED}✗{RESET}  {msg}")

def warn(msg: str):
    print(f"  {YELLOW}⚠{RESET}  {msg}")

def info(msg: str):
    print(f"  {BLUE}ℹ{RESET}  {msg}")

def ask(prompt: str, default: str | None = None, secret: bool = False) -> str:
    if default is not None:
        full = f"  {prompt} [{BOLD}{default}{RESET}]: "
    else:
        full = f"  {prompt}: "
    val = getpass.getpass(full) if secret else input(full).strip()
    if not val and default is not None:
        return default
    return val

def ask_choice(prompt: str, choices: list[str], default: int = 1) -> int:
    print(f"  {prompt}")
    for i, c in enumerate(choices, 1):
        marker = f"{BOLD}●{RESET}" if i == default else " "
        print(f"  {marker} [{i}] {c}")
    while True:
        raw = input(f"  Choice [{default}]: ").strip()
        if not raw:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(choices):
            return int(raw)
        warn(f"Enter a number between 1 and {len(choices)}.")

def abort(reason: str):
    print(f"\n{RED}{BOLD}  Aborted:{RESET} {reason}\n")
    sys.exit(1)

def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        capture: bool = True) -> subprocess.CompletedProcess:
    """Silent subprocess — returns result without printing anything."""
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        capture_output=capture,
        text=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Spinner helper — ALL long background tasks go through here
# ══════════════════════════════════════════════════════════════════════════════

def run_with_spinner(
    label: str,
    cmd: list[str],
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: int = 600,
    fatal: bool = True,
) -> subprocess.CompletedProcess:
    """
    Run a command silently with an animated spinner.
    Shows output only if the command fails.
    Set fatal=False to return the result without aborting on failure.
    """
    frames   = itertools.cycle(["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"])
    done_evt = threading.Event()
    box: dict = {}

    def _worker():
        try:
            box["res"] = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                env={**os.environ, **(env or {})},
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            box["res"] = subprocess.CompletedProcess(cmd, 124, "", f"Timed out after {timeout}s")
        except Exception as exc:
            box["res"] = subprocess.CompletedProcess(cmd, 1, "", str(exc))
        finally:
            done_evt.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    col = 60  # spinner line width
    while not done_evt.wait(timeout=0.1):
        if _USE_ANSI:
            sys.stdout.write(f"\r  {CYAN}{next(frames)}{RESET}  {label}...")
            sys.stdout.flush()

    t.join()
    res = box.get("res", subprocess.CompletedProcess(cmd, 1, "", "Unknown error"))

    # Clear spinner line
    if _USE_ANSI:
        sys.stdout.write(f"\r{' ' * col}\r")
        sys.stdout.flush()

    if res.returncode == 0:
        ok(label)
    else:
        fail(f"{label}  (exit {res.returncode})")
        # Show last 2 000 chars of output to help diagnose
        if res.stdout and res.stdout.strip():
            print()
            print(f"  {DIM}--- stdout ---{RESET}")
            print(res.stdout.strip()[-2000:])
        if res.stderr and res.stderr.strip():
            print()
            print(f"  {DIM}--- stderr ---{RESET}")
            print(res.stderr.strip()[-2000:])
        if fatal:
            abort(f"{label} failed. See output above.")

    return res


# ══════════════════════════════════════════════════════════════════════════════
# OS / platform helpers
# ══════════════════════════════════════════════════════════════════════════════

def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False

def _is_admin_windows() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def _venv_bin(venv_dir: Path, name: str) -> Path:
    if OS == "Windows":
        p = venv_dir / "Scripts" / (name + ".exe")
        return p if p.exists() else venv_dir / "Scripts" / name
    return venv_dir / "bin" / name

def _find_psql() -> str:
    if OS == "Windows":
        for ver in ("17", "16", "15", "14"):
            p = Path(rf"C:\Program Files\PostgreSQL\{ver}\bin\psql.exe")
            if p.exists():
                return str(p)
    # Check Homebrew explicit paths first (PATH may not include /opt/homebrew/bin)
    if OS == "Darwin":
        for p in [
            "/opt/homebrew/bin/psql",
            "/opt/homebrew/opt/postgresql@15/bin/psql",
            "/opt/homebrew/opt/postgresql@16/bin/psql",
            "/opt/homebrew/opt/postgresql@17/bin/psql",
            "/usr/local/bin/psql",
            "/usr/local/opt/postgresql@15/bin/psql",
        ]:
            if Path(p).exists():
                return p
    found = shutil.which("psql")
    return found or "psql"

def _pg_bin_dir() -> str:
    psql = _find_psql()
    return str(Path(psql).parent) if psql != "psql" else "/usr/bin"

def get_log_dir() -> Path:
    if OS == "Darwin":
        return Path.home() / "Library" / "Logs" / "LeadMachine"
    elif OS == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "LeadMachine" / "logs"
    else:
        return Path("/var/log/leadmachine") if _is_root() \
               else Path.home() / ".local" / "share" / "leadmachine" / "logs"


# ══════════════════════════════════════════════════════════════════════════════
# Package installation (OS-specific) — all use spinner
# ══════════════════════════════════════════════════════════════════════════════

def _brew(pkg: str, label: str):
    if not shutil.which("brew"):
        abort("Homebrew is required but not found. Run: bash installer/install.sh")
    run_with_spinner(label, ["brew", "install", pkg], timeout=600)

def _apt(*pkgs: str, label: str):
    run_with_spinner(label, ["sudo", "apt-get", "install", "-y", *pkgs], timeout=300)

def _winpkg(winget_id: str, choco_id: str, label: str) -> bool:
    if shutil.which("winget"):
        res = run_with_spinner(
            label, ["winget", "install", winget_id, "--silent",
                    "--accept-package-agreements", "--accept-source-agreements"],
            timeout=300, fatal=False,
        )
        if res.returncode == 0:
            return True
    if shutil.which("choco"):
        res = run_with_spinner(label, ["choco", "install", choco_id, "-y"],
                               timeout=300, fatal=False)
        if res.returncode == 0:
            return True
    return False

def install_postgresql():
    if OS == "Darwin":
        _brew("postgresql@15", "Installing PostgreSQL")
        run_with_spinner("Starting PostgreSQL",
                         ["brew", "services", "start", "postgresql@15"], timeout=60)
    elif OS == "Linux":
        run_with_spinner("Updating package list", ["sudo", "apt-get", "update", "-qq"],
                         timeout=120)
        _apt("postgresql", "postgresql-contrib", label="Installing PostgreSQL")
        run_with_spinner("Enabling PostgreSQL service",
                         ["sudo", "systemctl", "enable", "--now", "postgresql"],
                         timeout=60)
    elif OS == "Windows":
        if not _winpkg("PostgreSQL.PostgreSQL", "postgresql", "Installing PostgreSQL"):
            abort("Could not install PostgreSQL automatically.\n"
                  "  Download from: https://www.postgresql.org/download/windows/")
    time.sleep(3)

def install_caddy():
    if OS == "Darwin":
        _brew("caddy", "Installing Caddy")
    elif OS == "Linux":
        info("Adding Caddy repository…")
        for step_cmd, step_label in [
            (["sudo", "apt-get", "install", "-y",
              "debian-keyring", "debian-archive-keyring", "apt-transport-https", "curl"],
             "Installing Caddy prerequisites"),
            (["sudo", "bash", "-c",
              "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key'"
              " | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg"],
             "Adding Caddy GPG key"),
            (["sudo", "bash", "-c",
              "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt'"
              " | tee /etc/apt/sources.list.d/caddy-stable.list"],
             "Adding Caddy apt source"),
            (["sudo", "apt-get", "update", "-qq"], "Updating package list"),
            (["sudo", "apt-get", "install", "-y", "caddy"], "Installing Caddy"),
        ]:
            run_with_spinner(step_label, step_cmd, timeout=180)
    elif OS == "Windows":
        if not _winpkg("CaddyServer.Caddy", "caddy", "Installing Caddy"):
            info("Download Caddy manually: https://caddyserver.com/download")
            info("Place caddy.exe somewhere in your PATH, then re-run.")

def install_node():
    if shutil.which("node"):
        return
    if OS == "Darwin":
        _brew("node", "Installing Node.js")
    elif OS == "Linux":
        run_with_spinner("Updating package list", ["sudo", "apt-get", "update", "-qq"],
                         timeout=120)
        _apt("nodejs", "npm", label="Installing Node.js")
    elif OS == "Windows":
        if not _winpkg("OpenJS.NodeJS", "nodejs", "Installing Node.js"):
            warn("Could not install Node.js — frontend build may fail.")


# ══════════════════════════════════════════════════════════════════════════════
# Frontend build helper
# ══════════════════════════════════════════════════════════════════════════════

def _build_frontend_if_needed():
    dist = ROOT / "frontend" / "dist"
    if dist.exists() and any(dist.iterdir()):
        ok("Frontend assets already built")
        return
    info("frontend/dist/ not found — building from source (git clone flow)…")
    install_node()
    frontend_dir = ROOT / "frontend"
    run_with_spinner("Installing frontend packages",
                     ["npm", "install"], cwd=frontend_dir, timeout=300)
    run_with_spinner("Building frontend",
                     ["npm", "run", "build"], cwd=frontend_dir, timeout=300)
    ok("Frontend built ✔")


# ══════════════════════════════════════════════════════════════════════════════
# PostgreSQL helpers
# ══════════════════════════════════════════════════════════════════════════════

def _pg_isready() -> bool:
    try:
        # Also check Homebrew explicit path for pg_isready
        pg = shutil.which("pg_isready")
        if not pg and OS == "Darwin":
            for p in [
                "/opt/homebrew/bin/pg_isready",
                "/opt/homebrew/opt/postgresql@15/bin/pg_isready",
                "/opt/homebrew/opt/postgresql@16/bin/pg_isready",
                "/usr/local/bin/pg_isready",
            ]:
                if Path(p).exists():
                    pg = p
                    break
        if pg:
            return run([pg]).returncode == 0
        psql = _find_psql()
        return run([psql, "-U", "postgres", "-c", "SELECT 1", "-d", "postgres"]).returncode == 0
    except FileNotFoundError:
        return False

def _pg_admin_psql(sql: str, db: str = "postgres") -> subprocess.CompletedProcess:
    psql = _find_psql()
    if OS == "Linux" and not _is_root():
        return run(["sudo", "-u", "postgres", psql, "-d", db, "-c", sql])
    elif OS == "Darwin":
        user = os.environ.get("USER", "postgres")
        res  = run([psql, "-U", user, "-d", db, "-c", sql])
        if res.returncode != 0:
            res = run([psql, "-U", "postgres", "-d", db, "-c", sql])
        return res
    else:
        return run([psql, "-U", "postgres", "-d", db, "-c", sql])

def _create_pg_db(name: str, user: str, password: str) -> bool:
    r1 = _pg_admin_psql(
        f"DO $$ BEGIN "
        f"  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='{user}') THEN "
        f"    CREATE ROLE {user} LOGIN PASSWORD '{password}'; "
        f"  END IF; "
        f"END $$;"
    )
    if r1.returncode != 0:
        fail(f"Could not create PostgreSQL role: {r1.stderr.strip()[:120]}")
        return False
    _pg_admin_psql(
        f"SELECT 'CREATE DATABASE {name} OWNER {user}' "
        f"WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='{name}')\\gexec"
    )
    return True


# ══════════════════════════════════════════════════════════════════════════════
# NSSM helpers (Windows)
# ══════════════════════════════════════════════════════════════════════════════

def _find_nssm() -> str | None:
    return shutil.which("nssm")

def _ensure_nssm() -> str | None:
    nssm = _find_nssm()
    if nssm:
        return nssm
    if shutil.which("winget"):
        res = run_with_spinner(
            "Installing NSSM",
            ["winget", "install", "NSSM.NSSM", "--silent",
             "--accept-package-agreements", "--accept-source-agreements"],
            timeout=120, fatal=False,
        )
        if res.returncode == 0:
            return _find_nssm()
    if shutil.which("choco"):
        res = run_with_spinner("Installing NSSM",
                               ["choco", "install", "nssm", "-y"],
                               timeout=120, fatal=False)
        if res.returncode == 0:
            return _find_nssm()
    warn("NSSM could not be installed automatically.")
    info("Download: https://nssm.cc/release/nssm-2.24.zip — put nssm.exe in PATH, then re-run.")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Caddyfile generation
# ══════════════════════════════════════════════════════════════════════════════

def _is_real_domain(url: str) -> bool:
    m = re.match(r'^https?://([^/:]+)', url)
    if not m:
        return False
    h = m.group(1)
    return (h != "localhost"
            and not h.startswith("127.")
            and not h.startswith("192.168.")
            and not h.startswith("10.")
            and not re.match(r'^\d+\.\d+\.\d+\.\d+$', h))

def generate_caddyfile(install_dir: Path, app_url: str) -> Path:
    dist = install_dir.as_posix() + "/frontend/dist"
    base = f"""\
:8080 {{
    handle /api/* {{
        reverse_proxy 127.0.0.1:8000
    }}
    handle {{
        root * {dist}
        try_files {{path}} /index.html
        file_server
    }}
}}
"""
    extra = ""
    if _is_real_domain(app_url):
        m = re.match(r'^https?://([^/]+)', app_url)
        domain = m.group(1) if m else app_url
        extra = f"""
{domain} {{
    handle /api/* {{
        reverse_proxy 127.0.0.1:8000
    }}
    handle {{
        root * {dist}
        try_files {{path}} /index.html
        file_server
    }}
}}
"""
    path = install_dir / "Caddyfile"
    path.write_text(base + extra)
    ok("Caddyfile written")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# Service file generation
# ══════════════════════════════════════════════════════════════════════════════

def _generate_plists(install_dir: Path, venv_dir: Path, log_dir: Path) -> list[Path]:
    uvicorn   = _venv_bin(venv_dir, "uvicorn")
    caddy_bin = shutil.which("caddy") or "/opt/homebrew/bin/caddy"
    pg_bin    = _pg_bin_dir()
    agents    = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    backend_plist = agents / "com.leadmachine.backend.plist"
    caddy_plist   = agents / "com.leadmachine.caddy.plist"

    backend_plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.leadmachine.backend</string>
  <key>ProgramArguments</key>
  <array>
    <string>{uvicorn}</string>
    <string>app.main:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8000</string>
    <string>--workers</string><string>2</string>
  </array>
  <key>WorkingDirectory</key><string>{install_dir}/backend</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>{pg_bin}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>StandardOutPath</key><string>{log_dir}/backend.log</string>
  <key>StandardErrorPath</key><string>{log_dir}/backend-error.log</string>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
  <key>ThrottleInterval</key><integer>5</integer>
</dict></plist>""")

    caddy_plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.leadmachine.caddy</string>
  <key>ProgramArguments</key>
  <array>
    <string>{caddy_bin}</string>
    <string>run</string>
    <string>--config</string><string>{install_dir}/Caddyfile</string>
  </array>
  <key>WorkingDirectory</key><string>{install_dir}</string>
  <key>StandardOutPath</key><string>{log_dir}/caddy.log</string>
  <key>StandardErrorPath</key><string>{log_dir}/caddy-error.log</string>
  <key>KeepAlive</key><true/>
  <key>RunAtLoad</key><true/>
</dict></plist>""")

    return [backend_plist, caddy_plist]


def _generate_systemd_units(install_dir: Path, venv_dir: Path, log_dir: Path) -> list[Path]:
    uvicorn   = _venv_bin(venv_dir, "uvicorn")
    caddy_bin = shutil.which("caddy") or "/usr/bin/caddy"
    pg_bin    = _pg_bin_dir()
    units_dir = Path("/etc/systemd/system") if _is_root() \
                else Path.home() / ".config" / "systemd" / "user"
    units_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    backend_unit = units_dir / "leadmachine-backend.service"
    caddy_unit   = units_dir / "leadmachine-caddy.service"

    backend_unit.write_text(f"""[Unit]
Description=Lead Machine Backend
After=network.target postgresql.service

[Service]
Type=simple
WorkingDirectory={install_dir}/backend
ExecStart={uvicorn} app.main:app --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
Environment="PATH={pg_bin}:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=default.target
""")

    caddy_unit.write_text(f"""[Unit]
Description=Lead Machine Caddy
After=network.target

[Service]
Type=simple
ExecStart={caddy_bin} run --config {install_dir}/Caddyfile
WorkingDirectory={install_dir}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
""")

    return [backend_unit, caddy_unit]


def _start_systemd_services() -> bool:
    ctl   = ["systemctl"] if _is_root() else ["systemctl", "--user"]
    names = ["leadmachine-backend", "leadmachine-caddy"]
    run_with_spinner("Reloading systemd", ctl + ["daemon-reload"], timeout=30)
    run_with_spinner("Enabling services", ctl + ["enable"] + names, timeout=30)
    run_with_spinner("Starting services", ctl + ["start"]  + names, timeout=60)
    if not _is_root():
        user = os.environ.get("USER") or os.environ.get("LOGNAME", "")
        if user:
            run(["loginctl", "enable-linger", user])
            ok("Linger enabled — services start on boot without login")
    return True


def _start_nssm_services(install_dir: Path, venv_dir: Path, log_dir: Path) -> bool:
    nssm = _ensure_nssm()
    if not nssm:
        return False
    uvicorn_exe = str(_venv_bin(venv_dir, "uvicorn"))
    caddy_bin   = shutil.which("caddy") or "caddy"
    caddyfile   = str(install_dir / "Caddyfile")
    log_dir.mkdir(parents=True, exist_ok=True)

    for svc in ("LeadMachineBackend", "LeadMachineCaddy"):
        run([nssm, "stop", svc])
        run([nssm, "remove", svc, "confirm"])

    for cmd in [
        [nssm, "install", "LeadMachineBackend", uvicorn_exe,
         "app.main:app --host 127.0.0.1 --port 8000 --workers 2"],
        [nssm, "set", "LeadMachineBackend", "AppDirectory", str(install_dir / "backend")],
        [nssm, "set", "LeadMachineBackend", "AppStdout", str(log_dir / "backend.log")],
        [nssm, "set", "LeadMachineBackend", "AppStderr", str(log_dir / "backend-error.log")],
        [nssm, "set", "LeadMachineBackend", "Start", "SERVICE_AUTO_START"],
        [nssm, "install", "LeadMachineCaddy", caddy_bin, f"run --config {caddyfile}"],
        [nssm, "set", "LeadMachineCaddy", "AppDirectory", str(install_dir)],
        [nssm, "set", "LeadMachineCaddy", "AppStdout", str(log_dir / "caddy.log")],
        [nssm, "set", "LeadMachineCaddy", "AppStderr", str(log_dir / "caddy-error.log")],
        [nssm, "set", "LeadMachineCaddy", "Start", "SERVICE_AUTO_START"],
    ]:
        run(cmd)  # quick config — no spinner needed

    run_with_spinner("Starting services",
                     [nssm, "start", "LeadMachineBackend"], timeout=30, fatal=False)
    run_with_spinner("Starting Caddy",
                     [nssm, "start", "LeadMachineCaddy"],   timeout=30, fatal=False)
    return True


def setup_services(install_dir: Path, venv_dir: Path) -> bool:
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    if OS == "Darwin":
        info("Generating launchd service files…")
        plists = _generate_plists(install_dir, venv_dir, log_dir)
        ok(f"Service files written to ~/Library/LaunchAgents/")
        for plist in plists:
            run(["launchctl", "unload", str(plist)])
            res = run(["launchctl", "load", "-w", str(plist)])
            label = plist.stem
            if res.returncode == 0:
                ok(f"Loaded: {label}")
            else:
                warn(f"launchctl load failed for {label} — try manually after install")
        return True

    elif OS == "Linux":
        info("Generating systemd unit files…")
        _generate_systemd_units(install_dir, venv_dir, log_dir)
        return _start_systemd_services()

    elif OS == "Windows":
        return _start_nssm_services(install_dir, venv_dir, log_dir)

    warn(f"Unknown OS '{OS}' — start services manually.")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Step 1 — System check + environment bootstrap
# ══════════════════════════════════════════════════════════════════════════════

def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) != 0

def check_system():
    print_step(1, 7, "System Setup")
    passed = True

    if OS == "Windows":
        if _is_admin_windows():
            ok("Running as Administrator")
        else:
            fail("Administrator privileges required on Windows.")
            info("Right-click your terminal and choose 'Run as administrator'.")
            passed = False

    ok(f"Platform: {OS} {platform.release()} ({platform.machine()})")

    v = sys.version_info
    if v >= (3, 11):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor} — need 3.11+. Re-run via install.sh.")
        passed = False

    if not passed:
        abort("System requirements not met.")

    # Disk space
    free_mb = shutil.disk_usage(ROOT).free // (1024 * 1024)
    if free_mb >= 500:
        ok(f"Disk space: {free_mb:,} MB free")
    else:
        warn(f"Disk space low: {free_mb} MB — recommend 500 MB+")

    # Ensure python3-venv on Linux
    if OS == "Linux" and run([sys.executable, "-m", "venv", "--help"]).returncode != 0:
        run_with_spinner("Installing python3-venv",
                         ["sudo", "apt-get", "install", "-y", "python3-venv", "python3-pip"],
                         timeout=120)

    # Ports
    for port in (8000, 8080):
        if is_port_free(port):
            ok(f"Port {port} available")
        else:
            warn(f"Port {port} is in use — may conflict with Lead Machine")

    # Build frontend if dist/ is absent (git clone)
    _build_frontend_if_needed()

    _COMPLETED.append("System check complete")


# ══════════════════════════════════════════════════════════════════════════════
# Step 2 — License activation
# ══════════════════════════════════════════════════════════════════════════════

def _parse_license_key(key: str) -> dict | None:
    key = key.strip().upper()
    m = re.match(r'^LM-([A-Z0-9+/=]+)-(\d+)-(\d{8})-([A-F0-9]{4})$', key)
    if not m:
        return None
    b64_name, seats_str, expiry_str, checksum = m.groups()
    import base64
    try:
        licensee = base64.b64decode(b64_name + "==").decode("utf-8", errors="replace")
    except Exception:
        licensee = b64_name
    if hashlib.sha256(key.rsplit("-",1)[0].encode()).hexdigest()[:4].upper() != checksum:
        return None
    try:
        from datetime import date
        expiry = date(int(expiry_str[:4]), int(expiry_str[4:6]), int(expiry_str[6:]))
        return {"expired": expiry < date.today(),
                "licensee": licensee, "seats": int(seats_str), "expiry": expiry}
    except ValueError:
        return None

def activate_license():
    # License is entered via the web UI after install — skip here
    ok("License will be activated in the web setup")
    CFG["license_key"] = ""
    _COMPLETED.append("License: pending (web UI)")


# ══════════════════════════════════════════════════════════════════════════════
# Step 3 — Database setup
# ══════════════════════════════════════════════════════════════════════════════

def setup_database():
    print_step(3, 7, "Database Setup")

    # Always PostgreSQL — auto-install if needed, no user interaction
    if not _pg_isready():
        install_postgresql()
        time.sleep(3)
        if not _pg_isready():
            abort("PostgreSQL could not be started. Check your installation.")
    else:
        ok("PostgreSQL is running")

    db_name = "leadmachine"
    db_user = "leadmachine"
    db_pass = secrets.token_hex(16)

    _create_pg_db(db_name, db_user, db_pass)
    ok(f"Database ready")

    db_url = f"postgresql+asyncpg://{db_user}:{db_pass}@localhost:5432/{db_name}"
    CFG.update(db_type="postgresql", db_url=db_url, database_url=db_url,
               db_name=db_name, db_user=db_user, db_pass=db_pass)
    _COMPLETED.append(f"Database: PostgreSQL ({db_name})")


# ══════════════════════════════════════════════════════════════════════════════
# Step 4 — LLM provider + API keys
# ══════════════════════════════════════════════════════════════════════════════

def _test_anthropic_key(key: str) -> bool:
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code != 401
    except Exception:
        return False

def _test_openai_key(key: str) -> bool:
    req = urllib.request.Request(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code != 401
    except Exception:
        return False

def _test_apollo_key(key: str) -> bool:
    url = f"https://api.apollo.io/v1/auth/health?api_key={urllib.parse.quote(key)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as r:
            return json.loads(r.read().decode()).get("is_logged_in", False)
    except Exception:
        return False

def _test_brave_key(key: str) -> bool:
    req = urllib.request.Request(
        "https://api.search.brave.com/res/v1/web/search?q=test&count=1",
        headers={"Accept": "application/json", "X-Subscription-Token": key},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code not in (401, 403)
    except Exception:
        return False

def _test_telegram(token: str) -> bool:
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/getMe", timeout=10
        ) as r:
            return json.loads(r.read().decode()).get("ok", False)
    except Exception:
        return False

def _prompt_key(label: str, cfg_key: str, required: bool, validator, hint: str = "") -> str:
    if hint:
        info(hint)
    suffix = "" if required else "  (optional — press Enter to skip)"
    for attempt in range(1, 4):
        value = ask(f"{label}{suffix}", secret=True)
        if not value:
            if required:
                if attempt < 3:
                    warn("This key is required.")
                    continue
                abort(f"{label} is required.")
            info(f"Skipping {label}.")
            return ""
        # Validate silently (no spinner — fast HTTP check)
        sys.stdout.write(f"  {CYAN}⠋{RESET}  Validating...")
        sys.stdout.flush()
        try:
            valid = validator(value)
        except Exception:
            valid = False
        if _USE_ANSI:
            sys.stdout.write(f"\r{' '*40}\r")
            sys.stdout.flush()
        if valid:
            ok(f"{label} ✓")
            CFG[cfg_key] = value
            return value
        warn(f"{label} could not be validated (network issue or incorrect key).")
        keep = ask("Use it anyway?", default="yes")
        if keep.lower() in ("yes", "y"):
            warn(f"{label} saved without confirmation — verify later.")
            CFG[cfg_key] = value
            return value
        if attempt < 3:
            warn("Please try again.")
    return ""

def configure_api_keys():
    print_step(4, 10, "LLM Provider & API Keys")

    # ── LLM provider ────────────────────────────────────────────────────────
    choice = ask_choice(
        "Which LLM provider?",
        ["Anthropic (Claude)  — recommended",
         "OpenAI (GPT-4o / GPT-3.5)",
         "Other (configure manually later)"],
        default=1,
    )
    if choice == 1:
        CFG["llm_provider"] = "anthropic"
        _prompt_key("Anthropic API key", "ANTHROPIC_API_KEY", required=True,
                    validator=_test_anthropic_key,
                    hint="Get yours at: https://console.anthropic.com/settings/keys")
        CFG["llm_model"]   = ask("Model", default="claude-3-5-haiku-20241022")
        CFG["LLM_API_KEY"] = CFG.get("ANTHROPIC_API_KEY", "")
    elif choice == 2:
        CFG["llm_provider"] = "openai"
        _prompt_key("OpenAI API key", "OPENAI_API_KEY", required=True,
                    validator=_test_openai_key,
                    hint="Get yours at: https://platform.openai.com/api-keys")
        CFG["llm_model"]   = ask("Model", default="gpt-4o-mini")
        CFG["LLM_API_KEY"] = CFG.get("OPENAI_API_KEY", "")
    else:
        CFG["llm_provider"] = "other"
        CFG["llm_model"]    = ""
        CFG["LLM_API_KEY"]  = ""
        info("Set LLM_PROVIDER / LLM_API_KEY / LLM_MODEL in backend/.env after install.")

    print()
    print()
    info("Optional integrations:")

    # ── Apollo ────────────────────────────────────────────────────────────────
    _prompt_key("Apollo.io API key", "APOLLO_API_KEY", required=False,
                validator=_test_apollo_key,
                hint="Get yours at: https://developer.apollo.io")

    # ── Brave Search ──────────────────────────────────────────────────────────
    _prompt_key("Brave Search API key", "BRAVE_SEARCH_API_KEY", required=False,
                validator=_test_brave_key,
                hint="Get yours at: https://api.search.brave.com/app/keys")

    # ── Telegram ──────────────────────────────────────────────────────────────
    _prompt_key("Telegram bot token", "TELEGRAM_BOT_TOKEN", required=False,
                validator=_test_telegram,
                hint="Create a bot at: https://t.me/BotFather")
    if CFG.get("TELEGRAM_BOT_TOKEN"):
        chat = ask("Telegram chat_id (your user or group ID — optional)", default="")
        if chat:
            CFG["TELEGRAM_CHAT_ID"] = chat
            ok(f"Telegram chat_id saved")
        # Send test message
        if CFG.get("TELEGRAM_CHAT_ID"):
            if ask("Send a test message?", default="yes").lower() in ("yes", "y"):
                _telegram_test(CFG["TELEGRAM_BOT_TOKEN"], CFG["TELEGRAM_CHAT_ID"])

    _COMPLETED.append("API keys configured")

def _telegram_test(token: str, chat_id: str):
    msg  = "🚀 Lead Machine installation — Telegram working!"
    data = json.dumps({"chat_id": chat_id, "text": msg}).encode()
    req  = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage", data=data,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            if json.loads(r.read().decode()).get("ok"):
                ok("Test message sent ✔")
    except Exception as e:
        warn(f"Test message failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 5 — Admin account
# ══════════════════════════════════════════════════════════════════════════════

def create_admin():
    # Admin account is created via the web UI — skip here
    ok("Admin account will be created in the web setup")
    CFG.update(admin_name="", admin_email="", admin_username="", admin_password="")
    _COMPLETED.append("Admin: pending (web UI)")


# ══════════════════════════════════════════════════════════════════════════════
# Step 6 — Domain / URL + Caddyfile
# ══════════════════════════════════════════════════════════════════════════════

def configure_domain():
    # removed
    info("This is the URL where you'll access Lead Machine.\n")
    info("Examples:")
    info("  https://leadmachine.yourcompany.com")
    info("  http://192.168.1.100:8080  (local network)")
    info("  http://localhost            (this machine only)")
    print()

    while True:
        url = ask("Your Lead Machine URL", default="http://localhost")
        url = url.rstrip("/")
        if re.match(r'^https?://', url):
            break
        warn("URL must start with http:// or https://")

    ok(f"URL: {url}")
    CFG["app_url"]   = url
    CFG["use_https"] = url.startswith("https://")
    if CFG["use_https"]:
        info("HTTPS detected — Caddy will manage TLS automatically.")
    else:
        info("HTTP URL — ideal for local or VPN access.")

    # Caddy
    if not shutil.which("caddy"):
        warn("Caddy not found — installing now…")
        install_caddy()
    else:
        ok("Caddy is installed")

    generate_caddyfile(ROOT, url)
    _COMPLETED.append(f"URL: {url}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 7 — Write configuration
# ══════════════════════════════════════════════════════════════════════════════

def write_config():
    print_step(5, 7, "Writing Configuration")

    # Default URL — no domain step, always localhost:8080
    if "app_url" not in CFG:
        CFG["app_url"]   = "http://localhost:8080"
        CFG["use_https"] = False

    # Ensure Caddy is installed
    if not shutil.which("caddy"):
        install_caddy()
    else:
        ok("Caddy is installed")
    generate_caddyfile(ROOT, CFG["app_url"])

    llm_api = CFG.get("LLM_API_KEY", CFG.get("ANTHROPIC_API_KEY", ""))
    env = f"""# Lead Machine — Backend Configuration
# Generated {time.strftime('%Y-%m-%d %H:%M:%S')}
# ──────────────────────────────────────────────────────────────────────────────

APP_NAME=Lead Machine
SECRET_KEY={secrets.token_hex(32)}
FIRST_RUN=false

DATABASE_URL={CFG.get('database_url', 'sqlite+aiosqlite:///./data/leadmachine.db')}

CORS_ORIGINS={CFG.get('app_url', 'http://localhost:8080')}
APP_URL={CFG.get('app_url', 'http://localhost:8080')}

LLM_PROVIDER={CFG.get('llm_provider', '')}
LLM_MODEL={CFG.get('llm_model', '')}
LLM_API_KEY={llm_api}
ANTHROPIC_API_KEY={CFG.get('ANTHROPIC_API_KEY', '')}
OPENAI_API_KEY={CFG.get('OPENAI_API_KEY', '')}

APOLLO_API_KEY={CFG.get('APOLLO_API_KEY', '')}
BRAVE_SEARCH_API_KEY={CFG.get('BRAVE_SEARCH_API_KEY', '')}

TELEGRAM_BOT_TOKEN={CFG.get('TELEGRAM_BOT_TOKEN', '')}
TELEGRAM_CHAT_ID={CFG.get('TELEGRAM_CHAT_ID', '')}

LICENSE_KEY={CFG.get('license_key', '')}
LICENSING_SERVER_URL=http://100.88.20.22
UPDATE_SERVER_URL=http://100.88.20.22:9001

TELEMETRY_ENABLED=true
LOG_LEVEL=info
ACCESS_TOKEN_EXPIRE_MINUTES={60 * 24 * 7}
"""
    for path in (BACKEND / ".env", ROOT / ".env"):
        if path.exists():
            shutil.copy2(path, path.with_suffix(".env.bak"))
            info(f"Backed up existing {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(env)
        ok(f"Written: {path.relative_to(ROOT)}")

    (ROOT / "data").mkdir(exist_ok=True)
    _COMPLETED.append("Configuration written")


# ══════════════════════════════════════════════════════════════════════════════
# Step 8 — Venv + database initialisation + seeds
# ══════════════════════════════════════════════════════════════════════════════

def _load_env_dict(env_file: Path) -> dict:
    result = dict(os.environ)
    if env_file.exists():
        for raw in env_file.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result

def step_setup_venv(install_dir: Path) -> Path:
    venv_dir = install_dir / "backend" / ".venv"
    req_file = install_dir / "backend" / "requirements.txt"

    if not venv_dir.exists():
        run_with_spinner("Creating Python environment",
                         [sys.executable, "-m", "venv", str(venv_dir)],
                         timeout=60)

    pip = _venv_bin(venv_dir, "pip")
    if req_file.exists():
        run_with_spinner(
            "Installing Python packages  (this takes a few minutes)",
            [str(pip), "install", "-r", str(req_file)],
            timeout=600,
        )

    python = _venv_bin(venv_dir, "python")
    if not python.exists():
        python = _venv_bin(venv_dir, "python3")
    return python

def init_database():
    print_step(6, 7, "Installing & Setting Up")

    # venv
    venv_python = step_setup_venv(ROOT)
    venv_dir    = venv_python.parent.parent
    CFG["_venv_python"] = str(venv_python)
    CFG["_venv_dir"]    = str(venv_dir)

    env_file      = BACKEND / ".env"
    migration_env = _load_env_dict(env_file)
    migration_env["DATABASE_URL"] = CFG.get("database_url", "")

    # create tables
    if (BACKEND / "app" / "core" / "init_db.py").exists():
        run_with_spinner(
            "Setting up database",
            [str(venv_python), "-m", "app.core.init_db"],
            cwd=BACKEND, env=migration_env, timeout=120,
        )
    else:
        _inline_create_all(venv_python, migration_env)

    # seed admin
    _seed_admin(venv_python, migration_env)

    # seed tenant settings
    _seed_tenant_settings(venv_python)

    _COMPLETED.append("Database ready")

def _inline_create_all(python: Path, env: dict):
    code = ("import asyncio,sys,os\nsys.path.insert(0,'.')\n"
            "from sqlalchemy.ext.asyncio import create_async_engine\n"
            "from app.db.base import Base\nimport app.models\n"
            "async def go():\n"
            "  e=create_async_engine(os.environ['DATABASE_URL'],echo=False)\n"
            "  async with e.begin() as c: await c.run_sync(Base.metadata.create_all)\n"
            "  await e.dispose()\nasyncio.run(go())")
    tmp = BACKEND / "_wiz_create_tmp.py"
    tmp.write_text(code)
    try:
        run_with_spinner("Setting up database (fallback)",
                         [str(python), str(tmp)], cwd=BACKEND, env=env, timeout=120)
    finally:
        tmp.unlink(missing_ok=True)

def _seed_admin(python: Path, env: dict):
    # Admin account is created via the web UI on first run — skip seeding here
    ok("Admin account: will be created via web setup")

def _seed_admin_inline(python: Path, env: dict):
    code = f"""import asyncio,sys,os
sys.path.insert(0,'.')
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession,async_sessionmaker
from sqlalchemy import select
from app.db.base import Base
from app.models.organization import Organization
from app.models.user import User,UserRole
from app.models.tenant_settings import TenantSettings
import bcrypt,uuid
hp=lambda pw:bcrypt.hashpw(pw.encode(),bcrypt.gensalt()).decode()
async def go():
    e=create_async_engine(os.environ['DATABASE_URL'],echo=False)
    sf=async_sessionmaker(e,class_=AsyncSession,expire_on_commit=False)
    async with e.begin() as c: await c.run_sync(Base.metadata.create_all)
    async with sf() as s:
        r=await s.execute(select(Organization).limit(1))
        org=r.scalar_one_or_none()
        if not org:
            org=Organization(name='Lead Machine',slug='lead-machine')
            s.add(org);await s.flush()
            s.add(TenantSettings(id=str(uuid.uuid4()),organization_id=org.id))
        r2=await s.execute(select(User).where(User.username=={repr(CFG['admin_username'])}))
        if not r2.scalar_one_or_none():
            s.add(User(organization_id=org.id,username={repr(CFG['admin_username'])},
                full_name={repr(CFG['admin_name'])},email={repr(CFG['admin_email'])},
                hashed_password=hp({repr(CFG['admin_password'])}),
                role=UserRole.admin,is_active=True))
        await s.commit()
asyncio.run(go())
"""
    tmp = BACKEND / "_wiz_admin_tmp.py"
    tmp.write_text(code)
    try:
        run_with_spinner("Creating admin account",
                         [str(python), str(tmp)], cwd=BACKEND, env=env, timeout=60)
    finally:
        tmp.unlink(missing_ok=True)

def _seed_tenant_settings(venv_python: Path):
    lead_sources = json.dumps({
        "apollo": {"api_key": CFG.get("APOLLO_API_KEY", ""),
                   "enabled": bool(CFG.get("APOLLO_API_KEY"))}
    })
    code = """import asyncio,os,sys,json
sys.path.insert(0,'.')
from sqlalchemy.ext.asyncio import create_async_engine,AsyncSession,async_sessionmaker
from sqlalchemy import select
from app.db.base import Base
import app.models,uuid
from app.models.organization import Organization
from app.models.tenant_settings import TenantSettings
async def go():
    e=create_async_engine(os.environ['DATABASE_URL'],echo=False)
    sf=async_sessionmaker(e,class_=AsyncSession,expire_on_commit=False)
    async with sf() as s:
        r=await s.execute(select(Organization).limit(1))
        org=r.scalar_one_or_none()
        if not org:return
        r2=await s.execute(select(TenantSettings).limit(1))
        ts=r2.scalar_one_or_none()
        LS=json.loads(os.environ.get('LEAD_SOURCES_JSON','{}'))
        if ts:
            ts.engine_llm_provider=os.environ.get('LLM_PROVIDER') or ts.engine_llm_provider
            ts.engine_llm_model=os.environ.get('LLM_MODEL') or ts.engine_llm_model
            ts.engine_llm_api_key_enc=os.environ.get('LLM_API_KEY') or ts.engine_llm_api_key_enc
            ts.llm_provider=os.environ.get('LLM_PROVIDER') or ts.llm_provider
            ts.llm_model=os.environ.get('LLM_MODEL') or ts.llm_model
            ts.llm_api_key_enc=os.environ.get('LLM_API_KEY') or ts.llm_api_key_enc
            ts.apollo_api_key_enc=os.environ.get('APOLLO_API_KEY') or ts.apollo_api_key_enc
            if LS:ts.lead_sources_config=LS
        else:
            ts=TenantSettings(id=str(uuid.uuid4()),organization_id=org.id,
                engine_llm_provider=os.environ.get('LLM_PROVIDER',''),
                engine_llm_model=os.environ.get('LLM_MODEL',''),
                engine_llm_api_key_enc=os.environ.get('LLM_API_KEY',''),
                llm_provider=os.environ.get('LLM_PROVIDER',''),
                llm_model=os.environ.get('LLM_MODEL',''),
                llm_api_key_enc=os.environ.get('LLM_API_KEY',''),
                apollo_api_key_enc=os.environ.get('APOLLO_API_KEY',''),
                lead_sources_config=LS)
            s.add(ts)
        await s.commit()
    await e.dispose()
asyncio.run(go())
"""
    env_file = BACKEND / ".env"
    env_dict = _load_env_dict(env_file)
    env_dict.update({
        "DATABASE_URL":      CFG.get("database_url", ""),
        "LLM_PROVIDER":      CFG.get("llm_provider", ""),
        "LLM_MODEL":         CFG.get("llm_model", ""),
        "LLM_API_KEY":       CFG.get("LLM_API_KEY", ""),
        "APOLLO_API_KEY":    CFG.get("APOLLO_API_KEY", ""),
        "LEAD_SOURCES_JSON": lead_sources,
    })
    tmp = BACKEND / "_wiz_ts_tmp.py"
    tmp.write_text(code)
    try:
        run_with_spinner("Saving API key configuration",
                         [str(venv_python), str(tmp)],
                         cwd=BACKEND, env=env_dict, timeout=60, fatal=False)
    finally:
        tmp.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Step 9 — Start services
# ══════════════════════════════════════════════════════════════════════════════

def _wait_for_http(url: str, timeout: int = 90, interval: int = 3) -> bool:
    deadline = time.time() + timeout
    frames   = itertools.cycle(["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"])
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if r.status < 500:
                    return True
        except Exception:
            pass
        if _USE_ANSI:
            sys.stdout.write(f"\r  {CYAN}{next(frames)}{RESET}  Waiting for service…")
            sys.stdout.flush()
        time.sleep(interval)
    if _USE_ANSI:
        sys.stdout.write(f"\r{' '*50}\r")
        sys.stdout.flush()
    return False

def start_services():
    print_step(7, 7, "Starting Services")

    venv_dir = Path(CFG.get("_venv_dir", str(BACKEND / ".venv")))
    app_url  = CFG.get("app_url", "http://localhost")

    started = setup_services(ROOT, venv_dir)
    if not started:
        # Docker fallback
        compose = ROOT / "docker-compose.yml"
        if shutil.which("docker") and compose.exists():
            res = run_with_spinner(
                "Starting via Docker Compose",
                ["docker", "compose", "-f", str(compose), "up", "-d", "--build"],
                cwd=ROOT, timeout=300, fatal=False,
            )
            started = res.returncode == 0
        if not started:
            warn("Services could not be started automatically.")
            if OS == "Darwin":
                info("Start manually: launchctl load ~/Library/LaunchAgents/com.leadmachine.backend.plist")
            elif OS == "Linux":
                info("Start manually: systemctl --user start leadmachine-backend")
            elif OS == "Windows":
                info("Start manually: nssm start LeadMachineBackend")

    print()
    if _wait_for_http("http://localhost:8000/health", timeout=90):
        ok("Backend is up and running")
    else:
        warn("Backend didn't respond within 90 s — check logs if the app doesn't load.")

    m = re.match(r'^https?://[^:/?]+:(\d+)', app_url)
    probe = f"http://localhost:{m.group(1) if m else '8080'}"
    if _wait_for_http(probe, timeout=60):
        ok("Frontend is accessible")
    else:
        warn(f"Frontend didn't respond at {probe} — may still be starting up.")

    _COMPLETED.append("Services started")


# ══════════════════════════════════════════════════════════════════════════════
# Step 10 — Done
# ══════════════════════════════════════════════════════════════════════════════

def finish():
    print_step(7, 7, "Installation Complete")

    setup_url = "http://localhost:8080/setup"
    ok("Installation complete — opening Lead Machine in your browser…")

    # Wait for backend to be ready, then open /setup
    for _ in range(60):
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8000/health", timeout=2)
            break
        except Exception:
            time.sleep(3)

    if OS == "Darwin":
        try:
            subprocess.Popen(["open", setup_url])
        except Exception:
            pass
    elif OS == "Windows":
        try:
            os.startfile(setup_url)  # type: ignore[attr-defined]
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    # Fully silent — no prompts, no interaction.
    # License + admin setup happens in the web UI at http://localhost:8080/setup
    check_system()        # 1
    activate_license()    # 2 (no-op — deferred to web UI)
    setup_database()      # 3
    create_admin()        # 4 (no-op — deferred to web UI)
    write_config()        # 5
    init_database()       # 6
    start_services()      # 7
    finish()              # 7


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}  Installation cancelled.{RESET}\n")
        sys.exit(1)
