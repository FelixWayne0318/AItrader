#!/bin/bash
#
# Web Backend Port Conflict Fix (v1.0.0)
#
# Purpose: Fix port 8000 conflicts and restart web services
# Author: Auto-generated script
# Date: 2026-02-14
#
# This script:
# 1. Finds and kills processes using port 8000
# 2. Cleans up PM2 state
# 3. Restarts services from ecosystem.config.js
# 4. Verifies health
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print header
echo ""
echo "========================================"
echo "Web Port Conflict Fix (v1.0.0)"
echo "========================================"
echo ""

# Step 1: Find and kill processes on port 8000
echo -e "${BLUE}1. Checking for processes on port 8000...${NC}"

if command -v lsof &> /dev/null; then
    PIDS=$(sudo lsof -t -i:8000 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo -e "${YELLOW}  Found processes using port 8000: $PIDS${NC}"
        echo -e "${YELLOW}  Killing processes...${NC}"
        echo "$PIDS" | xargs -r sudo kill -9
        sleep 2
        echo -e "${GREEN}  ✓ Processes killed${NC}"
    else
        echo -e "${GREEN}  ✓ No processes found on port 8000${NC}"
    fi
elif command -v fuser &> /dev/null; then
    echo -e "${YELLOW}  Using fuser to kill port 8000...${NC}"
    sudo fuser -k 8000/tcp 2>/dev/null || echo "  No processes found"
    sleep 2
    echo -e "${GREEN}  ✓ Port cleared${NC}"
else
    echo -e "${YELLOW}  ⚠ Neither lsof nor fuser available, trying pkill...${NC}"
    pkill -f "uvicorn.*8000" || echo "  No uvicorn processes found"
    sleep 2
fi

# Step 2: Verify port is free
echo ""
echo -e "${BLUE}2. Verifying port 8000 is free...${NC}"
if command -v lsof &> /dev/null; then
    if sudo lsof -i:8000 &> /dev/null; then
        echo -e "${RED}  ✗ Port 8000 still occupied!${NC}"
        sudo lsof -i:8000
        exit 1
    else
        echo -e "${GREEN}  ✓ Port 8000 is free${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ Cannot verify (lsof not available), continuing...${NC}"
fi

# Step 3: Stop all PM2 services
echo ""
echo -e "${BLUE}3. Stopping PM2 services...${NC}"
pm2 stop all 2>/dev/null || echo "  No services to stop"
sleep 2
echo -e "${GREEN}  ✓ Services stopped${NC}"

# Step 4: Delete PM2 services
echo ""
echo -e "${BLUE}4. Cleaning PM2 process list...${NC}"
pm2 delete all 2>/dev/null || echo "  No services to delete"
sleep 1
echo -e "${GREEN}  ✓ PM2 process list cleaned${NC}"

# Step 5: Start services from ecosystem.config.js
echo ""
echo -e "${BLUE}5. Starting services from ecosystem.config.js...${NC}"
cd /home/linuxuser/nautilus_AItrader/web
pm2 start ecosystem.config.js
pm2 save
echo -e "${GREEN}  ✓ Services started${NC}"

# Step 6: Wait for services to start
echo ""
echo -e "${BLUE}6. Waiting for services to start (10 seconds)...${NC}"
sleep 10

# Step 7: Show PM2 status
echo ""
echo -e "${BLUE}7. PM2 Status:${NC}"
pm2 status

# Step 8: Check backend health
echo ""
echo -e "${BLUE}8. Checking backend health...${NC}"
HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/health 2>&1 || echo "FAILED")

if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}  ✓ Backend health check passed${NC}"
    echo "  Response: $HEALTH_RESPONSE"
else
    echo -e "${RED}  ✗ Backend health check failed${NC}"
    echo "  Response: $HEALTH_RESPONSE"
    echo ""
    echo -e "${YELLOW}Showing backend logs (last 50 lines):${NC}"
    pm2 logs algvex-backend --lines 50 --nostream
    exit 1
fi

# Step 9: Check frontend
echo ""
echo -e "${BLUE}9. Checking frontend...${NC}"
FRONTEND_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>&1 || echo "FAILED")

if [ "$FRONTEND_RESPONSE" = "200" ]; then
    echo -e "${GREEN}  ✓ Frontend accessible (HTTP 200)${NC}"
else
    echo -e "${YELLOW}  ⚠ Frontend returned: $FRONTEND_RESPONSE${NC}"
    echo "  This is normal if frontend is still loading"
fi

# Success
echo ""
echo "========================================"
echo -e "${GREEN}✅ Port conflict fix completed!${NC}"
echo "========================================"
echo ""
echo "Next steps:"
echo "  1. Visit http://139.180.157.152:3000 to verify website"
echo "  2. Check backend API: curl http://localhost:8000/health"
echo "  3. Monitor logs: pm2 logs --lines 50"
echo ""
