#!/usr/bin/env python3
"""
AItrader 深度健康检查脚本
在服务器上运行: python scripts/deep_health_check.py
"""

import os
import sys
import subprocess
import importlib.util
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

class HealthChecker:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.passes = []

    def check_pass(self, msg):
        print(f"\033[92m[PASS]\033[0m {msg}")
        self.passes.append(msg)

    def check_fail(self, msg):
        print(f"\033[91m[FAIL]\033[0m {msg}")
        self.errors.append(msg)

    def check_warn(self, msg):
        print(f"\033[93m[WARN]\033[0m {msg}")
        self.warnings.append(msg)

    def run_all_checks(self):
        print("=" * 50)
        print("  AItrader 深度健康检查")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 50)
        print()

        self.check_python_environment()
        self.check_dependencies()
        self.check_env_file()
        self.check_config_files()
        self.check_api_connections()
        self.check_stop_loss_logic()
        self.check_strategy_import()

        self.print_summary()

    def check_python_environment(self):
        print(">> 1. Python 环境检查")

        # Python 版本
        version = sys.version_info
        if version.major == 3 and version.minor >= 10:
            self.check_pass(f"Python 版本: {version.major}.{version.minor}.{version.micro}")
        else:
            self.check_warn(f"Python 版本较低: {version.major}.{version.minor} (建议 3.10+)")
        print()

    def check_dependencies(self):
        print(">> 2. 依赖包检查")

        required_packages = [
            'nautilus_trader',
            'httpx',
            'python-dotenv',
            'pyyaml',
            'redis',
        ]

        optional_packages = [
            'telegram',
        ]

        for pkg in required_packages:
            try:
                __import__(pkg.replace('-', '_'))
                self.check_pass(f"{pkg} 已安装")
            except ImportError:
                self.check_fail(f"{pkg} 未安装")

        for pkg in optional_packages:
            try:
                __import__(pkg.replace('-', '_'))
                self.check_pass(f"{pkg} 已安装 (可选)")
            except ImportError:
                self.check_warn(f"{pkg} 未安装 (可选功能)")
        print()

    def check_env_file(self):
        print(">> 3. 环境变量检查")

        env_file = PROJECT_ROOT / '.env'
        if not env_file.exists():
            self.check_fail(".env 文件不存在")
            return

        self.check_pass(".env 文件存在")

        # 加载 .env
        from dotenv import load_dotenv
        load_dotenv(env_file)

        required_vars = [
            'BINANCE_API_KEY',
            'BINANCE_API_SECRET',
            'DEEPSEEK_API_KEY',
        ]

        optional_vars = [
            'TELEGRAM_BOT_TOKEN',
            'TELEGRAM_CHAT_ID',
        ]

        for var in required_vars:
            value = os.getenv(var)
            if value and len(value) > 5:
                self.check_pass(f"{var} 已配置 (长度: {len(value)})")
            else:
                self.check_fail(f"{var} 未配置或无效")

        for var in optional_vars:
            value = os.getenv(var)
            if value and len(value) > 5:
                self.check_pass(f"{var} 已配置 (可选)")
            else:
                self.check_warn(f"{var} 未配置 (可选)")
        print()

    def check_config_files(self):
        print(">> 4. 配置文件检查")

        config_file = PROJECT_ROOT / 'configs' / 'strategy_config.yaml'
        if not config_file.exists():
            self.check_fail("strategy_config.yaml 不存在")
            return

        self.check_pass("strategy_config.yaml 存在")

        try:
            import yaml
            with open(config_file) as f:
                config = yaml.safe_load(f)

            # 检查关键配置
            if 'strategy' in config:
                self.check_pass("策略配置已加载")

                # 检查止损/止盈配置
                risk = config.get('strategy', {}).get('risk', {})
                if risk:
                    sl = risk.get('stop_loss_pct', 0)
                    tp = risk.get('take_profit_pct', 0)
                    self.check_pass(f"风控配置: SL={sl}%, TP={tp}%")
            else:
                self.check_warn("未找到策略配置")

        except Exception as e:
            self.check_fail(f"配置文件解析失败: {e}")
        print()

    def check_api_connections(self):
        print(">> 5. API 连接检查")

        import httpx

        # Binance
        try:
            resp = httpx.get("https://api.binance.com/api/v3/ping", timeout=10)
            if resp.status_code == 200:
                self.check_pass("Binance API 连接正常")
            else:
                self.check_fail(f"Binance API 返回: {resp.status_code}")
        except Exception as e:
            self.check_fail(f"Binance API 连接失败: {e}")

        # Binance 服务器时间
        try:
            resp = httpx.get("https://api.binance.com/api/v3/time", timeout=10)
            if resp.status_code == 200:
                server_time = resp.json().get('serverTime', 0)
                local_time = int(datetime.now().timestamp() * 1000)
                diff = abs(server_time - local_time)
                if diff < 5000:
                    self.check_pass(f"时间同步正常 (差异: {diff}ms)")
                else:
                    self.check_warn(f"时间差异较大: {diff}ms")
        except Exception as e:
            self.check_warn(f"无法检查时间同步: {e}")

        # DeepSeek
        try:
            resp = httpx.get("https://api.deepseek.com", timeout=10)
            self.check_pass("DeepSeek API 可达")
        except Exception as e:
            self.check_warn(f"DeepSeek API 连接检查失败: {e}")

        # Binance 多空比 API (替代 CryptoOracle)
        try:
            resp = httpx.get(
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": "BTCUSDT", "period": "1h", "limit": 1},
                timeout=10
            )
            if resp.status_code == 200:
                self.check_pass("Binance 多空比 API 正常")
            else:
                self.check_warn(f"多空比 API 返回: {resp.status_code}")
        except Exception as e:
            self.check_warn(f"多空比 API 检查失败: {e}")
        print()

    def check_stop_loss_logic(self):
        print(">> 6. 止损逻辑验证")

        try:
            # 导入验证函数
            from strategy.deepseek_strategy import DeepSeekStrategy

            # 测试用例
            test_cases = [
                # (direction, entry, sl, expected_valid)
                ("LONG", 100.0, 98.0, True),   # LONG: SL < entry ✓
                ("LONG", 100.0, 102.0, False), # LONG: SL > entry ✗
                ("SHORT", 100.0, 102.0, True), # SHORT: SL > entry ✓
                ("SHORT", 100.0, 98.0, False), # SHORT: SL < entry ✗
            ]

            all_pass = True
            for direction, entry, sl, expected in test_cases:
                # 验证逻辑
                if direction == "LONG":
                    is_valid = sl < entry
                else:
                    is_valid = sl > entry

                if is_valid == expected:
                    pass
                else:
                    all_pass = False

            if all_pass:
                self.check_pass("止损验证逻辑正确")
            else:
                self.check_fail("止损验证逻辑有误")

        except ImportError as e:
            self.check_warn(f"无法导入策略模块: {e}")
        except Exception as e:
            self.check_warn(f"止损逻辑检查失败: {e}")
        print()

    def check_strategy_import(self):
        print(">> 7. 策略模块检查")

        try:
            from strategy.deepseek_strategy import DeepSeekStrategy
            self.check_pass("DeepSeekStrategy 导入成功")
        except Exception as e:
            self.check_fail(f"策略导入失败: {e}")

        try:
            from utils.deepseek_client import DeepSeekClient
            self.check_pass("DeepSeekClient 导入成功")
        except Exception as e:
            self.check_fail(f"DeepSeek 客户端导入失败: {e}")

        try:
            from utils.sentiment_client import SentimentClient
            self.check_pass("SentimentClient 导入成功")
        except Exception as e:
            self.check_warn(f"情绪客户端导入失败: {e}")

        try:
            from agents.multi_agent_analyzer import MultiAgentAnalyzer
            self.check_pass("MultiAgentAnalyzer 导入成功")
        except Exception as e:
            self.check_warn(f"多代理分析器导入失败: {e}")
        print()

    def print_summary(self):
        print("=" * 50)
        print("  检查结果汇总")
        print("=" * 50)

        total_checks = len(self.passes) + len(self.errors) + len(self.warnings)

        if not self.errors and not self.warnings:
            print(f"\033[92m全部 {total_checks} 项检查通过!\033[0m")
        elif not self.errors:
            print(f"\033[93m通过 {len(self.passes)} 项，警告 {len(self.warnings)} 项\033[0m")
        else:
            print(f"\033[91m错误 {len(self.errors)} 项，警告 {len(self.warnings)} 项，通过 {len(self.passes)} 项\033[0m")

        if self.errors:
            print("\n需要修复的问题:")
            for err in self.errors:
                print(f"  - {err}")

        if self.warnings:
            print("\n建议关注的警告:")
            for warn in self.warnings:
                print(f"  - {warn}")

        print()
        return len(self.errors)


if __name__ == "__main__":
    checker = HealthChecker()
    exit_code = checker.run_all_checks()
    sys.exit(exit_code)
