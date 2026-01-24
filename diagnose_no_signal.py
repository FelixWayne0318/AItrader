#!/usr/bin/env python3
"""
诊断脚本: 为什么没有交易信号?
==============================

全面检查可能导致无交易信号的所有原因:
1. 服务状态检查
2. 日志分析 (on_timer 是否触发)
3. AI API 连接测试
4. 信号生成测试 (原始 DeepSeek vs MultiAgent)
5. 配置一致性检查
6. 订单执行流程验证

用法:
    python3 diagnose_no_signal.py
"""

import os
import sys
import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

# =============================================================================
# 颜色输出
# =============================================================================
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.RESET}\n")

def print_section(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}[{text}]{Colors.RESET}")
    print("-" * 60)

def print_ok(text: str):
    print(f"  {Colors.GREEN}✅ {text}{Colors.RESET}")

def print_warn(text: str):
    print(f"  {Colors.YELLOW}⚠️  {text}{Colors.RESET}")

def print_error(text: str):
    print(f"  {Colors.RED}❌ {text}{Colors.RESET}")

def print_info(text: str):
    print(f"  {Colors.WHITE}ℹ️  {text}{Colors.RESET}")

# =============================================================================
# 1. 服务状态检查
# =============================================================================
def check_service_status() -> Dict[str, Any]:
    """检查 systemd 服务状态"""
    print_section("1. 服务状态检查")

    result = {
        "running": False,
        "active_state": "unknown",
        "uptime": None,
        "memory": None,
        "pid": None,
    }

    try:
        # 获取服务状态
        cmd = ["systemctl", "show", "nautilus-trader", "--property=ActiveState,SubState,MainPID,MemoryCurrent,ExecMainStartTimestamp"]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

        for line in output.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                if key == 'ActiveState':
                    result['active_state'] = value
                    result['running'] = value == 'active'
                elif key == 'MainPID':
                    result['pid'] = value if value != '0' else None
                elif key == 'MemoryCurrent':
                    if value and value != '[not set]':
                        try:
                            mb = int(value) / (1024 * 1024)
                            result['memory'] = f"{mb:.1f} MB"
                        except:
                            pass
                elif key == 'ExecMainStartTimestamp':
                    if value and value != 'n/a':
                        result['uptime'] = value

        if result['running']:
            print_ok(f"服务运行中 (PID: {result['pid']})")
            if result['memory']:
                print_info(f"内存使用: {result['memory']}")
            if result['uptime']:
                print_info(f"启动时间: {result['uptime']}")
        else:
            print_error(f"服务未运行! 状态: {result['active_state']}")
            print_info("启动命令: sudo systemctl start nautilus-trader")

    except subprocess.CalledProcessError as e:
        print_error(f"无法获取服务状态: {e}")
    except FileNotFoundError:
        print_warn("systemctl 不可用 (可能不是 systemd 系统)")

    return result

# =============================================================================
# 2. 日志分析
# =============================================================================
def analyze_logs() -> Dict[str, Any]:
    """分析最近的服务日志"""
    print_section("2. 日志分析 (最近 30 分钟)")

    result = {
        "on_timer_count": 0,
        "signal_count": 0,
        "error_count": 0,
        "last_timer": None,
        "last_signal": None,
        "errors": [],
        "signals": [],
    }

    try:
        # 获取最近 30 分钟的日志
        cmd = ["journalctl", "-u", "nautilus-trader", "--since", "30 minutes ago", "--no-pager", "-o", "short-iso"]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

        lines = output.strip().split('\n')
        print_info(f"获取到 {len(lines)} 行日志")

        for line in lines:
            line_lower = line.lower()

            # 检查 on_timer 触发
            if 'on_timer' in line_lower or 'timer triggered' in line_lower:
                result['on_timer_count'] += 1
                result['last_timer'] = line[:25]  # 时间戳

            # 检查信号生成
            if 'signal:' in line_lower or 'judge decision' in line_lower:
                result['signal_count'] += 1
                result['last_signal'] = line
                if len(result['signals']) < 5:
                    result['signals'].append(line)

            # 检查错误
            if 'error' in line_lower or 'failed' in line_lower or 'exception' in line_lower:
                result['error_count'] += 1
                if len(result['errors']) < 10:
                    result['errors'].append(line)

        # 输出结果
        if result['on_timer_count'] > 0:
            print_ok(f"on_timer 触发次数: {result['on_timer_count']}")
            print_info(f"最近触发: {result['last_timer']}")
        else:
            print_error("最近 30 分钟内 on_timer 未触发!")
            print_info("可能原因:")
            print_info("  - 服务刚启动，需等待下一个 15 分钟周期")
            print_info("  - 服务未正常运行")
            print_info("  - K线数据未收到")

        if result['signal_count'] > 0:
            print_ok(f"信号生成次数: {result['signal_count']}")
            for sig in result['signals'][:3]:
                print_info(f"  {sig[-100:]}")
        else:
            print_warn("最近 30 分钟内无信号生成记录")

        if result['error_count'] > 0:
            print_error(f"错误数量: {result['error_count']}")
            for err in result['errors'][:5]:
                print_info(f"  {err[-150:]}")
        else:
            print_ok("无错误记录")

    except subprocess.CalledProcessError as e:
        print_warn(f"无法获取日志: {e}")
    except FileNotFoundError:
        print_warn("journalctl 不可用")

    return result

# =============================================================================
# 3. API 连接测试
# =============================================================================
def test_api_connections() -> Dict[str, Any]:
    """测试 API 连接"""
    print_section("3. API 连接测试")

    result = {
        "deepseek": False,
        "binance": False,
        "telegram": False,
    }

    # 加载环境变量
    from dotenv import load_dotenv
    env_paths = [
        Path.home() / ".env.aitrader",
        Path(__file__).parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    # 测试 DeepSeek API
    print_info("测试 DeepSeek API...")
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            if response.choices:
                print_ok("DeepSeek API 连接成功")
                result['deepseek'] = True
            else:
                print_error("DeepSeek API 返回空响应")
        except Exception as e:
            print_error(f"DeepSeek API 连接失败: {e}")
    else:
        print_error("DEEPSEEK_API_KEY 未设置")

    # 测试 Binance API
    print_info("测试 Binance Futures API...")
    try:
        import aiohttp
        import asyncio

        async def test_binance():
            async with aiohttp.ClientSession() as session:
                async with session.get("https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return float(data.get('price', 0))
            return 0

        price = asyncio.run(test_binance())
        if price > 0:
            print_ok(f"Binance API 连接成功 (BTC 价格: ${price:,.2f})")
            result['binance'] = True
        else:
            print_error("Binance API 返回无效数据")
    except Exception as e:
        print_error(f"Binance API 连接失败: {e}")

    # 测试 Telegram Bot
    print_info("测试 Telegram Bot...")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if bot_token:
        try:
            import requests
            resp = requests.get(f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('ok'):
                    print_ok(f"Telegram Bot 连接成功 (@{data['result'].get('username', 'unknown')})")
                    result['telegram'] = True
                else:
                    print_error(f"Telegram Bot 无效: {data.get('description', 'unknown')}")
            else:
                print_error(f"Telegram API 返回状态码: {resp.status_code}")
        except Exception as e:
            print_error(f"Telegram Bot 连接失败: {e}")
    else:
        print_warn("TELEGRAM_BOT_TOKEN 未设置 (可选)")

    return result

# =============================================================================
# 4. 原始 DeepSeek vs MultiAgent 信号对比
# =============================================================================
def compare_signal_sources() -> Dict[str, Any]:
    """对比原始 DeepSeek 和 MultiAgent 的信号生成"""
    print_section("4. 信号源对比测试 (DeepSeek vs MultiAgent)")

    result = {
        "deepseek_signal": None,
        "multiagent_signal": None,
        "match": False,
        "deepseek_error": None,
        "multiagent_error": None,
    }

    # 加载环境变量
    from dotenv import load_dotenv
    env_paths = [
        Path.home() / ".env.aitrader",
        Path(__file__).parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        print_error("DEEPSEEK_API_KEY 未设置，跳过信号对比")
        return result

    # 获取市场数据
    print_info("获取市场数据...")
    try:
        import aiohttp
        import asyncio

        async def get_market_data():
            async with aiohttp.ClientSession() as session:
                # 获取 K线
                url = "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=15m&limit=50"
                async with session.get(url) as resp:
                    klines = await resp.json()

                # 获取价格
                url2 = "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
                async with session.get(url2) as resp2:
                    price_data = await resp2.json()

            return klines, float(price_data.get('price', 0))

        klines, current_price = asyncio.run(get_market_data())
        print_ok(f"获取到 {len(klines)} 根 K线，当前价格: ${current_price:,.2f}")
    except Exception as e:
        print_error(f"获取市场数据失败: {e}")
        return result

    # 构建简单的技术数据
    closes = [float(k[4]) for k in klines[-20:]]
    sma_20 = sum(closes) / len(closes)

    technical_data = {
        "sma_20": sma_20,
        "sma_5": sum(closes[-5:]) / 5,
        "rsi": 50.0,  # 简化
        "macd": 0.0,
        "overall_trend": "震荡整理",
    }

    price_data = {
        "price": current_price,
        "timestamp": datetime.now().isoformat(),
    }

    sentiment_data = {
        "long_short_ratio": 1.5,
        "source": "test",
    }

    # 测试原始 DeepSeek
    print_info("测试原始 DeepSeek 分析...")
    try:
        from utils.deepseek_client import DeepSeekAnalyzer

        deepseek = DeepSeekAnalyzer(
            api_key=api_key,
            model="deepseek-chat",
            temperature=0.1,
        )

        start = time.time()
        signal_ds = deepseek.analyze(
            price_data=price_data,
            technical_data=technical_data,
            sentiment_data=sentiment_data,
            current_position=None,
        )
        elapsed = time.time() - start

        result['deepseek_signal'] = {
            "signal": signal_ds.get('signal'),
            "confidence": signal_ds.get('confidence'),
            "time": f"{elapsed:.1f}s",
        }
        print_ok(f"DeepSeek: {signal_ds.get('signal')} / {signal_ds.get('confidence')} ({elapsed:.1f}s)")

    except Exception as e:
        result['deepseek_error'] = str(e)
        print_error(f"DeepSeek 分析失败: {e}")

    # 测试 MultiAgent
    print_info("测试 MultiAgent 分析 (Bull/Bear/Judge/Risk)...")
    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer

        multi_agent = MultiAgentAnalyzer(
            api_key=api_key,
            model="deepseek-chat",
            temperature=0.1,
            debate_rounds=1,  # 减少轮数加快测试
        )

        start = time.time()
        signal_ma = multi_agent.analyze(
            symbol="BTCUSDT",
            technical_report=technical_data,
            sentiment_report=sentiment_data,
            current_position=None,
            price_data=price_data,
        )
        elapsed = time.time() - start

        result['multiagent_signal'] = {
            "signal": signal_ma.get('signal'),
            "confidence": signal_ma.get('confidence'),
            "time": f"{elapsed:.1f}s",
            "judge_decision": signal_ma.get('judge_decision', {}),
        }
        print_ok(f"MultiAgent: {signal_ma.get('signal')} / {signal_ma.get('confidence')} ({elapsed:.1f}s)")

        # 显示 Judge 决策详情
        judge = signal_ma.get('judge_decision', {})
        if judge:
            print_info(f"  Winning Side: {judge.get('winning_side', 'N/A')}")
            print_info(f"  Bullish Count: {judge.get('bullish_count', 'N/A')}/5")
            print_info(f"  Bearish Count: {judge.get('bearish_count', 'N/A')}/5")

    except Exception as e:
        result['multiagent_error'] = str(e)
        print_error(f"MultiAgent 分析失败: {e}")
        import traceback
        traceback.print_exc()

    # 对比结果
    if result['deepseek_signal'] and result['multiagent_signal']:
        ds_sig = result['deepseek_signal']['signal']
        ma_sig = result['multiagent_signal']['signal']
        result['match'] = ds_sig == ma_sig

        if result['match']:
            print_ok(f"信号一致: {ds_sig}")
        else:
            print_warn(f"信号不一致! DeepSeek={ds_sig}, MultiAgent={ma_sig}")
            print_info("这可能是正常的 - 两种方法的决策逻辑不同")

    return result

# =============================================================================
# 5. 配置检查
# =============================================================================
def check_configuration() -> Dict[str, Any]:
    """检查关键配置"""
    print_section("5. 配置检查")

    result = {
        "issues": [],
        "warnings": [],
    }

    # 检查 main_live.py
    main_live_path = Path(__file__).parent / "main_live.py"
    if main_live_path.exists():
        content = main_live_path.read_text()

        # 检查 reconciliation
        if "reconciliation=False" in content:
            result['issues'].append("main_live.py: reconciliation=False (应为 True)")
        elif "reconciliation=True" in content:
            print_ok("reconciliation=True (已启用仓位对账)")

        # 检查 load_all
        if "load_all=False" in content:
            result['issues'].append("main_live.py: load_all=False (应为 True)")
        elif "load_all=True" in content:
            print_ok("load_all=True (加载所有工具)")

    # 检查 strategy_config.yaml
    config_path = Path(__file__).parent / "configs" / "strategy_config.yaml"
    if config_path.exists():
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # 检查 min_confidence_to_trade
        min_conf = config.get('min_confidence_to_trade', 'MEDIUM')
        print_info(f"min_confidence_to_trade: {min_conf}")

        # 检查 timer_interval_sec
        timer = config.get('timer_interval_sec', 900)
        print_info(f"timer_interval_sec: {timer}s ({timer/60:.1f}分钟)")

        # 检查 debate_rounds
        rounds = config.get('debate_rounds', 2)
        print_info(f"debate_rounds: {rounds}")

        # 检查 enable_auto_sl_tp
        sl_tp = config.get('enable_auto_sl_tp', True)
        if sl_tp:
            print_ok("enable_auto_sl_tp=True")
        else:
            result['warnings'].append("enable_auto_sl_tp=False (止损止盈未启用)")

    # 检查 deepseek_strategy.py 中的 MultiAgent 使用
    strategy_path = Path(__file__).parent / "strategy" / "deepseek_strategy.py"
    if strategy_path.exists():
        content = strategy_path.read_text()

        if "self.multi_agent.analyze" in content:
            print_ok("使用 MultiAgent 作为信号源")
        elif "self.deepseek.analyze" in content:
            print_info("使用原始 DeepSeek 作为信号源")

        if "self._execute_trade(signal_data" in content:
            print_ok("_execute_trade 被正确调用")
        else:
            result['issues'].append("_execute_trade 可能未被调用")

    # 输出问题
    if result['issues']:
        print_error(f"发现 {len(result['issues'])} 个问题:")
        for issue in result['issues']:
            print_info(f"  - {issue}")
    else:
        print_ok("配置检查通过")

    if result['warnings']:
        print_warn(f"发现 {len(result['warnings'])} 个警告:")
        for warn in result['warnings']:
            print_info(f"  - {warn}")

    return result

# =============================================================================
# 6. Timer 触发检查
# =============================================================================
def check_timer_trigger() -> Dict[str, Any]:
    """检查 Timer 触发机制"""
    print_section("6. Timer 触发机制检查")

    result = {
        "next_trigger": None,
        "minutes_until": None,
    }

    now = datetime.now()

    # 计算下一个 15 分钟整点
    minutes = now.minute
    next_15 = ((minutes // 15) + 1) * 15
    if next_15 >= 60:
        next_trigger = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    else:
        next_trigger = now.replace(minute=next_15, second=0, microsecond=0)

    result['next_trigger'] = next_trigger.strftime("%H:%M:%S")
    result['minutes_until'] = (next_trigger - now).seconds // 60

    print_info(f"当前时间: {now.strftime('%H:%M:%S')}")
    print_info(f"下次触发: {result['next_trigger']} (约 {result['minutes_until']} 分钟后)")

    # 检查 strategy 中的 timer 设置
    strategy_path = Path(__file__).parent / "strategy" / "deepseek_strategy.py"
    if strategy_path.exists():
        content = strategy_path.read_text()

        if "self.clock.set_timer" in content:
            print_ok("Timer 已在策略中设置")
        else:
            print_warn("未找到 Timer 设置代码")

        if "def on_timer" in content:
            print_ok("on_timer 方法存在")
        else:
            print_error("on_timer 方法不存在!")

    return result

# =============================================================================
# 7. K线数据接收检查
# =============================================================================
def check_bar_data() -> Dict[str, Any]:
    """检查 K线数据是否正常接收"""
    print_section("7. K线数据检查 (从日志)")

    result = {
        "bar_count": 0,
        "last_bar": None,
    }

    try:
        # 搜索最近的 K线相关日志
        cmd = ["journalctl", "-u", "nautilus-trader", "--since", "30 minutes ago", "--no-pager", "-o", "short-iso"]
        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)

        for line in output.strip().split('\n'):
            if 'bar' in line.lower() or 'kline' in line.lower() or 'on_bar' in line.lower():
                result['bar_count'] += 1
                result['last_bar'] = line

        if result['bar_count'] > 0:
            print_ok(f"K线数据记录数: {result['bar_count']}")
            if result['last_bar']:
                print_info(f"最新: {result['last_bar'][-100:]}")
        else:
            print_warn("最近 30 分钟内无 K线数据记录")
            print_info("可能原因:")
            print_info("  - WebSocket 连接问题")
            print_info("  - 服务刚启动")

    except Exception as e:
        print_warn(f"无法检查: {e}")

    return result

# =============================================================================
# 8. 实际执行模拟
# =============================================================================
def simulate_execution() -> Dict[str, Any]:
    """模拟完整的信号生成到执行流程"""
    print_section("8. 模拟执行流程")

    result = {
        "steps": [],
        "would_execute": False,
        "blocking_reason": None,
    }

    # 加载环境变量
    from dotenv import load_dotenv
    env_paths = [
        Path.home() / ".env.aitrader",
        Path(__file__).parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break

    print_info("模拟 on_timer → _execute_trade 流程...")

    # Step 1: 检查 trading_paused
    print_info("Step 1: 检查 is_trading_paused")
    result['steps'].append(("is_trading_paused", "无法检测 (需从服务日志)", "⚠️"))

    # Step 2: 检查信号生成
    print_info("Step 2: 生成信号")
    try:
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        if api_key:
            from agents.multi_agent_analyzer import MultiAgentAnalyzer
            import aiohttp
            import asyncio

            async def get_price():
                async with aiohttp.ClientSession() as session:
                    url = "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
                    async with session.get(url) as resp:
                        data = await resp.json()
                        return float(data.get('price', 0))

            current_price = asyncio.run(get_price())

            multi_agent = MultiAgentAnalyzer(api_key=api_key, debate_rounds=1)
            signal = multi_agent.analyze(
                symbol="BTCUSDT",
                technical_report={"rsi": 50, "sma_20": current_price * 0.99},
                sentiment_report={"long_short_ratio": 1.5},
                current_position=None,
                price_data={"price": current_price},
            )

            sig = signal.get('signal', 'UNKNOWN')
            conf = signal.get('confidence', 'UNKNOWN')
            result['steps'].append(("signal_generation", f"{sig} / {conf}", "✅"))

            # Step 3: 检查 confidence
            print_info(f"Step 3: 检查 confidence (signal={sig}, conf={conf})")
            min_conf = "MEDIUM"  # 默认
            conf_levels = {'LOW': 0, 'MEDIUM': 1, 'HIGH': 2}

            if conf_levels.get(conf, 0) >= conf_levels.get(min_conf, 1):
                result['steps'].append(("confidence_check", f"{conf} >= {min_conf}", "✅"))
            else:
                result['steps'].append(("confidence_check", f"{conf} < {min_conf}", "❌"))
                result['blocking_reason'] = f"Confidence {conf} 低于最低要求 {min_conf}"

            # Step 4: 检查 HOLD
            print_info(f"Step 4: 检查 signal (HOLD?)")
            if sig == 'HOLD':
                result['steps'].append(("hold_check", "Signal is HOLD", "⚠️"))
                result['blocking_reason'] = "Signal 是 HOLD，不执行交易"
            else:
                result['steps'].append(("hold_check", f"Signal is {sig}", "✅"))

            # Step 5: 计算仓位
            print_info("Step 5: 计算仓位大小")
            base_usdt = 100.0
            conf_mult = {'LOW': 0.5, 'MEDIUM': 1.0, 'HIGH': 1.5}.get(conf, 1.0)
            position_usdt = base_usdt * conf_mult
            quantity = position_usdt / current_price

            if quantity > 0.001:  # min_trade_amount
                result['steps'].append(("position_size", f"${position_usdt:.2f} = {quantity:.4f} BTC", "✅"))
            else:
                result['steps'].append(("position_size", f"量太小: {quantity:.6f}", "❌"))
                result['blocking_reason'] = "计算的仓位量太小"

            # 结论
            if sig in ['BUY', 'SELL'] and conf_levels.get(conf, 0) >= 1 and quantity > 0.001:
                result['would_execute'] = True
                print_ok(f"✅ 会执行交易: {sig} {quantity:.4f} BTC")
            else:
                print_warn(f"⚠️ 不会执行交易: {result['blocking_reason']}")

        else:
            result['steps'].append(("api_key", "DEEPSEEK_API_KEY 未设置", "❌"))

    except Exception as e:
        result['steps'].append(("error", str(e), "❌"))
        print_error(f"模拟失败: {e}")

    # 打印步骤总结
    print("\n  执行步骤总结:")
    for step, detail, status in result['steps']:
        print(f"    {status} {step}: {detail}")

    return result

# =============================================================================
# 主函数
# =============================================================================
def main():
    print_header("无交易信号诊断工具")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  目的: 找出为什么系统不产生交易信号")

    all_results = {}

    # 1. 服务状态
    all_results['service'] = check_service_status()

    # 2. 日志分析
    all_results['logs'] = analyze_logs()

    # 3. API 连接
    all_results['api'] = test_api_connections()

    # 4. 信号对比 (可选，耗时较长)
    print("\n" + "="*70)
    user_input = input("是否进行信号源对比测试? (耗时约 30-60 秒) [y/N]: ").strip().lower()
    if user_input == 'y':
        all_results['signals'] = compare_signal_sources()
    else:
        print_info("跳过信号对比测试")

    # 5. 配置检查
    all_results['config'] = check_configuration()

    # 6. Timer 检查
    all_results['timer'] = check_timer_trigger()

    # 7. K线数据
    all_results['bars'] = check_bar_data()

    # 8. 模拟执行 (可选)
    print("\n" + "="*70)
    user_input = input("是否进行执行流程模拟? (耗时约 20-40 秒) [y/N]: ").strip().lower()
    if user_input == 'y':
        all_results['execution'] = simulate_execution()
    else:
        print_info("跳过执行流程模拟")

    # ==========================================================================
    # 总结
    # ==========================================================================
    print_header("诊断总结")

    issues = []
    warnings = []

    # 检查服务
    if not all_results['service'].get('running'):
        issues.append("服务未运行")

    # 检查日志
    if all_results['logs'].get('on_timer_count', 0) == 0:
        issues.append("on_timer 最近 30 分钟内未触发")
    if all_results['logs'].get('error_count', 0) > 0:
        warnings.append(f"日志中有 {all_results['logs']['error_count']} 个错误")

    # 检查 API
    if not all_results['api'].get('deepseek'):
        issues.append("DeepSeek API 连接失败")
    if not all_results['api'].get('binance'):
        issues.append("Binance API 连接失败")

    # 检查配置
    if all_results.get('config', {}).get('issues'):
        issues.extend(all_results['config']['issues'])

    # 检查执行
    if 'execution' in all_results:
        if not all_results['execution'].get('would_execute'):
            reason = all_results['execution'].get('blocking_reason', '未知原因')
            warnings.append(f"模拟执行被阻止: {reason}")

    # 输出总结
    if issues:
        print_error(f"发现 {len(issues)} 个严重问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print_ok("未发现严重问题")

    if warnings:
        print_warn(f"发现 {len(warnings)} 个警告:")
        for i, warn in enumerate(warnings, 1):
            print(f"  {i}. {warn}")

    # 建议
    print_section("建议操作")

    if not all_results['service'].get('running'):
        print_info("1. 启动服务: sudo systemctl start nautilus-trader")
        print_info("2. 查看日志: sudo journalctl -u nautilus-trader -f --no-hostname")
    elif all_results['logs'].get('on_timer_count', 0) == 0:
        print_info("1. 服务已运行但 on_timer 未触发")
        print_info(f"2. 等待到下次触发时间: {all_results['timer'].get('next_trigger', 'N/A')}")
        print_info("3. 或重启服务: sudo systemctl restart nautilus-trader")
    else:
        print_info("1. 查看完整日志分析错误原因")
        print_info("2. 运行 diagnose_realtime.py 进行详细诊断")

    print("\n" + "="*70)
    print("诊断完成")
    print("="*70 + "\n")

if __name__ == "__main__":
    main()
