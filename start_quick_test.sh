#!/bin/bash
# Quick Test Configuration for DeepSeek Trading Strategy
# This script sets up environment variables for rapid testing

# Set fast test parameters
export TIMEFRAME='1m'                    # 1-minute bars for quick testing
export BASE_POSITION_USDT='30'           # Reduced position size
export EQUITY='400'                      # Account equity

# Navigate to project directory
cd /home/ubuntu/nautilus_deepseek

# Kill existing processes
pkill -f "main_live.py" 2>/dev/null
sleep 2

# Start the trading system with quick test settings
echo "=========================================="
echo "Starting Quick Test Mode"
echo "=========================================="
echo "Timeframe: 1 minute"
echo "Indicators will initialize in ~15 minutes"
echo "Analysis runs every 1 minute"
echo "=========================================="
echo ""

python main_live.py

