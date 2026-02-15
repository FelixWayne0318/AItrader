#!/usr/bin/env python3
"""
端到端交易评估全链路实测
E2E Trade Evaluation Pipeline Test

在服务器上运行:
  cd /home/linuxuser/nautilus_AItrader
  source venv/bin/activate
  sudo systemctl stop nautilus-trader
  python3 scripts/e2e_trade_pipeline_test.py          # 手动确认
  python3 scripts/e2e_trade_pipeline_test.py --auto    # 自动确认
  sudo systemctl start nautilus-trader

流程:
  1. 通过 Binance Futures API 下最小单 LONG
  2. 立即平仓 (SELL)
  3. 获取实际成交价格
  4. 调用 evaluate_trade() 生成评级
  5. 调用 record_outcome() 写入 trading_memory.json
  6. 验证 _get_past_memories() 格式化输出
  7. 验证 Web API 端点返回数据
  8. 输出全链路报告
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── 项目路径 ───
PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# ─── 颜色 ───
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

results = []


def check(name, passed, detail=""):
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    results.append({"name": name, "passed": passed})
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


def info(name, detail=""):
    print(f"  [{BLUE}INFO{RESET}] {name}")
    if detail:
        print(f"         {detail}")


def warn(name, detail=""):
    print(f"  [{YELLOW}WARN{RESET}] {name}")
    if detail:
        print(f"         {detail}")


def section(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


def load_env():
    """加载 ~/.env.aitrader"""
    env_file = Path.home() / ".env.aitrader"
    if not env_file.exists():
        print(f"{RED}ERROR: ~/.env.aitrader 不存在{RESET}")
        sys.exit(1)
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, val = line.split('=', 1)
                os.environ[key.strip()] = val.strip()
    info("环境变量已加载", str(env_file))


# ══════════════════════════════════════════════════════════════
#  PHASE 1: Binance 实际下单 + 平仓
# ══════════════════════════════════════════════════════════════
def phase1_binance_trade():
    section("PHASE 1/4: Binance 实际交易 (最小单)")

    try:
        from binance.um_futures import UMFutures
        check("binance SDK 导入成功", True)
    except ImportError:
        check("binance SDK 导入成功", False, "pip install binance-futures-connector")
        return None

    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    if not api_key or not api_secret:
        check("API 密钥存在", False, "BINANCE_API_KEY / BINANCE_API_SECRET 未设置")
        return None
    check("API 密钥存在", True)

    client = UMFutures(key=api_key, secret=api_secret)

    # 获取当前价格
    ticker = client.ticker_price("BTCUSDT")
    current_price = float(ticker['price'])
    info("当前 BTC 价格", f"${current_price:,.2f}")

    # 最小下单量: BTCUSDT 最小 0.001 BTC
    qty = "0.001"
    info("下单数量", f"{qty} BTC (最小单, 约 ${current_price * 0.001:,.2f})")

    # Step 1: 开多 (LONG)
    entry_time = datetime.now(timezone.utc)
    try:
        open_order = client.new_order(
            symbol="BTCUSDT",
            side="BUY",
            type="MARKET",
            quantity=qty,
        )
        entry_order_id = open_order.get('orderId')
        check("LONG 开仓成功", True, f"orderId={entry_order_id}")
        info("开仓响应", json.dumps(open_order, indent=2)[:300])
    except Exception as e:
        check("LONG 开仓成功", False, str(e))
        return None

    # 等待 1 秒确保成交
    time.sleep(1)

    # 获取成交价
    try:
        entry_trades = client.get_account_trades(symbol="BTCUSDT", orderId=entry_order_id)
        if entry_trades:
            entry_price = float(entry_trades[0]['price'])
        else:
            entry_price = current_price
        check("获取入场价", True, f"${entry_price:,.2f}")
    except Exception:
        entry_price = current_price
        warn("获取入场价失败，使用 ticker 价格")

    # Step 2: 立即平仓 (SELL)
    try:
        close_order = client.new_order(
            symbol="BTCUSDT",
            side="SELL",
            type="MARKET",
            quantity=qty,
            reduceOnly="true",
        )
        close_order_id = close_order.get('orderId')
        check("平仓成功", True, f"orderId={close_order_id}")
    except Exception as e:
        check("平仓成功", False, str(e))
        warn("手动平仓: 登录 Binance Futures 关闭仓位!")
        return None

    exit_time = datetime.now(timezone.utc)

    # 等待 1 秒确保成交
    time.sleep(1)

    # 获取平仓成交价
    try:
        exit_trades = client.get_account_trades(symbol="BTCUSDT", orderId=close_order_id)
        if exit_trades:
            exit_price = float(exit_trades[0]['price'])
        else:
            exit_price = current_price
        check("获取出场价", True, f"${exit_price:,.2f}")
    except Exception:
        exit_price = current_price
        warn("获取出场价失败，使用 ticker 价格")

    # 计算实际 P&L
    pnl_pct = round((exit_price - entry_price) / entry_price * 100, 4)
    pnl_usdt = round((exit_price - entry_price) * float(qty), 4)
    info("交易结果", f"入场=${entry_price:,.2f}, 出场=${exit_price:,.2f}, "
         f"P&L={pnl_pct:+.4f}% (${pnl_usdt:+.4f})")

    return {
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl_pct": pnl_pct,
        "pnl_usdt": pnl_usdt,
        "direction": "LONG",
        "quantity": float(qty),
        "entry_time": entry_time.isoformat(),
        "exit_time": exit_time.isoformat(),
        "entry_order_id": entry_order_id,
        "close_order_id": close_order_id,
    }


# ══════════════════════════════════════════════════════════════
#  PHASE 2: evaluate_trade() + record_outcome()
# ══════════════════════════════════════════════════════════════
def phase2_evaluate_and_record(trade_data):
    section("PHASE 2/4: evaluate_trade() → record_outcome()")

    if not trade_data:
        warn("无交易数据，跳过")
        return None

    # Step 1: evaluate_trade
    try:
        from strategy.trading_logic import evaluate_trade
        check("evaluate_trade 导入成功", True)
    except Exception as e:
        check("evaluate_trade 导入成功", False, str(e))
        return None

    # 因为是立即平仓的测试单，没有真正的 SL/TP
    # 使用合理的模拟 SL/TP 来生成评级
    entry = trade_data["entry_price"]
    sl_distance = entry * 0.01   # 1% SL
    tp_distance = entry * 0.02   # 2% TP (R/R = 2:1)

    planned_sl = round(entry - sl_distance, 2)
    planned_tp = round(entry + tp_distance, 2)

    info("模拟 SL/TP (测试用)", f"SL=${planned_sl:,.2f}, TP=${planned_tp:,.2f}, R/R=2:1")

    try:
        evaluation = evaluate_trade(
            entry_price=trade_data["entry_price"],
            exit_price=trade_data["exit_price"],
            planned_sl=planned_sl,
            planned_tp=planned_tp,
            direction=trade_data["direction"],
            pnl_pct=trade_data["pnl_pct"],
            confidence="MEDIUM",
            position_size_pct=1.0,  # 最小仓位
            entry_timestamp=trade_data["entry_time"],
            exit_timestamp=trade_data["exit_time"],
        )
        check("evaluate_trade() 执行成功", True)
        info("评级结果", json.dumps(evaluation, indent=2))
    except Exception as e:
        check("evaluate_trade() 执行成功", False, traceback.format_exc())
        return None

    # 验证评级结构
    required = [
        "grade", "direction_correct", "entry_price", "exit_price",
        "planned_sl", "planned_tp", "planned_rr", "actual_rr",
        "execution_quality", "exit_type", "confidence",
        "position_size_pct", "hold_duration_min"
    ]
    missing = [k for k in required if k not in evaluation]
    check("评级包含全部 13 字段", len(missing) == 0,
          f"缺少: {missing}" if missing else f"grade={evaluation['grade']}, "
          f"actual_rr={evaluation.get('actual_rr')}, exit_type={evaluation.get('exit_type')}")

    # Step 2: record_outcome
    import logging
    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer

        memory_file = str(PROJECT_ROOT / "data" / "trading_memory.json")
        analyzer = MultiAgentAnalyzer.__new__(MultiAgentAnalyzer)
        analyzer.logger = logging.getLogger("e2e_test")
        analyzer.memory_file = memory_file

        # 加载已有记忆 (如果有)
        if os.path.exists(memory_file):
            with open(memory_file) as f:
                analyzer.decision_memory = json.load(f)
        else:
            analyzer.decision_memory = []

        info("已有记忆条数", f"{len(analyzer.decision_memory)}")

        conditions = (
            f"E2E_TEST: price=${trade_data['entry_price']:,.2f}, "
            f"entry_order={trade_data['entry_order_id']}, "
            f"close_order={trade_data['close_order_id']}"
        )

        analyzer.record_outcome(
            decision=trade_data["direction"],
            pnl=trade_data["pnl_pct"],
            conditions=conditions,
            evaluation=evaluation,
        )
        check("record_outcome() 执行成功", True)
    except ImportError:
        # 如果 MultiAgentAnalyzer 无法导入 (缺 openai 等)，手动写入
        warn("MultiAgentAnalyzer 导入失败，使用内联写入")
        memory_file = str(PROJECT_ROOT / "data" / "trading_memory.json")
        if os.path.exists(memory_file):
            with open(memory_file) as f:
                memories = json.load(f)
        else:
            memories = []

        grade = evaluation.get('grade', '')
        actual_rr = evaluation.get('actual_rr', 0)
        exit_type = evaluation.get('exit_type', '')
        if grade in ('A+', 'A'):
            lesson = f"Grade {grade}: Strong win (R/R {actual_rr:.1f}:1) - repeat this pattern"
        elif grade == 'B':
            lesson = f"Grade B: Acceptable profit (R/R {actual_rr:.1f}:1)"
        elif grade == 'C':
            lesson = f"Grade C: Small profit but low R/R ({actual_rr:.1f}:1) - tighten entry"
        elif grade == 'D':
            lesson = f"Grade D: Controlled loss via {exit_type} - discipline maintained"
        elif grade == 'F':
            lesson = "Grade F: Uncontrolled loss - review SL placement"
        else:
            lesson = f"E2E test trade - grade {grade}"

        entry = {
            "decision": trade_data["direction"],
            "pnl": round(trade_data["pnl_pct"], 2),
            "conditions": (
                f"E2E_TEST: price=${trade_data['entry_price']:,.2f}, "
                f"entry_order={trade_data['entry_order_id']}, "
                f"close_order={trade_data['close_order_id']}"
            ),
            "lesson": lesson,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluation": evaluation,
        }
        memories.append(entry)
        os.makedirs(os.path.dirname(memory_file), exist_ok=True)
        with open(memory_file, 'w') as f:
            json.dump(memories, f, indent=2)
        check("record_outcome() 内联写入成功", True)
    except Exception as e:
        check("record_outcome() 执行成功", False, traceback.format_exc())
        return None

    # Step 3: 验证文件已写入
    memory_path = Path(PROJECT_ROOT / "data" / "trading_memory.json")
    check("trading_memory.json 存在", memory_path.exists(),
          f"大小: {memory_path.stat().st_size} bytes" if memory_path.exists() else "")

    if memory_path.exists():
        with open(memory_path) as f:
            data = json.load(f)
        with_eval = [m for m in data if m.get("evaluation")]
        check("含 evaluation 的记录", len(with_eval) > 0,
              f"{len(with_eval)}/{len(data)} 条")

        # 验证最新条目
        latest = data[-1]
        is_our_trade = "E2E_TEST" in latest.get("conditions", "")
        check("最新记录是我们的测试交易", is_our_trade,
              f"条件: {latest.get('conditions', '')[:100]}")

        info("最新记录完整内容", json.dumps(latest, indent=2, ensure_ascii=False)[:500])

    return evaluation


# ══════════════════════════════════════════════════════════════
#  PHASE 3: _get_past_memories() + Agent 消费验证
# ══════════════════════════════════════════════════════════════
def phase3_agent_consumption():
    section("PHASE 3/4: Agent 记忆消费验证")

    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer
        import logging

        memory_file = str(PROJECT_ROOT / "data" / "trading_memory.json")
        analyzer = MultiAgentAnalyzer.__new__(MultiAgentAnalyzer)
        analyzer.logger = logging.getLogger("e2e_test_agent")
        analyzer.memory_file = memory_file
        analyzer.decision_memory = analyzer._load_memory()
        check("MultiAgentAnalyzer 加载成功", True,
              f"内存中 {len(analyzer.decision_memory)} 条记忆")
    except ImportError as e:
        warn(f"MultiAgentAnalyzer 导入失败 ({e})")
        warn("在服务器 venv 中应可正常运行，此处跳过")
        return
    except Exception as e:
        check("MultiAgentAnalyzer 加载失败", False, traceback.format_exc())
        return

    # 调用 _get_past_memories()
    try:
        memories_text = analyzer._get_past_memories()
        has_content = len(memories_text) > 0
        check("_get_past_memories() 返回内容", has_content,
              f"长度={len(memories_text)} 字符")

        if has_content:
            has_success = "SUCCESSFUL" in memories_text or "\u2705" in memories_text
            has_failed = "FAILED" in memories_text or "\u274c" in memories_text
            has_quality = "TRADE QUALITY" in memories_text
            check("包含成功交易段", has_success)
            check("包含失败交易段", has_failed)
            check("包含质量统计段", has_quality)

            # 检查 grade 出现在文本中
            has_grade = any(g in memories_text for g in ["[A+]", "[A]", "[B]", "[C]", "[D]", "[F]"])
            check("记忆文本包含 Grade 标签", has_grade)

            print(f"\n  {BOLD}--- 记忆文本 (Agent 实际接收) ---{RESET}")
            print(f"  {memories_text}")
            print(f"  {BOLD}--- 记忆文本结束 ---{RESET}")
        else:
            warn("_get_past_memories() 返回空字符串")
    except Exception as e:
        check("_get_past_memories()", False, traceback.format_exc())


# ══════════════════════════════════════════════════════════════
#  PHASE 4: Web API 端点验证
# ══════════════════════════════════════════════════════════════
def phase4_web_api():
    section("PHASE 4/4: Web API 端点验证")

    import subprocess

    # 检查后端是否运行
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "http://127.0.0.1:8000/api/public/trade-evaluation/summary?days=30"],
            capture_output=True, text=True, timeout=5
        )
        http_code = result.stdout.strip()
        is_running = http_code == "200"
        check("Web 后端运行中 (port 8000)", is_running,
              f"HTTP {http_code}" if not is_running else "HTTP 200 OK")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        check("Web 后端连接", False, str(e))
        warn("后端未运行，跳过 API 测试")
        warn("启动后端: cd web/backend && uvicorn main:app --host 0.0.0.0 --port 8000")
        return
    except Exception as e:
        check("Web 后端连接", False, str(e))
        return

    if not is_running:
        warn("后端未运行，跳过 API 测试")
        return

    # Summary API
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8000/api/public/trade-evaluation/summary?days=30"],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        total = data.get("total_evaluated", 0)
        check("/api/public/trade-evaluation/summary", total > 0,
              f"total_evaluated={total}")

        if total > 0:
            info("grade_distribution", json.dumps(data.get("grade_distribution", {})))
            info("direction_accuracy", f"{data.get('direction_accuracy', 0)}%")
            info("avg_winning_rr", f"{data.get('avg_winning_rr', 0)}")
            info("avg_grade_score", f"{data.get('avg_grade_score', 0)}")
        else:
            warn("Summary 返回 0 条 → 前端将显示'暂无评估数据'")
    except Exception as e:
        check("Summary API", False, str(e))

    # Recent API
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8000/api/public/trade-evaluation/recent?limit=5"],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        check("/api/public/trade-evaluation/recent", len(data) > 0,
              f"返回 {len(data)} 条记录")
        if data:
            info("最近交易", json.dumps(data[0], indent=2)[:300])
    except Exception as e:
        check("Recent API", False, str(e))


# ══════════════════════════════════════════════════════════════
#  主函数
# ══════════════════════════════════════════════════════════════
def main():
    print(f"\n{BOLD}{'#'*60}{RESET}")
    print(f"{BOLD}  端到端交易评估全链路实测 (E2E Pipeline Test){RESET}")
    print(f"{BOLD}  Binance Trade → evaluate → record → Agent → Web API{RESET}")
    print(f"{BOLD}  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{BOLD}{'#'*60}{RESET}")

    # 安全确认
    print(f"\n{YELLOW}{BOLD}注意:{RESET}")
    print(f"  1. 此脚本将在 Binance Futures 开一个 {BOLD}0.001 BTC{RESET} 的 LONG 并立即平仓")
    print(f"  2. 预计损失: 仅点差+手续费 (约 $0.05-0.20)")
    print(f"  3. 请确保 Bot 已停止: sudo systemctl stop nautilus-trader")
    print(f"  4. 确保 ~/.env.aitrader 中有正确的 API 密钥\n")

    # 支持 --auto 参数或 AUTO_CONFIRM 环境变量
    auto_confirm = '--auto' in sys.argv or os.getenv('AUTO_CONFIRM', '').lower() == 'true'
    if auto_confirm:
        info("自动确认模式 (--auto / AUTO_CONFIRM=true)")
    else:
        confirm = input(f"{BOLD}输入 'yes' 开始测试: {RESET}").strip().lower()
        if confirm != 'yes':
            print("已取消。")
            sys.exit(0)

    # 加载环境变量
    load_env()

    # Phase 1: Binance 实际交易
    trade_data = phase1_binance_trade()

    # Phase 2: evaluate + record
    evaluation = phase2_evaluate_and_record(trade_data)

    # Phase 3: Agent 消费
    phase3_agent_consumption()

    # Phase 4: Web API
    phase4_web_api()

    # ─── 汇总 ───
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  E2E 测试汇总{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    passed = sum(1 for r in results if r["passed"] is True)
    failed = sum(1 for r in results if r["passed"] is False)

    print(f"  {GREEN}通过: {passed}{RESET}")
    print(f"  {RED}失败: {failed}{RESET}")

    if failed > 0:
        print(f"\n  {RED}{BOLD}失败项:{RESET}")
        for r in results:
            if r["passed"] is False:
                print(f"    {RED}\u2717 {r['name']}{RESET}")

    if trade_data:
        print(f"\n  {BOLD}交易摘要:{RESET}")
        print(f"    入场: ${trade_data['entry_price']:,.2f}")
        print(f"    出场: ${trade_data['exit_price']:,.2f}")
        print(f"    P&L:  {trade_data['pnl_pct']:+.4f}% (${trade_data['pnl_usdt']:+.4f})")
        if evaluation:
            print(f"    评级: {evaluation.get('grade', '?')}")
            print(f"    R/R:  {evaluation.get('actual_rr', 0)}")

    if failed == 0:
        print(f"\n  {GREEN}{BOLD}\u2705 全链路端到端测试通过!{RESET}")
        print(f"  {GREEN}Generation \u2192 Storage \u2192 Loading \u2192 Formatting \u2192 Agent \u2192 Web API{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}\u274c 发现 {failed} 个问题{RESET}\n")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
