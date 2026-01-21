#!/bin/bash

# Setup script for DeepSeek AI Trading Strategy
# Supports Ubuntu 22.04+ with Python 3.11

set -e  # Exit on error

echo "======================================================================"
echo "DeepSeek AI Trading Strategy - Setup Script"
echo "======================================================================"
echo ""

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    OS_VERSION=$VERSION_ID
else
    OS="unknown"
fi

echo "Detected OS: $OS $OS_VERSION"

# =============================================================================
# Step 1: Ensure Python 3.11+ is installed
# =============================================================================
echo ""
echo "Step 1: Checking Python 3.11..."

install_python311_ubuntu() {
    echo "Installing Python 3.11 via deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install python3.11 python3.11-venv python3.11-dev -y
}

# Check if Python 3.11 is available
if command -v python3.11 &> /dev/null; then
    PYTHON_CMD="python3.11"
    echo "Python 3.11 found: $(python3.11 --version)"
elif command -v python3 &> /dev/null; then
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$py_version" == "3.11" ]] || [[ "$py_version" == "3.12" ]] || [[ "$py_version" == "3.13" ]]; then
        PYTHON_CMD="python3"
        echo "Python $py_version found (compatible)"
    else
        echo "Python $py_version found but 3.11+ required"
        if [[ "$OS" == "ubuntu" ]]; then
            install_python311_ubuntu
            PYTHON_CMD="python3.11"
        else
            echo "Please install Python 3.11+ manually"
            exit 1
        fi
    fi
else
    echo "Python 3 not found"
    if [[ "$OS" == "ubuntu" ]]; then
        install_python311_ubuntu
        PYTHON_CMD="python3.11"
    else
        echo "Please install Python 3.11+ manually"
        exit 1
    fi
fi

echo "Using Python: $PYTHON_CMD ($($PYTHON_CMD --version))"

# =============================================================================
# Step 2: Create virtual environment
# =============================================================================
echo ""
echo "Step 2: Setting up virtual environment..."

VENV_DIR="venv"

# Remove old venv if Python version mismatch
if [ -d "$VENV_DIR" ]; then
    existing_py=$($VENV_DIR/bin/python --version 2>/dev/null || echo "unknown")
    required_py=$($PYTHON_CMD --version)
    if [[ "$existing_py" != "$required_py" ]]; then
        echo "Existing venv has $existing_py, need $required_py"
        echo "Backing up old venv to venv_backup_$(date +%Y%m%d_%H%M%S)..."
        mv "$VENV_DIR" "venv_backup_$(date +%Y%m%d_%H%M%S)"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment with $PYTHON_CMD..."
    $PYTHON_CMD -m venv $VENV_DIR
    echo "Virtual environment created"
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# =============================================================================
# Step 3: Install dependencies
# =============================================================================
echo ""
echo "Step 3: Installing dependencies..."

pip install --upgrade pip -q
pip install -r requirements.txt

echo "Dependencies installed"

# Verify NautilusTrader version
NT_VERSION=$(python -c "import nautilus_trader; print(nautilus_trader.__version__)" 2>/dev/null || echo "unknown")
echo "NautilusTrader version: $NT_VERSION"

# =============================================================================
# Step 4: Create .env if needed
# =============================================================================
echo ""
echo "Step 4: Checking configuration..."

if [ ! -f ".env" ]; then
    if [ -f ".env.template" ]; then
        echo "Creating .env from template..."
        cp .env.template .env
        echo ".env created - PLEASE EDIT WITH YOUR API KEYS"
    else
        echo "Warning: .env.template not found"
    fi
else
    echo ".env already exists"
fi

# Create logs directory
mkdir -p logs

# =============================================================================
# Step 5: Setup systemd service (optional)
# =============================================================================
echo ""
echo "Step 5: Systemd service setup..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="/etc/systemd/system/nautilus-trader.service"

if [ -f "$SERVICE_FILE" ]; then
    echo "Systemd service already exists"
    echo "To update, run: sudo cp $SCRIPT_DIR/nautilus-trader.service $SERVICE_FILE && sudo systemctl daemon-reload"
else
    echo "To install systemd service, run:"
    echo "  sudo cp $SCRIPT_DIR/nautilus-trader.service $SERVICE_FILE"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl enable nautilus-trader"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "======================================================================"
echo "Setup Complete!"
echo "======================================================================"
echo ""
echo "Python:          $($PYTHON_CMD --version)"
echo "NautilusTrader:  $NT_VERSION"
echo "Virtual env:     $SCRIPT_DIR/$VENV_DIR"
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env with your API keys:"
echo "   nano .env"
echo ""
echo "2. Install systemd service (for auto-start):"
echo "   sudo cp nautilus-trader.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable nautilus-trader"
echo "   sudo systemctl start nautilus-trader"
echo ""
echo "3. Or run manually:"
echo "   source venv/bin/activate"
echo "   python main_live.py"
echo ""
echo "4. View logs:"
echo "   sudo journalctl -u nautilus-trader -f --no-hostname"
echo ""
