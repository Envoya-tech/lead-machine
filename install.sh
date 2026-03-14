#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${CYAN}"
echo "  ██╗     ███████╗ █████╗ ██████╗     ███╗   ███╗ █████╗  ██████╗██╗  ██╗██╗███╗   ██╗███████╗"
echo "  ██║     ██╔════╝██╔══██╗██╔══██╗    ████╗ ████║██╔══██╗██╔════╝██║  ██║██║████╗  ██║██╔════╝"
echo "  ██║     █████╗  ███████║██║  ██║    ██╔████╔██║███████║██║     ███████║██║██╔██╗ ██║█████╗  "
echo "  ██║     ██╔══╝  ██╔══██║██║  ██║    ██║╚██╔╝██║██╔══██║██║     ██╔══██║██║██║╚██╗██║██╔══╝  "
echo "  ███████╗███████╗██║  ██║██████╔╝    ██║ ╚═╝ ██║██║  ██║╚██████╗██║  ██║██║██║ ╚████║███████╗"
echo "  ╚══════╝╚══════╝╚═╝  ╚═╝╚═════╝     ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝╚══════╝"
echo -e "${NC}"
echo -e "${CYAN}Lead Machine — Installer${NC}"
echo ""

# ── Check Docker ──────────────────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found.${NC}"
    echo "   Install Docker Desktop from: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo -e "${RED}❌ Docker Compose V2 not found.${NC}"
    echo "   Update Docker Desktop to the latest version."
    exit 1
fi

echo -e "${GREEN}✅ Docker $(docker --version | cut -d' ' -f3 | tr -d ',') detected${NC}"

# ── Set up .env ───────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate random SECRET_KEY
    if command -v openssl &> /dev/null; then
        SECRET=$(openssl rand -hex 32)
    else
        SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi
    # Replace placeholder in .env (works on both macOS and Linux)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/generate-a-strong-random-key-here/$SECRET/" .env
    else
        sed -i "s/generate-a-strong-random-key-here/$SECRET/" .env
    fi
    echo -e "${GREEN}✅ Created .env with random secret key${NC}"
else
    echo -e "${GREEN}✅ .env already exists${NC}"
fi

# ── Create data directory ─────────────────────────────────────────────────────
mkdir -p data
echo -e "${GREEN}✅ Data directory ready${NC}"

# ── Build ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}🔨 Building Lead Machine (this takes ~2 min on first run)...${NC}"
docker compose -f docker-compose.standalone.yml build

# ── Start ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}🚀 Starting Lead Machine...${NC}"
docker compose -f docker-compose.standalone.yml up -d

# ── Wait for health ────────────────────────────────────────────────────────────
echo -e "${CYAN}⏳ Waiting for services...${NC}"
READY=false
for i in $(seq 1 40); do
    if curl -sf http://localhost/api/v1/health > /dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 3
    echo -n "."
done
echo ""

if [ "$READY" = false ]; then
    echo -e "${YELLOW}⚠️  Services are taking longer than expected.${NC}"
    echo "   Check status with: docker compose -f docker-compose.standalone.yml logs"
else
    echo -e "${GREEN}✅ Lead Machine is ready!${NC}"
fi

# ── Get local IP ──────────────────────────────────────────────────────────────
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[^ ]+' || echo "")

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Lead Machine is running! 🚀            ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║   Local:    http://localhost             ║${NC}"
if [ -n "$LOCAL_IP" ]; then
echo -e "${GREEN}║   Network:  http://$LOCAL_IP           ║${NC}"
fi
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║   First time? Complete the Setup Wizard  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "Commands:"
echo "  Start:   docker compose -f docker-compose.standalone.yml up -d"
echo "  Stop:    docker compose -f docker-compose.standalone.yml down"
echo "  Logs:    docker compose -f docker-compose.standalone.yml logs -f"
echo "  Update:  git pull && docker compose -f docker-compose.standalone.yml up -d --build"
echo ""

# Open browser
if command -v open &> /dev/null; then
    open http://localhost
elif command -v xdg-open &> /dev/null; then
    xdg-open http://localhost
fi
