#!/bin/bash
# 服务器健康检查脚本
# 用法: ./scripts/health_check.sh

set -e

BRANCH="main"
INSTALL_DIR="/home/linuxuser/nautilus_AItrader"
SERVICE_NAME="nautilus-trader"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

echo "========================================"
echo "  AItrader 服务器健康检查"
echo "========================================"
echo ""

# 函数：打印结果
check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((ERRORS++))
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARNINGS++))
}

# 1. 检查服务状态
echo ">> 1. 检查服务状态"
if systemctl is-active --quiet "$SERVICE_NAME"; then
    check_pass "服务 $SERVICE_NAME 正在运行"
else
    check_fail "服务 $SERVICE_NAME 未运行"
fi

# 2. 检查进程
echo ""
echo ">> 2. 检查进程"
if pgrep -f "python.*main_live.py" > /dev/null; then
    PID=$(pgrep -f "python.*main_live.py")
    check_pass "main_live.py 进程运行中 (PID: $PID)"
else
    check_fail "main_live.py 进程未找到"
fi

# 3. 检查 Git 分支和版本
echo ""
echo ">> 3. 检查代码版本"
cd "$INSTALL_DIR"
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" == "$BRANCH" ]; then
    check_pass "分支正确: $CURRENT_BRANCH"
else
    check_fail "分支错误: $CURRENT_BRANCH (应为 $BRANCH)"
fi

# 检查是否有未同步的提交
git fetch origin "$BRANCH" --quiet 2>/dev/null || true
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "unknown")
if [ "$LOCAL" == "$REMOTE" ]; then
    check_pass "代码已同步到最新"
    echo "        提交: $(git log --oneline -1)"
else
    check_warn "本地代码可能与远程不同步"
    echo "        本地: $(git log --oneline -1)"
fi

# 4. 检查 systemd 服务配置
echo ""
echo ">> 4. 检查服务配置"
SERVICE_FILE="/etc/systemd/system/nautilus-trader.service"
if [ -f "$SERVICE_FILE" ]; then
    # 检查入口文件
    if grep -q "main_live.py" "$SERVICE_FILE"; then
        check_pass "入口文件配置正确 (main_live.py)"
    else
        check_fail "入口文件配置错误 (应使用 main_live.py)"
    fi

    # 检查 AUTO_CONFIRM
    if grep -q "AUTO_CONFIRM=true" "$SERVICE_FILE"; then
        check_pass "AUTO_CONFIRM=true 已配置"
    else
        check_fail "缺少 AUTO_CONFIRM=true 配置"
    fi
else
    check_fail "服务配置文件不存在: $SERVICE_FILE"
fi

# 5. 检查环境变量文件
echo ""
echo ">> 5. 检查环境配置"
ENV_FILE="$INSTALL_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    check_pass ".env 文件存在"

    # 检查必要的环境变量
    for VAR in BINANCE_API_KEY BINANCE_API_SECRET DEEPSEEK_API_KEY; do
        if grep -q "^$VAR=" "$ENV_FILE" && ! grep -q "^$VAR=$" "$ENV_FILE"; then
            check_pass "$VAR 已配置"
        else
            check_fail "$VAR 未配置或为空"
        fi
    done

    # Telegram 配置（可选）
    if grep -q "^TELEGRAM_BOT_TOKEN=" "$ENV_FILE"; then
        check_pass "Telegram 已配置"
    else
        check_warn "Telegram 未配置（可选）"
    fi
else
    check_fail ".env 文件不存在"
fi

# 6. 检查 Python 虚拟环境
echo ""
echo ">> 6. 检查 Python 环境"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    check_pass "虚拟环境存在"
    PYTHON_VERSION=$("$VENV_PYTHON" --version 2>&1)
    echo "        Python 版本: $PYTHON_VERSION"
else
    check_fail "虚拟环境不存在: $VENV_PYTHON"
fi

# 7. 检查关键文件
echo ""
echo ">> 7. 检查关键文件"
for FILE in main_live.py strategy/deepseek_strategy.py utils/deepseek_client.py configs/strategy_config.yaml; do
    if [ -f "$INSTALL_DIR/$FILE" ]; then
        check_pass "$FILE 存在"
    else
        check_fail "$FILE 缺失"
    fi
done

# 8. 检查最近日志
echo ""
echo ">> 8. 检查最近日志"
RECENT_LOGS=$(journalctl -u "$SERVICE_NAME" -n 50 --no-hostname 2>/dev/null || echo "")

# 检查启动成功标志
if echo "$RECENT_LOGS" | grep -q "Strategy Started\|Instrument.*BTCUSDT"; then
    check_pass "策略已成功启动"
else
    check_warn "未检测到策略启动标志（可能刚重启）"
fi

# 检查错误
ERROR_COUNT=$(echo "$RECENT_LOGS" | grep -ci "error\|exception\|failed\|traceback" || echo "0")
if [ "$ERROR_COUNT" -gt 0 ]; then
    check_warn "日志中发现 $ERROR_COUNT 处错误/异常关键词"
else
    check_pass "最近日志无明显错误"
fi

# 检查止损相关
if echo "$RECENT_LOGS" | grep -q "Invalid stop_loss\|SL validation failed"; then
    check_warn "发现止损验证警告（已自动修正）"
fi

# 9. 检查内存使用
echo ""
echo ">> 9. 检查资源使用"
if pgrep -f "python.*main_live.py" > /dev/null; then
    PID=$(pgrep -f "python.*main_live.py")
    MEM=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{print int($1/1024)}')
    if [ -n "$MEM" ]; then
        if [ "$MEM" -lt 1000 ]; then
            check_pass "内存使用正常: ${MEM}MB"
        else
            check_warn "内存使用较高: ${MEM}MB"
        fi
    fi
fi

# 10. 检查网络连接
echo ""
echo ">> 10. 检查网络连接"
if curl -s --connect-timeout 5 https://api.binance.com/api/v3/ping > /dev/null 2>&1; then
    check_pass "Binance API 可达"
else
    check_fail "无法连接 Binance API"
fi

if curl -s --connect-timeout 5 https://api.deepseek.com > /dev/null 2>&1; then
    check_pass "DeepSeek API 可达"
else
    check_warn "无法连接 DeepSeek API（可能需要验证）"
fi

# 汇总
echo ""
echo "========================================"
echo "  检查结果汇总"
echo "========================================"
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}全部检查通过!${NC}"
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}通过，但有 $WARNINGS 个警告${NC}"
else
    echo -e "${RED}发现 $ERRORS 个错误，$WARNINGS 个警告${NC}"
fi

echo ""
echo ">> 最近5条日志:"
echo "----------------------------------------"
journalctl -u "$SERVICE_NAME" -n 5 --no-hostname 2>/dev/null || echo "无法获取日志"
echo "----------------------------------------"

exit $ERRORS
