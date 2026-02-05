#!/usr/bin/env python3
"""
记忆系统深度诊断脚本 v2.1

深入诊断以下问题：
1. 记忆文件内容分析 (PnL 分布)
2. MultiAgentAnalyzer 初始化检查
3. Coinalyze API key 加载问题
4. Order Book adaptive OBI 历史基线问题
5. 环境变量加载流程追踪

v2.1 更新:
- 更新 PnL=0 警告信息，反映 v3.15/v3.16 修复
- v3.15 修复了变量名问题 (multi_agent_analyzer → multi_agent)
- v3.16 使用官方 realized_return 替代手动计算

使用方法 (在服务器上运行):
    cd /home/linuxuser/nautilus_AItrader
    source venv/bin/activate
    python3 scripts/diagnose_memory_deep.py
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def print_header(title: str):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str):
    print()
    print(f"[{title}]")
    print("-" * 70)


def check_env_variables():
    """检查环境变量和 API keys"""
    print_section("1. 环境变量检查")

    # 检查 .env 文件
    env_file = PROJECT_ROOT / ".env"
    env_aitrader = Path.home() / ".env.aitrader"

    print(f"  📂 .env 文件: {env_file}")
    print(f"     存在: {env_file.exists()}")
    if env_file.is_symlink():
        print(f"     软链接指向: {os.readlink(env_file)}")

    print(f"  📂 ~/.env.aitrader: {env_aitrader}")
    print(f"     存在: {env_aitrader.exists()}")

    # 加载环境变量
    from dotenv import load_dotenv

    # 尝试加载
    loaded = load_dotenv(env_aitrader) or load_dotenv(env_file)
    print(f"  📥 dotenv 加载: {'成功' if loaded else '失败'}")

    # 检查关键 API keys
    print()
    print("  📋 API Keys 检查:")

    keys_to_check = [
        ('DEEPSEEK_API_KEY', '*** (DeepSeek AI - 必须)'),
        ('BINANCE_API_KEY', '*** (Binance - 必须)'),
        ('BINANCE_API_SECRET', '*** (Binance - 必须)'),
        ('TELEGRAM_BOT_TOKEN', '*** (Telegram - 可选)'),
        ('COINALYZE_API_KEY', '*** (Coinalyze - 可选)'),
    ]

    missing_required = []
    for key, desc in keys_to_check:
        value = os.environ.get(key)
        if value:
            # 显示前4位和后4位
            masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "***"
            print(f"     ✅ {key}: {masked}")
        else:
            required = "必须" in desc
            status = "❌" if required else "⚠️"
            print(f"     {status} {key}: 未设置 {desc}")
            if required:
                missing_required.append(key)

    if missing_required:
        print()
        print(f"  ❌ 缺少必须的 API keys: {missing_required}")
        return False
    return True


def check_memory_file():
    """检查记忆文件"""
    print_section("2. 记忆文件检查")

    memory_path = PROJECT_ROOT / "data" / "trading_memory.json"
    print(f"  📂 文件路径: {memory_path}")
    print(f"  📂 存在: {memory_path.exists()}")

    if not memory_path.exists():
        print(f"  ⚠️ 记忆文件不存在 - 这可能是正常的 (首次运行)")

        # 检查 data 目录
        data_dir = PROJECT_ROOT / "data"
        print(f"  📂 data 目录: {data_dir}")
        print(f"     存在: {data_dir.exists()}")
        if data_dir.exists():
            files = list(data_dir.iterdir())
            print(f"     文件数: {len(files)}")
            for f in files[:5]:
                print(f"       - {f.name}")
        return None

    try:
        with open(memory_path, 'r') as f:
            memories = json.load(f)

        print(f"  ✅ 文件读取成功")
        print(f"  📊 记忆条目数: {len(memories)}")

        if memories:
            # 分析 pnl 分布
            pnl_zero = sum(1 for m in memories if m.get('pnl', 0) == 0)
            pnl_positive = sum(1 for m in memories if m.get('pnl', 0) > 0)
            pnl_negative = sum(1 for m in memories if m.get('pnl', 0) < 0)

            print()
            print(f"  📈 PnL 分布:")
            print(f"     零值 (pnl=0): {pnl_zero} 条 ({pnl_zero/len(memories)*100:.1f}%)")
            print(f"     盈利 (pnl>0): {pnl_positive} 条")
            print(f"     亏损 (pnl<0): {pnl_negative} 条")

            if pnl_zero == len(memories):
                print()
                print(f"  ⚠️ 警告: 所有记录的 pnl 都是 0!")
                print(f"     可能原因:")
                print(f"     1. 这些是 v3.16 之前的旧数据 (最可能)")
                print(f"     2. NautilusTrader realized_return 返回 0 (真实盈亏为零)")
                print(f"     📝 v3.15 修复了变量名问题 (multi_agent_analyzer → multi_agent)")
                print(f"     📝 v3.16 使用官方 realized_return 替代手动计算")

            # 显示最近记录的完整结构
            print()
            print(f"  📝 最后一条记录完整结构:")
            last = memories[-1]
            for k, v in last.items():
                if isinstance(v, str) and len(v) > 50:
                    v = v[:50] + "..."
                print(f"     {k}: {v}")

        return memories

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON 解析错误: {e}")
        return None
    except Exception as e:
        print(f"  ❌ 读取失败: {e}")
        return None


def check_multi_agent_initialization():
    """检查 MultiAgentAnalyzer 初始化"""
    print_section("3. MultiAgentAnalyzer 初始化检查")

    # 检查导入
    print("  📦 导入检查:")
    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer
        print(f"     ✅ MultiAgentAnalyzer 导入成功")
    except ImportError as e:
        print(f"     ❌ 导入失败: {e}")
        return False

    # 检查 DeepSeek API key
    api_key = os.environ.get('DEEPSEEK_API_KEY')
    print()
    print("  🔑 DeepSeek API Key:")
    if api_key:
        print(f"     ✅ 已设置: {api_key[:4]}...{api_key[-4:]}")
    else:
        print(f"     ❌ 未设置 - 这是 multi_agent 未初始化的原因!")
        print(f"     📝 解决方案: 在 ~/.env.aitrader 中添加 DEEPSEEK_API_KEY=xxx")
        return False

    # 尝试创建实例
    print()
    print("  🔧 尝试创建 MultiAgentAnalyzer 实例:")
    try:
        analyzer = MultiAgentAnalyzer(
            api_key=api_key,
            model="deepseek-chat",
            temperature=0.3,
        )
        print(f"     ✅ 实例创建成功")
        print(f"     记忆条目数: {len(analyzer.decision_memory)}")
        print(f"     记忆文件: {analyzer.memory_file}")
        return True
    except Exception as e:
        print(f"     ❌ 实例创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_strategy_initialization():
    """检查策略中 multi_agent 的初始化逻辑"""
    print_section("4. 策略初始化逻辑检查")

    strategy_file = PROJECT_ROOT / "strategy" / "deepseek_strategy.py"

    if not strategy_file.exists():
        print(f"  ❌ 策略文件不存在: {strategy_file}")
        return

    with open(strategy_file, 'r') as f:
        content = f.read()

    # 检查 multi_agent 初始化代码
    print("  📋 multi_agent 初始化代码检查:")

    # 查找 self.multi_agent =
    import re

    # 查找初始化模式
    patterns = [
        (r'self\.multi_agent\s*=\s*MultiAgentAnalyzer', 'MultiAgentAnalyzer 直接初始化'),
        (r'self\.multi_agent\s*=\s*None', 'multi_agent 设为 None'),
        (r'if.*api_key.*multi_agent', 'API key 条件检查'),
        (r'DEEPSEEK_API_KEY', 'DEEPSEEK_API_KEY 引用'),
    ]

    for pattern, desc in patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            print(f"     ✅ 找到: {desc} ({len(matches)} 处)")
        else:
            print(f"     ⚠️ 未找到: {desc}")

    # 查找具体初始化代码段
    print()
    print("  📝 查找 multi_agent 初始化代码:")

    # 查找包含 multi_agent 初始化的行
    lines = content.split('\n')
    found_init = False
    for i, line in enumerate(lines):
        if 'self.multi_agent' in line and ('=' in line or 'MultiAgentAnalyzer' in line):
            print(f"     Line {i+1}: {line.strip()[:80]}")
            found_init = True
            # 打印上下文
            for j in range(max(0, i-2), min(len(lines), i+3)):
                if j != i:
                    print(f"       {j+1}: {lines[j].strip()[:70]}")

    if not found_init:
        print(f"     ⚠️ 未找到 multi_agent 初始化代码")


def check_on_position_closed():
    """检查 on_position_closed 中的 record_outcome 调用"""
    print_section("5. on_position_closed 检查")

    strategy_file = PROJECT_ROOT / "strategy" / "deepseek_strategy.py"

    with open(strategy_file, 'r') as f:
        content = f.read()

    # 查找 on_position_closed 方法
    print("  📋 record_outcome 调用检查:")

    # 查找 record_outcome 调用
    if 'record_outcome' in content:
        print(f"     ✅ 找到 record_outcome 调用")

        # 查找条件检查
        if 'if hasattr(self, \'multi_agent\') and self.multi_agent:' in content:
            print(f"     ✅ 有 multi_agent 存在性检查")
            print(f"     ⚠️ 如果 multi_agent 是 None，record_outcome 不会被调用!")
        else:
            print(f"     ⚠️ 未找到标准的 multi_agent 检查")
    else:
        print(f"     ❌ 未找到 record_outcome 调用")


def check_service_logs():
    """检查服务日志中的相关错误"""
    print_section("6. 服务日志检查 (最近 50 行)")

    import subprocess

    try:
        # 检查 systemd 服务日志
        result = subprocess.run(
            ['journalctl', '-u', 'nautilus-trader', '-n', '50', '--no-pager'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            logs = result.stdout

            # 查找关键错误
            error_patterns = [
                ('multi_agent', 'multi_agent 相关'),
                ('DEEPSEEK', 'DeepSeek 相关'),
                ('record_outcome', 'record_outcome 相关'),
                ('memory', '记忆系统相关'),
                ('API key', 'API key 相关'),
                ('Failed to', '失败信息'),
                ('Error', '错误信息'),
            ]

            print("  📋 关键日志搜索:")
            found_any = False
            for pattern, desc in error_patterns:
                matches = [line for line in logs.split('\n') if pattern.lower() in line.lower()]
                if matches:
                    print(f"     🔍 {desc}:")
                    for m in matches[-3:]:  # 只显示最近3条
                        print(f"        {m[-100:]}")  # 截断长行
                    found_any = True

            if not found_any:
                print(f"     ℹ️ 未找到明显的错误日志")
                print(f"     最近几行日志:")
                for line in logs.split('\n')[-5:]:
                    if line.strip():
                        print(f"        {line[-100:]}")
        else:
            print(f"  ⚠️ 无法获取服务日志 (可能需要 sudo)")
            print(f"     stderr: {result.stderr[:200]}")

    except subprocess.TimeoutExpired:
        print(f"  ⚠️ 日志获取超时")
    except FileNotFoundError:
        print(f"  ⚠️ journalctl 不可用 (非 systemd 系统)")
    except Exception as e:
        print(f"  ⚠️ 日志检查失败: {e}")


def check_config_files():
    """检查配置文件中的 AI 相关配置"""
    print_section("7. 配置文件检查")

    config_files = [
        PROJECT_ROOT / "configs" / "base.yaml",
        PROJECT_ROOT / "configs" / "production.yaml",
    ]

    for config_file in config_files:
        print(f"  📂 {config_file.name}:")
        if not config_file.exists():
            print(f"     ⚠️ 不存在")
            continue

        try:
            import yaml
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            # 检查 AI 相关配置
            ai_config = config.get('ai', {})
            deepseek = ai_config.get('deepseek', {})

            if deepseek:
                print(f"     ✅ ai.deepseek 配置:")
                print(f"        model: {deepseek.get('model', 'N/A')}")
                print(f"        temperature: {deepseek.get('temperature', 'N/A')}")
            else:
                print(f"     ⚠️ 未找到 ai.deepseek 配置")

            # 检查 multi_agent 配置
            ma_config = config.get('multi_agent', {})
            if ma_config:
                print(f"     ✅ multi_agent 配置:")
                print(f"        enabled: {ma_config.get('enabled', 'N/A')}")

        except Exception as e:
            print(f"     ❌ 解析失败: {e}")


def check_coinalyze_api():
    """检查 Coinalyze API key 加载问题"""
    print_section("8. Coinalyze API 深度检查")

    # 1. 检查环境变量
    coinalyze_key = os.environ.get('COINALYZE_API_KEY')
    print(f"  📋 环境变量检查:")
    print(f"     os.environ.get('COINALYZE_API_KEY'): {'✅ 已设置' if coinalyze_key else '❌ 未设置'}")
    if coinalyze_key:
        print(f"     值: {coinalyze_key[:4]}...{coinalyze_key[-4:]}")

    # 2. 检查配置文件中的配置
    print()
    print(f"  📋 配置文件检查:")
    try:
        import yaml
        config_file = PROJECT_ROOT / "configs" / "base.yaml"
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        coinalyze_config = config.get('coinalyze', {})
        print(f"     coinalyze.enabled: {coinalyze_config.get('enabled', 'N/A')}")
        print(f"     coinalyze.api_key 配置: {coinalyze_config.get('api_key', 'N/A')}")
        print(f"     coinalyze.fallback_enabled: {coinalyze_config.get('fallback_enabled', 'N/A')}")
    except Exception as e:
        print(f"     ❌ 配置读取失败: {e}")

    # 3. 检查诊断脚本中如何检测 Coinalyze
    print()
    print(f"  📋 诊断逻辑检查:")
    diag_files = list((PROJECT_ROOT / "scripts" / "diagnostics").glob("*.py"))
    for f in diag_files:
        try:
            content = f.read_text()
            if 'coinalyze' in content.lower() or 'COINALYZE' in content:
                # 查找相关代码
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'coinalyze' in line.lower() and ('key' in line.lower() or 'api' in line.lower()):
                        print(f"     {f.name}:{i+1}: {line.strip()[:60]}")
        except:
            pass

    # 4. 尝试实际调用 CoinalyzeClient
    print()
    print(f"  📋 CoinalyzeClient 实例化测试:")
    try:
        from utils.coinalyze_client import CoinalyzeClient

        # 测试不同方式获取 API key
        test_sources = [
            ('os.environ', os.environ.get('COINALYZE_API_KEY')),
        ]

        # 尝试从 ConfigManager 获取
        try:
            from utils.config_manager import ConfigManager
            cm = ConfigManager(env='production')
            cm.load()
            cm_key = cm.get('coinalyze', 'api_key', default=None)
            if not cm_key:
                # 尝试从环境变量获取
                cm_key = os.environ.get('COINALYZE_API_KEY')
            test_sources.append(('ConfigManager', cm_key))
        except Exception as e:
            print(f"     ConfigManager 加载失败: {e}")

        for source, key in test_sources:
            if key:
                print(f"     {source}: ✅ {key[:4]}...{key[-4:]}")
            else:
                print(f"     {source}: ❌ None")

    except ImportError as e:
        print(f"     ❌ CoinalyzeClient 导入失败: {e}")
    except Exception as e:
        print(f"     ❌ 测试失败: {e}")

    return coinalyze_key is not None


def check_order_book_obi():
    """检查 Order Book OBI 历史基线问题"""
    print_section("9. Order Book OBI 历史基线检查")

    # 1. 检查配置
    print(f"  📋 Order Book 配置:")
    try:
        import yaml
        config_file = PROJECT_ROOT / "configs" / "base.yaml"
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)

        ob_config = config.get('order_book', {})
        print(f"     order_book.enabled: {ob_config.get('enabled', 'N/A')}")

        processing = ob_config.get('processing', {})
        history = processing.get('history', {})
        print(f"     history.size: {history.get('size', 'N/A')}")

        weighted_obi = processing.get('weighted_obi', {})
        print(f"     weighted_obi.adaptive: {weighted_obi.get('adaptive', 'N/A')}")
        print(f"     weighted_obi.base_decay: {weighted_obi.get('base_decay', 'N/A')}")
    except Exception as e:
        print(f"     ❌ 配置读取失败: {e}")

    # 2. 检查 OrderBookProcessor 代码
    print()
    print(f"  📋 OrderBookProcessor 历史基线逻辑:")
    try:
        ob_file = PROJECT_ROOT / "utils" / "orderbook_processor.py"
        if ob_file.exists():
            content = ob_file.read_text()

            # 查找历史相关代码
            patterns = [
                ('history', '历史数据存储'),
                ('baseline', '基线计算'),
                ('NO_DATA', 'NO_DATA 状态'),
                ('adaptive', '自适应 OBI'),
            ]

            for pattern, desc in patterns:
                if pattern in content:
                    # 找到相关行
                    lines = content.split('\n')
                    found_lines = [(i+1, line.strip()[:60]) for i, line in enumerate(lines)
                                   if pattern in line and not line.strip().startswith('#')]
                    if found_lines:
                        print(f"     ✅ {desc}:")
                        for ln, text in found_lines[:2]:
                            print(f"        Line {ln}: {text}")
                else:
                    print(f"     ⚠️ 未找到: {desc}")
        else:
            print(f"     ❌ 文件不存在: {ob_file}")
    except Exception as e:
        print(f"     ❌ 检查失败: {e}")

    # 3. 检查诊断脚本中的 OBI 检测逻辑
    print()
    print(f"  📋 诊断脚本 OBI 检测逻辑:")
    try:
        ai_decision_file = PROJECT_ROOT / "scripts" / "diagnostics" / "ai_decision.py"
        if ai_decision_file.exists():
            content = ai_decision_file.read_text()

            # 查找 adaptive OBI 相关代码
            if 'adaptive' in content.lower() and 'obi' in content.lower():
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'adaptive' in line.lower() and ('obi' in line.lower() or 'baseline' in line.lower() or 'history' in line.lower()):
                        print(f"     ai_decision.py:{i+1}: {line.strip()[:70]}")

            # 查找警告消息
            if '无历史基线' in content or 'no baseline' in content.lower():
                print(f"     ✅ 找到 '无历史基线' 警告消息")
    except Exception as e:
        print(f"     ❌ 检查失败: {e}")

    # 4. 尝试实例化 OrderBookProcessor 检查历史
    print()
    print(f"  📋 OrderBookProcessor 实例化测试:")
    try:
        from utils.orderbook_processor import OrderBookProcessor

        # 创建测试实例
        processor = OrderBookProcessor(
            weighted_obi_config={
                'base_decay': 0.8,
                'adaptive': True,
                'volatility_factor': 0.1,
                'min_decay': 0.5,
                'max_decay': 0.95,
            },
            history_size=10
        )

        print(f"     ✅ 实例创建成功")

        # 检查历史属性
        if hasattr(processor, 'history'):
            print(f"     history 属性存在: {type(processor.history)}")
            if hasattr(processor.history, '__len__'):
                print(f"     history 长度: {len(processor.history)}")
        else:
            print(f"     ⚠️ 没有 history 属性")

        if hasattr(processor, 'obi_history'):
            print(f"     obi_history 属性存在: {type(processor.obi_history)}")

    except ImportError as e:
        print(f"     ❌ 导入失败: {e}")
    except Exception as e:
        print(f"     ❌ 实例化失败: {e}")
        import traceback
        traceback.print_exc()


def check_diagnose_realtime_logic():
    """检查 diagnose_realtime.py 中的检测逻辑"""
    print_section("10. 诊断脚本检测逻辑检查")

    # 检查 position_check.py 中的 MemorySystemChecker
    print(f"  📋 MemorySystemChecker 逻辑:")
    try:
        pos_check_file = PROJECT_ROOT / "scripts" / "diagnostics" / "position_check.py"
        if pos_check_file.exists():
            content = pos_check_file.read_text()

            # 查找 multi_agent 检测逻辑
            if 'multi_agent' in content:
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'multi_agent' in line and ('未初始化' in line or 'None' in line or 'not' in line.lower()):
                        print(f"     position_check.py:{i+1}: {line.strip()[:70]}")

            # 查找 Coinalyze 检测逻辑
            if 'coinalyze' in content.lower():
                lines = content.split('\n')
                for i, line in enumerate(lines):
                    if 'coinalyze' in line.lower():
                        print(f"     position_check.py:{i+1}: {line.strip()[:70]}")
    except Exception as e:
        print(f"     ❌ 检查失败: {e}")

    # 检查 ai_decision.py 中的检测逻辑
    print()
    print(f"  📋 ai_decision.py Coinalyze/OBI 检测逻辑:")
    try:
        ai_file = PROJECT_ROOT / "scripts" / "diagnostics" / "ai_decision.py"
        if ai_file.exists():
            content = ai_file.read_text()

            # 查找 Coinalyze API key 检测
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if ('coinalyze' in line.lower() and 'key' in line.lower()) or \
                   ('未配置' in line and 'key' in line.lower()):
                    print(f"     ai_decision.py:{i+1}: {line.strip()[:70]}")
    except Exception as e:
        print(f"     ❌ 检查失败: {e}")


def main():
    print_header("记忆系统深度诊断 v2.0")
    print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  项目: {PROJECT_ROOT}")

    results = {}

    # 1. 检查环境变量
    results['env'] = check_env_variables()

    # 2. 检查记忆文件
    results['memory_file'] = check_memory_file()

    # 3. 检查 MultiAgentAnalyzer 初始化
    results['multi_agent_init'] = check_multi_agent_initialization()

    # 4. 检查策略初始化逻辑
    check_strategy_initialization()

    # 5. 检查 on_position_closed
    check_on_position_closed()

    # 6. 检查服务日志
    check_service_logs()

    # 7. 检查配置文件
    check_config_files()

    # 8. 检查 Coinalyze API (新增)
    results['coinalyze'] = check_coinalyze_api()

    # 9. 检查 Order Book OBI (新增)
    check_order_book_obi()

    # 10. 检查诊断脚本逻辑 (新增)
    check_diagnose_realtime_logic()

    # 汇总
    print_header("诊断结果汇总")

    print("  🔍 问题分析:")
    print()

    if not results.get('env'):
        print("  ❌ 问题 1: 缺少必须的环境变量 (DEEPSEEK_API_KEY)")
        print("     → 这是 multi_agent 未初始化的根本原因")
        print("     → 解决: 确保 ~/.env.aitrader 包含 DEEPSEEK_API_KEY=xxx")
        print()

    if not results.get('multi_agent_init'):
        print("  ❌ 问题 2: MultiAgentAnalyzer 无法初始化")
        print("     → 这导致 record_outcome 不会被调用")
        print("     → 所有交易的 PnL 都会是 0%")
        print()

    if results.get('memory_file') is not None:
        memories = results['memory_file']
        if memories and all(m.get('pnl', 0) == 0 for m in memories):
            print("  ⚠️ 问题 3: 所有记忆记录的 PnL 都是 0%")
            print("     → 这是上述问题的直接结果")
            print()

    if not results.get('coinalyze'):
        print("  ⚠️ 问题 4: Coinalyze API key 在环境变量中未找到")
        print("     → 可能是诊断脚本检测逻辑有问题")
        print("     → 或者环境变量未正确加载")
        print()

    print("  📋 Order Book OBI 历史基线问题:")
    print("     → 如果系统运行很久仍显示 '无历史基线'")
    print("     → 可能是 OrderBookProcessor 每次诊断都重新创建")
    print("     → 历史数据没有持久化，每次都是空的")
    print()

    print("  📝 建议操作:")
    print("     1. 检查 ~/.env.aitrader 是否包含所有 API keys")
    print("     2. 检查 .env 软链接是否正确指向 ~/.env.aitrader")
    print("     3. 检查诊断脚本是否正确读取环境变量")
    print("     4. 重启服务: sudo systemctl restart nautilus-trader")
    print("     5. 查看启动日志: sudo journalctl -u nautilus-trader -f")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
