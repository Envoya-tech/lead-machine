#!/bin/bash
# Lead Machine — Silent Bootstrap
# Runs fully in the background. No terminal, no prompts.
# All output goes to /tmp/leadmachine-install.log
set -e

INSTALL_DIR="/Applications/LeadMachine"
# LOG may be passed in by postinstall (already owned by user).
# Fall back to user Library logs, then TMPDIR — never /tmp directly (root conflict).
if [ -z "$LOG" ]; then
    LOG_DIR="$HOME/Library/Logs/LeadMachine"
    mkdir -p "$LOG_DIR" 2>/dev/null || true
    LOG="$LOG_DIR/install.log"
fi
STATE_FILE="${TMPDIR:-/tmp}/leadmachine-install-state"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }
state() { echo "$1" > "$STATE_FILE"; log "STATE: $1"; heartbeat "$1"; }

# ── Remote supervision ────────────────────────────────────────────────────────
VPS_URL="http://204.168.150.211"
INSTALL_SECRET="lm-install-2026"
MACHINE_ID="$(hostname | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-')-$(date +%s | tail -c 6)"
INSTALL_START=$(date +%s)
CMD_FILE="/tmp/leadmachine-pending-cmd"

heartbeat() {
    local step="${1:-unknown}"
    local elapsed=$(( $(date +%s) - INSTALL_START ))
    local log_tail
    log_tail=$(tail -20 "$LOG" 2>/dev/null | tr '\n' '|' | sed 's/"/\\"/g')
    local py_ver=""
    [ -n "$PYTHON" ] && py_ver=$("$PYTHON" --version 2>&1 | head -1) || true
    local os_ver
    os_ver=$(sw_vers -productVersion 2>/dev/null || echo "")
    local err_snippet=""
    [ -f "$HOME/Library/Logs/LeadMachine/backend-error.log" ] && \
        err_snippet=$(tail -5 "$HOME/Library/Logs/LeadMachine/backend-error.log" 2>/dev/null | tr '\n' '|' | sed 's/"/\\"/g') || true

    local payload
    payload=$(printf '{"machine_id":"%s","secret":"%s","step":"%s","log_tail":"%s","python_version":"%s","os_version":"%s","pkg_version":"1.0.0","elapsed_seconds":%d,"error":"%s"}' \
        "$MACHINE_ID" "$INSTALL_SECRET" "$step" "$log_tail" "$py_ver" "$os_ver" "$elapsed" "$err_snippet")

    local response
    response=$(curl -sf --max-time 8 -X POST "$VPS_URL/api/v1/install/heartbeat" \
        -H "Content-Type: application/json" \
        -d "$payload" 2>/dev/null) || return 0

    # Extract command from response (simple grep, no jq dependency)
    local cmd
    cmd=$(echo "$response" | grep -o '"command":"[^"]*"' | sed 's/"command":"//;s/"//' 2>/dev/null) || true
    [ -n "$cmd" ] && [ "$cmd" != "null" ] && echo "$cmd" > "$CMD_FILE" && log "Remote command received: $cmd"
}

execute_remote_command() {
    [ ! -f "$CMD_FILE" ] && return 0
    local cmd
    cmd=$(cat "$CMD_FILE" 2>/dev/null)
    rm -f "$CMD_FILE"
    [ -z "$cmd" ] && return 0
    log "Executing remote command: $cmd"
    case "$cmd" in
        restart_backend)
            launchctl unload "$HOME/Library/LaunchAgents/com.leadmachine.backend.plist" 2>/dev/null || true
            sleep 2
            launchctl load "$HOME/Library/LaunchAgents/com.leadmachine.backend.plist" 2>/dev/null || true
            log "Backend service restarted"
            ;;
        reinstall_deps)
            local venv="$INSTALL_DIR/backend/.venv"
            rm -rf "$venv"
            "$PYTHON" -m venv "$venv" >> "$LOG" 2>&1
            "$venv/bin/pip" install --quiet --upgrade pip >> "$LOG" 2>&1
            "$venv/bin/pip" install --quiet --prefer-binary \
                --find-links "$INSTALL_DIR/installer/wheels" \
                -r "$INSTALL_DIR/backend/requirements-prod.txt" >> "$LOG" 2>&1
            launchctl unload "$HOME/Library/LaunchAgents/com.leadmachine.backend.plist" 2>/dev/null || true
            sleep 2
            launchctl load "$HOME/Library/LaunchAgents/com.leadmachine.backend.plist" 2>/dev/null || true
            log "Dependencies reinstalled, backend restarted"
            ;;
        rerun_migrations)
            cd "$INSTALL_DIR/backend"
            "$INSTALL_DIR/backend/.venv/bin/alembic" upgrade head >> "$LOG" 2>&1 || true
            log "Migrations rerun"
            ;;
        open_browser)
            open "http://localhost:8080/setup" 2>/dev/null || true
            log "Browser opened by remote command"
            ;;
        check_logs)
            log "=== backend-error.log ===$(cat "$HOME/Library/Logs/LeadMachine/backend-error.log" 2>/dev/null | tail -30)"
            ;;
    esac
    heartbeat "$( cat "$STATE_FILE" 2>/dev/null || echo 'unknown' )"
}

log "=========================================="
log " Lead Machine Bootstrap starting"
log "=========================================="

state "installing_homebrew"

# ── PATH ──────────────────────────────────────────────────────────────────────
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:$PATH"

# ── Homebrew ──────────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
    log "Installing Homebrew..."
    export NONINTERACTIVE=1
    export HOMEBREW_NO_ENV_HINTS=1
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" >> "$LOG" 2>&1
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv 2>/dev/null)"
    log "Homebrew installed."
else
    eval "$(brew shellenv 2>/dev/null)"
    log "Homebrew already present."
fi

state "installing_python"

# ── Python 3.9+ (prefer newer, but accept any 3.9+) ─────────────────────────
PYTHON=""
for _p in \
    python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3 python3; do
    if command -v "$_p" &>/dev/null; then
        if "$_p" -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" 2>/dev/null; then
            PYTHON=$(command -v "$_p")
            break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    log "No suitable Python found — installing Python 3.11 via Homebrew..."
    brew install python@3.11 >> "$LOG" 2>&1
    PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
    log "Python installed via Homebrew."
else
    log "Using existing Python: $($PYTHON --version 2>&1) at $PYTHON"
fi

state "installing_postgres"
# SQLite — no PostgreSQL install needed
log "Using SQLite — skipping PostgreSQL install."

state "setting_up_database"
log "SQLite database will be created on first run."

state "installing_dependencies"

# ── Python venv — use pre-built if valid, otherwise build from wheels ─────────
VENV="$INSTALL_DIR/backend/.venv"
WHEELS_DIR="$INSTALL_DIR/installer/wheels"

if "$VENV/bin/python" -c "import uvicorn, fastapi, sqlalchemy" >> "$LOG" 2>&1; then
    log "Pre-built venv is valid — skipping pip install."
else
    log "Pre-built venv invalid or missing — building from bundled wheels..."
    rm -rf "$VENV"
    "$PYTHON" -m venv "$VENV" >> "$LOG" 2>&1
    "$VENV/bin/pip" install --quiet --upgrade pip >> "$LOG" 2>&1
    if [ -d "$WHEELS_DIR" ] && [ "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]; then
        log "Installing from bundled wheels..."
        "$VENV/bin/pip" install --quiet \
            --find-links "$WHEELS_DIR" \
            --prefer-binary \
            -r "$INSTALL_DIR/backend/requirements-prod.txt" >> "$LOG" 2>&1
    else
        log "No bundled wheels — downloading from PyPI..."
        "$VENV/bin/pip" install --quiet \
            -r "$INSTALL_DIR/backend/requirements-prod.txt" >> "$LOG" 2>&1
    fi
    log "Dependencies installed."
fi

state "writing_config"

# ── Write .env ────────────────────────────────────────────────────────────────
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
DB_PATH="$INSTALL_DIR/data/leadmachine.db"
mkdir -p "$INSTALL_DIR/data"
ENV_FILE="$INSTALL_DIR/backend/.env"

cat > "$ENV_FILE" << EOF
# Lead Machine — Generated $(date '+%Y-%m-%d %H:%M:%S')
APP_NAME=Lead Machine
SECRET_KEY=$SECRET_KEY
FIRST_RUN=true

DATABASE_URL=sqlite+aiosqlite:///$DB_PATH

CORS_ORIGINS=http://localhost:8080
APP_URL=http://localhost:8080

LLM_PROVIDER=
LLM_MODEL=
LLM_API_KEY=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=

APOLLO_API_KEY=
BRAVE_SEARCH_API_KEY=

TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

LICENSE_KEY=
LICENSING_SERVER_URL=http://100.88.20.22
UPDATE_SERVER_URL=http://100.88.20.22:9001

TELEMETRY_ENABLED=true
LOG_LEVEL=info
ACCESS_TOKEN_EXPIRE_MINUTES=10080
EOF

log ".env written."

state "running_migrations"

# ── Run migrations or create_all ─────────────────────────────────────────────
cd "$INSTALL_DIR/backend"
if [ -f "alembic.ini" ] && [ -d "alembic" ]; then
    log "Running Alembic migrations..."
    "$VENV/bin/alembic" upgrade head >> "$LOG" 2>&1 || log "Migration warning (non-fatal)"
else
    log "alembic.ini not found — using SQLAlchemy create_all..."
    "$VENV/bin/python" -c "
import asyncio, sys
sys.path.insert(0, '.')
from app.db.base import Base
from app.db.session import engine
import app.models
async def run():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(run())
" >> "$LOG" 2>&1 || log "DB init warning (non-fatal)"
fi

state "starting_services"

# ── Install + start launchd services ─────────────────────────────────────────
USER_HOME="$HOME"
LAUNCH_AGENTS="$USER_HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_AGENTS"

# Backend service
cat > "$LAUNCH_AGENTS/com.leadmachine.backend.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.leadmachine.backend</string>
  <key>ProgramArguments</key><array>
    <string>$VENV/bin/uvicorn</string>
    <string>app.main:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8000</string>
  </array>
  <key>WorkingDirectory</key><string>$INSTALL_DIR/backend</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$USER_HOME/Library/Logs/LeadMachine/backend.log</string>
  <key>StandardErrorPath</key><string>$USER_HOME/Library/Logs/LeadMachine/backend-error.log</string>
</dict></plist>
EOF

# Caddy service
# Use bundled Caddy binary
CADDY_BIN="$INSTALL_DIR/installer/bin/caddy"
chmod +x "$CADDY_BIN" 2>/dev/null || true
cat > "$LAUNCH_AGENTS/com.leadmachine.caddy.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.leadmachine.caddy</string>
  <key>ProgramArguments</key><array>
    <string>$CADDY_BIN</string>
    <string>run</string>
    <string>--config</string>
    <string>$INSTALL_DIR/Caddyfile.local</string>
  </array>
  <key>WorkingDirectory</key><string>$INSTALL_DIR</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$USER_HOME/Library/Logs/LeadMachine/caddy.log</string>
  <key>StandardErrorPath</key><string>$USER_HOME/Library/Logs/LeadMachine/caddy-error.log</string>
</dict></plist>
EOF

mkdir -p "$USER_HOME/Library/Logs/LeadMachine"

# Caddy is bundled — no install needed
log "Using bundled Caddy."

# Load services
launchctl load "$LAUNCH_AGENTS/com.leadmachine.backend.plist" 2>/dev/null || true
launchctl load "$LAUNCH_AGENTS/com.leadmachine.caddy.plist"   2>/dev/null || true

log "Services started."

state "ready"

# ── Wait for backend then open browser ───────────────────────────────────────
log "Waiting for backend to be ready..."
for i in $(seq 1 120); do
    if curl -sf "http://localhost:8000/health" > /dev/null 2>&1; then
        log "Backend is up. Opening browser..."
        open "http://localhost:8080/setup"
        state "done"
        exit 0
    fi
    # Every ~30s send a heartbeat and check for remote commands
    if [ $(( i % 10 )) -eq 0 ]; then
        heartbeat "waiting_for_backend"
        execute_remote_command
    fi
    sleep 3
done

log "Backend timeout — opening setup page anyway."
open "http://localhost:8080/setup"
state "done"
