#!/bin/bash

# Setup script for DeepSeek AI Trading Strategy
# Supports Ubuntu 22.04+ with Python 3.12+

set -e  # Exit on error

echo "======================================================================"
echo "DeepSeek AI Trading Strategy - Setup Script"
echo "======================================================================"
echo ""

# =============================================================================
# Step 0: 停止所有运行中的实例 (防止多实例冲突)
# =============================================================================
echo "Step 0: 停止运行中的实例..."

# 停止 systemd 服务 (如果存在)
if systemctl is-active --quiet nautilus-trader 2>/dev/null; then
    echo "停止 systemd 服务..."
    sudo systemctl stop nautilus-trader
fi

# 清理所有 main_live.py 进程
if pgrep -f "main_live.py" > /dev/null 2>&1; then
    echo "发现运行中的 main_live.py 进程，正在停止..."
    sudo pkill -f "main_live.py" || true
    sleep 2
    # 如果还有残留，强制杀掉
    if pgrep -f "main_live.py" > /dev/null 2>&1; then
        echo "强制终止残留进程..."
        sudo pkill -9 -f "main_live.py" || true
        sleep 1
    fi
    echo "已清理所有旧进程"
else
    echo "没有运行中的实例"
fi

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
# Step 1: Ensure Python 3.12+ is installed (NautilusTrader 1.222.0 requires >= 3.12)
# =============================================================================
echo ""
echo "Step 1: Checking Python 3.12+..."

install_python312_ubuntu() {
    echo "Installing Python 3.12 via deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    sudo apt update
    sudo apt install python3.12 python3.12-venv python3.12-dev -y
}

# Check if Python 3.12 is available
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
    echo "Python 3.12 found: $(python3.12 --version)"
elif command -v python3 &> /dev/null; then
    py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    if [[ "$py_version" == "3.12" ]] || [[ "$py_version" == "3.13" ]] || [[ "$py_version" == "3.14" ]]; then
        PYTHON_CMD="python3"
        echo "Python $py_version found (compatible)"
    else
        echo "Python $py_version found but 3.12+ required"
        if [[ "$OS" == "ubuntu" ]]; then
            install_python312_ubuntu
            PYTHON_CMD="python3.12"
        else
            echo "Please install Python 3.12+ manually"
            exit 1
        fi
    fi
else
    echo "Python 3 not found"
    if [[ "$OS" == "ubuntu" ]]; then
        install_python312_ubuntu
        PYTHON_CMD="python3.12"
    else
        echo "Please install Python 3.12+ manually"
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
# Step 4: Create .env if needed (支持永久存储)
# =============================================================================
echo ""
echo "Step 4: Checking configuration..."

# 永久存储位置
ENV_PERMANENT="$HOME/.env.aitrader"

# 检查是否已有永久配置
if [ -f "${ENV_PERMANENT}" ]; then
    echo "Found permanent config: ${ENV_PERMANENT}"
    # 确保软链接存在
    if [ ! -L ".env" ] || [ "$(readlink -f .env)" != "${ENV_PERMANENT}" ]; then
        rm -f .env 2>/dev/null || true
        ln -sf "${ENV_PERMANENT}" .env
        echo "Created symlink: .env -> ${ENV_PERMANENT}"
    else
        echo "Symlink already correct"
    fi
elif [ -f ".env" ] && [ ! -L ".env" ]; then
    # 存在旧的 .env 文件（非软链接），迁移到永久位置
    echo "Migrating existing .env to permanent location..."
    cp .env "${ENV_PERMANENT}"
    chmod 600 "${ENV_PERMANENT}"
    rm -f .env
    ln -sf "${ENV_PERMANENT}" .env
    echo "Migrated to ${ENV_PERMANENT}"
elif [ -f ".env.template" ]; then
    # 首次安装，从模板创建
    echo "First time setup, creating config from template..."
    cp .env.template "${ENV_PERMANENT}"
    chmod 600 "${ENV_PERMANENT}"
    ln -sf "${ENV_PERMANENT}" .env
    echo "Created ${ENV_PERMANENT} - PLEASE EDIT WITH YOUR API KEYS"
    echo "  nano ${ENV_PERMANENT}"
else
    echo "Warning: .env.template not found"
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
