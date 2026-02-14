#!/bin/bash
#
# Backend Complete Fix Script (v1.0.0)
#
# Purpose: Comprehensive fix for all backend issues
# Author: Claude Code
# Date: 2026-02-14
#
# Run on server: cd /home/linuxuser/nautilus_AItrader/web && bash fix_backend_complete.sh
#
# This script:
# 1. Kills port 8000 processes
# 2. Creates/recreates virtual environment
# 3. Installs dependencies
# 4. Restarts PM2 services
# 5. Verifies health
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo "========================================"
echo "Backend Complete Fix (v1.0.0)"
echo "========================================"
echo ""

# Environment
REPO_DIR="/home/linuxuser/nautilus_AItrader"
if [ ! -d "$REPO_DIR" ]; then
    echo -e "${RED}✗ Repo directory not found: $REPO_DIR${NC}"
    exit 1
fi

cd "$REPO_DIR/web"
echo -e "${GREEN}✓ Working directory: $(pwd)${NC}"
echo ""

# Step 1: Kill port 8000 processes
echo -e "${BLUE}[1/9] Killing processes on port 8000${NC}"
echo "-------------------------------------------"
if command -v lsof &> /dev/null; then
    PIDS=$(sudo lsof -t -i:8000 2>/dev/null || true)
    if [ -n "$PIDS" ]; then
        echo -e "${YELLOW}Found processes: $PIDS${NC}"
        echo "$PIDS" | xargs -r sudo kill -9
        sleep 2
        echo -e "${GREEN}✓ Processes killed${NC}"
    else
        echo -e "${GREEN}✓ No processes found${NC}"
    fi
else
    echo -e "${YELLOW}⚠ lsof not available, using pkill${NC}"
    pkill -f "uvicorn.*8000" || echo "No uvicorn processes found"
    sleep 2
fi
echo ""

# Step 2: Stop PM2 services
echo -e "${BLUE}[2/9] Stopping PM2 services${NC}"
echo "-------------------------------------------"
pm2 stop all 2>/dev/null || echo "No services to stop"
sleep 2
echo -e "${GREEN}✓ Services stopped${NC}"
echo ""

# Step 3: Check Python version
echo -e "${BLUE}[3/9] Checking Python version${NC}"
echo "-------------------------------------------"
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD &> /dev/null; then
    echo -e "${RED}✗ python3 not found!${NC}"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1)
echo -e "${GREEN}✓ Python: $PYTHON_VERSION${NC}"

PYTHON_MAJOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)")

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 12 ]; }; then
    echo -e "${RED}✗ Python 3.12+ required (current: $PYTHON_VERSION)${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python version compatible${NC}"
echo ""

# Step 4: Create/recreate virtual environment
echo -e "${BLUE}[4/9] Setting up virtual environment${NC}"
echo "-------------------------------------------"
cd backend

if [ -d "venv" ]; then
    echo -e "${YELLOW}⚠ Removing existing venv${NC}"
    rm -rf venv
fi

echo "Creating new virtual environment..."
$PYTHON_CMD -m venv venv

if [ ! -f "venv/bin/python3" ]; then
    echo -e "${RED}✗ Failed to create venv${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Virtual environment created${NC}"
echo ""

# Step 5: Upgrade pip
echo -e "${BLUE}[5/9] Upgrading pip${NC}"
echo "-------------------------------------------"
venv/bin/python3 -m pip install --upgrade pip
echo -e "${GREEN}✓ Pip upgraded${NC}"
echo ""

# Step 6: Install dependencies
echo -e "${BLUE}[6/9] Installing dependencies${NC}"
echo "-------------------------------------------"
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}✗ requirements.txt not found!${NC}"
    exit 1
fi

echo "Installing packages (this may take a few minutes)..."
venv/bin/pip install -r requirements.txt

# Verify critical packages
echo ""
echo "Verifying critical packages:"
PACKAGES=("fastapi" "uvicorn" "sqlalchemy" "pandas" "empyrical-reloaded")
for pkg in "${PACKAGES[@]}"; do
    if venv/bin/pip show "$pkg" &> /dev/null; then
        VERSION=$(venv/bin/pip show "$pkg" | grep "Version:" | awk '{print $2}')
        echo -e "  ${GREEN}✓ $pkg ($VERSION)${NC}"
    else
        echo -e "  ${RED}✗ $pkg not installed${NC}"
    fi
done
echo ""

cd ..  # Back to web/
echo ""

# Step 7: Delete and restart PM2
echo -e "${BLUE}[7/9] Restarting PM2 services${NC}"
echo "-------------------------------------------"
pm2 delete all 2>/dev/null || echo "No services to delete"
sleep 1

echo "Starting services from ecosystem.config.js..."
pm2 start ecosystem.config.js
pm2 save
echo -e "${GREEN}✓ Services started${NC}"
echo ""

# Step 8: Wait and verify
echo -e "${BLUE}[8/9] Waiting for services (15 seconds)${NC}"
echo "-------------------------------------------"
sleep 15

pm2 status
echo ""

# Step 9: Health check
echo -e "${BLUE}[9/9] Health Check${NC}"
echo "-------------------------------------------"

# Check backend health
echo "Testing backend health..."
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/health 2>&1 || echo "FAILED")

if echo "$HEALTH_RESPONSE" | grep -q "200"; then
    echo -e "${GREEN}✓ Backend health check PASSED${NC}"
    echo "$HEALTH_RESPONSE" | head -3
elif echo "$HEALTH_RESPONSE" | grep -q "404"; then
    echo -e "${YELLOW}⚠ Backend responds but health endpoint returns 404${NC}"
    echo "Response: $HEALTH_RESPONSE"
    echo ""
    echo "Checking logs for errors..."
    pm2 logs algvex-backend --lines 30 --nostream
    exit 1
else
    echo -e "${RED}✗ Backend health check FAILED${NC}"
    echo "Response: $HEALTH_RESPONSE"
    echo ""
    echo "Showing backend logs..."
    pm2 logs algvex-backend --lines 50 --nostream
    exit 1
fi

echo ""

# Check frontend
echo "Testing frontend..."
FRONTEND_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>&1 || echo "FAILED")

if [ "$FRONTEND_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓ Frontend accessible (HTTP 200)${NC}"
else
    echo -e "${YELLOW}⚠ Frontend returned: $FRONTEND_RESPONSE${NC}"
fi

echo ""

# Success
echo "========================================"
echo -e "${GREEN}✅ Backend fix completed successfully!${NC}"
echo "========================================"
echo ""
echo "Summary:"
echo "  • Virtual environment: $(realpath backend/venv)"
echo "  • Python version: $($PYTHON_CMD --version)"
echo "  • Backend: http://localhost:8000/api/health"
echo "  • Frontend: http://localhost:3000"
echo "  • Public URL: http://139.180.157.152:3000"
echo ""
echo "Next steps:"
echo "  1. Visit http://139.180.157.152:3000 to verify website"
echo "  2. Monitor logs: pm2 logs --lines 50"
echo "  3. Check status: pm2 status"
echo ""
