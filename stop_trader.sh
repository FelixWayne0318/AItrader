#!/bin/bash

# DeepSeek Trading Strategy Stop Script

if [ -f trader.pid ]; then
    PID=$(cat trader.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "🛑 Stopping trading strategy (PID: $PID)..."
        kill $PID
        sleep 2
        
        # 强制终止（如果还在运行）
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  Process still running, forcing termination..."
            kill -9 $PID
        fi
        
        rm trader.pid
        echo "✅ Trading strategy stopped"
    else
        echo "⚠️  Process not running (PID: $PID)"
        rm trader.pid
    fi
else
    echo "❌ No PID file found. Is the trader running?"
fi

