#!/bin/bash

# DeepSeek Trading Strategy Startup Script

# 设置工作目录
cd /home/ubuntu/nautilus_deepseek

# 激活虚拟环境
source /home/ubuntu/deepseek_venv/bin/activate

# 设置环境变量（用于 systemd/supervisor）
export AUTO_CONFIRM=true
export EQUITY=400  # 实际账户余额

# 创建日志目录
mkdir -p logs

# 运行策略（后台运行）
nohup python main_live.py > logs/trader_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# 保存 PID
echo $! > trader.pid

echo "✅ Trading strategy started with PID: $(cat trader.pid)"
echo "📋 View logs: tail -f logs/trader_*.log"
echo "🛑 Stop trader: kill $(cat trader.pid)"

