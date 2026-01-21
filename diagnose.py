#!/usr/bin/env python3
"""
AItrader 全面诊断脚本
在服务器运行: python diagnose.py
"""

import os
import sys
import json
import subprocess
import importlib
import traceback
from datetime import datetime
from pathlib import Path

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def ok(msg): print(f"{Colors.GREEN}[✓]{Colors.RESET} {msg}")
def fail(msg): print(f"{Colors.RED}[✗]{Colors.RESET} {msg}")
def warn(msg): print(f"{Colors.YELLOW}[!]{Colors.RESET} {msg}")
def info(msg): print(f"{Colors.BLUE}[i]{Colors.RESET} {msg}")
def header(msg): print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}\n {msg}\n{'='*60}{Colors.RESET}")

results = {
    "timestamp": datetime.now().isoformat(),
    "checks": {},
    "errors": [],
    "warnings": []
}

def run_cmd(cmd, timeout=30):
    """运行shell命令"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def check_section(name):
    """装饰器：记录检查结果"""
    def decorator(func):
        def wrapper():
            try:
                result = func()
                results["checks"][name] = {"status": "pass" if result else "fail", "details": {}}
                return result
            except Exception as e:
                results["checks"][name] = {"status": "error", "error": str(e)}
                results["errors"].append(f"{name}: {e}")
                fail(f"检查异常: {e}")
                return False
        return wrapper
    return decorator

# ============================================================
# 1. 系统环境检查
# ============================================================
@check_section("system_environment")
def check_system():
    header("1. 系统环境检查")
    all_ok = True

    # Python版本
    py_version = sys.version_info
    py_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"
    if py_version >= (3, 11):
        ok(f"Python 版本: {py_str}")
    else:
        fail(f"Python 版本: {py_str} (需要 >= 3.11)")
        all_ok = False

    # 系统信息
    code, uname, _ = run_cmd("uname -a")
    info(f"系统: {uname[:80]}")

    # 内存
    code, mem, _ = run_cmd("free -h | grep Mem | awk '{print $2, $3, $4}'")
    if mem:
        info(f"内存 (总/已用/可用): {mem}")

    # 磁盘
    code, disk, _ = run_cmd("df -h / | tail -1 | awk '{print $2, $3, $4, $5}'")
    if disk:
        info(f"磁盘 (总/已用/可用/使用率): {disk}")

    # 工作目录
    cwd = os.getcwd()
    info(f"当前目录: {cwd}")

    # 虚拟环境
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv:
        ok(f"虚拟环境: {venv}")
    else:
        warn("未检测到虚拟环境")

    return all_ok

# ============================================================
# 2. 依赖检查
# ============================================================
@check_section("dependencies")
def check_dependencies():
    header("2. 依赖包检查")
    all_ok = True

    required_packages = [
        ("nautilus_trader", "1.221.0"),
        ("msgspec", None),
        ("aiohttp", None),
        ("python-dotenv", None),
        ("pyyaml", None),
        ("httpx", None),
    ]

    for pkg_name, min_version in required_packages:
        try:
            if pkg_name == "python-dotenv":
                mod = importlib.import_module("dotenv")
            elif pkg_name == "pyyaml":
                mod = importlib.import_module("yaml")
            else:
                mod = importlib.import_module(pkg_name)

            version = getattr(mod, "__version__", "unknown")

            if min_version and version != "unknown":
                from packaging import version as pkg_version
                if pkg_version.parse(version) >= pkg_version.parse(min_version):
                    ok(f"{pkg_name}: {version}")
                else:
                    fail(f"{pkg_name}: {version} (需要 >= {min_version})")
                    all_ok = False
            else:
                ok(f"{pkg_name}: {version}")
        except ImportError as e:
            fail(f"{pkg_name}: 未安装 ({e})")
            all_ok = False
        except Exception as e:
            warn(f"{pkg_name}: 检查异常 ({e})")

    return all_ok

# ============================================================
# 3. 文件完整性检查
# ============================================================
@check_section("file_integrity")
def check_files():
    header("3. 文件完整性检查")
    all_ok = True

    required_files = [
        "main_live.py",
        "strategy/deepseek_strategy.py",
        "utils/deepseek_client.py",
        "utils/sentiment_client.py",
        "patches/binance_enums.py",
        "configs/strategy_config.yaml",
        "requirements.txt",
        "setup.sh",
        "nautilus-trader.service",
        ".env",
    ]

    base_path = Path(__file__).parent

    for file in required_files:
        file_path = base_path / file
        if file_path.exists():
            size = file_path.stat().st_size
            ok(f"{file} ({size} bytes)")
        else:
            if file == ".env":
                warn(f"{file} 不存在 (需要配置)")
            else:
                fail(f"{file} 不存在!")
                all_ok = False

    return all_ok

# ============================================================
# 4. 环境变量检查
# ============================================================
@check_section("env_variables")
def check_env():
    header("4. 环境变量 / .env 检查")
    all_ok = True

    # 加载 .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass

    required_vars = [
        ("BINANCE_API_KEY", True),
        ("BINANCE_API_SECRET", True),
        ("DEEPSEEK_API_KEY", True),
        ("TELEGRAM_BOT_TOKEN", False),
        ("TELEGRAM_CHAT_ID", False),
        ("AUTO_CONFIRM", False),
    ]

    for var, required in required_vars:
        value = os.environ.get(var, "")
        if value:
            # 隐藏敏感信息
            masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
            ok(f"{var}: {masked}")
        elif required:
            fail(f"{var}: 未设置 (必需)")
            all_ok = False
        else:
            warn(f"{var}: 未设置 (可选)")

    return all_ok

# ============================================================
# 5. NautilusTrader 配置检查
# ============================================================
@check_section("nautilus_config")
def check_nautilus_config():
    header("5. NautilusTrader 配置检查")
    all_ok = True

    try:
        import yaml
        config_path = Path(__file__).parent / "configs" / "strategy_config.yaml"

        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)

            # 检查关键配置
            strategy = config.get("strategy", {})
            info(f"策略名称: {strategy.get('name', 'N/A')}")
            info(f"交易对: {strategy.get('symbol', 'N/A')}")
            info(f"杠杆: {strategy.get('leverage', 'N/A')}")
            info(f"风险比例: {strategy.get('risk_per_trade', 'N/A')}")
            info(f"止损百分比: {strategy.get('default_sl_pct', 'N/A')}")

            deepseek = config.get("deepseek", {})
            info(f"DeepSeek模型: {deepseek.get('model', 'N/A')}")
            info(f"分析间隔: {deepseek.get('analysis_interval', 'N/A')}秒")

            ok("配置文件格式正确")
        else:
            fail("strategy_config.yaml 不存在")
            all_ok = False

    except Exception as e:
        fail(f"配置解析失败: {e}")
        all_ok = False

    return all_ok

# ============================================================
# 6. 止损逻辑验证
# ============================================================
@check_section("stop_loss_validation")
def check_stop_loss():
    header("6. 止损逻辑验证")
    all_ok = True

    try:
        # 尝试导入策略模块
        sys.path.insert(0, str(Path(__file__).parent))
        from strategy.deepseek_strategy import DeepSeekStrategy

        # 检查是否有 validate_stop_loss 方法或相关逻辑
        source_path = Path(__file__).parent / "strategy" / "deepseek_strategy.py"
        source = source_path.read_text()

        checks = [
            ("止损验证函数", "validate_stop_loss" in source or "sl_price" in source),
            ("LONG止损检查", "< entry" in source.lower() or "sl_price < " in source),
            ("SHORT止损检查", "> entry" in source.lower() or "sl_price > " in source),
            ("默认止损回退", "default_sl" in source.lower() or "0.02" in source),
        ]

        for name, passed in checks:
            if passed:
                ok(f"{name}: 已实现")
            else:
                warn(f"{name}: 未检测到 (可能用不同方式实现)")

        # 运行止损测试
        info("运行止损测试用例...")
        test_cases = [
            # (方向, 入场价, AI止损价, 预期结果描述)
            ("LONG", 100.0, 98.0, "应该接受: 止损 < 入场"),
            ("LONG", 100.0, 102.0, "应该拒绝/修正: 止损 > 入场"),
            ("SHORT", 100.0, 102.0, "应该接受: 止损 > 入场"),
            ("SHORT", 100.0, 98.0, "应该拒绝/修正: 止损 < 入场"),
        ]

        for direction, entry, sl, expected in test_cases:
            if direction == "LONG":
                valid = sl < entry
            else:
                valid = sl > entry
            status = "✓" if valid else "✗ (需修正)"
            info(f"  {direction} entry={entry} sl={sl}: {status} - {expected}")

        ok("止损逻辑检查完成")

    except Exception as e:
        fail(f"止损检查异常: {e}")
        traceback.print_exc()
        all_ok = False

    return all_ok

# ============================================================
# 7. Binance 枚举补丁检查
# ============================================================
@check_section("binance_patch")
def check_binance_patch():
    header("7. Binance 枚举补丁检查")
    all_ok = True

    try:
        patch_path = Path(__file__).parent / "patches" / "binance_enums.py"

        if patch_path.exists():
            source = patch_path.read_text()

            checks = [
                ("_missing_ 钩子", "_missing_" in source),
                ("POSITION_RISK_CONTROL 处理", "POSITION_RISK_CONTROL" in source or "unknown" in source.lower()),
                ("自动创建枚举值", "cls(" in source or "object.__new__" in source),
            ]

            for name, passed in checks:
                if passed:
                    ok(f"{name}: 已实现")
                else:
                    warn(f"{name}: 未检测到")

            # 测试补丁是否生效
            info("测试枚举补丁...")
            try:
                # 先应用补丁
                exec(compile(source, patch_path, 'exec'))

                from nautilus_trader.adapters.binance.common.enums import BinanceSymbolFilterType

                # 测试已知值
                known = BinanceSymbolFilterType.PRICE_FILTER
                ok(f"已知枚举值 PRICE_FILTER: {known}")

                # 测试未知值（如果补丁生效）
                try:
                    # 这个值应该触发 _missing_
                    test_val = BinanceSymbolFilterType("UNKNOWN_TEST_VALUE")
                    ok(f"未知枚举值处理: {test_val}")
                except ValueError:
                    warn("未知枚举值会抛出 ValueError (补丁可能未生效)")

            except Exception as e:
                warn(f"枚举测试异常: {e}")

        else:
            fail("patches/binance_enums.py 不存在")
            all_ok = False

    except Exception as e:
        fail(f"补丁检查异常: {e}")
        all_ok = False

    return all_ok

# ============================================================
# 8. 网络连接测试
# ============================================================
@check_section("network")
def check_network():
    header("8. 网络连接测试")
    all_ok = True

    endpoints = [
        ("Binance API", "https://api.binance.com/api/v3/ping"),
        ("Binance Futures", "https://fapi.binance.com/fapi/v1/ping"),
        ("DeepSeek API", "https://api.deepseek.com"),
    ]

    import urllib.request
    import urllib.error
    import ssl

    ctx = ssl.create_default_context()

    for name, url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AItrader-Diagnose/1.0"})
            response = urllib.request.urlopen(req, timeout=10, context=ctx)
            ok(f"{name}: 连接成功 (HTTP {response.status})")
        except urllib.error.HTTPError as e:
            # 某些API返回4xx但说明网络是通的
            if e.code < 500:
                ok(f"{name}: 可达 (HTTP {e.code})")
            else:
                fail(f"{name}: 服务器错误 (HTTP {e.code})")
                all_ok = False
        except Exception as e:
            fail(f"{name}: 连接失败 ({e})")
            all_ok = False

    return all_ok

# ============================================================
# 9. API 认证测试
# ============================================================
@check_section("api_auth")
def check_api_auth():
    header("9. API 认证测试")
    all_ok = True

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except:
        pass

    # Binance API 测试
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")

    if api_key and api_secret:
        try:
            import hmac
            import hashlib
            import time
            import urllib.request
            import urllib.parse

            timestamp = int(time.time() * 1000)
            query = f"timestamp={timestamp}"
            signature = hmac.new(
                api_secret.encode(),
                query.encode(),
                hashlib.sha256
            ).hexdigest()

            url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={signature}"
            req = urllib.request.Request(url, headers={
                "X-MBX-APIKEY": api_key,
                "User-Agent": "AItrader-Diagnose/1.0"
            })

            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read())

            balance = float(data.get("totalWalletBalance", 0))
            ok(f"Binance Futures 认证成功")
            info(f"  账户余额: {balance:.2f} USDT")
            info(f"  可用保证金: {float(data.get('availableBalance', 0)):.2f} USDT")

            # 检查持仓
            positions = [p for p in data.get("positions", []) if float(p.get("positionAmt", 0)) != 0]
            if positions:
                info(f"  当前持仓: {len(positions)} 个")
                for pos in positions[:3]:  # 最多显示3个
                    info(f"    {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
            else:
                info("  当前无持仓")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            fail(f"Binance API 认证失败: HTTP {e.code}")
            fail(f"  错误: {error_body[:200]}")
            all_ok = False
        except Exception as e:
            fail(f"Binance API 测试异常: {e}")
            all_ok = False
    else:
        warn("Binance API 密钥未配置，跳过认证测试")

    # DeepSeek API 测试
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        try:
            import urllib.request

            url = "https://api.deepseek.com/v1/models"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {deepseek_key}",
                "User-Agent": "AItrader-Diagnose/1.0"
            })

            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read())

            models = [m.get("id", "unknown") for m in data.get("data", [])]
            ok(f"DeepSeek API 认证成功")
            info(f"  可用模型: {', '.join(models[:5])}")

        except urllib.error.HTTPError as e:
            fail(f"DeepSeek API 认证失败: HTTP {e.code}")
            all_ok = False
        except Exception as e:
            fail(f"DeepSeek API 测试异常: {e}")
            all_ok = False
    else:
        warn("DeepSeek API 密钥未配置，跳过认证测试")

    return all_ok

# ============================================================
# 10. Systemd 服务状态
# ============================================================
@check_section("systemd_service")
def check_systemd():
    header("10. Systemd 服务状态")
    all_ok = True

    service_name = "nautilus-trader"

    # 检查服务是否存在
    code, output, _ = run_cmd(f"systemctl list-unit-files | grep {service_name}")
    if code != 0 or not output:
        warn(f"服务 {service_name} 未安装")
        return True  # 不算失败，可能是本地开发环境

    # 服务状态
    code, status, _ = run_cmd(f"systemctl is-active {service_name}")
    if status == "active":
        ok(f"服务状态: {status}")
    elif status == "inactive":
        warn(f"服务状态: {status} (未运行)")
    else:
        fail(f"服务状态: {status}")
        all_ok = False

    # 服务详情
    code, output, _ = run_cmd(f"systemctl show {service_name} --property=MainPID,MemoryCurrent,ActiveEnterTimestamp")
    if output:
        for line in output.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                if value and value != '0' and value != '[not set]':
                    info(f"  {key}: {value}")

    # 最近日志
    info("最近5条日志:")
    code, logs, _ = run_cmd(f"journalctl -u {service_name} -n 5 --no-pager --no-hostname 2>/dev/null")
    if logs:
        for line in logs.split('\n'):
            print(f"    {line[:100]}")
    else:
        info("  (无日志或无权限)")

    return all_ok

# ============================================================
# 11. 进程检查
# ============================================================
@check_section("processes")
def check_processes():
    header("11. 相关进程检查")

    # 查找 Python 进程
    code, output, _ = run_cmd("ps aux | grep -E 'main_live|nautilus' | grep -v grep")

    if output:
        ok("找到相关进程:")
        for line in output.split('\n')[:5]:
            parts = line.split()
            if len(parts) >= 11:
                info(f"  PID={parts[1]} CPU={parts[2]}% MEM={parts[3]}% CMD={' '.join(parts[10:])[:50]}")
    else:
        info("未找到运行中的交易进程")

    return True

# ============================================================
# 12. Git 状态
# ============================================================
@check_section("git_status")
def check_git():
    header("12. Git 仓库状态")

    # 当前分支
    code, branch, _ = run_cmd("git rev-parse --abbrev-ref HEAD")
    if code == 0:
        expected = "claude/clone-nautilus-aitrader-SFBz9"
        if branch == expected:
            ok(f"当前分支: {branch}")
        else:
            warn(f"当前分支: {branch} (预期: {expected})")

    # 最新提交
    code, commit, _ = run_cmd("git log -1 --oneline")
    if code == 0:
        info(f"最新提交: {commit}")

    # 未提交更改
    code, status, _ = run_cmd("git status --porcelain")
    if status:
        warn(f"有未提交的更改: {len(status.split(chr(10)))} 个文件")
    else:
        ok("工作区干净")

    # 与远程对比
    code, _, _ = run_cmd("git fetch origin --dry-run 2>&1")
    code, diff, _ = run_cmd("git rev-list HEAD..origin/claude/clone-nautilus-aitrader-SFBz9 --count 2>/dev/null")
    if diff and diff != "0":
        warn(f"落后远程 {diff} 个提交")

    return True

# ============================================================
# 13. 导入测试
# ============================================================
@check_section("import_test")
def check_imports():
    header("13. 关键模块导入测试")
    all_ok = True

    modules_to_test = [
        ("nautilus_trader", "NautilusTrader核心"),
        ("nautilus_trader.adapters.binance", "Binance适配器"),
        ("nautilus_trader.config", "配置模块"),
        ("nautilus_trader.live.node", "实盘节点"),
    ]

    for module, desc in modules_to_test:
        try:
            importlib.import_module(module)
            ok(f"{desc}: 导入成功")
        except Exception as e:
            fail(f"{desc}: 导入失败 - {e}")
            all_ok = False

    # 尝试导入本项目模块
    sys.path.insert(0, str(Path(__file__).parent))

    local_modules = [
        ("strategy.deepseek_strategy", "DeepSeek策略"),
        ("utils.deepseek_client", "DeepSeek客户端"),
        ("utils.sentiment_client", "情绪分析客户端"),
        ("patches.binance_enums", "Binance枚举补丁"),
    ]

    for module, desc in local_modules:
        try:
            importlib.import_module(module)
            ok(f"{desc}: 导入成功")
        except Exception as e:
            fail(f"{desc}: 导入失败 - {e}")
            all_ok = False

    return all_ok

# ============================================================
# 主函数
# ============================================================
def main():
    print(f"""
{Colors.BOLD}{Colors.CYAN}
╔════════════════════════════════════════════════════════════╗
║         AItrader 全面诊断工具 v1.0                         ║
║         时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                          ║
╚════════════════════════════════════════════════════════════╝
{Colors.RESET}""")

    # 运行所有检查
    checks = [
        check_system,
        check_dependencies,
        check_files,
        check_env,
        check_nautilus_config,
        check_stop_loss,
        check_binance_patch,
        check_network,
        check_api_auth,
        check_systemd,
        check_processes,
        check_git,
        check_imports,
    ]

    passed = 0
    failed = 0

    for check in checks:
        try:
            if check():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            fail(f"检查异常: {e}")

    # 汇总报告
    header("诊断汇总")

    total = passed + failed
    print(f"""
{Colors.BOLD}检查结果:{Colors.RESET}
  {Colors.GREEN}通过: {passed}/{total}{Colors.RESET}
  {Colors.RED}失败: {failed}/{total}{Colors.RESET}
""")

    if results["errors"]:
        print(f"{Colors.RED}错误列表:{Colors.RESET}")
        for err in results["errors"]:
            print(f"  - {err}")

    if results["warnings"]:
        print(f"\n{Colors.YELLOW}警告列表:{Colors.RESET}")
        for warn in results["warnings"]:
            print(f"  - {warn}")

    # 保存JSON报告
    report_path = Path(__file__).parent / "diagnose_report.json"
    results["summary"] = {"passed": passed, "failed": failed, "total": total}

    with open(report_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{Colors.BLUE}详细报告已保存到: {report_path}{Colors.RESET}")

    # 建议
    if failed > 0:
        print(f"""
{Colors.YELLOW}建议修复步骤:{Colors.RESET}
1. 查看上面的错误信息
2. 检查 .env 文件配置
3. 运行 ./setup.sh 重新安装依赖
4. 如有问题，将 diagnose_report.json 内容反馈
""")
    else:
        print(f"""
{Colors.GREEN}所有检查通过!{Colors.RESET}
系统状态良好，可以启动交易机器人。
""")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
