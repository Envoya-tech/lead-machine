#!/bin/bash
# Lead Machine — show running status and access URLs

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'

backend_ok=false
frontend_ok=false

curl -s http://localhost:8000/health > /dev/null 2>&1 && backend_ok=true
curl -s http://localhost:3000 > /dev/null 2>&1 && frontend_ok=true

echo ""
echo -e "  Backend  $([ "$backend_ok"  = true ] && echo "${GREEN}● running${NC}" || echo "${RED}● stopped${NC}")"
echo -e "  Frontend $([ "$frontend_ok" = true ] && echo "${GREEN}● running${NC}" || echo "${RED}● stopped${NC}")"
echo ""

TAILSCALE_IP=$(tailscale ip -4 2>/dev/null | head -1)
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || python3 -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2>/dev/null)

if [ -n "$TAILSCALE_IP" ]; then
  echo -e "  ${GREEN}Tailscale:${NC}  http://${TAILSCALE_IP}:3000"
fi
if [ -n "$LOCAL_IP" ]; then
  echo -e "  ${YELLOW}Local:${NC}      http://${LOCAL_IP}:3000"
fi
echo ""
