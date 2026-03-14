#!/bin/bash
# Lead Machine — Rescue Script
# Run as the normal user (not sudo) — it will ask for sudo password once.
set -e
APP="/Applications/LeadMachine"
BACKEND="$APP/backend"
LOG="$HOME/Library/Logs/LeadMachine/install.log"

echo "🔧 Lead Machine rescue starting..."
mkdir -p "$HOME/Library/Logs/LeadMachine"

# Fix ownership
echo "  Fixing permissions..."
sudo chown -R "$(whoami):staff" "$APP"

# Create venv
echo "  Creating Python environment..."
PYTHON=$(command -v python3.11 || command -v python3.12 || command -v python3)
"$PYTHON" -m venv "$BACKEND/.venv"

# Install dependencies
echo "  Installing dependencies (using bundled wheels)..."
"$BACKEND/.venv/bin/pip" install --quiet --upgrade pip
"$BACKEND/.venv/bin/pip" install --quiet --prefer-binary \
    --find-links "$APP/installer/wheels" \
    -r "$BACKEND/requirements-prod.txt"

# Write .env if missing
if [ ! -f "$BACKEND/.env" ]; then
    echo "  Writing config..."
    mkdir -p "$BACKEND/data"
    SECRET=$(openssl rand -hex 32)
    cat > "$BACKEND/.env" << EOF
APP_NAME=Lead Machine
SECRET_KEY=$SECRET
FIRST_RUN=true
DATABASE_URL=sqlite+aiosqlite:///$BACKEND/data/leadmachine.db
CORS_ORIGINS=http://localhost:8080
APP_URL=http://localhost:8080
LLM_PROVIDER=
LLM_API_KEY=
ANTHROPIC_API_KEY=
APOLLO_API_KEY=
BRAVE_SEARCH_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ACCESS_TOKEN_EXPIRE_MINUTES=10080
EOF
fi

# Run migrations (or create_all if alembic not available)
echo "  Setting up database..."
cd "$BACKEND"
mkdir -p data
if [ -f "alembic.ini" ] && [ -d "alembic" ]; then
    .venv/bin/alembic upgrade head 2>&1 | tail -3
else
    echo "  (alembic not found — using create_all)"
    .venv/bin/python -c "
import asyncio, sys
sys.path.insert(0, '.')
from app.db.base import Base
from app.db.session import engine
import app.models
async def run(): 
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
asyncio.run(run())
print('Database tables created.')
" 2>&1 | tail -5
fi

# Install launchd services
echo "  Installing services..."
VENV="$BACKEND/.venv"
LAUNCH="$HOME/Library/LaunchAgents"
CADDY="$APP/installer/bin/caddy"
mkdir -p "$LAUNCH" "$HOME/Library/Logs/LeadMachine"
chmod +x "$CADDY" 2>/dev/null || true

cat > "$LAUNCH/com.leadmachine.backend.plist" << EOF
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
  <key>WorkingDirectory</key><string>$BACKEND</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/LeadMachine/backend.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/LeadMachine/backend-error.log</string>
</dict></plist>
EOF

cat > "$LAUNCH/com.leadmachine.caddy.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.leadmachine.caddy</string>
  <key>ProgramArguments</key><array>
    <string>$CADDY</string>
    <string>run</string>
    <string>--config</string>
    <string>$APP/Caddyfile.local</string>
  </array>
  <key>WorkingDirectory</key><string>$APP</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/LeadMachine/caddy.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/LeadMachine/caddy-error.log</string>
</dict></plist>
EOF

# Stop old instances
launchctl unload "$LAUNCH/com.leadmachine.backend.plist" 2>/dev/null || true
launchctl unload "$LAUNCH/com.leadmachine.caddy.plist"   2>/dev/null || true
sleep 1

# Start services
launchctl load "$LAUNCH/com.leadmachine.backend.plist"
launchctl load "$LAUNCH/com.leadmachine.caddy.plist"

# Wait for backend
echo "  Waiting for backend..."
for i in $(seq 1 20); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  ✅ Backend is up!"
        open http://localhost:8080/setup
        echo ""
        echo "✅ Lead Machine is running at http://localhost:8080/setup"
        exit 0
    fi
    sleep 2
done

echo "  ⚠️  Backend slow to start — check: cat ~/Library/Logs/LeadMachine/backend-error.log"
echo "  Try opening: http://localhost:8080/setup"
