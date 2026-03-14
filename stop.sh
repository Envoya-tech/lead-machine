#!/bin/bash
# Lead Machine — stop all services

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${CYAN}⛔ Stopping Lead Machine...${NC}"

for svc in backend frontend; do
  PID_FILE="/tmp/lm-${svc}.pid"
  if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID" && echo "  Stopped $svc (PID $PID)"
    fi
    rm -f "$PID_FILE"
  fi
done

# Kill any stray uvicorn / vite processes on our ports
/usr/sbin/lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
/usr/sbin/lsof -ti:3000 2>/dev/null | xargs kill -9 2>/dev/null || true

echo -e "${GREEN}✅ Done${NC}"
