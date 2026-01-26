#!/usr/bin/env python3
"""
配置管理方案实施全面诊断 (CONFIG_MANAGEMENT_PROPOSAL.md v3.1.0)

完整验证 Phase 0-6 的所有实施内容，确保配置管理方案正确实施。
v3.0.0: 添加 MTF (多时间框架) 三层架构验证。
v3.1.0: 添加 MTF 详细配置验证、初始化配置、Order Flow 配置检查。

Usage:
    python3 scripts/comprehensive_diagnosis.py
    python3 scripts/comprehensive_diagnosis.py --quick          # 跳过性能测试
    python3 scripts/comprehensive_diagnosis.py --json result.json  # 导出 JSON 结果
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class DiagnosticResult:
    """诊断结果"""
    def __init__(self, phase: str, name: str, passed: bool, message: str = "", details: str = ""):
        self.phase = phase
        self.name = name
        self.passed = passed
        self.message = message
        self.details = details

    def to_dict(self):
        return {
            'phase': self.phase,
            'name': self.name,
            'passed': self.passed,
            'message': self.message,
            'details': self.details
        }


class ConfigManagementDiagnostic:
    """配置管理方案诊断"""

    def __init__(self, quick_mode: bool = False):
        self.quick_mode = quick_mode
        self.results: List[DiagnosticResult] = []
        self.start_time = time.time()

    def add_result(self, phase: str, name: str, passed: bool, message: str = "", details: str = ""):
        """添加诊断结果"""
        result = DiagnosticResult(phase, name, passed, message, details)
        self.results.append(result)
        return result

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 70)
        print("  配置管理方案实施全面诊断 (CONFIG_MANAGEMENT_PROPOSAL.md v3.1.0)")
        print("  v3.1.0: MTF 详细配置 + 初始化配置 + Order Flow 检查")
        print("=" * 70)
        print()

        # Phase 0: 配置冲突修复
        print("Phase 0: 配置冲突修复")
        print("-" * 70)
        self.test_phase0_rsi_threshold()
        self.test_phase0_main_live_config_loading()
        print()

        # Phase 1: ConfigManager 基础设施
        print("Phase 1: ConfigManager 基础设施")
        print("-" * 70)
        self.test_phase1_config_files_exist()
        self.test_phase1_configmanager_loading()
        self.test_phase1_path_aliases()
        print()

        # Phase 2: main_live.py ConfigManager 集成
        print("Phase 2: main_live.py ConfigManager 集成")
        print("-" * 70)
        self.test_phase2_main_live_integration()
        print()

        # Phase 3: trading_logic.py 常量迁移
        print("Phase 3: trading_logic.py 常量迁移")
        print("-" * 70)
        self.test_phase3_trading_logic_migration()
        self.test_phase3_multi_agent_imports()
        print()

        # Phase 4: utils/*.py 网络参数迁移
        print("Phase 4: utils/*.py 网络参数迁移")
        print("-" * 70)
        self.test_phase4_utils_parameterization()
        self.test_phase4_strategy_dataclass_fields()
        print()

        # Phase 5: CLI 环境切换
        print("Phase 5: CLI 环境切换")
        print("-" * 70)
        self.test_phase5_cli_args()
        print()

        # Phase 6: 文档同步
        print("Phase 6: 文档同步")
        print("-" * 70)
        self.test_phase6_documentation_sync()
        print()

        # Phase 7: MTF 多时间框架 (v3.0.0 新增)
        print("Phase 7: MTF 多时间框架 (v3.1.0)")
        print("-" * 70)
        self.test_phase7_mtf_config()
        self.test_phase7_mtf_manager()
        self.test_phase7_mtf_dataclass_fields()
        self.test_phase7_mtf_layer_details()  # v3.1.0 新增
        self.test_phase7_mtf_initialization()  # v3.1.0 新增
        print()

        # Phase 8: Order Flow 配置 (v3.1.0 新增)
        print("Phase 8: Order Flow 配置 (v3.1.0)")
        print("-" * 70)
        self.test_phase8_order_flow_config()
        print()

        # 综合验证
        print("综合验证")
        print("-" * 70)
        self.test_comprehensive_circular_imports()
        self.test_comprehensive_config_coverage()
        if not self.quick_mode:
            self.test_comprehensive_performance()
        print()

        # 总结
        self.print_summary()

    # ==================== Phase 0 测试 ====================

    def test_phase0_rsi_threshold(self):
        """测试 Phase 0: RSI 阈值修复"""
        try:
            # 检查 strategy/deepseek_strategy.py 的默认值
            strategy_file = project_root / 'strategy' / 'deepseek_strategy.py'
            content = strategy_file.read_text()

            # 查找 rsi_extreme_threshold_upper 和 rsi_extreme_threshold_lower
            if 'rsi_extreme_threshold_upper: float = 70.0' in content and \
               'rsi_extreme_threshold_lower: float = 30.0' in content:
                self.add_result(
                    'Phase 0', 'RSI 阈值修复',
                    True,
                    'RSI 默认值已修复为 70.0/30.0'
                )
                print("✅ [Phase 0] RSI 阈值修复")
                print("   RSI 默认值已修复为 70.0/30.0")
            else:
                self.add_result(
                    'Phase 0', 'RSI 阈值修复',
                    False,
                    'RSI 默认值未修复或值不正确',
                    f'Expected: 70.0/30.0'
                )
                print("❌ [Phase 0] RSI 阈值修复")
                print("   RSI 默认值未修复或值不正确")
        except Exception as e:
            self.add_result('Phase 0', 'RSI 阈值修复', False, str(e))
            print(f"❌ [Phase 0] RSI 阈值修复: {e}")

    def test_phase0_main_live_config_loading(self):
        """测试 Phase 0: main_live.py 配置加载"""
        try:
            main_live = project_root / 'main_live.py'
            content = main_live.read_text()

            # 检查是否使用 config_manager.get() 而非硬编码
            if 'config_manager.get(' in content and \
               "from utils.config_manager import ConfigManager" in content:
                self.add_result(
                    'Phase 0', 'main_live.py 配置加载',
                    True,
                    'main_live.py 已使用 ConfigManager'
                )
                print("✅ [Phase 0] main_live.py 配置加载")
                print("   main_live.py 已使用 ConfigManager")
            else:
                self.add_result(
                    'Phase 0', 'main_live.py 配置加载',
                    False,
                    'main_live.py 未使用 ConfigManager'
                )
                print("❌ [Phase 0] main_live.py 配置加载")
                print("   main_live.py 未使用 ConfigManager")
        except Exception as e:
            self.add_result('Phase 0', 'main_live.py 配置加载', False, str(e))
            print(f"❌ [Phase 0] main_live.py 配置加载: {e}")

    # ==================== Phase 1 测试 ====================

    def test_phase1_config_files_exist(self):
        """测试 Phase 1: 配置文件存在性"""
        try:
            required_files = [
                'configs/base.yaml',
                'configs/production.yaml',
                'configs/development.yaml',
                'configs/backtest.yaml',
                'utils/config_manager.py',
                'scripts/validate_path_aliases.py',
                'scripts/check_circular_imports.sh',
                'scripts/benchmark_config.py'
            ]

            missing = []
            for file_path in required_files:
                if not (project_root / file_path).exists():
                    missing.append(file_path)

            if not missing:
                self.add_result(
                    'Phase 1', '配置文件存在性',
                    True,
                    '所有配置文件已创建'
                )
                print("✅ [Phase 1] 配置文件存在性")
                print("   所有配置文件已创建")
            else:
                self.add_result(
                    'Phase 1', '配置文件存在性',
                    False,
                    f'缺失文件: {", ".join(missing)}'
                )
                print("❌ [Phase 1] 配置文件存在性")
                print(f"   缺失文件: {', '.join(missing)}")
        except Exception as e:
            self.add_result('Phase 1', '配置文件存在性', False, str(e))
            print(f"❌ [Phase 1] 配置文件存在性: {e}")

    def test_phase1_configmanager_loading(self):
        """测试 Phase 1: ConfigManager 加载"""
        try:
            from utils.config_manager import ConfigManager

            config = ConfigManager(env='production')
            config_dict = config.load()

            # 检查顶级键
            required_keys = [
                'trading', 'trading_logic', 'capital', 'position',
                'indicators', 'ai', 'sentiment', 'risk', 'network',
                'telegram', 'execution', 'timing', 'logging',
                'diagnostics', 'runtime', 'binance'
            ]

            missing_keys = [key for key in required_keys if key not in config_dict]

            if not missing_keys:
                self.add_result(
                    'Phase 1', 'ConfigManager 加载',
                    True,
                    f'配置加载成功 ({len(config_dict)} 个顶级键)'
                )
                print("✅ [Phase 1] ConfigManager 加载")
                print(f"   配置加载成功 ({len(config_dict)} 个顶级键)")
            else:
                self.add_result(
                    'Phase 1', 'ConfigManager 加载',
                    False,
                    f'缺失顶级键: {", ".join(missing_keys)}'
                )
                print("❌ [Phase 1] ConfigManager 加载")
                print(f"   缺失顶级键: {', '.join(missing_keys)}")
        except Exception as e:
            self.add_result('Phase 1', 'ConfigManager 加载', False, str(e))
            print(f"❌ [Phase 1] ConfigManager 加载: {e}")

    def test_phase1_path_aliases(self):
        """测试 Phase 1: PATH_ALIASES 兼容"""
        try:
            from utils.config_manager import ConfigManager

            config = ConfigManager(env='production')
            config.load()

            # 测试关键路径别名
            test_cases = [
                (('strategy', 'deepseek', 'temperature'), ('ai', 'deepseek', 'temperature')),
                (('strategy', 'equity'), ('capital', 'equity')),
                (('strategy', 'leverage'), ('capital', 'leverage')),
            ]

            all_passed = True
            for old_path, new_path in test_cases:
                old_value = config.get(*old_path)
                new_value = config.get(*new_path)
                if old_value != new_value:
                    all_passed = False
                    break

            if all_passed:
                self.add_result(
                    'Phase 1', 'PATH_ALIASES 兼容',
                    True,
                    '所有路径别名验证通过'
                )
                print("✅ [Phase 1] PATH_ALIASES 兼容")
                print("   所有路径别名验证通过")
            else:
                self.add_result(
                    'Phase 1', 'PATH_ALIASES 兼容',
                    False,
                    '部分路径别名失败'
                )
                print("❌ [Phase 1] PATH_ALIASES 兼容")
                print("   部分路径别名失败")
        except Exception as e:
            self.add_result('Phase 1', 'PATH_ALIASES 兼容', False, str(e))
            print(f"❌ [Phase 1] PATH_ALIASES 兼容: {e}")

    # ==================== Phase 2 测试 ====================

    def test_phase2_main_live_integration(self):
        """测试 Phase 2: main_live.py ConfigManager 集成"""
        try:
            main_live = project_root / 'main_live.py'
            content = main_live.read_text()

            # 检查关键集成点
            checks = [
                ('from utils.config_manager import ConfigManager', 'ConfigManager 导入'),
                ('config_manager = ConfigManager(env=args.env)', 'ConfigManager 初始化'),
                ('config_dict = config_manager.load()', '配置加载'),
                ('config_manager.validate()', '配置验证'),
            ]

            all_passed = True
            missing = []
            for check_str, description in checks:
                if check_str not in content:
                    all_passed = False
                    missing.append(description)

            if all_passed:
                self.add_result(
                    'Phase 2', 'main_live.py 集成',
                    True,
                    'main_live.py 已完全集成 ConfigManager'
                )
                print("✅ [Phase 2] main_live.py 集成")
                print("   main_live.py 已完全集成 ConfigManager")
            else:
                self.add_result(
                    'Phase 2', 'main_live.py 集成',
                    False,
                    f'缺失集成点: {", ".join(missing)}'
                )
                print("❌ [Phase 2] main_live.py 集成")
                print(f"   缺失集成点: {', '.join(missing)}")
        except Exception as e:
            self.add_result('Phase 2', 'main_live.py 集成', False, str(e))
            print(f"❌ [Phase 2] main_live.py 集成: {e}")

    # ==================== Phase 3 测试 ====================

    def test_phase3_trading_logic_migration(self):
        """测试 Phase 3: trading_logic.py 迁移"""
        try:
            trading_logic = project_root / 'strategy' / 'trading_logic.py'
            content = trading_logic.read_text()

            # 检查关键迁移点
            checks = [
                ('def _get_trading_logic_config()', '配置加载函数'),
                ('def get_min_sl_distance_pct()', '公共访问函数'),
                ('from utils.config_manager import get_config', '延迟导入'),
            ]

            all_passed = True
            missing = []
            for check_str, description in checks:
                if check_str not in content:
                    all_passed = False
                    missing.append(description)

            if all_passed:
                self.add_result(
                    'Phase 3', 'trading_logic.py 迁移',
                    True,
                    'trading_logic.py 已迁移到配置化'
                )
                print("✅ [Phase 3] trading_logic.py 迁移")
                print("   trading_logic.py 已迁移到配置化")
            else:
                self.add_result(
                    'Phase 3', 'trading_logic.py 迁移',
                    False,
                    f'缺失迁移点: {", ".join(missing)}'
                )
                print("❌ [Phase 3] trading_logic.py 迁移")
                print(f"   缺失迁移点: {', '.join(missing)}")
        except Exception as e:
            self.add_result('Phase 3', 'trading_logic.py 迁移', False, str(e))
            print(f"❌ [Phase 3] trading_logic.py 迁移: {e}")

    def test_phase3_multi_agent_imports(self):
        """测试 Phase 3: multi_agent_analyzer.py 导入"""
        try:
            multi_agent = project_root / 'agents' / 'multi_agent_analyzer.py'
            content = multi_agent.read_text()

            # 检查是否使用函数而非常量
            if 'get_min_sl_distance_pct' in content and \
               'get_default_sl_pct' in content:
                self.add_result(
                    'Phase 3', 'multi_agent_analyzer.py 导入',
                    True,
                    'multi_agent_analyzer.py 导入已更新'
                )
                print("✅ [Phase 3] multi_agent_analyzer.py 导入")
                print("   multi_agent_analyzer.py 导入已更新")
            else:
                self.add_result(
                    'Phase 3', 'multi_agent_analyzer.py 导入',
                    False,
                    'multi_agent_analyzer.py 导入未更新'
                )
                print("❌ [Phase 3] multi_agent_analyzer.py 导入")
                print("   multi_agent_analyzer.py 导入未更新")
        except Exception as e:
            self.add_result('Phase 3', 'multi_agent_analyzer.py 导入', False, str(e))
            print(f"❌ [Phase 3] multi_agent_analyzer.py 导入: {e}")

    # ==================== Phase 4 测试 ====================

    def test_phase4_utils_parameterization(self):
        """测试 Phase 4: utils 文件参数化"""
        try:
            # 检查关键 utils 文件的参数化
            files_to_check = [
                ('utils/deepseek_client.py', ['signal_history_count', 'retry_delay']),
                ('agents/multi_agent_analyzer.py', ['retry_delay', 'json_parse_max_retries']),
                ('utils/telegram_command_handler.py', ['startup_delay', 'polling_max_retries']),
                ('utils/binance_account.py', ['cache_ttl', 'recv_window']),
                ('utils/sentiment_client.py', ['timeout']),
            ]

            all_passed = True
            missing_params = []

            for file_path, params in files_to_check:
                full_path = project_root / file_path
                if full_path.exists():
                    content = full_path.read_text()
                    for param in params:
                        if param not in content:
                            all_passed = False
                            missing_params.append(f"{file_path}:{param}")

            if all_passed:
                self.add_result(
                    'Phase 4', 'utils 文件参数化',
                    True,
                    '所有 utils 文件已参数化'
                )
                print("✅ [Phase 4] utils 文件参数化")
                print("   所有 utils 文件已参数化")
            else:
                self.add_result(
                    'Phase 4', 'utils 文件参数化',
                    False,
                    f'缺失参数: {", ".join(missing_params)}'
                )
                print("❌ [Phase 4] utils 文件参数化")
                print(f"   缺失参数: {', '.join(missing_params)}")
        except Exception as e:
            self.add_result('Phase 4', 'utils 文件参数化', False, str(e))
            print(f"❌ [Phase 4] utils 文件参数化: {e}")

    def test_phase4_strategy_dataclass_fields(self):
        """测试 Phase 4: strategy dataclass 字段"""
        try:
            strategy_file = project_root / 'strategy' / 'deepseek_strategy.py'
            content = strategy_file.read_text()

            # 检查新增的 dataclass 字段
            required_fields = [
                'deepseek_retry_delay',
                'deepseek_signal_history_count',
                'multi_agent_retry_delay',
                'multi_agent_json_parse_max_retries',
                'network_telegram_startup_delay',
                'network_binance_recv_window',
                'sentiment_timeout',
                'volume_ma_period',
                'support_resistance_lookback',
            ]

            missing_fields = []
            for field in required_fields:
                if f'{field}:' not in content:
                    missing_fields.append(field)

            if not missing_fields:
                self.add_result(
                    'Phase 4', 'strategy dataclass 字段',
                    True,
                    f'所有 {len(required_fields)} 个新字段已添加'
                )
                print("✅ [Phase 4] strategy dataclass 字段")
                print(f"   所有 {len(required_fields)} 个新字段已添加")
            else:
                self.add_result(
                    'Phase 4', 'strategy dataclass 字段',
                    False,
                    f'缺失字段: {", ".join(missing_fields)}'
                )
                print("❌ [Phase 4] strategy dataclass 字段")
                print(f"   缺失字段: {', '.join(missing_fields)}")
        except Exception as e:
            self.add_result('Phase 4', 'strategy dataclass 字段', False, str(e))
            print(f"❌ [Phase 4] strategy dataclass 字段: {e}")

    # ==================== Phase 5 测试 ====================

    def test_phase5_cli_args(self):
        """测试 Phase 5: CLI 参数"""
        try:
            main_live = project_root / 'main_live.py'
            content = main_live.read_text()

            # 检查 argparse 实现
            checks = [
                ('def parse_args():', 'argparse 函数'),
                ("'--env'", '--env 参数'),
                ("'--dry-run'", '--dry-run 参数'),
                ("choices=['production', 'development', 'backtest']", '环境选项'),
            ]

            all_passed = True
            missing = []
            for check_str, description in checks:
                if check_str not in content:
                    all_passed = False
                    missing.append(description)

            if all_passed:
                self.add_result(
                    'Phase 5', 'CLI 参数',
                    True,
                    'CLI 环境切换已实现'
                )
                print("✅ [Phase 5] CLI 参数")
                print("   CLI 环境切换已实现")
            else:
                self.add_result(
                    'Phase 5', 'CLI 参数',
                    False,
                    f'缺失 CLI 特性: {", ".join(missing)}'
                )
                print("❌ [Phase 5] CLI 参数")
                print(f"   缺失 CLI 特性: {', '.join(missing)}")
        except Exception as e:
            self.add_result('Phase 5', 'CLI 参数', False, str(e))
            print(f"❌ [Phase 5] CLI 参数: {e}")

    # ==================== Phase 6 测试 ====================

    def test_phase6_documentation_sync(self):
        """测试 Phase 6: 文档同步"""
        try:
            # 检查关键文档文件
            docs_to_check = [
                ('CLAUDE.md', ['配置管理', 'ConfigManager']),
                ('README.md', ['Configuration Management', 'environment']),
                ('docs/CONFIG_MANAGEMENT_PROPOSAL.md', ['Phase 0-6 已完成', 'v2.9.1']),
            ]

            all_passed = True
            missing = []

            for doc_path, keywords in docs_to_check:
                full_path = project_root / doc_path
                if full_path.exists():
                    content = full_path.read_text()
                    for keyword in keywords:
                        if keyword not in content:
                            all_passed = False
                            missing.append(f"{doc_path}:{keyword}")
                else:
                    all_passed = False
                    missing.append(f"{doc_path} (文件不存在)")

            if all_passed:
                self.add_result(
                    'Phase 6', '文档同步',
                    True,
                    '所有文档已同步'
                )
                print("✅ [Phase 6] 文档同步")
                print("   所有文档已同步")
            else:
                self.add_result(
                    'Phase 6', '文档同步',
                    False,
                    f'缺失文档内容: {", ".join(missing)}'
                )
                print("❌ [Phase 6] 文档同步")
                print(f"   缺失文档内容: {', '.join(missing)}")
        except Exception as e:
            self.add_result('Phase 6', '文档同步', False, str(e))
            print(f"❌ [Phase 6] 文档同步: {e}")

    # ==================== Phase 7 测试 (MTF) ====================

    def test_phase7_mtf_config(self):
        """测试 Phase 7: MTF 配置"""
        try:
            import yaml
            base_config = project_root / 'configs' / 'base.yaml'

            if not base_config.exists():
                self.add_result('Phase 7', 'MTF 配置', False, 'base.yaml 不存在')
                print("❌ [Phase 7] MTF 配置")
                print("   base.yaml 不存在")
                return

            with open(base_config, 'r') as f:
                config = yaml.safe_load(f)

            mtf = config.get('multi_timeframe', {})

            # 检查 MTF 配置结构
            required_keys = ['enabled', 'trend_layer', 'decision_layer', 'execution_layer']
            missing = [k for k in required_keys if k not in mtf]

            if missing:
                self.add_result('Phase 7', 'MTF 配置', False, f'缺失配置: {", ".join(missing)}')
                print("❌ [Phase 7] MTF 配置")
                print(f"   缺失配置: {', '.join(missing)}")
                return

            # 检查各层配置
            trend = mtf.get('trend_layer', {})
            decision = mtf.get('decision_layer', {})
            execution = mtf.get('execution_layer', {})

            details = []
            details.append(f"enabled={mtf.get('enabled')}")
            details.append(f"trend={trend.get('timeframe', 'N/A')}")
            details.append(f"decision={decision.get('timeframe', 'N/A')}")
            details.append(f"execution={execution.get('default_timeframe', 'N/A')}")

            self.add_result(
                'Phase 7', 'MTF 配置',
                True,
                f'MTF 配置完整: {", ".join(details)}'
            )
            print("✅ [Phase 7] MTF 配置")
            print(f"   {', '.join(details)}")

        except Exception as e:
            self.add_result('Phase 7', 'MTF 配置', False, str(e))
            print(f"❌ [Phase 7] MTF 配置: {e}")

    def test_phase7_mtf_manager(self):
        """测试 Phase 7: MultiTimeframeManager 模块"""
        try:
            mtf_file = project_root / 'indicators' / 'multi_timeframe_manager.py'

            if not mtf_file.exists():
                self.add_result('Phase 7', 'MTF Manager', False, 'multi_timeframe_manager.py 不存在')
                print("❌ [Phase 7] MTF Manager")
                print("   multi_timeframe_manager.py 不存在")
                return

            content = mtf_file.read_text()

            # 检查关键类和枚举
            checks = [
                ('class MultiTimeframeManager', 'MultiTimeframeManager 类'),
                ('class RiskState', 'RiskState 枚举'),
                ('class DecisionState', 'DecisionState 枚举'),
                ('def route_bar', 'route_bar 方法'),
                ('def evaluate_risk_state', 'evaluate_risk_state 方法'),
                ('def check_execution_confirmation', 'check_execution_confirmation 方法'),
            ]

            missing = []
            for check_str, description in checks:
                if check_str not in content:
                    missing.append(description)

            if missing:
                self.add_result('Phase 7', 'MTF Manager', False, f'缺失: {", ".join(missing)}')
                print("❌ [Phase 7] MTF Manager")
                print(f"   缺失: {', '.join(missing)}")
            else:
                # 尝试导入验证
                try:
                    from indicators.multi_timeframe_manager import (
                        MultiTimeframeManager,
                        RiskState,
                        DecisionState
                    )
                    self.add_result('Phase 7', 'MTF Manager', True, '模块导入成功')
                    print("✅ [Phase 7] MTF Manager")
                    print("   模块导入成功")
                except ImportError as e:
                    self.add_result('Phase 7', 'MTF Manager', False, f'导入失败: {e}')
                    print(f"❌ [Phase 7] MTF Manager: 导入失败 {e}")

        except Exception as e:
            self.add_result('Phase 7', 'MTF Manager', False, str(e))
            print(f"❌ [Phase 7] MTF Manager: {e}")

    def test_phase7_mtf_dataclass_fields(self):
        """测试 Phase 7: strategy dataclass MTF 字段"""
        try:
            strategy_file = project_root / 'strategy' / 'deepseek_strategy.py'
            content = strategy_file.read_text()

            # 检查 MTF 相关字段
            mtf_fields = [
                'mtf_enabled',
            ]

            missing = []
            for field in mtf_fields:
                if f'{field}:' not in content and f'{field} =' not in content:
                    missing.append(field)

            # 检查 MTF 初始化逻辑
            mtf_init_checks = [
                ('MultiTimeframeManager', 'MTF Manager 导入'),
                ('_prefetch_multi_timeframe_bars', 'MTF 预取方法'),
            ]

            for check_str, description in mtf_init_checks:
                if check_str not in content:
                    missing.append(description)

            if not missing:
                self.add_result(
                    'Phase 7', 'MTF dataclass 字段',
                    True,
                    'MTF 字段和方法已集成到 strategy'
                )
                print("✅ [Phase 7] MTF dataclass 字段")
                print("   MTF 字段和方法已集成到 strategy")
            else:
                self.add_result(
                    'Phase 7', 'MTF dataclass 字段',
                    False,
                    f'缺失: {", ".join(missing)}'
                )
                print("❌ [Phase 7] MTF dataclass 字段")
                print(f"   缺失: {', '.join(missing)}")

        except Exception as e:
            self.add_result('Phase 7', 'MTF dataclass 字段', False, str(e))
            print(f"❌ [Phase 7] MTF dataclass 字段: {e}")

    def test_phase7_mtf_layer_details(self):
        """测试 Phase 7.1: MTF 层详细配置 (v3.1.0)"""
        try:
            import yaml
            base_config = project_root / 'configs' / 'base.yaml'

            if not base_config.exists():
                self.add_result('Phase 7', 'MTF 层详细配置', False, 'base.yaml 不存在')
                print("❌ [Phase 7] MTF 层详细配置")
                return

            with open(base_config, 'r') as f:
                config = yaml.safe_load(f)

            mtf = config.get('multi_timeframe', {})
            if not mtf.get('enabled', False):
                self.add_result('Phase 7', 'MTF 层详细配置', True, 'MTF 未启用，跳过')
                print("⏭️ [Phase 7] MTF 层详细配置: MTF 未启用，跳过")
                return

            missing = []

            # 趋势层详细字段
            trend = mtf.get('trend_layer', {})
            trend_required = ['timeframe', 'sma_period']
            for field in trend_required:
                if field not in trend:
                    missing.append(f'trend_layer.{field}')

            # 决策层详细字段
            decision = mtf.get('decision_layer', {})
            decision_required = ['timeframe']
            for field in decision_required:
                if field not in decision:
                    missing.append(f'decision_layer.{field}')

            # 执行层详细字段
            execution = mtf.get('execution_layer', {})
            execution_required = ['default_timeframe']
            for field in execution_required:
                if field not in execution:
                    missing.append(f'execution_layer.{field}')

            if not missing:
                self.add_result('Phase 7', 'MTF 层详细配置', True, '所有必需字段存在')
                print("✅ [Phase 7] MTF 层详细配置")
                print("   所有必需字段存在")
                # 显示可选字段状态
                optional_found = []
                if 'require_above_sma' in trend:
                    optional_found.append('trend.require_above_sma')
                if 'require_macd_positive' in trend:
                    optional_found.append('trend.require_macd_positive')
                if 'debate_rounds' in decision:
                    optional_found.append('decision.debate_rounds')
                if 'rsi_entry_min' in execution:
                    optional_found.append('execution.rsi_entry_min/max')
                if optional_found:
                    print(f"   可选字段: {', '.join(optional_found)}")
            else:
                self.add_result('Phase 7', 'MTF 层详细配置', False, f'缺失: {", ".join(missing)}')
                print("❌ [Phase 7] MTF 层详细配置")
                print(f"   缺失: {', '.join(missing)}")

        except Exception as e:
            self.add_result('Phase 7', 'MTF 层详细配置', False, str(e))
            print(f"❌ [Phase 7] MTF 层详细配置: {e}")

    def test_phase7_mtf_initialization(self):
        """测试 Phase 7.2: MTF 初始化配置 (v3.1.0)"""
        try:
            import yaml
            base_config = project_root / 'configs' / 'base.yaml'

            if not base_config.exists():
                self.add_result('Phase 7', 'MTF 初始化配置', False, 'base.yaml 不存在')
                print("❌ [Phase 7] MTF 初始化配置")
                return

            with open(base_config, 'r') as f:
                config = yaml.safe_load(f)

            mtf = config.get('multi_timeframe', {})
            if not mtf.get('enabled', False):
                self.add_result('Phase 7', 'MTF 初始化配置', True, 'MTF 未启用，跳过')
                print("⏭️ [Phase 7] MTF 初始化配置: MTF 未启用，跳过")
                return

            init_config = mtf.get('initialization', {})
            if not init_config:
                self.add_result('Phase 7', 'MTF 初始化配置', False, 'initialization 段不存在')
                print("❌ [Phase 7] MTF 初始化配置")
                print("   initialization 段不存在")
                return

            # 检查必需字段
            required_fields = ['trend_min_bars', 'decision_min_bars', 'execution_min_bars']
            missing = [f for f in required_fields if f not in init_config]

            if not missing:
                details = []
                details.append(f"trend={init_config.get('trend_min_bars')}")
                details.append(f"decision={init_config.get('decision_min_bars')}")
                details.append(f"execution={init_config.get('execution_min_bars')}")
                self.add_result('Phase 7', 'MTF 初始化配置', True, f'配置完整: {", ".join(details)}')
                print("✅ [Phase 7] MTF 初始化配置")
                print(f"   {', '.join(details)}")
                if 'request_timeout_sec' in init_config:
                    print(f"   timeout={init_config['request_timeout_sec']}s, retries={init_config.get('max_retry_attempts', 'N/A')}")
            else:
                self.add_result('Phase 7', 'MTF 初始化配置', False, f'缺失: {", ".join(missing)}')
                print("❌ [Phase 7] MTF 初始化配置")
                print(f"   缺失: {', '.join(missing)}")

        except Exception as e:
            self.add_result('Phase 7', 'MTF 初始化配置', False, str(e))
            print(f"❌ [Phase 7] MTF 初始化配置: {e}")

    # ==================== Phase 8 测试 (Order Flow) ====================

    def test_phase8_order_flow_config(self):
        """测试 Phase 8: Order Flow 配置 (v3.1.0)"""
        try:
            import yaml
            base_config = project_root / 'configs' / 'base.yaml'

            if not base_config.exists():
                self.add_result('Phase 8', 'Order Flow 配置', False, 'base.yaml 不存在')
                print("❌ [Phase 8] Order Flow 配置")
                return

            with open(base_config, 'r') as f:
                config = yaml.safe_load(f)

            order_flow = config.get('order_flow', {})

            if not order_flow:
                self.add_result('Phase 8', 'Order Flow 配置', True, 'order_flow 段不存在 (可选功能)')
                print("⏭️ [Phase 8] Order Flow 配置: 段不存在 (可选功能)")
                return

            enabled = order_flow.get('enabled', False)

            if not enabled:
                self.add_result('Phase 8', 'Order Flow 配置', True, 'Order Flow 未启用')
                print("⏭️ [Phase 8] Order Flow 配置: 未启用")
                return

            # 检查子配置
            issues = []
            binance = order_flow.get('binance', {})
            coinalyze = order_flow.get('coinalyze', {})

            if binance.get('enabled'):
                if not binance.get('symbol'):
                    issues.append('binance.symbol 未配置')

            if coinalyze.get('enabled'):
                if not coinalyze.get('api_key'):
                    issues.append('coinalyze.api_key 未配置')

            if not issues:
                details = []
                details.append(f"enabled={enabled}")
                details.append(f"binance={binance.get('enabled', False)}")
                details.append(f"coinalyze={coinalyze.get('enabled', False)}")
                self.add_result('Phase 8', 'Order Flow 配置', True, f'{", ".join(details)}')
                print("✅ [Phase 8] Order Flow 配置")
                print(f"   {', '.join(details)}")
            else:
                self.add_result('Phase 8', 'Order Flow 配置', False, f'问题: {", ".join(issues)}')
                print("⚠️  [Phase 8] Order Flow 配置")
                print(f"   问题: {', '.join(issues)}")

        except Exception as e:
            self.add_result('Phase 8', 'Order Flow 配置', False, str(e))
            print(f"❌ [Phase 8] Order Flow 配置: {e}")

    # ==================== 综合验证 ====================

    def test_comprehensive_circular_imports(self):
        """测试综合: 循环导入风险"""
        try:
            # 尝试按依赖顺序导入所有模块
            from utils.config_manager import ConfigManager
            from utils.deepseek_client import DeepSeekAnalyzer
            from agents.multi_agent_analyzer import MultiAgentAnalyzer
            from strategy.trading_logic import (
                get_min_sl_distance_pct,
                get_default_sl_pct,
            )
            from strategy.deepseek_strategy import DeepSeekAIStrategy

            self.add_result(
                '综合', '循环导入风险',
                True,
                '无循环导入问题'
            )
            print("✅ [综合] 循环导入风险")
            print("   无循环导入问题")
        except ImportError as e:
            self.add_result('综合', '循环导入风险', False, str(e))
            print(f"❌ [综合] 循环导入风险: {e}")
        except Exception as e:
            self.add_result('综合', '循环导入风险', False, str(e))
            print(f"❌ [综合] 循环导入风险: {e}")

    def test_comprehensive_config_coverage(self):
        """测试综合: 配置参数覆盖率"""
        try:
            from utils.config_manager import ConfigManager

            config = ConfigManager(env='production')
            config.load()

            # 检查关键配置参数是否存在
            critical_params = [
                ('ai', 'deepseek', 'temperature'),
                ('capital', 'equity'),
                ('capital', 'leverage'),
                ('trading', 'instrument_id'),
                ('risk', 'rsi_extreme_threshold_upper'),
                ('network', 'telegram', 'startup_delay'),
                ('network', 'binance', 'recv_window'),
                ('sentiment', 'timeout'),
                ('trading_logic', 'min_sl_distance_pct'),
                ('indicators', 'rsi_period'),
            ]

            missing = []
            for path in critical_params:
                value = config.get(*path)
                if value is None:
                    missing.append('.'.join(path))

            if not missing:
                self.add_result(
                    '综合', '配置参数覆盖率',
                    True,
                    f'{len(critical_params)}/{len(critical_params)} 关键配置参数存在'
                )
                print("✅ [综合] 配置参数覆盖率")
                print(f"   {len(critical_params)}/{len(critical_params)} 关键配置参数存在")
            else:
                self.add_result(
                    '综合', '配置参数覆盖率',
                    False,
                    f'缺失参数: {", ".join(missing)}'
                )
                print("❌ [综合] 配置参数覆盖率")
                print(f"   缺失参数: {', '.join(missing)}")
        except Exception as e:
            self.add_result('综合', '配置参数覆盖率', False, str(e))
            print(f"❌ [综合] 配置参数覆盖率: {e}")

    def test_comprehensive_performance(self):
        """测试综合: 性能基线"""
        try:
            from utils.config_manager import ConfigManager
            import time

            iterations = 10
            times = []

            for _ in range(iterations):
                # 创建新实例测试加载时间
                start = time.time()
                config = ConfigManager(env='production')
                config.load()
                elapsed = (time.time() - start) * 1000  # ms
                times.append(elapsed)

            avg_time = sum(times) / len(times)

            # 目标: < 200ms
            if avg_time < 200:
                self.add_result(
                    '综合', '性能基线',
                    True,
                    f'平均加载时间: {avg_time:.2f}ms (目标: < 200ms)'
                )
                print("✅ [综合] 性能基线")
                print(f"   平均加载时间: {avg_time:.2f}ms (目标: < 200ms)")
            else:
                self.add_result(
                    '综合', '性能基线',
                    False,
                    f'平均加载时间: {avg_time:.2f}ms 超过目标 200ms',
                    f'最小: {min(times):.2f}ms, 最大: {max(times):.2f}ms'
                )
                print("⚠️  [综合] 性能基线")
                print(f"   平均加载时间: {avg_time:.2f}ms 超过目标 200ms")
        except Exception as e:
            self.add_result('综合', '性能基线', False, str(e))
            print(f"❌ [综合] 性能基线: {e}")

    # ==================== 总结 ====================

    def print_summary(self):
        """打印诊断总结"""
        print("=" * 70)
        print("  诊断摘要")
        print("=" * 70)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print(f"  总计测试: {total}")
        print(f"  ✅ 通过: {passed}")
        print(f"  ❌ 失败: {failed}")

        if failed > 0:
            print(f"  ⚠️  警告: {failed}")

        print("=" * 70)
        print()

        elapsed = time.time() - self.start_time
        print(f"总耗时: {elapsed:.2f}s")
        print()

        return failed == 0

    def export_json(self, output_file: str):
        """导出 JSON 结果"""
        result_data = {
            'timestamp': time.time(),
            'total': len(self.results),
            'passed': sum(1 for r in self.results if r.passed),
            'failed': sum(1 for r in self.results if not r.passed),
            'results': [r.to_dict() for r in self.results]
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, indent=2, ensure_ascii=False)

        print(f"✅ 结果已导出到: {output_file}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description='配置管理方案实施全面诊断 (CONFIG_MANAGEMENT_PROPOSAL.md v3.1.0 + MTF + Order Flow)'
    )
    parser.add_argument(
        '--quick',
        action='store_true',
        help='快速模式（跳过性能测试）'
    )
    parser.add_argument(
        '--json',
        type=str,
        metavar='FILE',
        help='导出 JSON 结果到指定文件'
    )

    args = parser.parse_args()

    # 运行诊断
    diagnostic = ConfigManagementDiagnostic(quick_mode=args.quick)
    diagnostic.run_all_tests()

    # 导出 JSON（如果指定）
    if args.json:
        diagnostic.export_json(args.json)

    # 返回状态码
    all_passed = diagnostic.print_summary()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
