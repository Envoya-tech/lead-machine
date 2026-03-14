#!/bin/bash
# Lead Machine — Silent Bootstrap
# Runs fully in the background. No terminal, no prompts.
# All output goes to /tmp/leadmachine-install.log
set -e

INSTALL_DIR="/Applications/LeadMachine"
LOG="/tmp/leadmachine-install.log"
STATE_FILE="/tmp/leadmachine-install-state"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG"; }
state() { echo "$1" > "$STATE_FILE"; log "STATE: $1"; }

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

# ── Python 3.11+ ──────────────────────────────────────────────────────────────
PYTHON=""
for _p in python3.13 python3.12 python3.11; do
    if command -v "$_p" &>/dev/null; then
        if "$_p" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>/dev/null; then
            PYTHON="$_p"; break
        fi
    fi
done
if [ -z "$PYTHON" ]; then
    log "Installing Python 3.11 via Homebrew..."
    brew install python@3.11 >> "$LOG" 2>&1
    PYTHON="$(brew --prefix python@3.11)/bin/python3.11"
    log "Python installed."
fi
log "Using Python: $($PYTHON --version 2>&1)"

state "installing_postgres"
# SQLite — no PostgreSQL install needed
log "Using SQLite — skipping PostgreSQL install."

state "setting_up_database"
log "SQLite database will be created on first run."

state "installing_dependencies"

# ── Python venv + pip install (offline from bundled wheels) ──────────────────
VENV="$INSTALL_DIR/backend/.venv"
WHEELS_DIR="$INSTALL_DIR/installer/wheels"

if [ ! -d "$VENV" ]; then
    log "Creating virtual environment..."
    "$PYTHON" -m venv "$VENV" >> "$LOG" 2>&1
fi

log "Installing Python dependencies..."
"$VENV/bin/pip" install --quiet --upgrade pip >> "$LOG" 2>&1

if [ -d "$WHEELS_DIR" ] && [ "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]; then
    log "Installing from bundled wheels (offline)..."
    "$VENV/bin/pip" install --quiet \
        --find-links "$WHEELS_DIR" \
        --prefer-binary \
        -r "$INSTALL_DIR/backend/requirements-prod.txt" >> "$LOG" 2>&1
else
    log "No bundled wheels found — downloading from PyPI..."
    "$VENV/bin/pip" install --quiet \
        -r "$INSTALL_DIR/backend/requirements-prod.txt" >> "$LOG" 2>&1
fi
log "Dependencies installed."

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

# ── Run Alembic migrations ────────────────────────────────────────────────────
if [ -f "$INSTALL_DIR/backend/alembic.ini" ]; then
    log "Running database migrations..."
    cd "$INSTALL_DIR/backend"
    "$VENV/bin/alembic" upgrade head >> "$LOG" 2>&1 || log "Migration warning (non-fatal)"
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
for i in $(seq 1 60); do
    if curl -sf "http://localhost:8000/health" > /dev/null 2>&1; then
        log "Backend is up. Opening browser..."
        open "http://localhost:8080/setup"
        state "done"
        exit 0
    fi
    sleep 3
done

log "Backend timeout — opening setup page anyway."
open "http://localhost:8080/setup"
state "done"
