#!/bin/bash
# 服务器健康检查脚本 (v2.0 - 崩溃诊断增强版)
# 用法: ./scripts/health_check.sh

set -e

BRANCH="main"
INSTALL_DIR="/home/linuxuser/nautilus_AItrader"
SERVICE_NAME="nautilus-trader"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0
CRITICAL=0

echo "========================================"
echo "  AItrader 服务器健康检查 v2.0"
echo "  崩溃诊断增强版"
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

check_critical() {
    echo -e "${RED}[CRITICAL]${NC} $1"
    ((CRITICAL++))
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# 1. 检查服务状态
echo ">> 1. 检查服务状态"
if systemctl is-active --quiet "$SERVICE_NAME"; then
    check_pass "服务 $SERVICE_NAME 正在运行"

    # 检查服务启动时间
    UPTIME=$(systemctl show "$SERVICE_NAME" -p ActiveEnterTimestamp --value)
    info "启动时间: $UPTIME"
else
    check_fail "服务 $SERVICE_NAME 未运行"
fi

# 2. 检查进程
echo ""
echo ">> 2. 检查进程状态"
if pgrep -f "python.*main_live.py" > /dev/null; then
    PID=$(pgrep -f "python.*main_live.py")
    check_pass "main_live.py 进程运行中 (PID: $PID)"

    # 检查进程状态 (是否为僵尸进程)
    PROC_STATE=$(ps -o stat= -p "$PID" 2>/dev/null || echo "unknown")
    if echo "$PROC_STATE" | grep -q "Z"; then
        check_critical "进程为僵尸状态 (defunct) - 需要重启"
    elif echo "$PROC_STATE" | grep -q "D"; then
        check_warn "进程处于不可中断睡眠 (可能 I/O 等待)"
    else
        info "进程状态: $PROC_STATE (正常)"
    fi

    # 检查线程数 (Telegram 后台线程泄漏检测)
    THREAD_COUNT=$(ps -o nlwp= -p "$PID" 2>/dev/null || echo "0")
    if [ "$THREAD_COUNT" -gt 50 ]; then
        check_critical "线程数异常: $THREAD_COUNT (>50, 可能线程泄漏)"
    elif [ "$THREAD_COUNT" -gt 20 ]; then
        check_warn "线程数偏高: $THREAD_COUNT (正常应 < 20)"
    else
        info "线程数: $THREAD_COUNT (正常)"
    fi
else
    check_fail "main_live.py 进程未找到"
    PID=""
fi

# 3. 检查 systemd 重启历史 (崩溃频率检测)
echo ""
echo ">> 3. 检查崩溃历史"
RESTART_COUNT=$(systemctl show "$SERVICE_NAME" -p NRestarts --value 2>/dev/null || echo "0")
if [ "$RESTART_COUNT" -eq 0 ]; then
    check_pass "未发现服务重启 (系统稳定)"
elif [ "$RESTART_COUNT" -lt 5 ]; then
    check_warn "服务已重启 $RESTART_COUNT 次"
else
    check_critical "服务已重启 $RESTART_COUNT 次 (频繁崩溃)"
fi

# 检查最近重启时间
LAST_EXIT_CODE=$(systemctl show "$SERVICE_NAME" -p ExecMainStatus --value 2>/dev/null || echo "0")
if [ "$LAST_EXIT_CODE" -ne 0 ]; then
    check_warn "上次退出码: $LAST_EXIT_CODE (非正常退出)"
fi

# 4. 检查内存使用 (OOM 风险检测)
echo ""
echo ">> 4. 检查内存使用"
if [ -n "$PID" ]; then
    MEM_RSS=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{print int($1/1024)}')
    MEM_VSZ=$(ps -o vsz= -p "$PID" 2>/dev/null | awk '{print int($1/1024)}')

    if [ -n "$MEM_RSS" ]; then
        if [ "$MEM_RSS" -gt 1800 ]; then
            check_critical "内存使用过高: ${MEM_RSS}MB (RSS) / ${MEM_VSZ}MB (VSZ) - 接近 OOM"
        elif [ "$MEM_RSS" -gt 1200 ]; then
            check_warn "内存使用偏高: ${MEM_RSS}MB (RSS) / ${MEM_VSZ}MB (VSZ)"
        else
            check_pass "内存使用正常: ${MEM_RSS}MB (RSS) / ${MEM_VSZ}MB (VSZ)"
        fi

        # 检查内存增长趋势 (简单检查)
        sleep 2
        MEM_RSS_2=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{print int($1/1024)}')
        if [ -n "$MEM_RSS_2" ]; then
            MEM_DIFF=$((MEM_RSS_2 - MEM_RSS))
            if [ "$MEM_DIFF" -gt 10 ]; then
                check_warn "内存在 2 秒内增长 ${MEM_DIFF}MB (可能存在泄漏)"
            fi
        fi
    fi
fi

# 5. 检查系统资源
echo ""
echo ">> 5. 检查系统资源"
TOTAL_MEM=$(free -m | awk 'NR==2{print $2}')
USED_MEM=$(free -m | awk 'NR==2{print $3}')
MEM_PERCENT=$((USED_MEM * 100 / TOTAL_MEM))

if [ "$MEM_PERCENT" -gt 90 ]; then
    check_critical "系统内存使用率: ${MEM_PERCENT}% (${USED_MEM}MB / ${TOTAL_MEM}MB) - 接近 OOM"
elif [ "$MEM_PERCENT" -gt 75 ]; then
    check_warn "系统内存使用率: ${MEM_PERCENT}% (${USED_MEM}MB / ${TOTAL_MEM}MB)"
else
    info "系统内存使用率: ${MEM_PERCENT}% (${USED_MEM}MB / ${TOTAL_MEM}MB)"
fi

# 6. 检查日志中的崩溃模式
echo ""
echo ">> 6. 检查日志错误模式 (最近 200 行)"
RECENT_LOGS=$(journalctl -u "$SERVICE_NAME" -n 200 --no-hostname 2>/dev/null || echo "")

# 检查 Rust panic (线程安全崩溃)
RUST_PANIC_COUNT=$(echo "$RECENT_LOGS" | grep -ci "panic\|RelativeStrengthIndex is unsendable\|thread.*panicked" || echo "0")
if [ "$RUST_PANIC_COUNT" -gt 0 ]; then
    check_critical "检测到 Rust panic: $RUST_PANIC_COUNT 次 (线程安全问题)"
fi

# 检查 Telegram 错误
TELEGRAM_ERROR_COUNT=$(echo "$RECENT_LOGS" | grep -ci "TCPTransport closed\|can't use getUpdates\|Telegram.*error\|event loop" || echo "0")
if [ "$TELEGRAM_ERROR_COUNT" -gt 5 ]; then
    check_critical "Telegram 错误频繁: $TELEGRAM_ERROR_COUNT 次 (事件循环冲突)"
elif [ "$TELEGRAM_ERROR_COUNT" -gt 0 ]; then
    check_warn "Telegram 错误: $TELEGRAM_ERROR_COUNT 次"
fi

# 检查 Python 异常
PYTHON_EXCEPTION_COUNT=$(echo "$RECENT_LOGS" | grep -ci "Traceback\|Exception\|Error:" || echo "0")
if [ "$PYTHON_EXCEPTION_COUNT" -gt 10 ]; then
    check_warn "Python 异常频繁: $PYTHON_EXCEPTION_COUNT 次"
fi

# 检查 OOM Killer
if echo "$RECENT_LOGS" | grep -qi "out of memory\|oom-kill\|killed process"; then
    check_critical "检测到 OOM Killer 触发 (内存不足导致进程被杀)"
fi

# 检查 Segmentation Fault
if echo "$RECENT_LOGS" | grep -qi "segmentation fault\|core dump"; then
    check_critical "检测到段错误 (segfault) - 严重内存问题"
fi

# 检查配置加载失败
if echo "$RECENT_LOGS" | grep -qi "ConfigManager.*failed\|Failed to load config"; then
    check_warn "检测到配置加载失败"
fi

# 7. 检查 Git 分支和版本
echo ""
echo ">> 7. 检查代码版本"
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
    info "提交: $(git log --oneline -1)"
else
    check_warn "本地代码可能与远程不同步"
    info "本地: $(git log --oneline -1)"
fi

# 8. 检查 systemd 服务配置
echo ""
echo ">> 8. 检查服务配置"
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

    # 检查重启策略
    if grep -q "Restart=on-failure" "$SERVICE_FILE"; then
        check_pass "自动重启已启用 (Restart=on-failure)"
    else
        check_warn "未启用自动重启"
    fi

    # 检查内存限制
    if grep -q "MemoryMax" "$SERVICE_FILE"; then
        MEM_MAX=$(grep "MemoryMax" "$SERVICE_FILE" | awk -F'=' '{print $2}')
        info "内存限制: $MEM_MAX"
    else
        check_warn "未配置内存限制 (MemoryMax) - 建议添加防止 OOM"
    fi
else
    check_fail "服务配置文件不存在: $SERVICE_FILE"
fi

# 9. 检查环境变量文件
echo ""
echo ">> 9. 检查环境配置"
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

# 10. 检查 Python 虚拟环境
echo ""
echo ">> 10. 检查 Python 环境"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    check_pass "虚拟环境存在"
    PYTHON_VERSION=$("$VENV_PYTHON" --version 2>&1)
    info "Python 版本: $PYTHON_VERSION"

    # 检查 Python 版本 (必须 3.11+)
    if echo "$PYTHON_VERSION" | grep -qE "Python 3\.(1[1-9]|[2-9][0-9])"; then
        check_pass "Python 版本满足要求 (3.11+)"
    else
        check_warn "Python 版本可能过低 (建议 3.11+)"
    fi
else
    check_fail "虚拟环境不存在: $VENV_PYTHON"
fi

# 11. 检查关键文件
echo ""
echo ">> 11. 检查关键文件"
for FILE in main_live.py strategy/deepseek_strategy.py utils/deepseek_client.py configs/base.yaml; do
    if [ -f "$INSTALL_DIR/$FILE" ]; then
        check_pass "$FILE 存在"
    else
        check_fail "$FILE 缺失"
    fi
done

# 12. 检查网络连接
echo ""
echo ">> 12. 检查网络连接"
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

# 13. 检查 Telegram 进程状态 (如果启用)
echo ""
echo ">> 13. 检查 Telegram 状态"
if [ -n "$PID" ]; then
    # 检查是否有 Telegram 相关线程
    TG_THREADS=$(ps -T -p "$PID" 2>/dev/null | grep -c "python" || echo "0")
    if [ "$TG_THREADS" -gt 1 ]; then
        info "Telegram 后台线程: $((TG_THREADS - 1)) 个"

        # 检查是否有 Telegram 错误日志
        TG_ERROR_RECENT=$(echo "$RECENT_LOGS" | tail -n 50 | grep -ci "Telegram.*error\|TCPTransport" || echo "0")
        if [ "$TG_ERROR_RECENT" -gt 0 ]; then
            check_warn "最近 50 行日志中有 $TG_ERROR_RECENT 次 Telegram 错误"
        else
            check_pass "Telegram 运行正常"
        fi
    else
        info "未检测到 Telegram 后台线程 (可能未启用)"
    fi
fi

# 14. 检查策略运行状态
echo ""
echo ">> 14. 检查策略运行状态"
if echo "$RECENT_LOGS" | grep -q "Strategy Started\|Instrument.*BTCUSDT"; then
    check_pass "策略已成功启动"
else
    check_warn "未检测到策略启动标志（可能刚重启）"
fi

# 检查是否有交易信号
if echo "$RECENT_LOGS" | grep -q "AI Signal:\|Judge Decision:\|Multi-Agent Analysis"; then
    check_pass "AI 分析正常运行"
else
    check_warn "未检测到 AI 分析日志"
fi

# 汇总
echo ""
echo "========================================"
echo "  检查结果汇总"
echo "========================================"
if [ $CRITICAL -gt 0 ]; then
    echo -e "${RED}严重问题: $CRITICAL 个 (需立即处理)${NC}"
fi
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}错误: $ERRORS 个${NC}"
fi
if [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}警告: $WARNINGS 个${NC}"
fi
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ] && [ $CRITICAL -eq 0 ]; then
    echo -e "${GREEN}全部检查通过!${NC}"
fi

echo ""
echo ">> 最近 10 条日志:"
echo "----------------------------------------"
journalctl -u "$SERVICE_NAME" -n 10 --no-hostname 2>/dev/null || echo "无法获取日志"
echo "----------------------------------------"

# 诊断建议
echo ""
echo ">> 诊断建议:"
if [ $CRITICAL -gt 0 ] || [ $ERRORS -gt 0 ]; then
    echo "1. 查看完整日志: journalctl -u $SERVICE_NAME -n 500 --no-pager"
    echo "2. 重启服务: sudo systemctl restart $SERVICE_NAME"
    echo "3. 查看崩溃日志: tail -n 100 /home/linuxuser/nautilus_AItrader/logs/crash.log"
    echo "4. 内存监控: watch -n 5 'ps aux | grep main_live'"
fi
if [ "$RESTART_COUNT" -gt 5 ]; then
    echo "⚠️ 服务频繁重启，建议检查:"
    echo "   - 内存泄漏: scripts/watchdog.sh (定期监控)"
    echo "   - 线程安全: 查找 'Rust panic' 关键词"
    echo "   - Telegram 冲突: 查找 'TCPTransport' 关键词"
fi

echo ""
exit $((CRITICAL + ERRORS))
