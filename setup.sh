#!/bin/bash

# Setup script for DeepSeek AI Trading Strategy

set -e  # Exit on error

echo "======================================================================"
echo "DeepSeek AI Trading Strategy - Setup Script"
echo "======================================================================"

# Check Python version
echo ""
echo "📋 Checking Python version..."
python_version=$(python --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

if [[ "$python_version" < "3.10" ]]; then
    echo "❌ Python 3.10 or higher required. Please upgrade."
    exit 1
fi
echo "✅ Python version OK"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo ""
    echo "📦 Creating virtual environment..."
    python -m venv venv
    echo "✅ Virtual environment created"
else
    echo ""
    echo "ℹ️  Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "🔌 Activating virtual environment..."
source venv/bin/activate || . venv/Scripts/activate
echo "✅ Virtual environment activated"

# Upgrade pip
echo ""
echo "⬆️  Upgrading pip..."
pip install --upgrade pip -q
echo "✅ pip upgraded"

# Install dependencies
echo ""
echo "📚 Installing dependencies..."
pip install -r requirements.txt
echo "✅ Dependencies installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "📝 Creating .env file from template..."
    cp .env.template .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your API keys:"
    echo "   - BINANCE_API_KEY"
    echo "   - BINANCE_API_SECRET"
    echo "   - DEEPSEEK_API_KEY"
else
    echo ""
    echo "ℹ️  .env file already exists"
fi

# Create logs directory
if [ ! -d "logs" ]; then
    echo ""
    echo "📂 Creating logs directory..."
    mkdir -p logs
    echo "✅ logs directory created"
fi

# Summary
echo ""
echo "======================================================================"
echo "Setup Complete! 🎉"
echo "======================================================================"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your API keys:"
echo "   nano .env"
echo ""
echo "2. Review configuration:"
echo "   cat configs/strategy_config.yaml"
echo ""
echo "3. (Optional) Set TEST_MODE=true in .env for simulation"
echo ""
echo "4. Run the strategy:"
echo "   python main_live.py"
echo ""
echo "For detailed instructions, see README.md"
echo ""
