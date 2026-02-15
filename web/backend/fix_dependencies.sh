#!/bin/bash
# Web Backend Dependency Fix Script (v3.0.2)
# Fixes recurring pandas-datareader incompatibility with Python 3.12
# See: web/backend/DEPENDENCY_ROOT_CAUSE.md

set -e

echo "========================================"
echo "Web Backend Dependency Fix (v3.0.2)"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to backend directory
BACKEND_DIR="/home/linuxuser/nautilus_AItrader/web/backend"
cd "$BACKEND_DIR" || exit 1

echo -e "${YELLOW}1. Stopping backend service...${NC}"
pm2 stop algvex-backend || echo "  (service not running)"
echo ""

echo -e "${YELLOW}2. Activating virtual environment...${NC}"
if [ ! -f "venv/bin/activate" ]; then
    echo -e "${RED}ERROR: venv not found. Creating venv...${NC}"
    python3 -m venv venv
fi
source venv/bin/activate
echo "  ✓ venv activated"
echo ""

echo -e "${YELLOW}3. Removing problematic packages...${NC}"
echo "  - Uninstalling empyrical (unmaintained)"
echo "  - Uninstalling pandas-datareader (Python 3.12 incompatible)"
pip uninstall -y empyrical pandas-datareader 2>/dev/null || echo "  (packages not found)"
echo "  ✓ Old packages removed"
echo ""

echo -e "${YELLOW}4. Installing empyrical-reloaded...${NC}"
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
echo "  ✓ Dependencies installed"
echo ""

echo -e "${YELLOW}5. Verification...${NC}"
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
echo "  Python version: $PYTHON_VERSION"

EMPYRICAL_VERSION=$(python3 -c "import empyrical; print(empyrical.__version__)" 2>/dev/null || echo "FAILED")
if [ "$EMPYRICAL_VERSION" = "FAILED" ]; then
    echo -e "${RED}  ✗ empyrical import failed!${NC}"
    exit 1
else
    echo -e "${GREEN}  ✓ empyrical version: $EMPYRICAL_VERSION${NC}"
fi

PANDAS_VERSION=$(python3 -c "import pandas; print(pandas.__version__)" 2>/dev/null || echo "FAILED")
if [ "$PANDAS_VERSION" = "FAILED" ]; then
    echo -e "${RED}  ✗ pandas import failed!${NC}"
    exit 1
else
    echo -e "${GREEN}  ✓ pandas version: $PANDAS_VERSION${NC}"
fi

# Test import of performance_service
echo "  Testing performance_service import..."
python3 -c "
import sys
sys.path.insert(0, '.')
from services.performance_service import PerformanceService
print('  ✓ performance_service import successful')
" || {
    echo -e "${RED}  ✗ performance_service import failed!${NC}"
    echo "  Check logs for details"
    exit 1
}
echo ""

echo -e "${YELLOW}6. Restarting backend service...${NC}"
pm2 restart algvex-backend
sleep 2
echo "  ✓ Service restarted"
echo ""

echo -e "${YELLOW}7. Checking service status...${NC}"
pm2 status algvex-backend
echo ""

echo -e "${YELLOW}8. Recent logs (last 30 lines)...${NC}"
pm2 logs algvex-backend --lines 30 --nostream
echo ""

echo -e "${GREEN}========================================"
echo "✅ Dependency fix completed!"
echo "========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Monitor logs: pm2 logs algvex-backend --lines 50"
echo "  2. Check health: curl http://localhost:8000/api/health"
echo "  3. If issues persist, check: web/backend/DEPENDENCY_ROOT_CAUSE.md"
echo ""
