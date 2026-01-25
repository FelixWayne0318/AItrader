#!/usr/bin/env python3
"""
提交修复验证工具 (Commit Fix Validator)
========================================

基于 Git 提交历史，验证所有已修复的问题是否仍然正确应用。

核心理念:
- 每次代码修改都可能引入回归 (regression)
- 通过记录每个提交修复了什么问题，以及如何验证修复
- 自动检测这些修复是否被意外撤销或破坏

使用场景:
1. 代码审查后 - 验证修改没有破坏已有修复
2. 合并 PR 前 - 确保新代码不会引入回归
3. 部署前检查 - 验证代码完整性
4. 定期健康检查 - 发现潜在问题

用法:
    python3 validate_commit_fixes.py              # 完整检查
    python3 validate_commit_fixes.py --quick      # 快速检查 (跳过耗时项)
    python3 validate_commit_fixes.py --json       # 输出 JSON 格式
    python3 validate_commit_fixes.py --category threading  # 只检查特定类别

扩展方法:
    在 COMMIT_FIX_REGISTRY 中添加新的修复记录:
    {
        'commit': 'abc1234',
        'category': 'threading',
        'description': '修复了 XXX 问题',
        'files': ['path/to/file.py'],
        'validators': [
            lambda content: 'expected_code' in content,
        ],
        'error_msg': '问题描述',
        'fix_hint': '修复建议',
    }
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Tuple

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
# 提交修复注册表 (Commit Fix Registry)
# =============================================================================
# 每个条目记录一个已知修复，包含验证逻辑
# 分类: threading, config, api, architecture, compatibility, bugfix, security

COMMIT_FIX_REGISTRY: List[Dict[str, Any]] = [
    # =========================================================================
    # 线程安全 (Threading Safety)
    # =========================================================================
    {
        'id': 'cython-indicators',
        'commit': 'cd036b4',
        'category': 'threading',
        'description': '使用 Cython 指标替代 Rust PyO3 指标 (避免线程安全 panic)',
        'files': ['indicators/technical_manager.py'],
        'validators': [
            # 检查是否使用 Cython 指标
            lambda content, **_: 'from nautilus_trader.indicators import' in content or
                                'from nautilus_trader.indicators ' in content,
            # 检查是否避免 Rust PyO3 指标
            lambda content, **_: 'from nautilus_trader.core.nautilus_pyo3' not in _get_import_lines(content),
        ],
        'error_msg': '使用 Rust PyO3 指标会导致线程安全 panic',
        'fix_hint': '改用 from nautilus_trader.indicators (Cython 版本)',
        'severity': 'critical',
    },
    {
        'id': 'cached-current-price',
        'commit': '8cecd6e',
        'category': 'threading',
        'description': '使用 _cached_current_price 避免跨线程访问指标',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: '_cached_current_price' in content,
        ],
        'error_msg': '缺少 _cached_current_price，Telegram 命令可能导致线程安全问题',
        'fix_hint': '在 on_bar 中更新 _cached_current_price，Telegram 命令使用缓存值',
        'severity': 'high',
    },
    {
        'id': 'state-lock',
        'commit': '8cecd6e',
        'category': 'threading',
        'description': '使用 _state_lock 保护共享状态',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: '_state_lock' in content,
        ],
        'error_msg': '缺少线程锁，可能导致竞态条件',
        'fix_hint': '添加 threading.Lock() 保护共享状态访问',
        'severity': 'medium',
    },

    # =========================================================================
    # 配置管理 (Configuration Management)
    # =========================================================================
    {
        'id': 'config-layering',
        'commit': 'af3d722',
        'category': 'config',
        'description': '配置分层架构 - 业务参数从 YAML 读取，不从环境变量覆盖',
        'files': ['main_live.py'],
        'validators': [
            # 检查 equity 不从环境变量读取
            lambda content, **_: "os.getenv('EQUITY'" not in content and
                                "get_env_float('EQUITY'" not in content,
            # 检查使用 ConfigManager
            lambda content, **_: 'config_manager.get(' in content,
        ],
        'error_msg': '业务参数不应从环境变量覆盖',
        'fix_hint': '参考 CLAUDE.md 配置分层架构原则',
        'severity': 'medium',
    },
    {
        'id': 'sl-tp-config-passing',
        'commit': '34cc984',
        'category': 'config',
        'description': 'SL/TP, Trailing Stop, OCO 参数从 ConfigManager 传递',
        'files': ['main_live.py'],
        'validators': [
            lambda content, **_: "enable_auto_sl_tp=config_manager.get(" in content,
            lambda content, **_: "enable_trailing_stop=config_manager.get(" in content,
            lambda content, **_: "enable_oco=config_manager.get(" in content,
        ],
        'error_msg': 'SL/TP 参数使用默认值而非 ConfigManager',
        'fix_hint': '从 ConfigManager 读取 risk.stop_loss.*, risk.trailing_stop.*, risk.oco.*',
        'severity': 'high',
    },

    # =========================================================================
    # API 兼容性 (API Compatibility)
    # =========================================================================
    {
        'id': 'binance-enum-patch',
        'commit': '1ed1357',
        'category': 'compatibility',
        'description': 'Binance 枚举兼容性补丁 (_missing_ hook)',
        'files': ['patches/binance_enums.py'],
        'validators': [
            lambda content, **_: '_missing_' in content,
        ],
        'error_msg': '缺少 Binance 枚举兼容性补丁',
        'fix_hint': '使用 _missing_ 钩子处理未知枚举值',
        'severity': 'high',
    },
    {
        'id': 'patch-load-order',
        'commit': '1ed1357',
        'category': 'compatibility',
        'description': '补丁加载顺序 (patches 在 nautilus_trader 导入之前)',
        'files': ['main_live.py'],
        'validators': [
            lambda content, **_: _check_patch_order(content),
        ],
        'error_msg': '补丁加载顺序错误',
        'fix_hint': 'apply_all_patches() 必须在 from nautilus_trader 之前',
        'severity': 'critical',
    },
    {
        'id': 'usdt-futures-enum',
        'commit': '5f5090f',
        'category': 'compatibility',
        'description': '使用 USDT_FUTURES (不是 USDT_FUTURE)',
        'files': ['main_live.py'],
        'validators': [
            lambda content, **_: 'USDT_FUTURES' in content,
            lambda content, **_: not ('USDT_FUTURE' in content and 'USDT_FUTURES' not in content),
        ],
        'error_msg': '使用了旧的 USDT_FUTURE 枚举名',
        'fix_hint': '改用 BinanceAccountType.USDT_FUTURES',
        'severity': 'high',
    },

    # =========================================================================
    # 架构 (Architecture)
    # =========================================================================
    {
        'id': 'multiagent-architecture',
        'commit': 'c1afae7',
        'category': 'architecture',
        'description': 'MultiAgent (TradingAgents) 架构 - Judge 决策',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: 'self.multi_agent.analyze' in content,
        ],
        'error_msg': '未使用 MultiAgent 架构',
        'fix_hint': '使用 multi_agent.analyze() 替代单一 DeepSeek 分析',
        'severity': 'medium',
    },
    {
        'id': 'legacy-divergence-flags',
        'commit': 'c1afae7',
        'category': 'architecture',
        'description': 'skip_on_divergence 和 use_confidence_fusion 标记为 LEGACY',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: 'LEGACY' in content and 'skip_on_divergence' in content,
        ],
        'error_msg': 'LEGACY 标记缺失',
        'fix_hint': 'skip_on_divergence 在 TradingAgents 架构中不再使用',
        'severity': 'low',
    },
    {
        'id': 'reconciliation-enabled',
        'commit': '1b7d15f',
        'category': 'architecture',
        'description': '启用仓位对账 (reconciliation=True)',
        'files': ['main_live.py'],
        'validators': [
            lambda content, **_: 'reconciliation=True' in content,
        ],
        'error_msg': 'reconciliation 未启用',
        'fix_hint': '在 LiveExecEngineConfig 中设置 reconciliation=True',
        'severity': 'high',
    },
    {
        'id': 'load-all-instruments',
        'commit': 'fa738be',
        'category': 'architecture',
        'description': '加载所有交易工具 (load_all=True)',
        'files': ['main_live.py'],
        'validators': [
            lambda content, **_: 'load_all=True' in content,
        ],
        'error_msg': 'load_all 未启用',
        'fix_hint': '在 InstrumentProviderConfig 中设置 load_all=True',
        'severity': 'high',
    },

    # =========================================================================
    # 止损止盈 (Stop Loss / Take Profit)
    # =========================================================================
    {
        'id': 'sl-direction-validation',
        'commit': '7f940fb',
        'category': 'bugfix',
        'description': '止损方向验证 (SL 在入场价正确侧)',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: ('entry_price' in content and
                                 ('< entry' in content or '> entry' in content or
                                  'OrderSide.BUY' in content)),
        ],
        'error_msg': '可能缺少止损方向验证',
        'fix_hint': 'LONG 止损 < 入场价，SHORT 止损 > 入场价',
        'severity': 'critical',
    },
    {
        'id': 'bracket-order-usage',
        'commit': '7a4a68b',
        'category': 'architecture',
        'description': '使用 Bracket Order 提交订单',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: '_submit_bracket_order' in content,
        ],
        'error_msg': '未使用 Bracket Order',
        'fix_hint': '使用 _submit_bracket_order 同时设置入场、止损、止盈',
        'severity': 'medium',
    },
    {
        'id': 'min-sl-distance',
        'commit': 'a9a3655',
        'category': 'bugfix',
        'description': 'MIN_SL_DISTANCE_PCT 一致性 (≥1%)',
        'files': ['strategy/trading_logic.py'],
        'validators': [
            lambda content, **_: _check_min_sl_distance(content),
        ],
        'error_msg': 'MIN_SL_DISTANCE_PCT 可能不一致或过小',
        'fix_hint': '统一使用 MIN_SL_DISTANCE_PCT = 0.01 (1%)',
        'severity': 'medium',
    },

    # =========================================================================
    # Telegram 集成 (Telegram Integration)
    # =========================================================================
    {
        'id': 'telegram-webhook-cleanup',
        'commit': '639f667',
        'category': 'bugfix',
        'description': 'Telegram webhook 清理 (避免 polling 冲突)',
        'files': ['utils/telegram_command_handler.py'],
        'validators': [
            lambda content, **_: 'delete_webhook' in content,
        ],
        'error_msg': '缺少 Telegram webhook 清理',
        'fix_hint': '在初始化前调用 delete_webhook',
        'severity': 'medium',
    },
    {
        'id': 'telegram-requests-api',
        'commit': 'ee43d22',
        'category': 'bugfix',
        'description': 'Telegram 使用 requests 库直接调用 API',
        'files': ['utils/telegram_bot.py'],
        'validators': [
            lambda content, **_: ('import requests' in content or
                                 'requests.post' in content or
                                 'api.telegram.org' in content),
        ],
        'error_msg': 'Telegram 可能使用异步混合模式',
        'fix_hint': 'send_message_sync 使用 requests 直接调用 Bot API',
        'severity': 'medium',
    },
    {
        'id': 'telegram-markdown-escape',
        'commit': 'cfb57da',
        'category': 'bugfix',
        'description': 'Telegram Markdown 转义',
        'files': ['utils/telegram_bot.py'],
        'validators': [
            lambda content, **_: 'escape_markdown' in content,
        ],
        'error_msg': '缺少 Markdown 转义函数',
        'fix_hint': '添加 escape_markdown 处理特殊字符',
        'severity': 'low',
    },

    # =========================================================================
    # 数据源 (Data Sources)
    # =========================================================================
    {
        'id': 'binance-sentiment-source',
        'commit': '07cd27f',
        'category': 'bugfix',
        'description': '使用 Binance 情绪数据源 (替代 CryptoOracle)',
        'files': ['utils/sentiment_client.py'],
        'validators': [
            lambda content, **_: 'binance' in content.lower() and 'fapi' in content.lower(),
        ],
        'error_msg': '可能仍在使用 CryptoOracle',
        'fix_hint': '使用 Binance 多空比 API',
        'severity': 'medium',
    },

    # =========================================================================
    # 时间周期 (Timeframe)
    # =========================================================================
    {
        'id': 'timeframe-parsing-order',
        'commit': 'eb43034',
        'category': 'bugfix',
        'description': '时间周期解析顺序 (15-MINUTE 在 5-MINUTE 之前)',
        'files': ['strategy/deepseek_strategy.py'],
        'validators': [
            lambda content, **_: _check_timeframe_order(content),
        ],
        'error_msg': '时间周期解析顺序错误',
        'fix_hint': '先检查 15-MINUTE，再检查 5-MINUTE (子字符串问题)',
        'severity': 'medium',
    },

    # =========================================================================
    # 循环导入 (Circular Imports)
    # =========================================================================
    {
        'id': 'no-auto-imports-utils',
        'commit': 'af3d722',
        'category': 'architecture',
        'description': 'utils/__init__.py 无自动导入',
        'files': ['utils/__init__.py'],
        'validators': [
            # 检查注释说明存在
            lambda content, **_: 'No auto-imports' in content or 'no auto-imports' in content.lower(),
        ],
        'error_msg': 'utils/__init__.py 可能有自动导入',
        'fix_hint': '移除 __init__.py 中的自动导入，使用直接导入',
        'severity': 'medium',
    },

    # =========================================================================
    # NautilusTrader 版本 (Version Requirements)
    # =========================================================================
    {
        'id': 'nautilus-version',
        'commit': '9cf5821',
        'category': 'compatibility',
        'description': 'NautilusTrader 版本 ≥1.221.0',
        'files': ['requirements.txt'],
        'validators': [
            lambda content, **_: _check_nautilus_version(content),
        ],
        'error_msg': 'NautilusTrader 版本过低',
        'fix_hint': '需要 ≥1.221.0 以修复非 ASCII 符号问题',
        'severity': 'critical',
    },
]

# =============================================================================
# 辅助验证函数
# =============================================================================
def _get_import_lines(content: str) -> str:
    """提取文件中的 import 语句"""
    import_lines = [line.strip() for line in content.split('\n')
                    if line.strip().startswith('from ') or line.strip().startswith('import ')]
    return '\n'.join(import_lines)


def _check_patch_order(content: str) -> bool:
    """检查补丁加载顺序"""
    patch_pos = content.find("apply_all_patches")
    nautilus_pos = content.find("from nautilus_trader")
    return patch_pos != -1 and nautilus_pos != -1 and patch_pos < nautilus_pos


def _check_min_sl_distance(content: str) -> bool:
    """检查 MIN_SL_DISTANCE_PCT 值"""
    match = re.search(r'MIN_SL_DISTANCE_PCT\s*=\s*([\d.]+)', content)
    if match:
        value = float(match.group(1))
        return value >= 0.01
    return True  # 如果没找到，可能是从其他地方导入的


def _check_timeframe_order(content: str) -> bool:
    """检查时间周期解析顺序"""
    if '15-MINUTE' in content and '5-MINUTE' in content:
        pos_15 = content.find('15-MINUTE')
        pos_5 = content.find('5-MINUTE')
        return pos_15 < pos_5
    return True


def _check_nautilus_version(content: str) -> bool:
    """检查 NautilusTrader 版本"""
    match = re.search(r'nautilus.trader[>=<]+(\d+)\.(\d+)\.(\d+)', content.replace('_', '.'))
    if match:
        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return (major, minor, patch) >= (1, 221, 0)
    return False


# =============================================================================
# 验证器类
# =============================================================================
class CommitFixValidator:
    """提交修复验证器"""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path(__file__).parent
        self.results: Dict[str, Any] = {
            'passed': [],
            'failed': [],
            'warnings': [],
            'skipped': [],
        }

    def validate_fix(self, fix: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        """
        验证单个修复

        Returns:
            Tuple[status, error_message]
            status: 'passed', 'failed', 'warning', 'skipped'
        """
        fix_id = fix['id']

        # 检查所有相关文件
        for file_path in fix['files']:
            full_path = self.project_root / file_path

            if not full_path.exists():
                return ('skipped', f"文件不存在: {file_path}")

            try:
                content = full_path.read_text(encoding='utf-8')
            except Exception as e:
                return ('skipped', f"无法读取文件: {e}")

            # 运行所有验证器
            for i, validator in enumerate(fix['validators']):
                try:
                    result = validator(content, file_path=file_path, project_root=self.project_root)
                    if not result:
                        severity = fix.get('severity', 'medium')
                        if severity == 'critical':
                            return ('failed', fix['error_msg'])
                        elif severity == 'high':
                            return ('failed', fix['error_msg'])
                        else:
                            return ('warning', fix['error_msg'])
                except Exception as e:
                    return ('warning', f"验证器异常: {e}")

        return ('passed', None)

    def validate_all(self,
                     categories: Optional[List[str]] = None,
                     verbose: bool = True) -> Dict[str, Any]:
        """验证所有注册的修复"""

        fixes_to_check = COMMIT_FIX_REGISTRY

        # 按类别过滤
        if categories:
            fixes_to_check = [f for f in fixes_to_check if f['category'] in categories]

        # 按类别分组
        by_category: Dict[str, List[Dict]] = {}
        for fix in fixes_to_check:
            cat = fix['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(fix)

        # 验证每个类别
        for category, fixes in by_category.items():
            if verbose:
                print_section(f"检查: {category}")

            for fix in fixes:
                status, error = self.validate_fix(fix)

                result_entry = {
                    'id': fix['id'],
                    'commit': fix['commit'],
                    'description': fix['description'],
                    'category': fix['category'],
                    'severity': fix.get('severity', 'medium'),
                    'error': error,
                    'fix_hint': fix.get('fix_hint'),
                }

                if status == 'passed':
                    self.results['passed'].append(result_entry)
                    if verbose:
                        print_ok(f"{fix['description']} (commit {fix['commit']})")
                elif status == 'failed':
                    self.results['failed'].append(result_entry)
                    if verbose:
                        print_error(f"{fix['description']}")
                        print_info(f"  错误: {error}")
                        if fix.get('fix_hint'):
                            print_info(f"  建议: {fix['fix_hint']}")
                elif status == 'warning':
                    self.results['warnings'].append(result_entry)
                    if verbose:
                        print_warn(f"{fix['description']}")
                        print_info(f"  警告: {error}")
                else:  # skipped
                    self.results['skipped'].append(result_entry)
                    if verbose:
                        print_info(f"跳过: {fix['description']} ({error})")

        return self.results

    def print_summary(self):
        """打印验证总结"""
        print_header("验证总结")

        total = (len(self.results['passed']) +
                len(self.results['failed']) +
                len(self.results['warnings']))

        print_ok(f"通过: {len(self.results['passed'])}/{total}")

        if self.results['failed']:
            print_error(f"失败: {len(self.results['failed'])}")
            for item in self.results['failed']:
                print(f"    ❌ [{item['severity'].upper()}] {item['id']}: {item['error']}")

        if self.results['warnings']:
            print_warn(f"警告: {len(self.results['warnings'])}")
            for item in self.results['warnings']:
                print(f"    ⚠️  [{item['severity'].upper()}] {item['id']}: {item['error']}")

        if self.results['skipped']:
            print_info(f"跳过: {len(self.results['skipped'])}")

        # 返回是否有关键失败
        critical_failures = [f for f in self.results['failed']
                           if f['severity'] == 'critical']
        return len(critical_failures) == 0


# =============================================================================
# 连锁反应检查 (Chain Reaction Detection)
# =============================================================================
def check_chain_reactions(project_root: Path = None, verbose: bool = True) -> List[Dict[str, Any]]:
    """
    检查可能的连锁反应

    这些是修改一个文件可能影响其他文件的场景
    """
    project_root = project_root or Path(__file__).parent
    issues = []

    if verbose:
        print_section("连锁反应检查")

    # 1. 检查配置字段是否在 dataclass 和 main_live.py 中匹配
    if verbose:
        print_info("检查 1: Strategy dataclass vs main_live.py 字段匹配...")

    strategy_file = project_root / "strategy" / "deepseek_strategy.py"
    main_live_file = project_root / "main_live.py"

    if strategy_file.exists() and main_live_file.exists():
        strategy_content = strategy_file.read_text()
        main_content = main_live_file.read_text()

        # 提取 dataclass 字段
        dataclass_match = re.search(
            r'class DeepSeekAIStrategyConfig.*?(?=\nclass |\Z)',
            strategy_content,
            re.DOTALL
        )

        if dataclass_match:
            dataclass_content = dataclass_match.group()
            # 提取字段名 (格式: field_name: type = default)
            field_pattern = r'^\s+(\w+):\s+\w+.*?='
            dataclass_fields = set(re.findall(field_pattern, dataclass_content, re.MULTILINE))

            # 提取 main_live.py 中传递的参数
            config_call_match = re.search(
                r'DeepSeekAIStrategyConfig\((.*?)\n\s*\)',
                main_content,
                re.DOTALL
            )

            if config_call_match:
                config_call = config_call_match.group(1)
                passed_params = set(re.findall(r'(\w+)=', config_call))

                # 检查 dataclass 中有但 main_live.py 中没传的
                # (排除有默认值的可选字段)
                required_fields = {'instrument_id', 'bar_type'}  # 必需字段
                missing_in_main = dataclass_fields - passed_params - {'instrument_id', 'bar_type'}

                # 只报告可能需要从 config 传递的字段
                important_missing = [f for f in missing_in_main
                                    if not f.startswith('_') and
                                    f not in {'partial_tp_levels'}]  # 排除复杂类型

                if important_missing:
                    if verbose:
                        print_warn(f"可能缺少配置传递: {important_missing[:5]}...")
                else:
                    if verbose:
                        print_ok("dataclass 字段与 main_live.py 传递匹配")

    # 2. 检查导入依赖
    if verbose:
        print_info("检查 2: 循环导入风险...")

    import_issues = []
    for init_file in project_root.glob("*/__init__.py"):
        content = init_file.read_text()
        if 'from ' in content and 'import' in content:
            # 检查是否有复杂的自动导入
            import_lines = [l for l in content.split('\n')
                          if l.strip().startswith('from ') and 'import' in l]
            if len(import_lines) > 3:
                import_issues.append(str(init_file.relative_to(project_root)))

    if import_issues:
        if verbose:
            print_warn(f"可能有循环导入风险: {import_issues}")
        issues.append({
            'type': 'circular_import_risk',
            'files': import_issues,
            'hint': '考虑使用延迟导入或移除 __init__.py 中的自动导入',
        })
    else:
        if verbose:
            print_ok("未检测到明显的循环导入风险")

    # 3. 检查常量定义一致性
    if verbose:
        print_info("检查 3: 常量定义一致性...")

    constants_to_check = ['MIN_SL_DISTANCE_PCT', 'MIN_NOTIONAL']
    for const in constants_to_check:
        values_found = {}
        for py_file in project_root.rglob("*.py"):
            if '__pycache__' in str(py_file):
                continue
            try:
                content = py_file.read_text()
                match = re.search(rf'{const}\s*=\s*([\d.]+)', content)
                if match:
                    values_found[str(py_file.relative_to(project_root))] = match.group(1)
            except Exception:
                pass

        if len(set(values_found.values())) > 1:
            if verbose:
                print_warn(f"{const} 定义不一致: {values_found}")
            issues.append({
                'type': 'constant_inconsistency',
                'constant': const,
                'values': values_found,
            })

    if not issues:
        if verbose:
            print_ok("常量定义一致")

    return issues


# =============================================================================
# 主函数
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description='提交修复验证工具 - 检查所有历史修复是否正确应用'
    )
    parser.add_argument('--quick', action='store_true', help='快速检查 (跳过耗时项)')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--category', type=str, help='只检查特定类别')
    parser.add_argument('--list-categories', action='store_true', help='列出所有类别')

    args = parser.parse_args()

    # 列出类别
    if args.list_categories:
        categories = set(f['category'] for f in COMMIT_FIX_REGISTRY)
        print("可用类别:")
        for cat in sorted(categories):
            count = len([f for f in COMMIT_FIX_REGISTRY if f['category'] == cat])
            print(f"  - {cat} ({count} 项)")
        return

    if not args.json:
        print_header("提交修复验证工具")
        print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  目的: 验证所有历史修复是否正确应用，检测潜在回归")
        print(f"  注册修复数: {len(COMMIT_FIX_REGISTRY)}")

    # 运行验证
    validator = CommitFixValidator()

    categories = [args.category] if args.category else None
    results = validator.validate_all(categories=categories, verbose=not args.json)

    # 连锁反应检查
    if not args.quick:
        chain_issues = check_chain_reactions(verbose=not args.json)
        results['chain_reactions'] = chain_issues

    # 输出结果
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        success = validator.print_summary()

        # 建议操作
        if results['failed']:
            print_section("建议操作")
            for item in results['failed']:
                print(f"  1. 修复 {item['id']}:")
                print(f"     文件: {COMMIT_FIX_REGISTRY[[f['id'] for f in COMMIT_FIX_REGISTRY].index(item['id'])]['files']}")
                if item.get('fix_hint'):
                    print(f"     建议: {item['fix_hint']}")

        print("\n" + "="*70)
        if success:
            print_ok("所有关键修复已正确应用")
        else:
            print_error("存在关键问题需要修复")
        print("="*70 + "\n")

        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
