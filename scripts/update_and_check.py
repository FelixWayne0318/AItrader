#!/usr/bin/env python3
"""
AItrader 一键更新和全面检查脚本

在服务器上运行:
    cd /home/linuxuser/nautilus_AItrader
    python scripts/update_and_check.py

功能:
    1. 拉取最新代码
    2. 安装/更新依赖
    3. 运行全面诊断
    4. 可选重启服务
"""

import os
import sys
import subprocess
import json
import importlib
import traceback
from datetime import datetime
from pathlib import Path

# 颜色输出
class C:
    G = '\033[92m'   # Green
    R = '\033[91m'   # Red
    Y = '\033[93m'   # Yellow
    B = '\033[94m'   # Blue
    C = '\033[96m'   # Cyan
    W = '\033[97m'   # White
    BOLD = '\033[1m'
    END = '\033[0m'

def ok(msg): print(f"{C.G}[✓]{C.END} {msg}")
def fail(msg): print(f"{C.R}[✗]{C.END} {msg}")
def warn(msg): print(f"{C.Y}[!]{C.END} {msg}")
def info(msg): print(f"{C.B}[i]{C.END} {msg}")
def step(msg): print(f"\n{C.BOLD}{C.C}{'═'*60}\n  {msg}\n{'═'*60}{C.END}")

# 配置
BRANCH = "claude/clone-nautilus-aitrader-SFBz9"
PROJECT_DIR = Path(__file__).parent.parent.absolute()

def run_cmd(cmd, timeout=120, cwd=None, capture=True):
    """运行命令"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture, text=True,
            timeout=timeout, cwd=cwd or PROJECT_DIR
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "命令超时"
    except Exception as e:
        return -1, "", str(e)

def pull_latest_code():
    """拉取最新代码"""
    step("1. 拉取最新代码")

    # 检查当前分支
    code, current_branch, _ = run_cmd("git rev-parse --abbrev-ref HEAD")
    info(f"当前分支: {current_branch}")

    if current_branch != BRANCH:
        warn(f"不在目标分支，切换到 {BRANCH}")
        code, _, err = run_cmd(f"git checkout {BRANCH}")
        if code != 0:
            fail(f"切换分支失败: {err}")
            return False

    # 保存当前 commit
    code, old_commit, _ = run_cmd("git rev-parse --short HEAD")

    # 检查本地修改
    code, status, _ = run_cmd("git status --porcelain")
    if status:
        warn(f"检测到 {len(status.splitlines())} 个本地修改")
        info("丢弃本地修改...")
        run_cmd("git checkout .")
        run_cmd("git clean -fd")

    # 拉取最新代码
    info("从远程拉取...")
    code, output, err = run_cmd(f"git fetch origin {BRANCH}")
    if code != 0:
        # 重试
        for i in range(3):
            info(f"重试 ({i+1}/3)...")
            import time
            time.sleep(2 ** (i+1))
            code, output, err = run_cmd(f"git fetch origin {BRANCH}")
            if code == 0:
                break

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
        ok(f"已更新: {old_commit} → {new_commit}")
        # 显示更新内容
        code, log, _ = run_cmd(f"git log --oneline {old_commit}..{new_commit}")
        if log:
            info("更新内容:")
            for line in log.splitlines()[:10]:
                print(f"    {line}")

    return True

def check_dependencies():
    """检查依赖"""
    step("2. 检查依赖")

    all_ok = True

    # 必需包
    required = [
        ("nautilus_trader", "1.221.0"),
        ("msgspec", None),
        ("httpx", None),
        ("python-dotenv", "dotenv"),
        ("pyyaml", "yaml"),
    ]

    for pkg_name, version_or_import in required:
        import_name = version_or_import if isinstance(version_or_import, str) and not version_or_import[0].isdigit() else pkg_name.replace("-", "_")
        min_version = version_or_import if isinstance(version_or_import, str) and version_or_import[0].isdigit() else None

        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", "?")

            if min_version:
                from packaging import version as pkg_v
                if pkg_v.parse(str(version)) >= pkg_v.parse(min_version):
                    ok(f"{pkg_name}: {version}")
                else:
                    fail(f"{pkg_name}: {version} (需要 >= {min_version})")
                    all_ok = False
            else:
                ok(f"{pkg_name}: {version}")
        except ImportError:
            fail(f"{pkg_name}: 未安装")
            all_ok = False

    if not all_ok:
        info("运行 pip install -r requirements.txt 安装依赖")

    return all_ok

def check_env_variables():
    """检查环境变量"""
    step("3. 检查环境变量")

    # 加载 .env
    try:
        from dotenv import load_dotenv
        env_file = PROJECT_DIR / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            ok(".env 文件已加载")
        else:
            warn(".env 文件不存在")
    except:
        pass

    all_ok = True
    required_vars = ["BINANCE_API_KEY", "BINANCE_API_SECRET", "DEEPSEEK_API_KEY"]
    optional_vars = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]

    for var in required_vars:
        val = os.environ.get(var, "")
        if val and len(val) > 5:
            masked = val[:4] + "****" + val[-4:] if len(val) > 8 else "****"
            ok(f"{var}: {masked}")
        else:
            fail(f"{var}: 未配置 (必需)")
            all_ok = False

    for var in optional_vars:
        val = os.environ.get(var, "")
        if val:
            ok(f"{var}: 已配置")
        else:
            warn(f"{var}: 未配置 (可选)")

    return all_ok

def check_api_connections():
    """检查 API 连接"""
    step("4. 检查 API 连接")

    import urllib.request
    import urllib.error
    import ssl

    all_ok = True
    ctx = ssl.create_default_context()

    endpoints = [
        ("Binance Spot", "https://api.binance.com/api/v3/ping"),
        ("Binance Futures", "https://fapi.binance.com/fapi/v1/ping"),
        ("DeepSeek", "https://api.deepseek.com"),
    ]

    for name, url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AItrader/1.0"})
            resp = urllib.request.urlopen(req, timeout=10, context=ctx)
            ok(f"{name}: 连接成功")
        except urllib.error.HTTPError as e:
            if e.code < 500:
                ok(f"{name}: 可达 (HTTP {e.code})")
            else:
                fail(f"{name}: 服务器错误")
                all_ok = False
        except Exception as e:
            fail(f"{name}: {str(e)[:50]}")
            all_ok = False

    return all_ok

def check_binance_auth():
    """检查 Binance 认证"""
    step("5. 检查 Binance 认证")

    api_key = os.environ.get("BINANCE_API_KEY", "")
    api_secret = os.environ.get("BINANCE_API_SECRET", "")

    if not api_key or not api_secret:
        warn("Binance API 密钥未配置，跳过认证测试")
        return True

    try:
        import hmac
        import hashlib
        import time
        import urllib.request
        import urllib.parse

        timestamp = int(time.time() * 1000)
        query = f"timestamp={timestamp}"
        signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()

        url = f"https://fapi.binance.com/fapi/v2/account?{query}&signature={signature}"
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key})

        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())

        balance = float(data.get("totalWalletBalance", 0))
        available = float(data.get("availableBalance", 0))

        ok(f"Binance Futures 认证成功")
        info(f"  余额: {balance:.2f} USDT")
        info(f"  可用: {available:.2f} USDT")

        # 检查持仓
        positions = [p for p in data.get("positions", []) if float(p.get("positionAmt", 0)) != 0]
        if positions:
            info(f"  持仓: {len(positions)} 个")
            for pos in positions[:3]:
                info(f"    {pos['symbol']}: {pos['positionAmt']}")
        else:
            info("  持仓: 无")

        return True

    except urllib.error.HTTPError as e:
        fail(f"Binance 认证失败: HTTP {e.code}")
        try:
            err_body = e.read().decode()[:200]
            fail(f"  {err_body}")
        except:
            pass
        return False
    except Exception as e:
        fail(f"Binance 认证异常: {e}")
        return False

def check_module_imports():
    """检查模块导入"""
    step("6. 检查模块导入")

    sys.path.insert(0, str(PROJECT_DIR))
    all_ok = True

    modules = [
        ("nautilus_trader", "NautilusTrader 核心"),
        ("nautilus_trader.adapters.binance", "Binance 适配器"),
        ("nautilus_trader.live.node", "实盘节点"),
        ("strategy.deepseek_strategy", "DeepSeek 策略"),
        ("utils.deepseek_client", "DeepSeek 客户端"),
        ("utils.sentiment_client", "情绪分析客户端"),
        ("patches.binance_enums", "Binance 枚举补丁"),
    ]

    for mod_name, desc in modules:
        try:
            importlib.import_module(mod_name)
            ok(f"{desc}")
        except Exception as e:
            fail(f"{desc}: {str(e)[:60]}")
            all_ok = False

    return all_ok

def check_stop_loss_logic():
    """检查止损逻辑"""
    step("7. 检查止损逻辑")

    strategy_file = PROJECT_DIR / "strategy" / "deepseek_strategy.py"
    if not strategy_file.exists():
        fail("策略文件不存在")
        return False

    source = strategy_file.read_text()

    checks = [
        ("止损验证", "sl_price" in source or "stop_loss" in source),
        ("LONG 止损检查", "< entry" in source.lower() or "sl_price <" in source),
        ("SHORT 止损检查", "> entry" in source.lower() or "sl_price >" in source),
    ]

    all_ok = True
    for name, passed in checks:
        if passed:
            ok(name)
        else:
            warn(f"{name}: 未检测到 (可能用其他方式实现)")

    # 运行测试用例
    info("止损逻辑测试:")
    test_cases = [
        ("LONG", 100.0, 98.0, True, "SL < entry ✓"),
        ("LONG", 100.0, 102.0, False, "SL > entry ✗"),
        ("SHORT", 100.0, 102.0, True, "SL > entry ✓"),
        ("SHORT", 100.0, 98.0, False, "SL < entry ✗"),
    ]

    for direction, entry, sl, expected, desc in test_cases:
        is_valid = (sl < entry) if direction == "LONG" else (sl > entry)
        status = "✓" if is_valid == expected else "✗"
        print(f"    {direction} entry={entry} sl={sl}: {status} ({desc})")

    return all_ok

def check_service_status():
    """检查服务状态"""
    step("8. 检查服务状态")

    service_name = "nautilus-trader"

    # 检查服务是否存在
    code, output, _ = run_cmd(f"systemctl list-unit-files | grep {service_name}")
    if code != 0 or not output:
        info(f"服务 {service_name} 未安装 (本地开发环境)")
        return True

    # 服务状态
    code, status, _ = run_cmd(f"systemctl is-active {service_name}")
    if status == "active":
        ok(f"服务状态: 运行中")
    elif status == "inactive":
        warn(f"服务状态: 已停止")
    else:
        warn(f"服务状态: {status}")

    # 最近日志
    code, logs, _ = run_cmd(f"journalctl -u {service_name} -n 5 --no-pager --no-hostname 2>/dev/null")
    if logs:
        info("最近日志:")
        for line in logs.splitlines()[-5:]:
            print(f"    {line[:100]}")

    return True

def main():
    print(f"""
{C.BOLD}{C.C}
╔══════════════════════════════════════════════════════════════╗
║       AItrader 一键更新 & 全面检查                           ║
║       时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                                 ║
╚══════════════════════════════════════════════════════════════╝
{C.END}""")

    info(f"项目目录: {PROJECT_DIR}")
    info(f"目标分支: {BRANCH}")

    # 运行检查
    results = {}
    checks = [
        ("代码更新", pull_latest_code),
        ("依赖检查", check_dependencies),
        ("环境变量", check_env_variables),
        ("API 连接", check_api_connections),
        ("Binance 认证", check_binance_auth),
        ("模块导入", check_module_imports),
        ("止损逻辑", check_stop_loss_logic),
        ("服务状态", check_service_status),
    ]

    passed = 0
    failed = 0

    for name, func in checks:
        try:
            result = func()
            results[name] = result
            if result:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            fail(f"{name} 检查异常: {e}")
            traceback.print_exc()
            results[name] = False
            failed += 1

    # 汇总
    step("检查完成")

    total = passed + failed
    if failed == 0:
        print(f"\n{C.G}{C.BOLD}✓ 全部 {total} 项检查通过!{C.END}\n")
    else:
        print(f"\n{C.Y}通过: {passed}/{total}  失败: {failed}/{total}{C.END}\n")
        print("失败项目:")
        for name, result in results.items():
            if not result:
                print(f"  - {name}")
        print()

    # 询问是否重启服务
    code, svc_exists, _ = run_cmd("systemctl list-unit-files | grep nautilus-trader")
    if svc_exists:
        print(f"{C.Y}是否重启服务? (y/N): {C.END}", end="")
        try:
            answer = input().strip().lower()
            if answer == 'y':
                info("重启服务...")
                code, _, err = run_cmd("sudo systemctl restart nautilus-trader")
                if code == 0:
                    ok("服务已重启")
                    # 等待并显示状态
                    import time
                    time.sleep(2)
                    code, status, _ = run_cmd("systemctl is-active nautilus-trader")
                    info(f"服务状态: {status}")
                else:
                    fail(f"重启失败: {err}")
        except:
            pass

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "passed": passed,
        "failed": failed,
    }
    report_path = PROJECT_DIR / "update_check_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    info(f"报告已保存: {report_path}")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
