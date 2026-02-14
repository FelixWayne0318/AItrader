#!/bin/bash
#
# Backend Comprehensive Diagnostic Tool (v1.0.0)
#
# Purpose: Deep analysis of why backend fails to start
# Author: Claude Code
# Date: 2026-02-14
#
# Run on server: cd /home/linuxuser/nautilus_AItrader/web && bash diagnose_backend.sh
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
echo "Backend Deep Diagnostic (v1.0.0)"
echo "========================================"
echo ""

# Step 1: Environment Detection
echo -e "${BLUE}[1/10] Environment Detection${NC}"
echo "-------------------------------------------"
REPO_DIR="/home/linuxuser/nautilus_AItrader"
if [ ! -d "$REPO_DIR" ]; then
    echo -e "${RED}✗ Repo directory not found: $REPO_DIR${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Repo directory: $REPO_DIR${NC}"
cd "$REPO_DIR/web"
echo -e "${GREEN}✓ Working directory: $(pwd)${NC}"
echo ""

# Step 2: Backend Directory Structure
echo -e "${BLUE}[2/10] Backend Directory Structure${NC}"
echo "-------------------------------------------"
if [ ! -d "backend" ]; then
    echo -e "${RED}✗ backend/ directory not found!${NC}"
    exit 1
fi
echo -e "${GREEN}✓ backend/ directory exists${NC}"

echo ""
echo "Directory tree:"
tree -L 3 backend 2>/dev/null || find backend -maxdepth 3 -type f -o -type d | head -50
echo ""

# Step 3: Virtual Environment Check
echo -e "${BLUE}[3/10] Virtual Environment Check${NC}"
echo "-------------------------------------------"
if [ -d "backend/venv" ]; then
    echo -e "${GREEN}✓ venv/ exists${NC}"
    if [ -f "backend/venv/bin/python3" ]; then
        echo -e "${GREEN}✓ python3 executable found${NC}"
        PYTHON_VERSION=$(backend/venv/bin/python3 --version 2>&1)
        echo "  Python version: $PYTHON_VERSION"
    else
        echo -e "${RED}✗ python3 executable not found in venv/bin/${NC}"
    fi

    if [ -f "backend/venv/bin/uvicorn" ]; then
        echo -e "${GREEN}✓ uvicorn executable found${NC}"
    else
        echo -e "${YELLOW}⚠ uvicorn executable not found (will use 'python -m uvicorn')${NC}"
    fi
else
    echo -e "${RED}✗ venv/ directory NOT FOUND!${NC}"
    echo ""
    echo -e "${YELLOW}This is likely the ROOT CAUSE of backend startup failure.${NC}"
    echo ""
    echo "Expected path: $REPO_DIR/web/backend/venv"
    echo ""
    echo "Solution: Create virtual environment"
    echo "  cd $REPO_DIR/web/backend"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo ""
fi
echo ""

# Step 4: Dependencies Check
echo -e "${BLUE}[4/10] Dependencies Check${NC}"
echo "-------------------------------------------"
if [ -f "backend/requirements.txt" ]; then
    echo -e "${GREEN}✓ requirements.txt exists${NC}"
    echo ""
    echo "Key dependencies:"
    grep -E "(fastapi|uvicorn|empyrical|pandas)" backend/requirements.txt | head -10
    echo ""

    if [ -f "backend/venv/bin/python3" ]; then
        echo "Installed packages (sample):"
        backend/venv/bin/pip list 2>/dev/null | grep -E "(fastapi|uvicorn|empyrical|pandas)" || echo "  (venv not activated or pip not available)"
    fi
else
    echo -e "${RED}✗ requirements.txt not found!${NC}"
fi
echo ""

# Step 5: PM2 Configuration
echo -e "${BLUE}[5/10] PM2 Configuration Check${NC}"
echo "-------------------------------------------"
if [ -f "ecosystem.config.js" ]; then
    echo -e "${GREEN}✓ ecosystem.config.js exists${NC}"
    echo ""
    echo "Backend configuration:"
    grep -A 15 "name: 'algvex-backend'" ecosystem.config.js | head -20
else
    echo -e "${RED}✗ ecosystem.config.js not found!${NC}"
fi
echo ""

# Step 6: PM2 Process Status
echo -e "${BLUE}[6/10] PM2 Process Status${NC}"
echo "-------------------------------------------"
if command -v pm2 &> /dev/null; then
    pm2 status 2>&1 | grep -E "(algvex|name|status|cpu|memory)" || echo "No PM2 processes found"
    echo ""

    PM2_BACKEND_STATUS=$(pm2 jlist 2>/dev/null | jq -r '.[] | select(.name == "algvex-backend") | .pm2_env.status' 2>/dev/null || echo "not_found")
    if [ "$PM2_BACKEND_STATUS" = "online" ]; then
        echo -e "${GREEN}✓ Backend status: online${NC}"
    elif [ "$PM2_BACKEND_STATUS" = "errored" ]; then
        echo -e "${RED}✗ Backend status: errored${NC}"
    elif [ "$PM2_BACKEND_STATUS" = "stopped" ]; then
        echo -e "${YELLOW}⚠ Backend status: stopped${NC}"
    else
        echo -e "${YELLOW}⚠ Backend not found in PM2 list${NC}"
    fi

    echo ""
    RESTARTS=$(pm2 jlist 2>/dev/null | jq -r '.[] | select(.name == "algvex-backend") | .pm2_env.restart_time' 2>/dev/null || echo "0")
    echo "Restart count: $RESTARTS"
else
    echo -e "${RED}✗ PM2 not installed${NC}"
fi
echo ""

# Step 7: Port 8000 Check
echo -e "${BLUE}[7/10] Port 8000 Status${NC}"
echo "-------------------------------------------"
if command -v lsof &> /dev/null; then
    if sudo lsof -i:8000 &> /dev/null; then
        echo -e "${GREEN}✓ Port 8000 is occupied${NC}"
        echo ""
        sudo lsof -i:8000
    else
        echo -e "${YELLOW}⚠ Port 8000 is FREE (backend not listening)${NC}"
    fi
else
    echo -e "${YELLOW}⚠ lsof not available${NC}"
fi
echo ""

# Step 8: Health Endpoint Test
echo -e "${BLUE}[8/10] Health Endpoint Test${NC}"
echo "-------------------------------------------"
echo "Testing http://localhost:8000/api/health"
HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/health 2>&1 || echo "CURL_FAILED")

if echo "$HEALTH_RESPONSE" | grep -q "200"; then
    echo -e "${GREEN}✓ Health check successful (HTTP 200)${NC}"
    echo "$HEALTH_RESPONSE"
elif echo "$HEALTH_RESPONSE" | grep -q "404"; then
    echo -e "${RED}✗ Health check returned 404 Not Found${NC}"
    echo "$HEALTH_RESPONSE"
    echo ""
    echo "Possible causes:"
    echo "  1. Backend is running but routes not registered"
    echo "  2. Wrong endpoint path in health check"
elif echo "$HEALTH_RESPONSE" | grep -q "CURL_FAILED"; then
    echo -e "${RED}✗ Cannot connect to backend (Connection refused)${NC}"
    echo ""
    echo "Possible causes:"
    echo "  1. Backend not running"
    echo "  2. Port 8000 not listening"
    echo "  3. Firewall blocking connection"
else
    echo -e "${YELLOW}⚠ Unexpected response${NC}"
    echo "$HEALTH_RESPONSE"
fi
echo ""

# Step 9: Backend Logs Analysis
echo -e "${BLUE}[9/10] Backend Logs Analysis${NC}"
echo "-------------------------------------------"
if command -v pm2 &> /dev/null; then
    echo "Last 30 lines of backend logs:"
    pm2 logs algvex-backend --lines 30 --nostream 2>&1 || echo "Cannot read logs"
else
    echo -e "${YELLOW}⚠ PM2 not available${NC}"
fi
echo ""

# Step 10: Config File Validation
echo -e "${BLUE}[10/10] Config File Validation${NC}"
echo "-------------------------------------------"
if [ -f "backend/.env" ]; then
    echo -e "${GREEN}✓ backend/.env exists${NC}"
    echo ""
    echo "Environment variables (non-sensitive):"
    grep -v -E "(SECRET|KEY|PASSWORD)" backend/.env | head -10 || echo "  (file is empty or all sensitive)"
else
    echo -e "${YELLOW}⚠ backend/.env not found (using defaults)${NC}"
fi

if [ -f "$HOME/.env.aitrader" ]; then
    echo -e "${GREEN}✓ ~/.env.aitrader exists${NC}"
else
    echo -e "${YELLOW}⚠ ~/.env.aitrader not found${NC}"
fi

if [ -f "$REPO_DIR/configs/base.yaml" ]; then
    echo -e "${GREEN}✓ configs/base.yaml exists${NC}"
else
    echo -e "${RED}✗ configs/base.yaml not found!${NC}"
fi
echo ""

# Summary
echo "========================================"
echo -e "${CYAN}Diagnostic Summary${NC}"
echo "========================================"
echo ""

ISSUES_FOUND=0

if [ ! -d "backend/venv" ]; then
    echo -e "${RED}[CRITICAL] Virtual environment missing${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

if [ ! -f "backend/venv/bin/python3" ]; then
    echo -e "${RED}[CRITICAL] Python executable not found in venv${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

if ! sudo lsof -i:8000 &> /dev/null; then
    echo -e "${YELLOW}[WARNING] Port 8000 not listening${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

if ! curl -s http://localhost:8000/api/health | grep -q "healthy"; then
    echo -e "${YELLOW}[WARNING] Health check failed${NC}"
    ISSUES_FOUND=$((ISSUES_FOUND + 1))
fi

if [ $ISSUES_FOUND -eq 0 ]; then
    echo -e "${GREEN}✅ No critical issues found!${NC}"
else
    echo ""
    echo -e "${RED}Found $ISSUES_FOUND issue(s) - see details above${NC}"
fi

echo ""
echo "========================================"
echo "Diagnostic Complete"
echo "========================================"
echo ""
