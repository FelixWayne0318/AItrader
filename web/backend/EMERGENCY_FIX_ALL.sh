#!/bin/bash
# ============================================================================
# EMERGENCY_FIX_ALL.sh - Comprehensive One-Command Fix
# ============================================================================
# Purpose: Fix ALL web backend/frontend issues in ONE command
# Usage: bash EMERGENCY_FIX_ALL.sh
# ============================================================================

set -e  # Exit on any error
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(dirname "$SCRIPT_DIR")"
REPO_DIR="$(dirname "$WEB_DIR")"
BACKEND_DIR="$WEB_DIR/backend"
FRONTEND_DIR="$WEB_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"

echo "============================================================================"
echo "EMERGENCY FIX ALL - Starting Comprehensive Repair"
echo "============================================================================"
echo "Repository: $REPO_DIR"
echo "Web Directory: $WEB_DIR"
echo "Backend: $BACKEND_DIR"
echo "Frontend: $FRONTEND_DIR"
echo ""

# ============================================================================
# Step 1: Git - Handle Local Changes and Pull Latest Code
# ============================================================================
echo "[1/10] Handling Git State..."
cd "$REPO_DIR"

# Check if there are uncommitted changes
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "  ⚠️  Uncommitted changes detected"
    echo "  📦 Stashing local changes..."
    git stash push -m "Emergency fix: auto-stashed $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  ✅ Changes stashed"
else
    echo "  ✅ No uncommitted changes"
fi

# Pull latest code
echo "  🔄 Pulling latest code from origin..."
if git pull origin "$(git rev-parse --abbrev-ref HEAD)"; then
    echo "  ✅ Code updated successfully"
else
    echo "  ❌ Failed to pull code"
    exit 1
fi

# ============================================================================
# Step 2: Kill Port 8000 Processes
# ============================================================================
echo ""
echo "[2/10] Cleaning Port 8000..."
PORT=8000
PIDS=$(lsof -ti:$PORT 2>/dev/null || true)

if [ -n "$PIDS" ]; then
    echo "  ⚠️  Found processes on port $PORT: $PIDS"
    for PID in $PIDS; do
        if ps -p $PID > /dev/null 2>&1; then
            PROC_INFO=$(ps -p $PID -o comm=,args= 2>/dev/null || echo "unknown")
            echo "  🔪 Killing PID $PID: $PROC_INFO"
            kill -9 $PID 2>/dev/null || true
            sleep 0.5
        fi
    done

    # Verify port is free
    sleep 1
    if lsof -ti:$PORT > /dev/null 2>&1; then
        echo "  ❌ Port $PORT still in use after cleanup"
        exit 1
    else
        echo "  ✅ Port $PORT freed"
    fi
else
    echo "  ✅ Port $PORT already free"
fi

# ============================================================================
# Step 3: PM2 - Stop and Delete Services
# ============================================================================
echo ""
echo "[3/10] Stopping PM2 Services..."
cd "$WEB_DIR"

# Stop services if running
if pm2 describe algvex-backend > /dev/null 2>&1; then
    echo "  🛑 Stopping algvex-backend..."
    pm2 stop algvex-backend || true
fi

if pm2 describe algvex-frontend > /dev/null 2>&1; then
    echo "  🛑 Stopping algvex-frontend..."
    pm2 stop algvex-frontend || true
fi

# Delete services to clean state
echo "  🗑️  Deleting old PM2 apps..."
pm2 delete algvex-backend 2>/dev/null || true
pm2 delete algvex-frontend 2>/dev/null || true

# Kill PM2 daemon to reset state
echo "  🔄 Resetting PM2 daemon..."
pm2 kill

echo "  ✅ PM2 services cleaned"

# ============================================================================
# Step 4: Backend - Check Python Version
# ============================================================================
echo ""
echo "[4/10] Verifying Python Version..."
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+')

if [ "$(printf '%s\n' "3.12" "$PYTHON_VERSION" | sort -V | head -n1)" != "3.12" ]; then
    echo "  ❌ Python version $PYTHON_VERSION is too old (need >= 3.12)"
    exit 1
else
    echo "  ✅ Python $PYTHON_VERSION is compatible"
fi

# ============================================================================
# Step 5: Backend - Create/Recreate Virtual Environment
# ============================================================================
echo ""
echo "[5/10] Setting Up Backend Virtual Environment..."
cd "$BACKEND_DIR"

# Remove old venv if exists
if [ -d "$VENV_DIR" ]; then
    echo "  🗑️  Removing old venv..."
    rm -rf "$VENV_DIR"
fi

# Create fresh venv
echo "  📦 Creating new venv..."
python3 -m venv venv

# Verify venv creation
if [ ! -f "$VENV_DIR/bin/python3" ]; then
    echo "  ❌ Failed to create venv"
    exit 1
fi

echo "  ✅ Virtual environment created"

# ============================================================================
# Step 6: Backend - Install Dependencies
# ============================================================================
echo ""
echo "[6/10] Installing Backend Dependencies..."
cd "$BACKEND_DIR"

# Activate venv
source venv/bin/activate

# Upgrade pip
echo "  📦 Upgrading pip..."
python3 -m pip install --upgrade pip > /dev/null 2>&1

# Install dependencies
echo "  📦 Installing requirements..."
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo "  ✅ Dependencies installed"
else
    echo "  ❌ requirements.txt not found"
    exit 1
fi

# Verify critical packages
echo "  🔍 Verifying critical packages..."
MISSING_PACKAGES=()

for PKG in fastapi uvicorn pydantic empyrical-reloaded pandas; do
    if ! python3 -c "import ${PKG//-/_}" 2>/dev/null; then
        MISSING_PACKAGES+=("$PKG")
    fi
done

if [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo "  ❌ Missing packages: ${MISSING_PACKAGES[*]}"
    exit 1
else
    echo "  ✅ All critical packages installed"
fi

# ============================================================================
# Step 7: Frontend - Install Dependencies
# ============================================================================
echo ""
echo "[7/10] Installing Frontend Dependencies..."
cd "$FRONTEND_DIR"

if [ -f "package.json" ]; then
    echo "  📦 Running npm install..."
    npm install
    echo "  ✅ Frontend dependencies installed"
else
    echo "  ⚠️  package.json not found, skipping"
fi

# ============================================================================
# Step 8: Frontend - Clear Cache and Rebuild
# ============================================================================
echo ""
echo "[8/10] Rebuilding Frontend..."
cd "$FRONTEND_DIR"

# Clear Next.js cache
if [ -d ".next" ]; then
    echo "  🗑️  Clearing .next cache..."
    rm -rf .next
fi

# Rebuild
echo "  🔨 Building frontend..."
if npm run build; then
    echo "  ✅ Frontend built successfully"
else
    echo "  ❌ Frontend build failed"
    exit 1
fi

# ============================================================================
# Step 9: Start PM2 Services
# ============================================================================
echo ""
echo "[9/10] Starting PM2 Services..."
cd "$WEB_DIR"

# Verify ecosystem.config.js exists
if [ ! -f "ecosystem.config.js" ]; then
    echo "  ❌ ecosystem.config.js not found"
    exit 1
fi

# Start services
echo "  🚀 Starting backend and frontend..."
pm2 start ecosystem.config.js

# Wait for startup
echo "  ⏳ Waiting for services to initialize (5 seconds)..."
sleep 5

# Check PM2 status
echo "  📊 PM2 Status:"
pm2 list

# ============================================================================
# Step 10: Health Check
# ============================================================================
echo ""
echo "[10/10] Running Health Checks..."

# Check backend health
echo "  🏥 Checking backend health..."
BACKEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/health || echo "000")

if [ "$BACKEND_HEALTH" = "200" ]; then
    echo "  ✅ Backend health check passed (HTTP $BACKEND_HEALTH)"
else
    echo "  ❌ Backend health check failed (HTTP $BACKEND_HEALTH)"
    echo ""
    echo "  📋 Last 20 lines of backend logs:"
    pm2 logs algvex-backend --lines 20 --nostream
    exit 1
fi

# Check frontend
echo "  🏥 Checking frontend..."
FRONTEND_STATUS=$(pm2 describe algvex-frontend 2>&1 | grep -oP 'status\s*│\s*\K\w+' || echo "unknown")

if [ "$FRONTEND_STATUS" = "online" ]; then
    echo "  ✅ Frontend is online"
else
    echo "  ⚠️  Frontend status: $FRONTEND_STATUS"
fi

# ============================================================================
# Final Report
# ============================================================================
echo ""
echo "============================================================================"
echo "✅ EMERGENCY FIX COMPLETED SUCCESSFULLY"
echo "============================================================================"
echo ""
echo "🔗 Access URLs:"
echo "   Frontend: http://$(hostname -I | awk '{print $1}'):3000"
echo "   Backend:  http://$(hostname -I | awk '{print $1}'):8000"
echo "   API Docs: http://$(hostname -I | awk '{print $1}'):8000/docs"
echo ""
echo "📊 Service Status:"
pm2 list
echo ""
echo "💡 Useful Commands:"
echo "   View logs:    pm2 logs"
echo "   Restart:      pm2 restart ecosystem.config.js"
echo "   Stop:         pm2 stop all"
echo "   Monitor:      pm2 monit"
echo ""
echo "============================================================================"
