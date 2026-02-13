#!/bin/bash

# DeepSeek Trading Strategy Restart Script

cd /home/ubuntu/nautilus_deepseek

echo "🔄 Restarting trading strategy..."

# 先停止（如果正在运行）
if [ -f trader.pid ]; then
    PID=$(cat trader.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "🛑 Stopping existing process (PID: $PID)..."
        kill $PID
        sleep 3
        
        # 强制终止（如果还在运行）
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  Process still running, forcing termination..."
            kill -9 $PID
            sleep 1
        fi
        
        rm trader.pid
        echo "✅ Process stopped"
    else
        echo "⚠️  Process not running (PID: $PID)"
        rm trader.pid
    fi
else
    echo "ℹ️  No PID file found, checking for running processes..."
    # 查找并停止所有 main_live.py 进程
    pkill -f "main_live.py"
    sleep 2
fi

# 确保没有残留进程
if pgrep -f "main_live.py" > /dev/null; then
    echo "⚠️  Found running processes, killing them..."
    pkill -9 -f "main_live.py"
    sleep 1
fi

# 激活虚拟环境
source /home/ubuntu/deepseek_venv/bin/activate

# 创建日志目录
mkdir -p logs

# 启动新进程（直接在命令行设置环境变量）
echo "🚀 Starting new process..."
AUTO_CONFIRM=true EQUITY=400 nohup python main_live.py > logs/trader_$(date +%Y%m%d_%H%M%S).log 2>&1 &

# 保存 PID
echo $! > trader.pid

echo "✅ Trading strategy restarted with PID: $(cat trader.pid)"
echo "📋 View logs: tail -f logs/trader_*.log"
echo "🛑 Stop trader: kill $(cat trader.pid)"

