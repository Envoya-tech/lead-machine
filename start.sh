#!/bin/bash
# Lead Machine — start frontend + backend
# Both bind to 0.0.0.0 so they're reachable via Tailscale and local network

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Colors ─────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

echo -e "${CYAN}⚡ Lead Machine — starting...${NC}\n"

# ── Tailscale IP ───────────────────────────────────────────────────────────────
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null)

# ── Backend ────────────────────────────────────────────────────────────────────
echo -e "${CYAN}→ Starting backend (port 8000)...${NC}"
cd "$SCRIPT_DIR/backend"
source .venv/bin/activate
nohup uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  > /tmp/lm-backend.log 2>&1 &
BACKEND_PID=$!
echo $BACKEND_PID > /tmp/lm-backend.pid
echo -e "  Backend PID: $BACKEND_PID"

# Wait for backend to be ready
for i in $(seq 1 10); do
  sleep 1
  if curl -s http://localhost:8000/health > /dev/null 2>&1; then break; fi
done

# ── Frontend ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}→ Starting frontend (port 3000)...${NC}"
cd "$SCRIPT_DIR/frontend"
nohup npm run dev > /tmp/lm-frontend.log 2>&1 &
FRONTEND_PID=$!
echo $FRONTEND_PID > /tmp/lm-frontend.pid
echo -e "  Frontend PID: $FRONTEND_PID"

sleep 2

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✅ Lead Machine is running${NC}"
echo ""
if [ -n "$TAILSCALE_IP" ]; then
  echo -e "  ${GREEN}Tailscale (anywhere):${NC}  http://${TAILSCALE_IP}:3000"
fi
if [ -n "$LOCAL_IP" ]; then
  echo -e "  ${YELLOW}Local network:${NC}         http://${LOCAL_IP}:3000"
fi
echo -e "  Local only:            http://localhost:3000"
echo ""
echo -e "  Logs:  tail -f /tmp/lm-backend.log"
echo -e "         tail -f /tmp/lm-frontend.log"
echo -e "  Stop:  ./stop.sh"
echo ""
