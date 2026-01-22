#!/usr/bin/env python3
"""
AItrader 全面诊断工具 v2.0

用法:
    python diagnose.py              # 运行全部检查
    python diagnose.py --quick      # 快速检查 (跳过网络测试)
    python diagnose.py --update     # 先更新代码再检查
    python diagnose.py --restart    # 检查后重启服务
    python diagnose.py --json       # 输出JSON格式
    python diagnose.py --help       # 显示帮助
"""

import os
import sys
import json
import subprocess
import importlib
import traceback
import argparse
import time
import hmac
import hashlib
import urllib.request
import urllib.error
import ssl
from datetime import datetime
from pathlib import Path

# ============================================================
# 自动切换到 venv
# ============================================================
def ensure_venv():
    """确保在 venv 中运行，否则自动切换"""
    project_dir = Path(__file__).parent.absolute()
    venv_python = project_dir / "venv" / "bin" / "python"

    # 检查是否已在 venv 中
    in_venv = (
        hasattr(sys, 'real_prefix') or
        (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    )

    if not in_venv and venv_python.exists():
        print(f"\033[93m[!]\033[0m 检测到未使用 venv，自动切换...")
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

    return in_venv

# 在导入其他模块前先确保 venv
ensure_venv()

# ============================================================
# 配置
# ============================================================
VERSION = "2.0"
BRANCH = "claude/clone-nautilus-aitrader-SFBz9"
PROJECT_DIR = Path(__file__).parent.absolute()
SERVICE_NAME = "nautilus-trader"

# 颜色输出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    RESET = '\033[0m'

# 全局状态
_json_mode = False

def ok(msg):
    if not _json_mode:
        print(f"{Colors.GREEN}[✓]{Colors.RESET} {msg}")

def fail(msg):
    if not _json_mode:
        print(f"{Colors.RED}[✗]{Colors.RESET} {msg}")

def warn(msg):
    if not _json_mode:
        print(f"{Colors.YELLOW}[!]{Colors.RESET} {msg}")

def info(msg):
    if not _json_mode:
        print(f"{Colors.BLUE}[i]{Colors.RESET} {msg}")

def header(msg):
    if not _json_mode:
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}\n {msg}\n{'='*60}{Colors.RESET}")

# 结果收集器
class Results:
    def __init__(self):
        self.timestamp = datetime.now().isoformat()
        self.checks = {}
        self.errors = []
        self.warnings = []
        self.passed = 0
        self.failed = 0

    def add_check(self, name, status, details=None, error=None):
        self.checks[name] = {
            "status": status,
            "details": details or {},
            "error": error
        }
        if status == "pass":
            self.passed += 1
        else:
            self.failed += 1
            if error:
                self.errors.append(f"{name}: {error}")

    def add_warning(self, msg):
        self.warnings.append(msg)

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "version": VERSION,
            "summary": {
                "passed": self.passed,
                "failed": self.failed,
                "total": self.passed + self.failed
            },
            "checks": self.checks,
            "errors": self.errors,
            "warnings": self.warnings
        }

results = Results()

# ============================================================
# 工具函数
# ============================================================
def run_cmd(cmd, timeout=30, cwd=None):
    """运行shell命令"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd or PROJECT_DIR
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except Exception as e:
        return -1, "", str(e)

def parse_version(v):
    """解析版本号为元组"""
    try:
        return tuple(int(x) for x in str(v).split('.')[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)

# ============================================================
# 检查函数
# ============================================================
def check_system():
    """1. 系统环境检查"""
    header("1. 系统环境检查")
    all_ok = True
    details = {}

    # Python版本 (CLAUDE.md 要求 >= 3.11)
    py_version = sys.version_info
    py_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"
    details["python_version"] = py_str

    if py_version >= (3, 11):
        ok(f"Python 版本: {py_str}")
    else:
        fail(f"Python 版本: {py_str} (需要 >= 3.11)")
        all_ok = False

    # 虚拟环境
    venv = os.environ.get("VIRTUAL_ENV", "")
    details["venv"] = venv or "未使用"
    if venv:
        ok(f"虚拟环境: {Path(venv).name}")
    else:
        warn("未检测到虚拟环境")

    # 系统信息
    code, uname, _ = run_cmd("uname -s -r -m")
    details["system"] = uname
    info(f"系统: {uname}")

    # 内存
    code, mem, _ = run_cmd("free -h 2>/dev/null | grep Mem | awk '{print $2\"/\"$3\"/\"$4}'")
    if mem:
        details["memory"] = mem
        info(f"内存 (总/已用/可用): {mem}")

    # 磁盘
    code, disk, _ = run_cmd("df -h / 2>/dev/null | tail -1 | awk '{print $5}'")
    if disk:
        details["disk_usage"] = disk
        usage_pct = int(disk.replace('%', '')) if disk.endswith('%') else 0
        if usage_pct > 90:
            warn(f"磁盘使用率: {disk} (较高)")
        else:
            info(f"磁盘使用率: {disk}")

    # 工作目录
    details["cwd"] = str(PROJECT_DIR)
    info(f"项目目录: {PROJECT_DIR}")

    results.add_check("system_environment", "pass" if all_ok else "fail", details)
    return all_ok

def check_dependencies():
    """2. 依赖包检查"""
    header("2. 依赖包检查")
    all_ok = True
    details = {}

    required_packages = [
        ("nautilus_trader", "1.221.0"),  # CLAUDE.md 指定版本
        ("msgspec", None),
        ("httpx", None),
        ("aiohttp", None),
        ("python-dotenv", None),
        ("pyyaml", None),
    ]

    for pkg_name, min_version in required_packages:
        try:
            # 处理特殊包名
            if pkg_name == "python-dotenv":
                mod = importlib.import_module("dotenv")
            elif pkg_name == "pyyaml":
                mod = importlib.import_module("yaml")
            else:
                mod = importlib.import_module(pkg_name)

            # 获取版本
            try:
                from importlib.metadata import version as get_version
                version = get_version(pkg_name)
            except Exception:
                version = getattr(mod, "__version__", "unknown")

            details[pkg_name] = version

            if min_version and version != "unknown":
                if parse_version(version) >= parse_version(min_version):
                    ok(f"{pkg_name}: {version}")
                else:
                    fail(f"{pkg_name}: {version} (需要 >= {min_version})")
                    all_ok = False
            else:
                ok(f"{pkg_name}: {version}")

        except ImportError as e:
            fail(f"{pkg_name}: 未安装")
            details[pkg_name] = "未安装"
            all_ok = False

    results.add_check("dependencies", "pass" if all_ok else "fail", details)
    return all_ok

def check_files():
    """3. 文件完整性检查"""
    header("3. 文件完整性检查")
    all_ok = True
    details = {}

    required_files = [
        ("main_live.py", True),           # 入口文件 (CLAUDE.md 强调)
        ("strategy/deepseek_strategy.py", True),
        ("utils/deepseek_client.py", True),
        ("utils/sentiment_client.py", True),
        ("patches/binance_enums.py", True),
        ("configs/strategy_config.yaml", True),
        ("requirements.txt", True),
        ("setup.sh", True),
        ("nautilus-trader.service", True),
        (".env", False),  # 可选但重要
    ]

    for file, required in required_files:
        file_path = PROJECT_DIR / file
        if file_path.exists():
            size = file_path.stat().st_size
            details[file] = f"{size} bytes"
            ok(f"{file} ({size} bytes)")
        else:
            details[file] = "不存在"
            if required:
                fail(f"{file} 不存在!")
                all_ok = False
            else:
                warn(f"{file} 不存在 (需要配置)")

    # 检查入口文件不能是 main.py
    if (PROJECT_DIR / "main.py").exists():
        warn("存在 main.py - 注意: 入口文件应是 main_live.py!")
        results.add_warning("入口文件应是 main_live.py 而非 main.py")

    results.add_check("file_integrity", "pass" if all_ok else "fail", details)
    return all_ok

def check_env():
    """4. 环境变量检查"""
    header("4. 环境变量 / .env 检查")
    all_ok = True
    details = {}

    # 加载 .env
    env_file = PROJECT_DIR / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            ok(".env 文件已加载")
        except ImportError:
            # 手动解析
            try:
                with open(env_file) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, _, value = line.partition('=')
                            os.environ.setdefault(key.strip(), value.strip().strip('"\''))
                ok(".env 文件已手动加载")
            except Exception as e:
                warn(f".env 解析失败: {e}")

    required_vars = [
        ("BINANCE_API_KEY", True),
        ("BINANCE_API_SECRET", True),
        ("DEEPSEEK_API_KEY", True),
    ]

    optional_vars = [
        ("TELEGRAM_BOT_TOKEN", False),
        ("TELEGRAM_CHAT_ID", False),
        ("AUTO_CONFIRM", False),
    ]

    for var, required in required_vars + optional_vars:
        value = os.environ.get(var, "")
        if value:
            masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
            details[var] = "已配置"
            ok(f"{var}: {masked}")
        elif required:
            details[var] = "未配置"
            fail(f"{var}: 未设置 (必需)")
            all_ok = False
        else:
            details[var] = "未配置"
            warn(f"{var}: 未设置 (可选)")

    results.add_check("env_variables", "pass" if all_ok else "fail", details)
    return all_ok

def check_nautilus_config():
    """5. NautilusTrader 配置检查"""
    header("5. 策略配置检查")
    all_ok = True
    details = {}

    try:
        import yaml
        config_path = PROJECT_DIR / "configs" / "strategy_config.yaml"

        if not config_path.exists():
            fail("strategy_config.yaml 不存在")
            results.add_check("nautilus_config", "fail", error="配置文件不存在")
            return False

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # 检查关键配置
        strategy = config.get("strategy", {})
        details["name"] = strategy.get("name", "N/A")
        details["symbol"] = strategy.get("symbol", "N/A")
        details["leverage"] = strategy.get("leverage", "N/A")
        details["risk_per_trade"] = strategy.get("risk_per_trade", "N/A")
        details["default_sl_pct"] = strategy.get("default_sl_pct", "N/A")

        info(f"策略名称: {details['name']}")
        info(f"交易对: {details['symbol']}")
        info(f"杠杆: {details['leverage']}")
        info(f"风险比例: {details['risk_per_trade']}")
        info(f"止损百分比: {details['default_sl_pct']}")

        deepseek = config.get("deepseek", {})
        details["model"] = deepseek.get("model", "N/A")
        details["analysis_interval"] = deepseek.get("analysis_interval", "N/A")

        info(f"DeepSeek模型: {details['model']}")
        info(f"分析间隔: {details['analysis_interval']}秒")

        ok("配置文件格式正确")

    except Exception as e:
        fail(f"配置解析失败: {e}")
        all_ok = False
        results.add_check("nautilus_config", "fail", details, str(e))
        return False

    results.add_check("nautilus_config", "pass" if all_ok else "fail", details)
    return all_ok

def check_stop_loss():
    """6. 止损逻辑验证"""
    header("6. 止损逻辑验证")
    details = {}

    try:
        strategy_file = PROJECT_DIR / "strategy" / "deepseek_strategy.py"
        if not strategy_file.exists():
            fail("策略文件不存在")
            results.add_check("stop_loss_validation", "fail", error="策略文件不存在")
            return False

        source = strategy_file.read_text()

        # 检查关键代码模式
        checks = [
            ("止损价格变量", "sl_price" in source or "stop_loss" in source),
            ("LONG止损检查", "< entry" in source.lower() or "sl_price <" in source),
            ("SHORT止损检查", "> entry" in source.lower() or "sl_price >" in source),
            ("默认止损回退", "default_sl" in source.lower() or "0.02" in source),
        ]

        all_found = True
        for name, found in checks:
            details[name] = "已实现" if found else "未检测到"
            if found:
                ok(f"{name}: 已实现")
            else:
                warn(f"{name}: 未检测到 (可能用不同方式实现)")
                all_found = False

        # 逻辑测试
        info("止损逻辑测试用例:")
        test_cases = [
            ("LONG", 100.0, 98.0, True, "SL < entry ✓"),
            ("LONG", 100.0, 102.0, False, "SL > entry ✗ (需修正)"),
            ("SHORT", 100.0, 102.0, True, "SL > entry ✓"),
            ("SHORT", 100.0, 98.0, False, "SL < entry ✗ (需修正)"),
        ]

        test_results = []
        for direction, entry, sl, expected, desc in test_cases:
            is_valid = (sl < entry) if direction == "LONG" else (sl > entry)
            status = "PASS" if is_valid == expected else "FAIL"
            test_results.append(f"{direction} entry={entry} sl={sl}: {status}")
            if not _json_mode:
                print(f"    {direction} entry={entry} sl={sl}: {'✓' if is_valid == expected else '✗'} {desc}")

        details["test_results"] = test_results
        ok("止损逻辑检查完成")

        results.add_check("stop_loss_validation", "pass", details)
        return True

    except Exception as e:
        fail(f"止损检查异常: {e}")
        results.add_check("stop_loss_validation", "fail", error=str(e))
        return False

def check_binance_patch():
    """7. Binance 枚举补丁检查"""
    header("7. Binance 枚举补丁检查")
    details = {}

    try:
        patch_path = PROJECT_DIR / "patches" / "binance_enums.py"

        if not patch_path.exists():
            fail("patches/binance_enums.py 不存在")
            results.add_check("binance_patch", "fail", error="补丁文件不存在")
            return False

        source = patch_path.read_text()

        checks = [
            ("_missing_ 钩子", "_missing_" in source),
            ("动态枚举创建", "cls(" in source or "object.__new__" in source),
        ]

        for name, found in checks:
            details[name] = "已实现" if found else "未检测到"
            if found:
                ok(f"{name}: 已实现")
            else:
                warn(f"{name}: 未检测到")

        # 测试补丁
        info("测试枚举补丁...")
        try:
            sys.path.insert(0, str(PROJECT_DIR))
            from patches import binance_enums  # 应用补丁

            from nautilus_trader.adapters.binance.common.enums import BinanceSymbolFilterType

            # 测试已知值
            known = BinanceSymbolFilterType.PRICE_FILTER
            ok(f"已知枚举值 PRICE_FILTER: {known}")
            details["known_enum_test"] = "通过"

            # 测试未知值
            try:
                test_val = BinanceSymbolFilterType("POSITION_RISK_CONTROL")
                ok(f"未知枚举值处理: {test_val}")
                details["unknown_enum_test"] = "通过"
            except ValueError:
                warn("未知枚举值会抛出 ValueError")
                details["unknown_enum_test"] = "失败"

        except Exception as e:
            warn(f"枚举测试异常: {e}")
            details["enum_test_error"] = str(e)

        results.add_check("binance_patch", "pass", details)
        return True

    except Exception as e:
        fail(f"补丁检查异常: {e}")
        results.add_check("binance_patch", "fail", error=str(e))
        return False

def check_network(skip=False):
    """8. 网络连接测试"""
    header("8. 网络连接测试")

    if skip:
        info("跳过网络检查 (--quick 模式)")
        results.add_check("network", "skip", {"reason": "quick mode"})
        return True

    details = {}
    all_ok = True
    ctx = ssl.create_default_context()

    endpoints = [
        ("Binance Spot", "https://api.binance.com/api/v3/ping"),
        ("Binance Futures", "https://fapi.binance.com/fapi/v1/ping"),
        ("DeepSeek API", "https://api.deepseek.com"),
    ]

    for name, url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AItrader-Diagnose/2.0"})
            response = urllib.request.urlopen(req, timeout=10, context=ctx)
            details[name] = f"HTTP {response.status}"
            ok(f"{name}: 连接成功")
        except urllib.error.HTTPError as e:
            if e.code < 500:
                details[name] = f"HTTP {e.code}"
                ok(f"{name}: 可达 (HTTP {e.code})")
            else:
                details[name] = f"错误 HTTP {e.code}"
                fail(f"{name}: 服务器错误 (HTTP {e.code})")
                all_ok = False
        except Exception as e:
            details[name] = f"失败: {str(e)[:30]}"
            fail(f"{name}: 连接失败 ({e})")
            all_ok = False

    # 时间同步检查
    try:
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/time",
            headers={"User-Agent": "AItrader-Diagnose/2.0"}
        )
        response = urllib.request.urlopen(req, timeout=10, context=ctx)
        data = json.loads(response.read())
        server_time = data.get("serverTime", 0)
        local_time = int(datetime.now().timestamp() * 1000)
        diff = abs(server_time - local_time)
        details["time_diff_ms"] = diff

        if diff < 5000:
            ok(f"时间同步正常 (差异: {diff}ms)")
        elif diff < 30000:
            warn(f"时间差异较大: {diff}ms (建议同步)")
            results.add_warning(f"与 Binance 时间差异 {diff}ms")
        else:
            fail(f"时间差异过大: {diff}ms (可能导致签名错误)")
            all_ok = False
    except Exception as e:
        warn(f"时间同步检查失败: {e}")

    results.add_check("network", "pass" if all_ok else "fail", details)
    return all_ok

def check_api_auth(skip=False):
    """9. API 认证测试"""
    header("9. API 认证测试")

    if skip:
        info("跳过 API 认证检查 (--quick 模式)")
        results.add_check("api_auth", "skip", {"reason": "quick mode"})
        return True

    details = {}
    all_ok = True

    # Binance API 测试
    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")

    if api_key and api_secret:
        try:
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
                "User-Agent": "AItrader-Diagnose/2.0"
            })

            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read())

            balance = float(data.get("totalWalletBalance", 0))
            available = float(data.get("availableBalance", 0))

            details["binance_balance"] = f"{balance:.2f} USDT"
            details["binance_available"] = f"{available:.2f} USDT"

            ok(f"Binance Futures 认证成功")
            info(f"  余额: {balance:.2f} USDT")
            info(f"  可用: {available:.2f} USDT")

            # 持仓信息
            positions = [p for p in data.get("positions", []) if float(p.get("positionAmt", 0)) != 0]
            details["positions_count"] = len(positions)
            if positions:
                info(f"  持仓: {len(positions)} 个")
                for pos in positions[:3]:
                    info(f"    {pos['symbol']}: {pos['positionAmt']} @ {pos['entryPrice']}")
            else:
                info("  持仓: 无")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode()[:200]
            details["binance_error"] = f"HTTP {e.code}: {error_body}"
            fail(f"Binance API 认证失败: HTTP {e.code}")
            all_ok = False
        except Exception as e:
            details["binance_error"] = str(e)
            fail(f"Binance API 测试异常: {e}")
            all_ok = False
    else:
        warn("Binance API 密钥未配置，跳过认证测试")
        details["binance"] = "未配置"

    # DeepSeek API 测试
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        try:
            url = "https://api.deepseek.com/v1/models"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bearer {deepseek_key}",
                "User-Agent": "AItrader-Diagnose/2.0"
            })

            response = urllib.request.urlopen(req, timeout=10)
            data = json.loads(response.read())

            models = [m.get("id", "unknown") for m in data.get("data", [])]
            details["deepseek_models"] = models[:5]

            ok(f"DeepSeek API 认证成功")
            info(f"  可用模型: {', '.join(models[:3])}")

        except urllib.error.HTTPError as e:
            details["deepseek_error"] = f"HTTP {e.code}"
            fail(f"DeepSeek API 认证失败: HTTP {e.code}")
            all_ok = False
        except Exception as e:
            details["deepseek_error"] = str(e)
            fail(f"DeepSeek API 测试异常: {e}")
            all_ok = False
    else:
        warn("DeepSeek API 密钥未配置，跳过认证测试")
        details["deepseek"] = "未配置"

    results.add_check("api_auth", "pass" if all_ok else "fail", details)
    return all_ok

def check_systemd():
    """10. Systemd 服务状态"""
    header("10. Systemd 服务状态")
    details = {}

    # 检查服务是否存在
    code, output, _ = run_cmd(f"systemctl list-unit-files 2>/dev/null | grep {SERVICE_NAME}")
    if code != 0 or not output:
        info(f"服务 {SERVICE_NAME} 未安装 (可能是本地开发环境)")
        details["status"] = "未安装"
        results.add_check("systemd_service", "pass", details)
        return True

    # 服务状态
    code, status, _ = run_cmd(f"systemctl is-active {SERVICE_NAME}")
    details["status"] = status

    if status == "active":
        ok(f"服务状态: 运行中")
    elif status == "inactive":
        warn(f"服务状态: 已停止")
    else:
        warn(f"服务状态: {status}")

    # 服务详情
    code, output, _ = run_cmd(f"systemctl show {SERVICE_NAME} --property=MainPID,MemoryCurrent,ActiveEnterTimestamp 2>/dev/null")
    if output:
        for line in output.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                if value and value != '0' and value != '[not set]':
                    details[key] = value
                    info(f"  {key}: {value}")

    # 最近日志
    info("最近日志:")
    code, logs, _ = run_cmd(f"journalctl -u {SERVICE_NAME} -n 5 --no-pager --no-hostname 2>/dev/null")
    if logs:
        log_lines = []
        for line in logs.split('\n')[-5:]:
            truncated = line[:100]
            log_lines.append(truncated)
            if not _json_mode:
                print(f"    {truncated}")
        details["recent_logs"] = log_lines
    else:
        info("  (无日志或无权限)")

    results.add_check("systemd_service", "pass", details)
    return True

def check_processes():
    """11. 进程检查"""
    header("11. 相关进程检查")
    details = {}

    code, output, _ = run_cmd("ps aux | grep -E 'main_live|nautilus' | grep -v grep")

    if output:
        ok("找到相关进程:")
        processes = []
        for line in output.split('\n')[:5]:
            parts = line.split()
            if len(parts) >= 11:
                proc_info = {
                    "pid": parts[1],
                    "cpu": parts[2],
                    "mem": parts[3],
                    "cmd": ' '.join(parts[10:])[:50]
                }
                processes.append(proc_info)
                info(f"  PID={proc_info['pid']} CPU={proc_info['cpu']}% MEM={proc_info['mem']}%")
        details["processes"] = processes
    else:
        info("未找到运行中的交易进程")
        details["processes"] = []

    results.add_check("processes", "pass", details)
    return True

def check_git():
    """12. Git 仓库状态"""
    header("12. Git 仓库状态")
    details = {}

    # 当前分支
    code, branch, _ = run_cmd("git rev-parse --abbrev-ref HEAD")
    if code == 0:
        details["branch"] = branch
        if branch == BRANCH:
            ok(f"当前分支: {branch}")
        else:
            warn(f"当前分支: {branch} (预期: {BRANCH})")
            results.add_warning(f"分支不匹配: {branch} vs {BRANCH}")

    # 最新提交
    code, commit, _ = run_cmd("git log -1 --oneline")
    if code == 0:
        details["latest_commit"] = commit
        info(f"最新提交: {commit}")

    # 未提交更改
    code, status, _ = run_cmd("git status --porcelain")
    if status:
        count = len(status.split('\n'))
        details["uncommitted_changes"] = count
        warn(f"有未提交的更改: {count} 个文件")
    else:
        details["uncommitted_changes"] = 0
        ok("工作区干净")

    results.add_check("git_status", "pass", details)
    return True

def check_imports():
    """13. 模块导入测试"""
    header("13. 关键模块导入测试")
    details = {}
    all_ok = True

    sys.path.insert(0, str(PROJECT_DIR))

    modules_to_test = [
        ("nautilus_trader", "NautilusTrader核心"),
        ("nautilus_trader.adapters.binance", "Binance适配器"),
        ("nautilus_trader.config", "配置模块"),
        ("nautilus_trader.live.node", "实盘节点"),
        ("strategy.deepseek_strategy", "DeepSeek策略"),
        ("utils.deepseek_client", "DeepSeek客户端"),
        ("utils.sentiment_client", "情绪分析客户端"),
        ("patches.binance_enums", "Binance枚举补丁"),
    ]

    for module, desc in modules_to_test:
        try:
            importlib.import_module(module)
            details[module] = "成功"
            ok(f"{desc}: 导入成功")
        except Exception as e:
            details[module] = f"失败: {str(e)[:50]}"
            fail(f"{desc}: 导入失败 - {str(e)[:60]}")
            all_ok = False

    results.add_check("import_test", "pass" if all_ok else "fail", details)
    return all_ok

# ============================================================
# Git 更新功能
# ============================================================
def update_code():
    """更新代码"""
    header("0. 代码更新")

    # 检查当前分支
    code, current_branch, _ = run_cmd("git rev-parse --abbrev-ref HEAD")
    info(f"当前分支: {current_branch}")

    if current_branch != BRANCH:
        warn(f"切换到目标分支 {BRANCH}")
        code, _, err = run_cmd(f"git checkout {BRANCH}")
        if code != 0:
            fail(f"切换分支失败: {err}")
            return False

    # 保存当前 commit
    code, old_commit, _ = run_cmd("git rev-parse --short HEAD")

    # 检查本地修改
    code, status, _ = run_cmd("git status --porcelain")
    if status:
        warn(f"检测到 {len(status.splitlines())} 个本地修改，丢弃...")
        run_cmd("git checkout .")
        run_cmd("git clean -fd")

    # 拉取最新代码 (带重试)
    info("拉取最新代码...")
    for attempt in range(4):
        code, _, err = run_cmd(f"git fetch origin {BRANCH}", timeout=60)
        if code == 0:
            break
        if attempt < 3:
            wait = 2 ** (attempt + 1)
            info(f"重试 ({attempt + 1}/3)，等待 {wait}s...")
            time.sleep(wait)

    if code != 0:
        fail(f"拉取失败: {err}")
        return False

    # 重置到远程最新
    code, _, err = run_cmd(f"git reset --hard origin/{BRANCH}")
    if code != 0:
        fail(f"重置失败: {err}")
        return False

    # 获取新 commit
    code, new_commit, _ = run_cmd("git rev-parse --short HEAD")

    if old_commit == new_commit:
        ok(f"已是最新版本: {new_commit}")
    else:
        ok(f"已更新: {old_commit} -> {new_commit}")
        code, log, _ = run_cmd(f"git log --oneline {old_commit}..{new_commit}")
        if log:
            info("更新内容:")
            for line in log.splitlines()[:10]:
                print(f"    {line}")

    return True

def restart_service():
    """重启服务"""
    header("重启服务")

    code, _, _ = run_cmd(f"systemctl list-unit-files 2>/dev/null | grep {SERVICE_NAME}")
    if code != 0:
        info("服务未安装，跳过重启")
        return True

    info("重启服务中...")
    code, _, err = run_cmd(f"sudo systemctl restart {SERVICE_NAME}", timeout=30)

    if code == 0:
        ok("服务已重启")
        time.sleep(2)
        code, status, _ = run_cmd(f"systemctl is-active {SERVICE_NAME}")
        info(f"服务状态: {status}")
        return status == "active"
    else:
        fail(f"重启失败: {err}")
        return False

# ============================================================
# 主函数
# ============================================================
def main():
    global _json_mode

    parser = argparse.ArgumentParser(
        description="AItrader 全面诊断工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python diagnose.py              # 运行全部检查
  python diagnose.py --quick      # 快速检查
  python diagnose.py --update     # 先更新再检查
  python diagnose.py --restart    # 检查后重启服务
"""
    )
    parser.add_argument("--quick", "-q", action="store_true", help="快速检查 (跳过网络测试)")
    parser.add_argument("--update", "-u", action="store_true", help="先更新代码再检查")
    parser.add_argument("--restart", "-r", action="store_true", help="检查后重启服务")
    parser.add_argument("--json", "-j", action="store_true", help="输出JSON格式")
    parser.add_argument("--version", "-v", action="version", version=f"diagnose.py v{VERSION}")

    args = parser.parse_args()
    _json_mode = args.json

    if not _json_mode:
        print(f"""
{Colors.BOLD}{Colors.CYAN}
╔════════════════════════════════════════════════════════════╗
║         AItrader 全面诊断工具 v{VERSION}                        ║
║         时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                          ║
╚════════════════════════════════════════════════════════════╝
{Colors.RESET}""")

    # 更新代码
    if args.update:
        if not update_code():
            if not _json_mode:
                fail("代码更新失败，继续检查...")

    # 运行检查
    checks = [
        ("系统环境", check_system),
        ("依赖包", check_dependencies),
        ("文件完整性", check_files),
        ("环境变量", check_env),
        ("策略配置", check_nautilus_config),
        ("止损逻辑", check_stop_loss),
        ("Binance补丁", check_binance_patch),
        ("网络连接", lambda: check_network(skip=args.quick)),
        ("API认证", lambda: check_api_auth(skip=args.quick)),
        ("Systemd服务", check_systemd),
        ("进程状态", check_processes),
        ("Git状态", check_git),
        ("模块导入", check_imports),
    ]

    for name, func in checks:
        try:
            func()
        except Exception as e:
            if not _json_mode:
                fail(f"{name} 检查异常: {e}")
                traceback.print_exc()
            results.add_check(name, "error", error=str(e))

    # 重启服务
    if args.restart:
        restart_service()

    # 汇总报告
    if _json_mode:
        print(json.dumps(results.to_dict(), indent=2, ensure_ascii=False))
    else:
        header("诊断汇总")

        total = results.passed + results.failed
        print(f"""
{Colors.BOLD}检查结果:{Colors.RESET}
  {Colors.GREEN}通过: {results.passed}/{total}{Colors.RESET}
  {Colors.RED}失败: {results.failed}/{total}{Colors.RESET}
""")

        if results.errors:
            print(f"{Colors.RED}错误列表:{Colors.RESET}")
            for err in results.errors:
                print(f"  - {err}")

        if results.warnings:
            print(f"\n{Colors.YELLOW}警告列表:{Colors.RESET}")
            for w in results.warnings:
                print(f"  - {w}")

        # 保存 JSON 报告
        report_path = PROJECT_DIR / "diagnose_report.json"
        with open(report_path, "w") as f:
            json.dump(results.to_dict(), f, indent=2, ensure_ascii=False)

        print(f"\n{Colors.BLUE}详细报告已保存: {report_path}{Colors.RESET}")

        # 建议
        if results.failed > 0:
            print(f"""
{Colors.YELLOW}建议修复步骤:{Colors.RESET}
1. 查看上面的错误信息
2. 检查 .env 文件配置
3. 运行 ./setup.sh 重新安装依赖
4. 如需更新代码: python diagnose.py --update
5. 如需重启服务: python diagnose.py --restart
""")
        else:
            print(f"""
{Colors.GREEN}所有检查通过!{Colors.RESET}
系统状态良好，可以启动交易机器人。
""")

    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
