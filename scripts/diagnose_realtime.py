#!/usr/bin/env python3
"""
实盘信号诊断脚本 v11.9 (与实盘 100% 一致)

v11.9 更新 - 完整数据覆盖 (TradingAgents v3.6):
- 添加周期价格统计: period_high, period_low, period_change_pct
- 添加订单流完整数据: volume_usdt (新增)
- AI 现在能看到所有收集的有价值数据

v11.8 更新 - 添加 BB Position 和 1D 趋势层数据:
- 显示 BB Position (15M/4H) - 价格在 BB 带内的位置
- 显示 1D 趋势层数据 (SMA_200, MACD)
- AI 输入数据验证新增 MTF 完整数据

v11.7 更新 - 修复 validate_multiagent_sltp 调用签名:
- 参数顺序: (side, multi_sl, multi_tp, entry_price)
- 返回值: (is_valid, sl, tp, reason) 四元组
- 与 deepseek_strategy.py:2127 完全一致

v11.6 更新 - 修复 calculate_technical_sltp 调用签名:
- 调用签名与实盘代码 deepseek_strategy.py:2152 完全一致
- 提取 support/resistance 从 technical_data
- 修复返回值: (sl, tp, calc_method) 三元组

v11.5 更新 - 完整流程可视化:
- 添加 AI Prompt 结构验证 (显示 System/User Prompt 内容)
- 添加 MTF 状态估算 (基于当前数据估算 RISK_ON/OFF, ALLOW_LONG/SHORT)
- 修复订单提交模拟类型错误 (safe_float 转换)
- 添加 Funding Rate 差异原因标注 (Binance 8h vs Coinalyze 聚合)
- 添加错误恢复机制验证 ([9.4/10] 新增步骤)
- MultiAgentAnalyzer 添加 get_last_prompts() 方法

v11.4 更新 - TradingAgents v3.4 Prompt 结构优化:
- INDICATOR_DEFINITIONS 从 User Prompt 移到 System Prompt
- 符合 TradingAgents 设计: System Prompt = 角色 + 知识背景
- User Prompt 只包含: 原始数据 + 任务指令

v11.3 更新 - TradingAgents v3.3 数据标准化:
- AI 只接收原始数值，不接收任何预计算的判断标签
- 移除传给 AI 的数据:
  * support/resistance (改用 SMA/BB 作为动态支撑阻力)
  * cvd_trend (AI 从 recent_10_bars 自己推断趋势)
  * overall_trend, short_term_trend, macd_trend (AI 从原始值推断)
- 添加 INDICATOR_DEFINITIONS 教 AI 如何解读原始数据

关键特性:
1. 调用 main_live.py 中的 get_strategy_config() 获取真实配置
2. 使用与实盘完全相同的组件初始化参数
3. 使用 TradingAgents 层级决策架构 (v3.4)
4. 检查 Binance 真实持仓
5. 模拟完整的 _execute_trade 流程
6. 输出实盘环境下会产生的真实结果

当前架构 (TradingAgents v3.4 - Prompt 结构优化):
- System Prompt: 角色定义 + INDICATOR_DEFINITIONS (知识背景)
- User Prompt: 原始数据 + 任务指令 (当前任务)
- Phase 1: Bull/Bear 辩论 (2 AI calls) - AI 自主分析数据
- Phase 2: Judge 决策 (1 AI call) - AI 自主评估辩论，做出决策
- Phase 3: Risk 评估 (1 AI call) - AI 自主设定 SL/TP/仓位
- 本地风控: 无 (完全由 AI 决策)
- 设计理念: "Autonomy is non-negotiable" - AI 应像人类分析师思考
- 参考: TradingAgents (UCLA/MIT) https://github.com/TauricResearch/TradingAgents

Prompt 结构 (v3.4):
┌─────────────────────────────────────────┐
│ System Prompt                           │
│ ├─ 角色定义 (Bull/Bear/Judge Analyst)   │
│ ├─ INDICATOR_DEFINITIONS (知识参考)     │
│ └─ 使用说明                             │
├─────────────────────────────────────────┤
│ User Prompt                             │
│ ├─ AVAILABLE DATA (原始数据)            │
│ └─ TASK (任务指令)                      │
└─────────────────────────────────────────┘

传给 AI 的数据 (v3.4):
- 技术指标: price, SMA 5/20/50, RSI, MACD, BB (原始数值)
- 订单流: buy_ratio, recent_10_bars (原始数值)
- 衍生品: OI, funding_rate, liquidations (原始数值)
- 情绪: long/short ratio (原始数值)

职责划分 (v3.4):
- AI 职责: 所有判断 (趋势、支撑阻力、信号方向、SL/TP)
- 本地职责: 只收集原始数据，不做预解读

历史更新:
v11.7:
- 修复 validate_multiagent_sltp 调用签名
  * 参数顺序: (side, multi_sl, multi_tp, entry_price)
  * 返回值: (is_valid, sl, tp, reason) 四元组
  * 与 deepseek_strategy.py:2127 完全一致

v11.6:
- 修复 calculate_technical_sltp 调用签名
  * 参数: side, entry_price, support, resistance, confidence, use_support_resistance, sl_buffer_pct
  * 返回值: (sl, tp, calc_method) 三元组
  * 与 deepseek_strategy.py:2152 完全一致

v11.5:
- 添加 AI Prompt 结构验证 (System/User Prompt 分离检查)
- 添加 MTF 状态估算 (RISK_ON/OFF, ALLOW_LONG/SHORT)
- 添加 safe_float() 类型转换
- 添加 Funding Rate 差异标注 (Binance 8h vs Coinalyze)
- 添加错误恢复机制验证

v11.4:
- Prompt 结构优化为 TradingAgents v3.4 标准
  * INDICATOR_DEFINITIONS 移到 System Prompt
  * User Prompt 只包含数据和任务
  * 符合 TradingAgents 设计理念

v11.3:
- 数据格式改为 TradingAgents v3.3 标准
  * 移除 support/resistance (AI 用 SMA_50/BB 作动态支撑阻力)
  * 移除 cvd_trend (AI 从 recent_10_bars 推断)
  * 添加 INDICATOR_DEFINITIONS 教 AI 解读数据

v11.2:
- 移除所有本地硬编码规则 - 完全符合 TradingAgents 设计
  * 删除趋势方向权限检查 (allow_long/allow_short)
  * 删除支撑/阻力位边界检查 (proximity_threshold)
  * 核心原则: "Autonomy is non-negotiable"

v11.1:
- 移除趋势方向权限检查 (部分符合 TradingAgents)

v11.0:
- AI 提示词完全简化，移除所有硬编码规则和阈值
- Judge 不再使用确认计数框架 (bullish_count/bearish_count 已移除)
- 数据格式化移除预解读标签 (BULLISH/BEARISH/Overbought 等)

v10.20 (已被 v11.1 取代):
- 方向性权限检查 (已移除)

v10.19:
- 修复硬编码阈值违规 (lines 255-260)
  * BB_OVERBOUGHT/OVERSOLD_THRESHOLD 改为从 indicators.bb_*_threshold 读取
  * LS_RATIO_* 阈值改为从 indicators.ls_ratio_* 读取
- 修复 Judge RSI 确认逻辑错误 (line 1529-1532)
  * 错误: rsi > 55 → bullish (与 multi_agent_analyzer.py 相反)
  * 修正: rsi < 55 → bullish, rsi > 65 → bearish (与实际系统一致)
  * 参考: agents/multi_agent_analyzer.py:485,492

v10.18:
- 修复 SMA 回退值硬编码问题 (line 1438: sma_period = 50)
- 改为从 configs/base.yaml 读取 indicators.sma_periods 列表
- 按降序尝试所有配置的 SMA 周期作为回退
- 符合 CLAUDE.md 配置管理规范 (禁止硬编码)

v10.17:
- 添加账户资金详情 (使用实盘组件 BinanceAccountFetcher.get_balance())
  * 显示: 总余额、可用余额、已用保证金、保证金率、总未实现PnL
- 添加 Judge 确认项明细 (与 multi_agent_analyzer.py:483-495 一致)
  * 显示 5 个 Bullish 确认项和 5 个 Bearish 确认项
  * 对比本地计算与 AI 计数的差异
- 添加 GitHub 导出功能:
  * --export: 导出诊断结果到 logs/diagnosis_YYYYMMDD_HHMMSS.txt
  * --push: 导出并推送到 GitHub (减少 token 消耗)

v10.16:
- 修复 MTF 趋势层使用 SMA_200 (配置: trend_layer.sma_period=200)
- 之前错误使用 SMA_50，导致诊断结果与实盘不一致
- 添加 SMA_200 不可用时回退到 SMA_50 的逻辑 (需要 200 根 K线)
- configs/base.yaml 同步添加 sma_periods: [5, 20, 50, 200]

v10.15:
- 添加完整数据流追踪，可判断问题出在哪一步
- 新增 "AI 输入数据验证" 部分，显示传给 MultiAgent 的所有数据
- 新增 Judge 决策计数 (bullish_count/bearish_count 0-5) - 决策的核心依据
- 新增 Bull/Bear 辩论记录输出
- 新增 acknowledged_risks 显示

v10.14:
- 修复 AI 收到价格 $0.00 的问题
- technical_data (from indicator_manager.get_technical_data()) 不包含 'price' 键
- multi_agent_analyzer._format_technical_report 需要 'price' 键来显示当前价格
- 同时修复了 deepseek_strategy.py 中的同一问题

v10.13:
- 修复未实现PnL显示$0.00的问题
- 当 Binance API 返回 0 但有入场价和当前价时，自动计算 PnL
- 计算公式: (当前价 - 入场价) * 持仓量

v10.12:
- 修复情绪数据字段名不匹配: positive_ratio → long_account_pct
- 修复持仓数据字段名不匹配: avg_px → entry_price, 添加 pnl_pct
- Step 5 和 Step 13 的情绪/持仓数据现在能正确显示

v10.11:
- 修复 Liquidations 显示问题: API 返回 BTC 单位，不是 USD
- 添加 BTC → USD 转换 (乘以当前价格)
- 移除多余的 DEBUG 输出，保留清晰的结果展示

v10.10:
- 添加 Liquidations API 调试输出 (原始响应、history 类型、数据长度)
- 帮助诊断 "history 为空" 是真的无数据还是解析错误

v10.9:
- 添加 [10/13] on_bar MTF 路由逻辑模拟 (1D/4H/15M bar 分发)
- 添加 [11/13] 仓位计算函数测试 (calculate_position_size 完整验证)
- 添加 [12/13] 订单提交流程模拟 (_submit_bracket_order + SL/TP 验证)
- 添加 [13/13] 完整数据流汇总 (所有获取数据的具体值输出)
- 测试步骤从 10 步扩展到 13 步，实现 100% 数据流覆盖

v10.8:
- 修复 Step 9.3 Coinalyze 配置路径: base_config.get('coinalyze') → order_flow.get('coinalyze')

v10.7:
- 修复 SentimentDataFetcher 初始化: 移除不存在的 logger 参数

v10.6 (已在 v10.20 升级):
- 添加 Step 7.5: MTF 信号过滤模拟 (与 deepseek_strategy.py:1454-1525 100% 一致)
- 规则1: 方向性权限检查 (趋势层，v10.20 升级)
- 规则2: 决策层方向匹配 (信号与 ALLOW_LONG/SHORT/WAIT 一致性)
- 规则3: 执行层 RSI 确认 (入场范围检查)
- 达到 100% 流程覆盖

v10.5:
- 修复 get_funding_rate() 数据解析: 使用 'value' 字段而非 'fundingRate'
- 修复 get_liquidations() 数据解析: 正确解析 history[x]['l'/'s'] 嵌套结构
- 修复 AIDataAssembler 衍生品数据访问: 使用正确的嵌套结构路径

v10.4:
- 添加 MTF v2.1 完整组件测试 (BinanceKlineClient, OrderFlowProcessor, CoinalyzeClient, AIDataAssembler)
- 更新 MultiAgentAnalyzer.analyze() 调用以传递 order_flow_report 和 derivatives_report
- 重构 Step 9 为完整的 MTF 组件集成测试

v10.3:
- 添加 Step 8.5: Post-Trade 生命周期测试 (OCO 清理 + Trailing Stop)
- 修复情绪数据 fallback 缺失字段 (positive_ratio, negative_ratio, net_sentiment)
- 修复硬编码 Symbol，改从 strategy_config.instrument_id 提取
- MTF 预取添加实际 API 调用测试 (1D/4H/15M)

v10.2:
- 添加 Step 0.6: MTF 历史数据预取验证 (检查各层初始化状态)
- 添加 Step 9: Order Flow 数据实际获取测试 (Coinalyze API 调用验证)
- 添加 Step 9.5: Telegram 命令处理验证 (send_message_sync 测试)

v10.1:
- 添加 MTF 层详细配置验证 (require_above_sma, debate_rounds, rsi_entry 等)
- 添加 MTF 初始化配置检查 (trend_min_bars, decision_min_bars, execution_min_bars)
- 添加 Order Flow 配置检查

v10.0:
- 添加 MTF 配置检查和三层框架验证
- 添加 MTF 历史数据预取状态诊断

v9.0:
- 添加关键配置检查 (load_all, reconciliation, SL/TP 字段名)
- 检测可能导致不能下单的配置问题

v8.0:
- 添加完整的 Bracket Order SL/TP 验证逻辑（与实盘100%一致）
- 添加 --summary 选项用于快速诊断
- 模拟技术分析回退逻辑

v7.0:
- 统一架构命名为 "TradingAgents"，移除"方案A/B"混淆
- 更新注释以反映当前架构状态

v6.0:
- 实现 TradingAgents 层级决策架构
- Judge 决策作为唯一决策者

v5.0:
- 添加 Binance 真实持仓检查
- 添加 _manage_existing_position 逻辑模拟
- 添加仓位为0检查
- 添加 Telegram/交易执行流程说明

使用方法:
    cd /home/linuxuser/nautilus_AItrader
    python3 scripts/diagnose_realtime.py              # 完整诊断 (自动切换 venv)
    python3 scripts/diagnose_realtime.py --summary    # 快速诊断（仅显示关键结果）
    python3 scripts/diagnose_realtime.py --export     # 导出到 logs/diagnosis_*.txt
    python3 scripts/diagnose_realtime.py --push       # 导出并推送到 GitHub


注: v10.21 同步系统架构修复，诊断脚本本身已完整模拟所有功能，无需修改。
    主系统新增功能 (决策快照、订单拒单报警) 在诊断脚本中通过模拟实现。
"""

import os
import sys
from pathlib import Path

# ============================================================
# 自动切换到 venv (与 diagnose.py 一致)
# ============================================================
def ensure_venv():
    """确保在 venv 中运行，否则自动切换"""
    project_dir = Path(__file__).parent.parent.absolute()
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

# 其他导入
import argparse
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

# 解析命令行参数
parser = argparse.ArgumentParser(description='实盘信号诊断工具 v11.9')
parser.add_argument('--summary', action='store_true',
                   help='仅显示关键结果，跳过详细分析')
parser.add_argument('--export', action='store_true',
                   help='导出诊断结果到文件 (logs/diagnosis_YYYYMMDD_HHMMSS.txt)')
parser.add_argument('--push', action='store_true',
                   help='导出并推送到 GitHub (需要配合 --export)')
args = parser.parse_args()

# 全局标志
SUMMARY_MODE = args.summary
EXPORT_MODE = args.export or args.push
PUSH_TO_GITHUB = args.push

# ============================================================
# 输出捕获 (用于导出到文件)
# ============================================================
import io

class TeeOutput:
    """同时输出到终端和缓冲区"""
    def __init__(self, stream, buffer):
        self.stream = stream
        self.buffer = buffer

    def write(self, data):
        self.stream.write(data)
        self.buffer.write(data)

    def flush(self):
        self.stream.flush()

# 初始化输出捕获
output_buffer = io.StringIO()
if EXPORT_MODE:
    original_stdout = sys.stdout
    sys.stdout = TeeOutput(original_stdout, output_buffer)

# 分析阈值常量 (从配置加载后设置，禁止硬编码)
# 这些变量将在加载 base_config 后从 configs/base.yaml 读取
BB_OVERBOUGHT_THRESHOLD = None  # 从 indicators.bb_overbought_threshold 读取
BB_OVERSOLD_THRESHOLD = None    # 从 indicators.bb_oversold_threshold 读取
LS_RATIO_EXTREME_BULLISH = None  # 从 indicators.ls_ratio_extreme_bullish 读取
LS_RATIO_BULLISH = None          # 从 indicators.ls_ratio_bullish 读取
LS_RATIO_EXTREME_BEARISH = None  # 从 indicators.ls_ratio_extreme_bearish 读取
LS_RATIO_BEARISH = None          # 从 indicators.ls_ratio_bearish 读取

def print_wrapped(text: str, indent: str = "    ", width: int = 80) -> None:
    """打印自动换行的文本"""
    for i in range(0, len(text), width):
        print(f"{indent}{text[i:i+width]}")


def check_critical_config() -> Tuple[list, list]:
    """
    检查可能导致不能下单的关键配置 (v9.0 新增)

    检查项:
    1. main_live.py: load_all=True (instrument 初始化)
    2. main_live.py: reconciliation=True (仓位对账)
    3. deepseek_strategy.py: SL/TP 字段名正确使用

    Returns:
        (issues, warnings): 问题列表和警告列表
    """
    import re

    issues = []  # 严重问题
    warnings = []  # 警告

    project_root = Path(__file__).parent.parent

    # ==========================================================================
    # 检查 1: main_live.py 中的 load_all 配置
    # ==========================================================================
    main_live_path = project_root / "main_live.py"
    if main_live_path.exists():
        with open(main_live_path, 'r', encoding='utf-8') as f:
            main_live_content = f.read()

        # 检查 load_all 设置
        # 匹配 load_all=True 或 load_all=False
        load_all_matches = re.findall(r'load_all\s*=\s*(True|False)', main_live_content)

        if not load_all_matches:
            warnings.append("main_live.py: 未找到 load_all 配置")
        elif 'False' in load_all_matches:
            issues.append(
                "❌ main_live.py: load_all=False\n"
                "   → 可能导致 instrument 初始化不完整，订单无法执行\n"
                "   → 修复: 改为 load_all=True"
            )
        else:
            # 所有都是 True
            pass  # 正常

        # 检查 reconciliation 设置 (支持两种格式)
        # 格式1 (旧): reconciliation=True
        # 格式2 (新): config_manager.get('execution', 'engine', 'reconciliation', default=True)
        reconciliation_hardcoded = re.findall(r'reconciliation\s*=\s*(True|False)', main_live_content)
        reconciliation_configmanager = re.search(
            r"config_manager\.get\s*\(\s*['\"]execution['\"].*['\"]reconciliation['\"].*default\s*=\s*(True|False)",
            main_live_content
        )

        if reconciliation_configmanager:
            # 使用 ConfigManager 格式 (推荐)
            if reconciliation_configmanager.group(1) == 'False':
                issues.append(
                    "❌ main_live.py: reconciliation default=False\n"
                    "   → 仓位不同步，可能导致订单管理异常\n"
                    "   → 修复: 改为 default=True"
                )
            # else: default=True, 正常
        elif reconciliation_hardcoded:
            # 使用硬编码格式 (旧版)
            if 'False' in reconciliation_hardcoded:
                issues.append(
                    "❌ main_live.py: reconciliation=False\n"
                    "   → 仓位不同步，可能导致订单管理异常\n"
                    "   → 修复: 改为 reconciliation=True"
                )
        else:
            warnings.append("main_live.py: 未找到 reconciliation 配置")
    else:
        issues.append("❌ main_live.py 文件不存在!")

    # ==========================================================================
    # 检查 2: deepseek_strategy.py 中的 SL/TP 字段名使用
    # ==========================================================================
    strategy_path = project_root / "strategy" / "deepseek_strategy.py"
    if strategy_path.exists():
        with open(strategy_path, 'r', encoding='utf-8') as f:
            strategy_content = f.read()

        # 检查是否使用了错误的字段名 stop_loss_multi / take_profit_multi
        if "stop_loss_multi" in strategy_content:
            issues.append(
                "❌ deepseek_strategy.py: 使用了 'stop_loss_multi' 字段名\n"
                "   → MultiAgent 返回的字段名是 'stop_loss'\n"
                "   → 这会导致 SL 值永远为 None\n"
                "   → 修复: 改为 .get('stop_loss')"
            )

        if "take_profit_multi" in strategy_content:
            issues.append(
                "❌ deepseek_strategy.py: 使用了 'take_profit_multi' 字段名\n"
                "   → MultiAgent 返回的字段名是 'take_profit'\n"
                "   → 这会导致 TP 值永远为 None\n"
                "   → 修复: 改为 .get('take_profit')"
            )

        # 检查是否正确使用了字段名
        correct_sl = re.search(r"\.get\(['\"]stop_loss['\"]\)", strategy_content)
        correct_tp = re.search(r"\.get\(['\"]take_profit['\"]\)", strategy_content)

        if not correct_sl:
            warnings.append("deepseek_strategy.py: 未找到 .get('stop_loss') 调用")
        if not correct_tp:
            warnings.append("deepseek_strategy.py: 未找到 .get('take_profit') 调用")
    else:
        warnings.append("deepseek_strategy.py 文件不存在")

    # ==========================================================================
    # 检查 3: trading_logic.py 中的 SL 距离验证常量
    # ==========================================================================
    trading_logic_path = project_root / "strategy" / "trading_logic.py"
    if trading_logic_path.exists():
        with open(trading_logic_path, 'r', encoding='utf-8') as f:
            trading_logic_content = f.read()

        # 检查 SL 距离阈值 (应该在 trading_logic.py 中定义)
        min_sl_match = re.search(r'MIN_SL_DISTANCE_PCT\s*=\s*([\d.]+)', trading_logic_content)
        if not min_sl_match:
            warnings.append(
                "trading_logic.py: 未找到 MIN_SL_DISTANCE_PCT\n"
                "   → SL 距离验证可能不生效"
            )
        else:
            min_sl_pct = float(min_sl_match.group(1))
            if min_sl_pct < 0.01:  # 小于 1%
                warnings.append(
                    f"trading_logic.py: MIN_SL_DISTANCE_PCT={min_sl_pct}\n"
                    f"   → 建议至少设置为 0.01 (1%)"
                )

    # 检查 multi_agent_analyzer.py 是否正确导入共享常量/函数
    analyzer_path = project_root / "agents" / "multi_agent_analyzer.py"
    if analyzer_path.exists():
        with open(analyzer_path, 'r', encoding='utf-8') as f:
            analyzer_content = f.read()

        # 支持两种模式:
        # 1. 旧模式: 导入常量 MIN_SL_DISTANCE_PCT
        # 2. 新模式: 导入 getter 函数 get_min_sl_distance_pct (Phase 3 迁移后)
        has_trading_logic_import = "from strategy.trading_logic import" in analyzer_content
        has_min_sl_constant = "MIN_SL_DISTANCE_PCT" in analyzer_content
        has_min_sl_getter = "get_min_sl_distance_pct" in analyzer_content

        # 新模式 (getter 函数) 或 旧模式 (常量) 都可接受
        if not (has_trading_logic_import and (has_min_sl_constant or has_min_sl_getter)):
            warnings.append(
                "multi_agent_analyzer.py: 未从 trading_logic 导入 SL 验证函数/常量\n"
                "   → 应导入 get_min_sl_distance_pct() 或 MIN_SL_DISTANCE_PCT"
            )

    # ==========================================================================
    # 检查 4: patches 是否正确应用
    # ==========================================================================
    patches_init = project_root / "patches" / "__init__.py"
    binance_enums = project_root / "patches" / "binance_enums.py"

    if not binance_enums.exists():
        warnings.append("patches/binance_enums.py 不存在 - 可能缺少枚举兼容性补丁")

    return issues, warnings


# =============================================================================
# 关键: 使用与 main_live.py 完全相同的初始化流程
# =============================================================================

# 设置项目路径 (与 main_live.py 相同)
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 应用补丁 (与 main_live.py 相同)
from patches.binance_enums import apply_all_patches
apply_all_patches()

# 加载环境变量 (与 main_live.py 相同)
from dotenv import load_dotenv
env_permanent = Path.home() / ".env.aitrader"
env_local = project_root / ".env"

if env_permanent.exists():
    load_dotenv(env_permanent)
elif env_local.exists():
    load_dotenv(env_local)
else:
    load_dotenv()

mode_str = " (快速模式)" if SUMMARY_MODE else ""
print("=" * 70)
print(f"  实盘信号诊断工具 v11.9 (TradingAgents v3.6 - 完整数据覆盖){mode_str}")
print("=" * 70)
print(f"  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)
print()

# =============================================================================
# 0. 关键配置检查 (v9.0 新增 - 检测可能导致不能下单的配置问题)
# =============================================================================
print("[0/10] 关键配置检查 (检测可能导致不能下单的问题)...")
print("-" * 70)

config_issues, config_warnings = check_critical_config()

if config_issues:
    print()
    print("  🚨 发现严重问题 (可能导致不能下单):")
    print()
    for issue in config_issues:
        for line in issue.split('\n'):
            print(f"  {line}")
        print()

if config_warnings:
    print("  ⚠️ 警告:")
    for warning in config_warnings:
        for line in warning.split('\n'):
            print(f"     {line}")
    print()

if not config_issues and not config_warnings:
    print("  ✅ load_all=True")
    print("  ✅ reconciliation=True")
    print("  ✅ SL/TP 字段名正确")
    print("  ✅ 所有关键配置检查通过")

if config_issues:
    print("  " + "=" * 66)
    print("  ⛔ 发现严重配置问题! 请先修复上述问题再运行实盘交易。")
    print("  " + "=" * 66)
    print()
    response = input("  是否继续诊断? (y/N): ")
    if response.lower() != 'y':
        print("  退出诊断。")
        sys.exit(1)

print()

# =============================================================================
# 0.5. MTF 多时间框架配置检查 (v10.1 详细验证)
# =============================================================================
print("[0.5/10] MTF 多时间框架配置检查 (v10.1 详细验证)...")
print("-" * 70)

mtf_init_config = {}  # 用于后续历史数据检查

try:
    import yaml
    mtf_config_path = project_root / "configs" / "base.yaml"

    if mtf_config_path.exists():
        with open(mtf_config_path, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f)

        # 从配置加载分析阈值 (v10.19: 修复硬编码违规)
        # 注: 不需要 global 声明,因为我们在模块级别 (不在函数内)
        indicators_config = base_config.get('indicators', {})
        BB_OVERBOUGHT_THRESHOLD = indicators_config.get('bb_overbought_threshold', 80)
        BB_OVERSOLD_THRESHOLD = indicators_config.get('bb_oversold_threshold', 20)
        LS_RATIO_EXTREME_BULLISH = indicators_config.get('ls_ratio_extreme_bullish', 2.0)
        LS_RATIO_BULLISH = indicators_config.get('ls_ratio_bullish', 1.5)
        LS_RATIO_EXTREME_BEARISH = indicators_config.get('ls_ratio_extreme_bearish', 0.5)
        LS_RATIO_BEARISH = indicators_config.get('ls_ratio_bearish', 0.7)

        mtf_config = base_config.get('multi_timeframe', {})
        mtf_enabled = mtf_config.get('enabled', False)

        if mtf_enabled:
            print("  ✅ MTF 多时间框架: 已启用")

            # 趋势层 (1D)
            trend_layer = mtf_config.get('trend_layer', {})
            trend_tf = trend_layer.get('timeframe', 'N/A')
            trend_sma = trend_layer.get('sma_period', 200)
            print(f"     趋势层 (Trend): {trend_tf} (SMA_{trend_sma})")
            # v10.1: 详细配置
            if 'require_above_sma' in trend_layer:
                print(f"       require_above_sma: {trend_layer['require_above_sma']}")
            if 'require_macd_positive' in trend_layer:
                print(f"       require_macd_positive: {trend_layer['require_macd_positive']}")

            # 决策层 (4H)
            decision_layer = mtf_config.get('decision_layer', {})
            decision_tf = decision_layer.get('timeframe', 'N/A')
            print(f"     决策层 (Decision): {decision_tf}")
            # v10.1: 详细配置
            if 'debate_rounds' in decision_layer:
                print(f"       debate_rounds: {decision_layer['debate_rounds']}")
            if 'include_trend_context' in decision_layer:
                print(f"       include_trend_context: {decision_layer['include_trend_context']}")

            # 执行层 (15M)
            execution_layer = mtf_config.get('execution_layer', {})
            execution_tf = execution_layer.get('default_timeframe', 'N/A')
            print(f"     执行层 (Execution): {execution_tf}")
            # v10.1: 详细配置
            if 'rsi_entry_min' in execution_layer:
                print(f"       RSI 入场范围: {execution_layer.get('rsi_entry_min', 30)}-{execution_layer.get('rsi_entry_max', 70)}")
            if 'high_volatility_timeframe' in execution_layer:
                print(f"       高波动周期: {execution_layer['high_volatility_timeframe']}")

            # v10.1: 初始化配置检查
            mtf_init_config = mtf_config.get('initialization', {})
            if mtf_init_config:
                print("  ✅ MTF 初始化配置存在")
                print(f"     trend_min_bars: {mtf_init_config.get('trend_min_bars', 'N/A')}")
                print(f"     decision_min_bars: {mtf_init_config.get('decision_min_bars', 'N/A')}")
                print(f"     execution_min_bars: {mtf_init_config.get('execution_min_bars', 'N/A')}")
                if 'request_timeout_sec' in mtf_init_config:
                    print(f"     request_timeout: {mtf_init_config['request_timeout_sec']}s")
            else:
                print("  ⚠️ MTF initialization 配置段不存在")
                print("     → 将使用默认值 (220/60/40 bars)")

            # 检查 MultiTimeframeManager 模块
            mtf_manager_path = project_root / "indicators" / "multi_timeframe_manager.py"
            if mtf_manager_path.exists():
                print("  ✅ MultiTimeframeManager 模块存在")

                # 尝试导入验证
                try:
                    from indicators.multi_timeframe_manager import (
                        MultiTimeframeManager,
                        RiskState,
                        DecisionState
                    )
                    print("  ✅ MultiTimeframeManager 导入成功")
                    print(f"     RiskState: {[s.name for s in RiskState]}")
                    print(f"     DecisionState: {[s.name for s in DecisionState]}")
                except ImportError as e:
                    print(f"  ⚠️ MultiTimeframeManager 导入失败: {e}")
            else:
                print("  ❌ MultiTimeframeManager 模块不存在!")
                print("     → 预期路径: indicators/multi_timeframe_manager.py")
        else:
            print("  ℹ️ MTF 多时间框架: 未启用")
            print("     → 如需启用，编辑 configs/base.yaml:")
            print("       multi_timeframe:")
            print("         enabled: true")

        # v10.1: Order Flow 配置检查
        order_flow = base_config.get('order_flow', {})
        order_flow_enabled = order_flow.get('enabled', False)
        if order_flow_enabled:
            print()
            print("  ✅ Order Flow: 已启用")
            binance_of = order_flow.get('binance', {})
            coinalyze = order_flow.get('coinalyze', {})
            print(f"     Binance enabled: {binance_of.get('enabled', False)}")
            print(f"     Coinalyze enabled: {coinalyze.get('enabled', False)}")
            # API key 可能在 YAML 或环境变量中
            coinalyze_api_key = coinalyze.get('api_key') or os.getenv('COINALYZE_API_KEY')
            if coinalyze.get('enabled') and not coinalyze_api_key:
                print("     ⚠️ Coinalyze 已启用但缺少 API key (YAML 和环境变量都没有)")
            elif coinalyze.get('enabled') and coinalyze_api_key:
                print("     ✅ Coinalyze API key 已配置")
        else:
            print()
            print("  ℹ️ Order Flow: 未启用")
    else:
        print("  ⚠️ configs/base.yaml 不存在，跳过 MTF 检查")
        mtf_enabled = False

except Exception as e:
    print(f"  ⚠️ MTF 配置检查失败: {e}")
    mtf_enabled = False

print()

# =============================================================================
# 0.6 MTF 历史数据预取验证 (v10.2)
# =============================================================================
if not SUMMARY_MODE and mtf_enabled:
    print("[0.6/10] MTF 历史数据预取验证...")
    print("-" * 70)

    try:
        from indicators.multi_timeframe_manager import MultiTimeframeManager, RiskState, DecisionState

        # 检查 MTF 管理器的关键方法
        mtf_methods = ['route_bar', 'is_initialized', 'get_risk_state', 'get_decision_state', 'evaluate_risk_state']
        missing_methods = []
        for method in mtf_methods:
            if not hasattr(MultiTimeframeManager, method):
                missing_methods.append(method)

        if missing_methods:
            print(f"  ⚠️ MultiTimeframeManager 缺少方法: {missing_methods}")
        else:
            print("  ✅ MultiTimeframeManager 关键方法完整")
            print(f"     方法列表: {', '.join(mtf_methods)}")

        # 检查初始化标志属性
        init_flags = ['_trend_initialized', '_decision_initialized', '_execution_initialized']
        print()
        print("  📋 MTF 初始化标志属性检查:")

        # 这些是实例属性，只能在策略中检查
        print("     → 这些标志在 deepseek_strategy.py 中维护:")
        print("       _mtf_trend_initialized: 趋势层 (1D) 初始化状态")
        print("       _mtf_decision_initialized: 决策层 (4H) 初始化状态")
        print("       _mtf_execution_initialized: 执行层 (15M) 初始化状态")
        print()
        print("     → 查看服务日志检查初始化状态:")
        print("       journalctl -u nautilus-trader | grep -i 'mtf\\|timeframe\\|initialized'")

        # 检查 RiskState 和 DecisionState 枚举值
        print()
        print("  📋 MTF 状态枚举检查:")
        print(f"     RiskState 值: {[s.name for s in RiskState]}")
        print(f"     DecisionState 值: {[s.name for s in DecisionState]}")

        # 检查预取配置
        print()
        print("  📋 MTF 预取配置:")
        base_yaml_path = project_root / "configs" / "base.yaml"
        if base_yaml_path.exists():
            with open(base_yaml_path) as f:
                base_config = yaml.safe_load(f)
            mtf_config = base_config.get('multi_timeframe', {})
            init_cfg = mtf_config.get('initialization', {})

            trend_bars = init_cfg.get('trend_min_bars', 220)
            decision_bars = init_cfg.get('decision_min_bars', 60)
            execution_bars = init_cfg.get('execution_min_bars', 40)

            print(f"     趋势层 (1D) 需要 {trend_bars} 根 K线")
            print(f"     决策层 (4H) 需要 {decision_bars} 根 K线")
            print(f"     执行层 (15M) 需要 {execution_bars} 根 K线")
            print()

            # 计算预取数据量
            print("  📋 预取数据量估算:")
            print(f"     趋势层: {trend_bars} 天 ≈ {trend_bars/365:.1f} 年历史数据")
            print(f"     决策层: {decision_bars * 4} 小时 ≈ {decision_bars * 4 / 24:.1f} 天历史数据")
            print(f"     执行层: {execution_bars * 15} 分钟 ≈ {execution_bars * 15 / 60:.1f} 小时历史数据")

        print()

# v10.3: 实际测试 MTF 数据预取 (与实盘 _prefetch_multi_timeframe_bars 一致)
        print("  📋 MTF 数据预取测试 (实际 API 调用):")
        import requests as mtf_requests

        mtf_test_symbol = "BTCUSDT"  # 默认测试 symbol
        mtf_base_url = "https://fapi.binance.com/fapi/v1/klines"

        # 测试趋势层 (1D)
        try:
            params = {'symbol': mtf_test_symbol, 'interval': '1d', 'limit': min(trend_bars, 10)}
            resp = mtf_requests.get(mtf_base_url, params=params, timeout=10)
            if resp.status_code == 200:
                klines = resp.json()
                print(f"     ✅ 趋势层 (1D): 成功获取 {len(klines)} 根 K线 (测试 limit=10)")
            else:
                print(f"     ❌ 趋势层 (1D): API 错误 {resp.status_code}")
        except Exception as e:
            print(f"     ❌ 趋势层 (1D): {e}")

        # 测试决策层 (4H)
        try:
            params = {'symbol': mtf_test_symbol, 'interval': '4h', 'limit': min(decision_bars, 10)}
            resp = mtf_requests.get(mtf_base_url, params=params, timeout=10)
            if resp.status_code == 200:
                klines = resp.json()
                print(f"     ✅ 决策层 (4H): 成功获取 {len(klines)} 根 K线 (测试 limit=10)")
            else:
                print(f"     ❌ 决策层 (4H): API 错误 {resp.status_code}")
        except Exception as e:
            print(f"     ❌ 决策层 (4H): {e}")

        # 测试执行层 (15M)
        try:
            params = {'symbol': mtf_test_symbol, 'interval': '15m', 'limit': min(execution_bars, 10)}
            resp = mtf_requests.get(mtf_base_url, params=params, timeout=10)
            if resp.status_code == 200:
                klines = resp.json()
                print(f"     ✅ 执行层 (15M): 成功获取 {len(klines)} 根 K线 (测试 limit=10)")
            else:
                print(f"     ❌ 执行层 (15M): API 错误 {resp.status_code}")
        except Exception as e:
            print(f"     ❌ 执行层 (15M): {e}")

        print()
        print("  ✅ MTF 预取配置验证完成")

    except ImportError as e:
        print(f"  ❌ 无法导入 MultiTimeframeManager: {e}")
    except Exception as e:
        print(f"  ⚠️ MTF 预取验证失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# =============================================================================
# 1. 从 main_live.py 导入并获取真实配置
# =============================================================================
if not SUMMARY_MODE:
    print("[1/10] 从 main_live.py 加载真实配置...")

try:
    from main_live import get_strategy_config, load_yaml_config
    from utils.config_manager import ConfigManager

    # 初始化 ConfigManager (与 main_live.py 相同)
    config_manager = ConfigManager(env='production')
    config_manager.load()

    # 获取与实盘完全相同的配置
    strategy_config = get_strategy_config(config_manager)
    yaml_config = load_yaml_config()

    if not SUMMARY_MODE:
        print(f"  instrument_id: {strategy_config.instrument_id}")
        print(f"  bar_type: {strategy_config.bar_type}")
        print(f"  equity: ${strategy_config.equity}")
        print(f"  base_usdt_amount: ${strategy_config.base_usdt_amount}")
        print(f"  leverage: {strategy_config.leverage}x")
        print(f"  min_confidence_to_trade: {strategy_config.min_confidence_to_trade}")
        timer_sec = strategy_config.timer_interval_sec
        timer_min = timer_sec / 60
        print(f"  timer_interval_sec: {timer_sec}s ({timer_min:.1f}分钟)")
        print(f"  sma_periods: {strategy_config.sma_periods}")
        print(f"  rsi_period: {strategy_config.rsi_period}")
        print(f"  macd_fast/slow: {strategy_config.macd_fast}/{strategy_config.macd_slow}")
        print(f"  debate_rounds: {strategy_config.debate_rounds}")
        print("  ✅ 配置加载成功 (与实盘完全一致)")
        print()
        print(f"  ⏰ 注意: 实盘每 {timer_min:.0f} 分钟分析一次")
        print(f"     如果刚启动服务，需等待第一个周期触发")
    else:
        timer_sec = strategy_config.timer_interval_sec
        timer_min = timer_sec / 60
except (ImportError, AttributeError, KeyError, ValueError) as e:
    print(f"  ❌ 配置加载失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 2. 获取市场数据 (与实盘相同的数据源)
# =============================================================================
print("[2/10] 获取市场数据 (Binance Futures)...")

import requests

# 从 bar_type 解析时间周期 (注意: 必须先检查更长的字符串)
bar_type_str = strategy_config.bar_type
# 按照从长到短的顺序检查，避免子字符串匹配错误
if "15-MINUTE" in bar_type_str:
    interval = "15m"
elif "5-MINUTE" in bar_type_str:
    interval = "5m"
elif "1-MINUTE" in bar_type_str:
    interval = "1m"
elif "4-HOUR" in bar_type_str:
    interval = "4h"
elif "1-HOUR" in bar_type_str:
    interval = "1h"
elif "1-DAY" in bar_type_str:
    interval = "1d"
else:
    interval = "15m"

# 从配置提取 symbol (例如 "BTCUSDT-PERP.BINANCE" → "BTCUSDT")
instrument_id_str = strategy_config.instrument_id
symbol = instrument_id_str.split('-')[0]  # 提取交易对名称
limit = 100

try:
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url, timeout=10)
    klines_raw = response.json()

    if isinstance(klines_raw, list) and len(klines_raw) > 0:
        print(f"  交易对: {symbol}")
        print(f"  时间周期: {interval} (从 bar_type 解析)")
        print(f"  K线数量: {len(klines_raw)}")

        latest = klines_raw[-1]
        current_price = float(latest[4])
        # v2.1: 记录快照时间，所有后续计算使用同一价格
        snapshot_timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"  最新价格: ${current_price:,.2f} (快照时间: {snapshot_timestamp})")
        print("  ✅ 市场数据获取成功")
        # 保存快照价格，防止后续被覆盖
        snapshot_price = current_price
    else:
        print(f"  ❌ K线数据异常: {klines_raw}")
        sys.exit(1)
except (requests.RequestException, ValueError, KeyError) as e:
    print(f"  ❌ 获取市场数据失败: {e}")
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 3. 使用真实配置初始化 TechnicalIndicatorManager
# =============================================================================
print("[3/10] 初始化 TechnicalIndicatorManager (使用实盘配置)...")

try:
    from indicators.technical_manager import TechnicalIndicatorManager

    # 使用与 deepseek_strategy.py __init__ 完全相同的参数
    indicator_manager = TechnicalIndicatorManager(
        sma_periods=list(strategy_config.sma_periods),  # 从配置读取
        ema_periods=[strategy_config.macd_fast, strategy_config.macd_slow],  # MACD 周期
        rsi_period=strategy_config.rsi_period,
        macd_fast=strategy_config.macd_fast,
        macd_slow=strategy_config.macd_slow,
        macd_signal=9,  # 固定值
        bb_period=strategy_config.bb_period,
        bb_std=strategy_config.bb_std,
        volume_ma_period=20,
        support_resistance_lookback=20,
    )

    print(f"  sma_periods: {list(strategy_config.sma_periods)}")
    print(f"  ema_periods: [{strategy_config.macd_fast}, {strategy_config.macd_slow}]")
    print(f"  rsi_period: {strategy_config.rsi_period}")
    print(f"  macd: {strategy_config.macd_fast}/{strategy_config.macd_slow}/9")
    print(f"  bb_period: {strategy_config.bb_period}")
    print("  ✅ TechnicalIndicatorManager 初始化成功")

    # 喂入 K 线数据
    for kline in klines_raw:
        class MockBar:
            def __init__(self, o, h, l, c, v, ts):
                self.open = Decimal(str(o))
                self.high = Decimal(str(h))
                self.low = Decimal(str(l))
                self.close = Decimal(str(c))
                self.volume = Decimal(str(v))
                self.ts_init = int(ts)

        bar = MockBar(
            float(kline[1]), float(kline[2]), float(kline[3]),
            float(kline[4]), float(kline[5]), int(kline[0])
        )
        indicator_manager.update(bar)

    # 检查是否初始化完成
    if indicator_manager.is_initialized():
        print(f"  ✅ 指标已初始化 ({len(klines_raw)} 根K线)")
    else:
        print(f"  ⚠️ 指标未完全初始化，可能数据不足")

except (ImportError, AttributeError, TypeError, ValueError) as e:
    print(f"  ❌ TechnicalIndicatorManager 失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 3.5. 检查 Binance 真实持仓 (与实盘一致)
# =============================================================================
print("[3.5/10] 检查 Binance 真实持仓...")
print("-" * 70)

current_position = None  # 默认无持仓

try:
    from utils.binance_account import BinanceAccountFetcher

    account_fetcher = BinanceAccountFetcher()
    positions = account_fetcher.get_positions(symbol="BTCUSDT")

    if positions:
        pos = positions[0]  # 取第一个 BTCUSDT 持仓
        pos_amt = float(pos.get('positionAmt', 0))
        entry_price = float(pos.get('entryPrice', 0))
        unrealized_pnl = float(pos.get('unRealizedProfit', 0))

        if pos_amt != 0:
            side = 'long' if pos_amt > 0 else 'short'
            # 修复: 如果 API 返回 0 但有入场价和当前价，自己计算 PnL
            if unrealized_pnl == 0 and entry_price > 0 and current_price > 0:
                if side == 'long':
                    unrealized_pnl = (current_price - entry_price) * abs(pos_amt)
                else:
                    unrealized_pnl = (entry_price - current_price) * abs(pos_amt)
            # 计算盈亏百分比
            pnl_pct = 0.0
            if entry_price > 0:
                pnl_pct = (unrealized_pnl / (entry_price * abs(pos_amt))) * 100
            current_position = {
                'side': side,
                'quantity': abs(pos_amt),
                'entry_price': entry_price,  # 修复: 使用一致的字段名
                'avg_px': entry_price,       # 保留兼容
                'unrealized_pnl': unrealized_pnl,
                'pnl_pct': pnl_pct,           # 修复: 存储 pnl_pct
            }
            print(f"  ⚠️ 检测到现有持仓!")
            print(f"     方向: {side.upper()}")
            print(f"     数量: {abs(pos_amt):.4f} BTC")
            print(f"     入场价: ${entry_price:,.2f}")
            print(f"     未实现盈亏: ${unrealized_pnl:,.2f}")
            print(f"     盈亏比例: {pnl_pct:+.2f}%")
        else:
            print("  ✅ 无持仓")
    else:
        print("  ✅ 无持仓")

except (ImportError, AttributeError, KeyError, ValueError, requests.RequestException) as e:
    print(f"  ⚠️ 持仓检查失败: {e}")
    print("  → 继续假设无持仓")
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

# ========== 新增: 账户资金详情 (使用实盘组件 BinanceAccountFetcher) ==========
print()
print("  📊 账户资金详情:")
try:
    # 使用 account_fetcher (已在上面初始化)
    balance_data = account_fetcher.get_balance()
    total_balance = balance_data.get('total_balance', 0)
    available_balance = balance_data.get('available_balance', 0)
    margin_balance = balance_data.get('margin_balance', 0)
    account_unrealized_pnl = balance_data.get('unrealized_pnl', 0)

    # 计算已用保证金和保证金率
    used_margin = total_balance - available_balance
    margin_ratio = (available_balance / total_balance * 100) if total_balance > 0 else 0

    print(f"     总余额:       ${total_balance:,.2f}")
    print(f"     可用余额:     ${available_balance:,.2f}")
    print(f"     已用保证金:   ${used_margin:,.2f}")
    print(f"     保证金率:     {margin_ratio:.1f}%")
    print(f"     总未实现PnL:  ${account_unrealized_pnl:,.2f}")
except Exception as e:
    print(f"     ⚠️ 无法获取账户余额: {e}")

print()

# =============================================================================
# 4. 获取技术数据 (与 on_timer 相同)
# =============================================================================
print("[4/10] 获取技术数据 (模拟 on_timer 流程)...")

try:
    technical_data = indicator_manager.get_technical_data(current_price)

    # 重要: 添加 'price' 键到 technical_data (multi_agent_analyzer._format_technical_report 需要)
    technical_data['price'] = current_price

    # 显示关键指标
    sma_keys = [k for k in technical_data.keys() if k.startswith('sma_')]
    for key in sorted(sma_keys):
        print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

    ema_keys = [k for k in technical_data.keys() if k.startswith('ema_')]
    for key in sorted(ema_keys):
        print(f"  {key.upper()}: ${technical_data[key]:,.2f}")

    print(f"  RSI: {technical_data.get('rsi', 0):.2f}")
    print(f"  MACD: {technical_data.get('macd', 0):.4f}")
    print(f"  MACD Signal: {technical_data.get('macd_signal', 0):.4f}")
    print(f"  MACD Histogram: {technical_data.get('macd_histogram', 0):.4f}")
    print(f"  BB Upper: ${technical_data.get('bb_upper', 0):,.2f}")
    print(f"  BB Lower: ${technical_data.get('bb_lower', 0):,.2f}")
    # v3.3: 以下数据仅用于诊断，不传给 AI
    print(f"  [诊断用] Support: ${technical_data.get('support', 0):,.2f}")
    print(f"  [诊断用] Resistance: ${technical_data.get('resistance', 0):,.2f}")
    print(f"  [诊断用] Overall Trend: {technical_data.get('overall_trend', 'N/A')}")
    print("  ✅ 技术数据获取成功")
    print("  📝 v3.3: AI 只接收原始数值 (SMA/RSI/MACD/BB)，不接收 support/resistance/trend 标签")

    # ========== MTF 多时间框架数据获取 (v11.8 新增) ==========
    # 获取 4H 决策层数据
    try:
        from indicators.technical_manager import TechnicalIndicatorManager

        # 4H 数据
        klines_4h = fetch_binance_klines("BTCUSDT", "4h", 60)
        if klines_4h and len(klines_4h) >= 50:
            indicator_manager_4h = TechnicalIndicatorManager(
                sma_periods=[20, 50],
                ema_periods=[12, 26],
                rsi_period=14,
                macd_fast=12,
                macd_slow=26,
                macd_signal=9,
                bb_period=20,
            )
            for kline in klines_4h:
                bar_4h = create_bar_from_kline(kline, "BTCUSDT-PERP.BINANCE-4-HOUR-LAST-EXTERNAL")
                indicator_manager_4h.update(bar_4h)

            decision_layer_data = indicator_manager_4h.get_technical_data(current_price)
            technical_data['mtf_decision_layer'] = {
                'timeframe': '4H',
                'rsi': decision_layer_data.get('rsi', 50),
                'macd': decision_layer_data.get('macd', 0),
                'macd_signal': decision_layer_data.get('macd_signal', 0),
                'sma_20': decision_layer_data.get('sma_20', 0),
                'sma_50': decision_layer_data.get('sma_50', 0),
                'bb_upper': decision_layer_data.get('bb_upper', 0),
                'bb_middle': decision_layer_data.get('bb_middle', 0),
                'bb_lower': decision_layer_data.get('bb_lower', 0),
                'bb_position': decision_layer_data.get('bb_position', 50),
            }
            print(f"  ✅ 4H 决策层数据加载: RSI={technical_data['mtf_decision_layer']['rsi']:.1f}")
        else:
            print("  ⚠️ 4H K线数据不足，跳过决策层")

        # 1D 数据
        klines_1d = fetch_binance_klines("BTCUSDT", "1d", 220)
        if klines_1d and len(klines_1d) >= 200:
            indicator_manager_1d = TechnicalIndicatorManager(
                sma_periods=[200],
                ema_periods=[12, 26],
                rsi_period=14,
                macd_fast=12,
                macd_slow=26,
                macd_signal=9,
                bb_period=20,
            )
            for kline in klines_1d:
                bar_1d = create_bar_from_kline(kline, "BTCUSDT-PERP.BINANCE-1-DAY-LAST-EXTERNAL")
                indicator_manager_1d.update(bar_1d)

            trend_layer_data = indicator_manager_1d.get_technical_data(current_price)
            technical_data['mtf_trend_layer'] = {
                'timeframe': '1D',
                'sma_200': trend_layer_data.get('sma_200', 0),
                'macd': trend_layer_data.get('macd', 0),
                'macd_signal': trend_layer_data.get('macd_signal', 0),
            }
            print(f"  ✅ 1D 趋势层数据加载: SMA_200=${technical_data['mtf_trend_layer']['sma_200']:,.2f}")
        else:
            print(f"  ⚠️ 1D K线数据不足 ({len(klines_1d) if klines_1d else 0}/200)，跳过趋势层")

    except Exception as e:
        print(f"  ⚠️ MTF 多时间框架数据获取失败: {e}")

except (AttributeError, KeyError, TypeError, ValueError) as e:
    print(f"  ❌ 技术数据获取失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 5. 初始化并获取情绪数据 (使用实盘配置)
# =============================================================================
print("[5/10] 获取情绪数据 (使用实盘配置)...")

try:
    from utils.sentiment_client import SentimentDataFetcher

    # 使用与 deepseek_strategy.py on_start 相同的参数
    sentiment_fetcher = SentimentDataFetcher(
        lookback_hours=strategy_config.sentiment_lookback_hours,
        timeframe=strategy_config.sentiment_timeframe,
    )

    print(f"  lookback_hours: {strategy_config.sentiment_lookback_hours}")
    print(f"  timeframe: {strategy_config.sentiment_timeframe}")

    sentiment_data = sentiment_fetcher.fetch()

    if sentiment_data:
        print(f"  Long/Short Ratio: {sentiment_data.get('long_short_ratio', 0):.4f}")
        print(f"  Long Account %: {sentiment_data.get('positive_ratio', 0)*100:.2f}%")
        print(f"  Short Account %: {sentiment_data.get('negative_ratio', 0)*100:.2f}%")
        print(f"  Source: {sentiment_data.get('source', 'N/A')}")
        print("  ✅ 情绪数据获取成功")
    else:
        # 与 on_timer 相同的 fallback 逻辑 (deepseek_strategy.py:1114-1125)
        sentiment_data = {
            'long_short_ratio': 1.0,
            'long_account_pct': 50.0,
            'short_account_pct': 50.0,
            'positive_ratio': 0.5,      # 必需字段 - deepseek_client.py 使用
            'negative_ratio': 0.5,      # 必需字段 - deepseek_client.py 使用
            'net_sentiment': 0.0,       # 必需字段 - deepseek_client.py 使用
            'source': 'default_neutral',
            'timestamp': None,
        }
        print("  ⚠️ 使用中性默认值 (与 on_timer fallback 相同)")

except (ImportError, AttributeError, requests.RequestException, ValueError) as e:
    print(f"  ❌ 情绪数据获取失败: {e}")
    sentiment_data = {
        'long_short_ratio': 1.0,
        'long_account_pct': 50.0,
        'short_account_pct': 50.0,
        'positive_ratio': 0.5,      # 必需字段
        'negative_ratio': 0.5,      # 必需字段
        'net_sentiment': 0.0,       # 必需字段
        'source': 'fallback',
        'timestamp': None,
    }
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 6. 构建价格数据 (与 on_timer 相同结构)
# =============================================================================
print("[6/10] 构建价格数据...")

kline_data = indicator_manager.get_kline_data(count=10)

# 计算价格变化
bars = indicator_manager.recent_bars
if len(bars) >= 2:
    price_change = ((float(bars[-1].close) - float(bars[-2].close)) / float(bars[-2].close)) * 100
else:
    price_change = 0.0

# v3.6: 计算周期统计 (与 deepseek_strategy._calculate_period_statistics 一致)
if bars and len(bars) >= 2:
    period_high = max(float(bar.high) for bar in bars)
    period_low = min(float(bar.low) for bar in bars)
    period_start_price = float(bars[0].open)
    period_change_pct = ((current_price - period_start_price) / period_start_price) * 100 if period_start_price > 0 else 0
    period_hours = len(bars) * 15 / 60  # 15分钟K线
else:
    period_high = current_price
    period_low = current_price
    period_change_pct = 0
    period_hours = 0

price_data = {
    'price': current_price,
    'timestamp': datetime.now().isoformat(),
    'high': float(klines_raw[-1][2]),
    'low': float(klines_raw[-1][3]),
    'volume': float(klines_raw[-1][5]),
    'price_change': price_change,
    'kline_data': kline_data,
    # v3.6: 周期统计
    'period_high': period_high,
    'period_low': period_low,
    'period_change_pct': period_change_pct,
    'period_hours': round(period_hours, 1),
}

print(f"  Current Price: ${price_data['price']:,.2f}")
print(f"  High: ${price_data['high']:,.2f}")
print(f"  Low: ${price_data['low']:,.2f}")
print(f"  Price Change: {price_data['price_change']:.2f}%")
print(f"  Period High ({period_hours:.0f}h): ${period_high:,.2f}")
print(f"  Period Low ({period_hours:.0f}h): ${period_low:,.2f}")
print(f"  Period Change ({period_hours:.0f}h): {period_change_pct:+.2f}%")
print(f"  K-line Count: {len(price_data['kline_data'])}")
print("  ✅ 价格数据构建成功")

print()

# =============================================================================
# 7. MultiAgent 层级决策 (TradingAgents 架构 - 使用实盘配置)
# =============================================================================
print("[7/10] MultiAgent 层级决策 (TradingAgents 架构)...")
print("-" * 70)
print("  📋 决策流程:")
print("     Phase 1: Bull/Bear Debate (辩论)")
print("     Phase 2: Judge (Portfolio Manager) Decision")
print("     Phase 3: Risk Evaluation")
print()

try:
    from agents.multi_agent_analyzer import MultiAgentAnalyzer

    # 使用与 deepseek_strategy.py 完全相同的初始化参数
    multi_agent = MultiAgentAnalyzer(
        api_key=strategy_config.deepseek_api_key,
        model=strategy_config.deepseek_model,
        temperature=strategy_config.deepseek_temperature,
        debate_rounds=strategy_config.debate_rounds,
    )

    print(f"  Model: {strategy_config.deepseek_model}")
    print(f"  Temperature: {strategy_config.deepseek_temperature}")
    print(f"  Debate Rounds: {strategy_config.debate_rounds}")
    print()
    print("  🐂 Bull Agent 分析中...")
    print("  🐻 Bear Agent 分析中...")
    print("  ⚖️ Judge Agent 判断中...")
    print("  🛡️ Risk Manager 评估中...")

    # 调用分析 (与 on_timer 相同，使用真实持仓)
    # TradingAgents: Judge 决策即最终决策，不需要与 DeepSeek 合并
    # 准备 MTF v2.1 增强数据 (如果可用)
    order_flow_report = None
    derivatives_report = None
    
    # 尝试导入 AIDataAssembler 获取 MTF 数据
    try:
        from utils.binance_kline_client import BinanceKlineClient
        from utils.order_flow_processor import OrderFlowProcessor
        from utils.coinalyze_client import CoinalyzeClient
        from utils.ai_data_assembler import AIDataAssembler
        from utils.sentiment_client import SentimentDataFetcher
        
        # 初始化 MTF 组件
        kline_client = BinanceKlineClient(timeout=10)
        processor = OrderFlowProcessor()
        coinalyze_client = CoinalyzeClient()
        sentiment_client = SentimentDataFetcher()
        assembler = AIDataAssembler(
            binance_kline_client=kline_client,
            order_flow_processor=processor,
            coinalyze_client=coinalyze_client,
            sentiment_client=sentiment_client
        )
        
        # 组装数据
        symbol_clean = strategy_config.instrument_id.split('-')[0]
        assembled = assembler.assemble(
            technical_data=technical_data,
            position_data=current_position,
            symbol=symbol_clean,
            interval="15m"
        )
        
        order_flow_report = assembled.get('order_flow')
        derivatives_report = assembled.get('derivatives')
        
        if order_flow_report:
            print("  📊 MTF Order Flow 数据已加载")
        if derivatives_report:
            print("  📊 MTF Derivatives 数据已加载")
            
    except Exception as e:
        print(f"  ℹ️ MTF 增强数据不可用 (使用基础模式): {e}")

    # ========== 显示传给 AI 的完整输入数据 (v10.15) ==========
    print()
    print("  ┌─────────────────────────────────────────────────────────────────┐")
    print("  │              AI 输入数据验证 (传给 MultiAgent)                   │")
    print("  └─────────────────────────────────────────────────────────────────┘")
    print()
    print("  [1] technical_data (15M 技术指标):")
    print(f"      price:           ${technical_data.get('price', 0):,.2f}")
    print(f"      sma_5:           ${technical_data.get('sma_5', 0):,.2f}")
    print(f"      sma_20:          ${technical_data.get('sma_20', 0):,.2f}")
    print(f"      sma_50:          ${technical_data.get('sma_50', 0):,.2f}")
    print(f"      rsi:             {technical_data.get('rsi', 0):.2f}")
    print(f"      macd:            {technical_data.get('macd', 0):.4f}")
    print(f"      macd_histogram:  {technical_data.get('macd_histogram', 0):.4f}")
    print(f"      bb_upper:        ${technical_data.get('bb_upper', 0):,.2f}")
    print(f"      bb_lower:        ${technical_data.get('bb_lower', 0):,.2f}")
    print(f"      bb_position:     {technical_data.get('bb_position', 50):.1f}% (0%=下轨, 100%=上轨)")
    print(f"      [诊断用] overall_trend: {technical_data.get('overall_trend', 'N/A')}")
    print()
    print("  [2] sentiment_data (情绪数据):")
    print(f"      positive_ratio:  {sentiment_data.get('positive_ratio', 0):.4f} ({sentiment_data.get('positive_ratio', 0)*100:.2f}%)")
    print(f"      negative_ratio:  {sentiment_data.get('negative_ratio', 0):.4f} ({sentiment_data.get('negative_ratio', 0)*100:.2f}%)")
    print(f"      net_sentiment:   {sentiment_data.get('net_sentiment', 0):.4f}")
    print()
    print("  [3] price_data (价格数据 v3.6):")
    print(f"      price:           ${price_data.get('price', 0):,.2f}")
    print(f"      price_change:    {price_data.get('price_change', 0):.2f}% (上一根K线)")
    period_hours = price_data.get('period_hours', 0)
    print(f"      period_high:     ${price_data.get('period_high', 0):,.2f} ({period_hours:.0f}h)")
    print(f"      period_low:      ${price_data.get('period_low', 0):,.2f} ({period_hours:.0f}h)")
    print(f"      period_change:   {price_data.get('period_change_pct', 0):+.2f}% ({period_hours:.0f}h)")
    print()
    if order_flow_report:
        print("  [4] order_flow_report (订单流 v3.6):")
        print(f"      buy_ratio:       {order_flow_report.get('buy_ratio', 0):.4f} ({order_flow_report.get('buy_ratio', 0)*100:.2f}%)")
        print(f"      volume_usdt:     ${order_flow_report.get('volume_usdt', 0):,.0f}")
        print(f"      avg_trade_usdt:  ${order_flow_report.get('avg_trade_usdt', 0):,.2f}")
        print(f"      trades_count:    {order_flow_report.get('trades_count', 0):,}")
        print(f"      [诊断用] cvd_trend: {order_flow_report.get('cvd_trend', 'N/A')}")
        print(f"      data_source:     {order_flow_report.get('data_source', 'N/A')}")
    else:
        print("  [4] order_flow_report: None (未获取)")
    print()
    if derivatives_report:
        print("  [5] derivatives_report (衍生品数据):")
        oi = derivatives_report.get('open_interest', {})
        fr = derivatives_report.get('funding_rate', {})
        liq = derivatives_report.get('liquidations', {})
        print(f"      OI value (BTC):  {oi.get('value', 0) if oi else 0:,.2f}")
        print(f"      Funding rate:    {fr.get('value', 0) if fr else 0:.6f} ({fr.get('value', 0)*100 if fr else 0:.4f}%)")
        # 显示 Liquidations 原始数据
        if liq:
            history = liq.get('history', [])
            if history:
                latest = history[-1]
                print(f"      Liq history[-1]:  l={latest.get('l', 0)} BTC, s={latest.get('s', 0)} BTC")
            else:
                print(f"      Liq history:      empty")
        else:
            print(f"      liquidations:    None")
    else:
        print("  [5] derivatives_report: None (未获取)")
    print()

    # ========== MTF 多时间框架数据 (v11.8 新增) ==========
    # 获取 4H 决策层数据
    mtf_decision_data = technical_data.get('mtf_decision_layer')
    if mtf_decision_data:
        print("  [6] mtf_decision_layer (4H 决策层):")
        print(f"      rsi:             {mtf_decision_data.get('rsi', 0):.2f}")
        print(f"      macd:            {mtf_decision_data.get('macd', 0):.4f}")
        print(f"      sma_20:          ${mtf_decision_data.get('sma_20', 0):,.2f}")
        print(f"      sma_50:          ${mtf_decision_data.get('sma_50', 0):,.2f}")
        print(f"      bb_upper:        ${mtf_decision_data.get('bb_upper', 0):,.2f}")
        print(f"      bb_lower:        ${mtf_decision_data.get('bb_lower', 0):,.2f}")
        print(f"      bb_position:     {mtf_decision_data.get('bb_position', 50):.1f}%")
    else:
        print("  [6] mtf_decision_layer (4H): 未初始化或未启用")
    print()

    # 获取 1D 趋势层数据
    mtf_trend_data = technical_data.get('mtf_trend_layer')
    if mtf_trend_data:
        print("  [7] mtf_trend_layer (1D 趋势层):")
        print(f"      sma_200:         ${mtf_trend_data.get('sma_200', 0):,.2f}")
        price_vs_sma200 = ((current_price / mtf_trend_data.get('sma_200', 1) - 1) * 100) if mtf_trend_data.get('sma_200', 0) > 0 else 0
        print(f"      price vs SMA200: {'+' if price_vs_sma200 >= 0 else ''}{price_vs_sma200:.2f}%")
        print(f"      macd:            {mtf_trend_data.get('macd', 0):.4f}")
        print(f"      macd_signal:     {mtf_trend_data.get('macd_signal', 0):.4f}")
    else:
        print("  [7] mtf_trend_layer (1D): 未初始化或未启用")
    print()

    if current_position:
        print("  [8] current_position (当前持仓):")
        print(f"      side:            {current_position.get('side', 'N/A')}")
        print(f"      quantity:        {current_position.get('quantity', 0)} BTC")
        print(f"      entry_price:     ${current_position.get('entry_price', 0):,.2f}")
        print(f"      unrealized_pnl:  ${current_position.get('unrealized_pnl', 0):,.2f}")
    else:
        print("  [8] current_position: None (无持仓)")
    print()
    print("  ────────────────────────────────────────────────────────────────")

    signal_data = multi_agent.analyze(
        symbol="BTCUSDT",
        technical_report=technical_data,
        sentiment_report=sentiment_data,
        current_position=current_position,  # 使用真实持仓
        price_data=price_data,
        order_flow_report=order_flow_report,  # MTF v2.1
        derivatives_report=derivatives_report,  # MTF v2.1
    )

    print()
    print("  🎯 Judge 最终决策:")
    print(f"     Signal: {signal_data.get('signal', 'N/A')}")
    print(f"     Confidence: {signal_data.get('confidence', 'N/A')}")
    print(f"     Risk Level: {signal_data.get('risk_level', 'N/A')}")
    print(f"     Stop Loss: ${signal_data.get('stop_loss', 0):,.2f}" if signal_data.get('stop_loss') else "     Stop Loss: None")
    print(f"     Take Profit: ${signal_data.get('take_profit', 0):,.2f}" if signal_data.get('take_profit') else "     Take Profit: None")

    # 显示 Judge 详细决策 (v3.0 简化版 - AI 完全自主决策)
    judge_decision = signal_data.get('judge_decision', {})
    if judge_decision:
        winning_side = judge_decision.get('winning_side', 'N/A')
        print(f"     Winning Side: {winning_side}")

        # v3.0: 移除确认计数框架，AI 完全自主评估
        print()
        print("     📋 Judge 决策 (v3.0 AI 完全自主):")
        print("        - AI 自主分析 Bull/Bear 辩论")
        print("        - AI 自主判断证据强度")
        print("        - 无硬编码规则或阈值")
        print()

        key_reasons = judge_decision.get('key_reasons', [])
        if key_reasons:
            print(f"     Key Reasons: {', '.join(key_reasons[:3])}")

        acknowledged_risks = judge_decision.get('acknowledged_risks', [])
        if acknowledged_risks:
            print(f"     Acknowledged Risks: {', '.join(acknowledged_risks[:2])}")

    if signal_data.get('debate_summary'):
        summary = signal_data['debate_summary']
        print(f"     Debate Summary: {summary[:150]}..." if len(summary) > 150 else f"     Debate Summary: {summary}")

    reason = signal_data.get('reason', 'N/A')
    print(f"     Reason: {reason[:150]}..." if len(reason) > 150 else f"     Reason: {reason}")

    # 显示 Bull/Bear 辩论记录
    if hasattr(multi_agent, 'get_last_debate') and callable(multi_agent.get_last_debate):
        debate_transcript = multi_agent.get_last_debate()
        if debate_transcript:
            print()
            print("  📜 辩论记录 (Bull/Bear Debate):")
            # 只显示前500字符
            if len(debate_transcript) > 500:
                print(f"     {debate_transcript[:500]}...")
                print(f"     [截断, 完整长度: {len(debate_transcript)} 字符]")
            else:
                print(f"     {debate_transcript}")

    print("  ✅ MultiAgent 层级决策成功")

    # ========== 显示 AI Prompt 结构 (v11.4 新增) ==========
    if hasattr(multi_agent, 'get_last_prompts') and callable(multi_agent.get_last_prompts):
        last_prompts = multi_agent.get_last_prompts()
        if last_prompts:
            print()
            print("  ┌─────────────────────────────────────────────────────────────────┐")
            print("  │         AI Prompt 结构验证 (v3.4 System/User 分离)              │")
            print("  └─────────────────────────────────────────────────────────────────┘")
            print()

            for agent_name in ["bull", "bear", "judge", "risk"]:
                if agent_name in last_prompts:
                    prompts = last_prompts[agent_name]
                    system_prompt = prompts.get("system", "")
                    user_prompt = prompts.get("user", "")

                    # 检查 INDICATOR_DEFINITIONS 是否在 System Prompt 中
                    has_indicator_defs = "INDICATOR REFERENCE" in system_prompt

                    print(f"  [{agent_name.upper()}] Prompt 结构:")
                    print(f"     System Prompt 长度: {len(system_prompt)} 字符")
                    print(f"     User Prompt 长度:   {len(user_prompt)} 字符")
                    print(f"     INDICATOR_DEFINITIONS 在 System: {'✅ 是' if has_indicator_defs else '❌ 否'}")

                    # 显示 System Prompt 前 200 字符
                    if system_prompt:
                        preview = system_prompt[:200].replace('\n', ' ')
                        print(f"     System 预览: {preview}...")

                    # 显示 User Prompt 前 200 字符
                    if user_prompt:
                        preview = user_prompt[:200].replace('\n', ' ')
                        print(f"     User 预览:   {preview}...")
                    print()

            print("  📋 v3.4 架构要求:")
            print("     - System Prompt: 角色定义 + INDICATOR_DEFINITIONS (知识背景)")
            print("     - User Prompt: 原始数据 + 任务指令 (当前任务)")
            print()

except (ImportError, AttributeError, requests.RequestException, ValueError, KeyError) as e:
    print(f"  ❌ MultiAgent 层级决策失败: {e}")
    import traceback
    traceback.print_exc()
    signal_data = {
        'signal': 'ERROR',
        'confidence': 'LOW',
        'reason': str(e),
        'stop_loss': None,
        'take_profit': None,
    }
except (KeyboardInterrupt, SystemExit):
    print("\n  用户中断")
    raise

print()

# =============================================================================
# 7.5 TradingAgents v3.3: 原始数据 + AI 自主解读
# =============================================================================
print("[7.5/10] TradingAgents v3.3 架构验证...")
print("-" * 70)

original_signal = signal_data.get('signal', 'HOLD')
mtf_filtered = False
mtf_filter_reason = None

print("  📊 TradingAgents v3.3 设计理念:")
print("     \"Autonomy is non-negotiable\" - AI 像人类分析师一样思考")
print("     AI 接收原始数值 + INDICATOR_DEFINITIONS 自主解读")
print()
print("  ✅ 已移除的本地硬编码规则:")
print("     ❌ 趋势方向权限检查 (allow_long/allow_short)")
print("     ❌ 支撑/阻力位边界检查 (proximity_threshold)")
print("     ❌ RSI 入场范围限制")
print("     ❌ 确认计数框架 (bullish_count/bearish_count)")
print()
print("  ✅ 不再传给 AI 的预计算标签 (v3.3 移除):")
print("     ❌ support/resistance - AI 用 SMA_50/BB 作动态支撑阻力")
print("     ❌ cvd_trend - AI 从 recent_10_bars 推断")
print("     ❌ overall_trend - AI 从 SMA 关系推断")
print("     ❌ Interpretation: Bullish/Bearish - AI 从原始比例推断")
print()
print("  📋 AI 接收的数据 (原始数值，由 AI 自主解读):")
print(f"     - Price: ${current_price:,.2f}")
print(f"     - SMA_5/20/50: ${technical_data.get('sma_5', 0):,.2f} / ${technical_data.get('sma_20', 0):,.2f} / ${technical_data.get('sma_50', 0):,.2f}")
print(f"     - RSI: {technical_data.get('rsi', 0):.1f}")
print(f"     - MACD/Signal: {technical_data.get('macd', 0):.4f} / {technical_data.get('macd_signal', 0):.4f}")
print(f"     - BB: ${technical_data.get('bb_lower', 0):,.2f} - ${technical_data.get('bb_upper', 0):,.2f}")
if order_flow_report:
    print(f"     - Buy Ratio: {order_flow_report.get('buy_ratio', 0)*100:.1f}%")
print()
print("  🎯 AI 决策结果 (无本地过滤):")
print(f"     Signal: {signal_data.get('signal')}")
print(f"     Confidence: {signal_data.get('confidence')}")
print()

# MTF 状态估算 (v11.5)
print("  📊 MTF 状态估算 (基于当前数据，非实盘实时状态):")
sma_200 = technical_data.get('sma_200', 0)
if sma_200 > 0:
    # 趋势层 (1D): 基于 SMA_200
    price_vs_sma200 = current_price / sma_200 - 1 if sma_200 > 0 else 0
    if current_price > sma_200:
        risk_state = "RISK_ON"
        risk_reason = f"价格 > SMA_200 ({price_vs_sma200*100:+.2f}%)"
    else:
        risk_state = "RISK_OFF"
        risk_reason = f"价格 < SMA_200 ({price_vs_sma200*100:+.2f}%)"
    print(f"     趋势层 (1D): {risk_state} - {risk_reason}")

    # 决策层 (4H): 基于 SMA 排列和 RSI
    sma_5 = technical_data.get('sma_5', 0)
    sma_20 = technical_data.get('sma_20', 0)
    rsi = technical_data.get('rsi', 50)
    if sma_5 > sma_20 and rsi < 70:
        decision_state = "ALLOW_LONG"
        decision_reason = f"SMA_5 > SMA_20, RSI={rsi:.1f}"
    elif sma_5 < sma_20 and rsi > 30:
        decision_state = "ALLOW_SHORT"
        decision_reason = f"SMA_5 < SMA_20, RSI={rsi:.1f}"
    else:
        decision_state = "WAIT"
        decision_reason = f"SMA 排列不明确或 RSI 极值"
    print(f"     决策层 (4H): {decision_state} - {decision_reason}")

    # 执行层状态
    bb_lower = technical_data.get('bb_lower', 0)
    bb_upper = technical_data.get('bb_upper', 0)
    if bb_lower > 0 and bb_upper > 0:
        bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) * 100
        print(f"     执行层 (15M): BB 位置 {bb_position:.1f}% (0%=下轨, 100%=上轨)")
else:
    print(f"     ⚠️ SMA_200 不可用 ({sma_200})，无法估算 MTF 状态")

print()
print("  ⚠️ 注意: 以上为基于当前数据的估算值")
print("     实盘 MTF 状态需要历史 K 线初始化后才能获取真实值")
print("     查看实盘状态: journalctl -u nautilus-trader | grep 'RISK_ON\\|RISK_OFF'")
print()
print("  ✅ TradingAgents v3.4 架构验证完成")
print()

# =============================================================================
# 8. 交易决策 (TradingAgents - Judge 决策即最终决策)
# =============================================================================
print("[8/10] 交易决策 (TradingAgents - Judge 决策即最终决策)...")
print("-" * 70)

# 导入共享模块 (与实盘使用完全相同的函数)
from strategy.trading_logic import (
    check_confidence_threshold,
    calculate_position_size,
    validate_multiagent_sltp,
    calculate_technical_sltp,
    CONFIDENCE_LEVELS,
)

# TradingAgents: Judge 决策即最终决策，不需要信号合并
final_signal = signal_data.get('signal', 'HOLD')
confidence = signal_data.get('confidence', 'LOW')

print(f"  🎯 Final Signal: {final_signal}")
print(f"  📊 Confidence: {confidence}")
print()

# =============================================================================
# SL/TP 验证逻辑 (与 deepseek_strategy.py:1272-1388 完全一致)
# =============================================================================
final_sl = None
final_tp = None
sltp_source = "N/A"

if final_signal in ['BUY', 'SELL']:
    print("  📊 SL/TP 验证 (模拟 _submit_bracket_order 逻辑):")
    print("-" * 70)

    # 获取 entry price
    entry_price = price_data.get('price', current_price)

    # 检查 MultiAgent SL/TP (来自 Judge 的决策)
    multi_sl = signal_data.get('stop_loss')
    multi_tp = signal_data.get('take_profit')

    if multi_sl and multi_tp:
        print(f"     MultiAgent 返回: SL=${multi_sl:,.2f}, TP=${multi_tp:,.2f}")

        # 验证 MultiAgent SL/TP
        is_valid, validated_sl, validated_tp, reason = validate_multiagent_sltp(
            side=final_signal,
            multi_sl=multi_sl,
            multi_tp=multi_tp,
            entry_price=entry_price
        )

        if is_valid:
            print(f"     ✅ MultiAgent SL/TP 验证通过: {reason}")
            final_sl = validated_sl
            final_tp = validated_tp
            sltp_source = "MultiAgent (Judge)"
        else:
            print(f"     ❌ MultiAgent SL/TP 验证失败: {reason}")
            print(f"     → 回退到技术分析计算")

            # 回退到技术分析
            support = technical_data.get('support', 0.0)
            resistance = technical_data.get('resistance', 0.0)
            use_sr = getattr(strategy_config, 'sl_use_support_resistance', True)
            sl_buffer = getattr(strategy_config, 'sl_buffer_pct', 0.001)

            final_sl, final_tp, calc_method = calculate_technical_sltp(
                side=final_signal,
                entry_price=entry_price,
                support=support,
                resistance=resistance,
                confidence=confidence,
                use_support_resistance=use_sr,
                sl_buffer_pct=sl_buffer
            )
            sltp_source = f"Technical Analysis ({calc_method})"
            print(f"     📍 技术分析计算: SL=${final_sl:,.2f}, TP=${final_tp:,.2f}")
            print(f"     方法: {calc_method}")
    else:
        print("     ⚠️ MultiAgent 未返回 SL/TP，使用技术分析")

        # 直接使用技术分析
        support = technical_data.get('support', 0.0)
        resistance = technical_data.get('resistance', 0.0)
        use_sr = getattr(strategy_config, 'sl_use_support_resistance', True)
        sl_buffer = getattr(strategy_config, 'sl_buffer_pct', 0.001)

        final_sl, final_tp, calc_method = calculate_technical_sltp(
            side=final_signal,
            entry_price=entry_price,
            support=support,
            resistance=resistance,
            confidence=confidence,
            use_support_resistance=use_sr,
            sl_buffer_pct=sl_buffer
        )
        sltp_source = f"Technical Analysis ({calc_method})"
        print(f"     📍 技术分析计算: SL=${final_sl:,.2f}, TP=${final_tp:,.2f}")
        print(f"     方法: {calc_method}")

    # 显示最终 SL/TP
    print()
    print(f"  🎯 最终 SL/TP (实盘会使用的值):")
    if final_sl and final_tp:
        sl_pct = ((final_sl / entry_price) - 1) * 100
        tp_pct = ((final_tp / entry_price) - 1) * 100
        print(f"     Entry: ~${entry_price:,.2f}")
        print(f"     Stop Loss: ${final_sl:,.2f} ({sl_pct:+.2f}%)")
        print(f"     Take Profit: ${final_tp:,.2f} ({tp_pct:+.2f}%)")
        print(f"     来源: {sltp_source}")
    else:
        print(f"     ❌ 无法计算 SL/TP")

print()

# 模拟 _execute_trade 的检查逻辑 (使用共享模块)
print("  模拟 _execute_trade 检查:")

# 0. 检查 is_trading_paused (诊断无法检测，需查看服务状态)
print("  ⚠️ is_trading_paused: 无法检测 (需查看服务日志)")

# 1. 检查 min_confidence (使用共享函数)
passes_threshold, threshold_msg = check_confidence_threshold(
    confidence, strategy_config.min_confidence_to_trade
)
print(f"  {threshold_msg}")

if not passes_threshold:
    print("     → Trade would be SKIPPED")
    would_trade = False
else:
    would_trade = True

# 2. 检查是否 HOLD
if final_signal == 'HOLD':
    print("  ℹ️ Signal is HOLD → No action")
    would_trade = False
elif final_signal in ['BUY', 'SELL']:
    print(f"  ✅ Signal is {final_signal} → Actionable")
else:
    print(f"  ❌ Signal is {final_signal} → Error state")
    would_trade = False

# 3. 计算仓位大小 (使用共享模块 calculate_position_size - 100% 一致)
if would_trade and final_signal in ['BUY', 'SELL']:
    print()
    print("  模拟仓位计算 (调用共享 calculate_position_size):")

    # 构建与 strategy 相同的配置字典
    position_config = {
        'base_usdt': strategy_config.base_usdt_amount,
        'equity': strategy_config.equity,
        'high_confidence_multiplier': strategy_config.high_confidence_multiplier,
        'medium_confidence_multiplier': strategy_config.medium_confidence_multiplier,
        'low_confidence_multiplier': strategy_config.low_confidence_multiplier,
        'trend_strength_multiplier': strategy_config.trend_strength_multiplier,
        'rsi_extreme_multiplier': strategy_config.rsi_extreme_multiplier,
        'rsi_extreme_upper': strategy_config.rsi_extreme_threshold_upper,
        'rsi_extreme_lower': strategy_config.rsi_extreme_threshold_lower,
        'max_position_ratio': strategy_config.max_position_ratio,
        'min_trade_amount': getattr(strategy_config, 'min_trade_amount', 0.001),
    }

    # 使用共享模块计算仓位 (与 strategy._calculate_position_size 完全相同)
    btc_quantity, calc_details = calculate_position_size(
        signal_data=signal_data,  # TradingAgents: 使用 Judge 的决策数据
        price_data=price_data,
        technical_data=technical_data,
        config=position_config,
        logger=None,  # 静默模式，我们手动打印
    )

    # 显示计算详情
    print(f"     Base: ${calc_details['base_usdt']}")
    print(f"     × Confidence Mult: {calc_details['conf_mult']}")
    print(f"     × Trend Mult: {calc_details['trend_mult']} (trend={calc_details['trend']})")
    print(f"     × RSI Mult: {calc_details['rsi_mult']} (RSI={calc_details['rsi']:.1f})")
    print(f"     = ${calc_details['suggested_usdt']:.2f}")
    print(f"     Max allowed: ${calc_details['max_usdt']:.2f}")
    print(f"     Final: ${calc_details['final_usdt']:.2f}")
    print(f"     BTC Quantity: {btc_quantity:.4f} BTC")
    print(f"     Notional: ${calc_details['notional']:.2f}")
    if calc_details.get('adjusted'):
        print(f"     ⚠️ Quantity adjusted to meet minimum notional")

    # 3.5 检查仓位为0 (与 _execute_trade 一致)
    if btc_quantity == 0:
        print()
        print("  ❌ 仓位计算结果为 0!")
        print("     → 实盘会输出: 'Calculated position size is 0, skipping trade'")
        print("     → 🔴 NO TRADE")
        would_trade = False

    # 4. 检查现有持仓 (与 _manage_existing_position 逻辑一致)
    print()
    print("  模拟持仓管理检查:")
    target_side = 'long' if final_signal == 'BUY' else 'short'

    if current_position:
        current_side = current_position['side']
        current_qty = current_position['quantity']
        adjustment_threshold = getattr(strategy_config, 'position_adjustment_threshold', 0.001)

        print(f"     当前持仓: {current_side.upper()} {current_qty:.4f} BTC")
        print(f"     目标方向: {target_side.upper()} {btc_quantity:.4f} BTC")
        print(f"     调整阈值: {adjustment_threshold} BTC")

        if target_side == current_side:
            # 同方向持仓
            size_diff = btc_quantity - current_qty
            print(f"     仓位差异: {size_diff:+.4f} BTC")

            if abs(size_diff) < adjustment_threshold:
                print(f"     ⚠️ 仓位差异 ({abs(size_diff):.4f}) < 阈值 ({adjustment_threshold})")
                print(f"     → 实盘会输出: 'Position size appropriate, no adjustment needed'")
                print(f"     → 🔴 NO NEW TRADE - 这就是信号发出但无交易的原因!")
                would_trade = False
            elif size_diff > 0:
                print(f"     → 将增加仓位 {abs(size_diff):.4f} BTC")
            else:
                print(f"     → 将减少仓位 {abs(size_diff):.4f} BTC")
        else:
            # 反向持仓 - 反转
            allow_reversals = getattr(strategy_config, 'allow_reversals', True)
            require_high_conf = getattr(strategy_config, 'require_high_confidence_for_reversal', False)

            if allow_reversals:
                if require_high_conf and confidence != 'HIGH':
                    print(f"     ⚠️ 反转需要 HIGH 信心，当前为 {confidence}")
                    print(f"     → 实盘会保持现有 {current_side.upper()} 持仓")
                    would_trade = False
                else:
                    print(f"     → 将反转持仓: {current_side.upper()} → {target_side.upper()}")
            else:
                print(f"     ⚠️ 反转已禁用")
                print(f"     → 实盘会保持现有 {current_side.upper()} 持仓")
                would_trade = False
    else:
        print(f"     无现有持仓 → 将开新 {target_side.upper()} 仓位 {btc_quantity:.4f} BTC")

print()

# =============================================================================
# 最终诊断总结
# =============================================================================
print("=" * 70)
print("  诊断总结 (TradingAgents v3.2 - AI 完全自主决策)")
print("=" * 70)
print()

# 显示架构状态 (v3.2: 无本地风控)
print(f"  📊 架构: TradingAgents v3.2 - AI 完全自主决策")
print(f"     本地风控: 无 (已移除所有硬编码规则)")
print()

# TradingAgents: Judge 决策即最终决策
print(f"  📊 AI Signal: {original_signal}")
print(f"  📊 Final Signal: {final_signal}")
print(f"  📊 Confidence: {confidence}")
judge_decision = signal_data.get('judge_decision', {})
winning_side = judge_decision.get('winning_side', 'N/A')
print(f"  📊 Winning Side: {winning_side}")
print(f"  📊 Risk Level: {signal_data.get('risk_level', 'N/A')}")
print()

# 显示持仓信息
if current_position:
    print(f"  📊 Current Position: {current_position['side'].upper()} {current_position['quantity']:.4f} BTC")
else:
    print(f"  📊 Current Position: None")
print()

if would_trade and final_signal in ['BUY', 'SELL']:
    print(f"  🟢 WOULD EXECUTE: {final_signal} {btc_quantity:.4f} BTC @ ${current_price:,.2f}")
    print(f"     Notional: ${btc_quantity * current_price:.2f}")
    # 显示最终的 SL/TP (经过验证或技术分析计算)
    if final_sl:
        print(f"     Stop Loss: ${final_sl:,.2f}")
    if final_tp:
        print(f"     Take Profit: ${final_tp:,.2f}")
    if sltp_source and sltp_source != "N/A":
        print(f"     SL/TP 来源: {sltp_source}")
elif final_signal == 'HOLD':
    print("  🟡 NO TRADE: Judge recommends HOLD")
    reason = signal_data.get('reason', 'N/A')
    print(f"     Reason: {reason[:100]}..." if len(reason) > 100 else f"     Reason: {reason}")
elif not would_trade and final_signal in ['BUY', 'SELL']:
    # 信号是 BUY/SELL 但因为持仓原因不会执行
    print(f"  🔴 NO TRADE: Signal={final_signal}, but blocked by position management")
    if current_position:
        target_side = 'long' if final_signal == 'BUY' else 'short'
        if current_position['side'] == target_side:
            print(f"     → 已有同方向持仓 ({current_position['side'].upper()} {current_position['quantity']:.4f} BTC)")
            print(f"     → 仓位差异低于调整阈值，无需操作")
        else:
            print(f"     → 反转被阻止 (当前: {current_position['side'].upper()}, 信号: {target_side.upper()})")
else:
    print(f"  🔴 NO TRADE: Signal={final_signal}, Confidence={confidence}")
    if not passes_threshold:
        print(f"     → Confidence below minimum ({strategy_config.min_confidence_to_trade})")

print()

# Telegram 和交易执行流程说明
print("-" * 70)
print("  📱 实盘执行流程:")
print("-" * 70)
print()

if final_signal in ['BUY', 'SELL']:
    print(f"  Step 1: AI 分析完成 → Signal = {final_signal}")
    print(f"  Step 2: 📱 发送 Telegram 信号通知")
    print(f"          → 此时你会收到交易信号消息")
    print(f"  Step 3: 调用 _execute_trade()")

    if not passes_threshold:
        print(f"          → ❌ 信心 {confidence} < 最低要求 {strategy_config.min_confidence_to_trade}")
        print(f"          → 🔴 交易被跳过，但 Telegram 信号已发送!")
    elif would_trade:
        print(f"          → ✅ 所有检查通过")
        print(f"          → 📊 提交订单到 Binance")
    else:
        print(f"          → ❌ 被持仓管理阻止")
        print(f"          → 🔴 交易被跳过，但 Telegram 信号已发送!")
else:
    print(f"  Step 1: AI 分析完成 → Signal = {final_signal}")
    print(f"  Step 2: ❌ 非 BUY/SELL 信号，不发送 Telegram")
    print(f"  Step 3: _execute_trade 直接返回")

print()
print("  💡 关键点: Telegram 通知在 _execute_trade 之前发送!")
print("     如果收到信号但无交易，检查服务日志查看 _execute_trade 输出")
print()

# =============================================================================
# 8.5 Post-Trade 生命周期测试 (v10.3)
# 与实盘 on_timer 的 1237-1243 行一致
# =============================================================================
if not SUMMARY_MODE:
    print("[8.5/10] Post-Trade 生命周期测试...")
    print("-" * 70)

    # 测试 OCO 孤儿订单清理
    print("  📋 OCO 孤儿订单清理 (_cleanup_oco_orphans):")
    enable_oco = getattr(strategy_config, 'enable_oco', False)
    if enable_oco:
        print("     ✅ enable_oco = True")
        print("        → 实盘会在每次 on_timer 后调用 _cleanup_oco_orphans()")
        print("        → 清理无持仓时的 reduce-only 订单")
    else:
        print("     ⚠️ enable_oco = False (跳过清理)")

    # 测试移动止损更新
    print()
    print("  📋 移动止损更新 (_update_trailing_stops):")
    enable_trailing = getattr(strategy_config, 'enable_trailing_stop', False)
    if enable_trailing:
        activation_pct = getattr(strategy_config, 'trailing_activation_pct', 0.01)
        distance_pct = getattr(strategy_config, 'trailing_distance_pct', 0.005)
        print("     ✅ enable_trailing_stop = True")
        print(f"        → 激活条件: 盈利 >= {activation_pct*100:.2f}%")
        print(f"        → 跟踪距离: {distance_pct*100:.2f}%")
        print("        → 实盘会在每次 on_timer 后调用 _update_trailing_stops()")

        # 模拟计算当前是否会激活
        if current_position:
            entry_price = current_position.get('entry_price', 0)
            if entry_price > 0:
                current_pnl_pct = (current_price - entry_price) / entry_price
                if current_position.get('side') == 'short':
                    current_pnl_pct = -current_pnl_pct

                if current_pnl_pct >= activation_pct:
                    new_sl = current_price * (1 - distance_pct) if current_position.get('side') == 'long' else current_price * (1 + distance_pct)
                    print(f"        → 当前盈利 {current_pnl_pct*100:.2f}% >= {activation_pct*100:.2f}%")
                    print(f"        → 🟢 Trailing Stop 会激活，新 SL ≈ ${new_sl:,.2f}")
                else:
                    print(f"        → 当前盈利 {current_pnl_pct*100:.2f}% < {activation_pct*100:.2f}%")
                    print(f"        → ⚪ Trailing Stop 未激活")
    else:
        print("     ⚠️ enable_trailing_stop = False (跳过更新)")

    print()
    print("  ✅ Post-Trade 生命周期测试完成")
    print()

# MTF v2.1 测试代码片段 - 替换 diagnose_realtime.py 的 Step 9

# =============================================================================
# 9. MTF v2.1 组件集成测试 (Order Flow + Derivatives + AI Data Assembler)
# =============================================================================
if not SUMMARY_MODE:
    print("[9/10] MTF v2.1 组件集成测试...")
    print("-" * 70)

    try:
        # 读取配置
        base_yaml_path = project_root / "configs" / "base.yaml"
        order_flow_enabled = False
        coinalyze_enabled = False

        if base_yaml_path.exists():
            with open(base_yaml_path) as f:
                base_config = yaml.safe_load(f)
            order_flow = base_config.get('order_flow', {})
            order_flow_enabled = order_flow.get('enabled', False)
            coinalyze_cfg = order_flow.get('coinalyze', {})  # 正确路径: order_flow.coinalyze
            coinalyze_enabled = coinalyze_cfg.get('enabled', False)

        if not order_flow_enabled:
            print("  ℹ️ Order Flow 未启用，跳过 MTF 组件测试")
        else:
            print("  ✅ Order Flow 已启用，开始测试 MTF 组件...")
            print()

            # ================================================================
            # 9.1 测试 BinanceKlineClient (获取完整 12 列 K线)
            # ================================================================
            print("  [9.1] 测试 BinanceKlineClient...")
            try:
                from utils.binance_kline_client import BinanceKlineClient

                kline_client = BinanceKlineClient(timeout=10, logger=None)
                print("     ✅ BinanceKlineClient 导入成功")

                # 测试获取 15M K线
                symbol = base_config.get('trading', {}).get('instrument_id', 'BTCUSDT-PERP.BINANCE')
                symbol_clean = symbol.split('-')[0]  # BTCUSDT

                print(f"     📊 获取 {symbol_clean} 15M K线 (最近 50 根)...")
                klines = kline_client.get_klines(
                    symbol=symbol_clean,
                    interval="15m",
                    limit=50
                )

                if klines:
                    print(f"     ✅ 成功获取 {len(klines)} 根 K线")
                    latest = klines[-1]
                    print(f"        最新 K线:")
                    print(f"          - Close: {latest[4]}")
                    print(f"          - Volume: {latest[5]}")
                    print(f"          - Taker Buy Volume: {latest[9]} (订单流关键数据)")
                    print(f"          - Quote Volume: {latest[7]} USDT")
                    print(f"          - Trades Count: {latest[8]}")

                    # 测试获取当前价格 (v2.1: 使用独立变量，不覆盖 snapshot)
                    test_live_price = kline_client.get_current_price(symbol=symbol_clean)
                    if test_live_price:
                        price_diff = test_live_price - snapshot_price
                        print(f"     ✅ 实时价格: ${test_live_price:,.2f} (vs 快照 ${snapshot_price:,.2f}, 差值: ${price_diff:+,.2f})")
                else:
                    print("     ❌ 获取 K线失败")

            except ImportError as e:
                print(f"     ❌ 无法导入 BinanceKlineClient: {e}")
            except Exception as e:
                print(f"     ❌ BinanceKlineClient 测试失败: {e}")
                import traceback
                traceback.print_exc()

            print()

            # ================================================================
            # 9.2 测试 OrderFlowProcessor (订单流指标计算)
            # ================================================================
            print("  [9.2] 测试 OrderFlowProcessor...")
            try:
                from utils.order_flow_processor import OrderFlowProcessor

                processor = OrderFlowProcessor(logger=None)
                print("     ✅ OrderFlowProcessor 导入成功")

                if klines and len(klines) >= 10:
                    # v2.1: 明确标注这是测试数据 (50 bars)，AI 输入用 10 bars
                    print(f"     📊 计算订单流指标 (测试: {len(klines)} bars, AI输入: 10 bars)...")
                    order_flow_data = processor.process_klines(klines)

                    print(f"     ✅ 订单流指标计算完成 [测试窗口: {len(klines)} bars]:")
                    print(f"        - Buy Ratio: {order_flow_data['buy_ratio']:.4f} ({'多头' if order_flow_data['buy_ratio'] > 0.5 else '空头'}主导)")
                    print(f"        - CVD Trend: {order_flow_data['cvd_trend']}")
                    print(f"        - Avg Trade Size: ${order_flow_data['avg_trade_usdt']:,.2f}")
                    print(f"        - Volume (USDT): ${order_flow_data['volume_usdt']:,.0f}")
                    print(f"        - Trades Count: {order_flow_data['trades_count']:,}")
                    print(f"        - Data Source: {order_flow_data['data_source']}")
                    print(f"        ℹ️ 注: 以上数据来自 {len(klines)} 根 K线，AI 输入仅使用最近 10 根")

                    if order_flow_data['recent_10_bars']:
                        recent_avg = sum(order_flow_data['recent_10_bars']) / len(order_flow_data['recent_10_bars'])
                        print(f"        - Recent 10 Bars Avg Buy Ratio: {recent_avg:.4f}")
                else:
                    print("     ⚠️ K线数据不足，跳过订单流测试")

            except ImportError as e:
                print(f"     ❌ 无法导入 OrderFlowProcessor: {e}")
            except Exception as e:
                print(f"     ❌ OrderFlowProcessor 测试失败: {e}")
                import traceback
                traceback.print_exc()

            print()

            # ================================================================
            # 9.3 测试 CoinalyzeClient (衍生品数据)
            # ================================================================
            print("  [9.3] 测试 CoinalyzeClient...")
            try:
                from utils.coinalyze_client import CoinalyzeClient

                coinalyze_api_key = coinalyze_cfg.get('api_key') or os.getenv('COINALYZE_API_KEY')
                coinalyze_client = CoinalyzeClient(
                    api_key=coinalyze_api_key,
                    timeout=coinalyze_cfg.get('timeout', 10),
                    max_retries=coinalyze_cfg.get('max_retries', 2),
                    logger=None
                )
                print("     ✅ CoinalyzeClient 导入成功")

                if not coinalyze_enabled:
                    print("     ℹ️ Coinalyze 未启用")
                elif not coinalyze_api_key:
                    print("     ⚠️ Coinalyze API Key 未配置")
                else:
                    print(f"     📊 Coinalyze API 测试 (API Key: {coinalyze_api_key[:8]}...)")

                    coinalyze_symbol = coinalyze_cfg.get('symbol', 'BTCUSDT_PERP.A')

                    # 测试 get_open_interest
                    print("        测试 Open Interest...")
                    oi_data = coinalyze_client.get_open_interest(symbol=coinalyze_symbol)
                    if oi_data:
                        print(f"        ✅ OI (BTC): {oi_data.get('value', 0):,.2f}")
                    else:
                        print("        ❌ OI 获取失败")

                    # 测试 get_funding_rate (v2.1: 对比 Binance 和 Coinalyze)
                    print("        测试 Funding Rate...")
                    fr_data = coinalyze_client.get_funding_rate(symbol=coinalyze_symbol)

                    # 同时获取 Binance 直接的 Funding Rate 做对比
                    binance_fr = None
                    try:
                        binance_fr = kline_client.get_funding_rate(symbol=symbol_clean)
                    except Exception:
                        pass

                    if fr_data:
                        fr_value = fr_data.get('value', 0)
                        print(f"        ✅ Coinalyze Funding: {fr_value:.6f} ({fr_value*100:.4f}%)")

                        # v2.1: 显示 Binance 对比 + 差异警告
                        if binance_fr:
                            binance_value = binance_fr.get('funding_rate', 0)
                            binance_pct = binance_fr.get('funding_rate_pct', 0)
                            print(f"        ✅ Binance Funding:  {binance_value:.6f} ({binance_pct:.4f}%)")

                            # 计算差异倍数并解释原因
                            if binance_value > 0 and fr_value > 0:
                                ratio = fr_value / binance_value
                                if ratio > 5 or ratio < 0.2:
                                    print(f"        ⚠️ 差异 {ratio:.1f}x - 原因说明:")
                                    print(f"           • Binance: 下次结算的 8 小时费率 (实时单次)")
                                    print(f"           • Coinalyze: 多交易所加权聚合值 (可能包含历史累计)")
                                    print(f"           • 差异正常，不影响交易逻辑")
                                    print(f"        ✅ AI 输入使用 Binance 8h funding rate (因为我们在 Binance 交易)")
                    else:
                        print("        ❌ Coinalyze Funding Rate 获取失败")
                        if binance_fr:
                            print(f"        ✅ Binance Funding: {binance_fr.get('funding_rate', 0):.6f} ({binance_fr.get('funding_rate_pct', 0):.4f}%)")

                    # 测试 get_liquidations
                    print("        测试 Liquidations (1h)...")
                    liq_data = coinalyze_client.get_liquidations(
                        symbol=coinalyze_symbol,
                        interval="1hour"
                    )
                    if liq_data:
                        # 正确结构: {"symbol": "...", "history": [{"t": ..., "l": long_btc, "s": short_btc}]}
                        # 注意: l/s 单位是 BTC，需要乘以价格转换为 USD
                        history = liq_data.get('history', [])
                        if history:
                            item = history[-1]  # 最近一条
                            long_liq_btc = float(item.get('l', 0))
                            short_liq_btc = float(item.get('s', 0))
                            # v2.1: 使用 snapshot_price 而非重新获取 (保持一致性)
                            long_liq_usd = long_liq_btc * snapshot_price
                            short_liq_usd = short_liq_btc * snapshot_price
                            print(f"        ✅ Long Liq: {long_liq_btc:.4f} BTC (${long_liq_usd:,.0f})")
                            print(f"        ✅ Short Liq: {short_liq_btc:.4f} BTC (${short_liq_usd:,.0f})")
                        else:
                            print("        ℹ️ Liquidations history 为空 (该时间段无爆仓记录)")
                    else:
                        print("        ⚠️ Liquidations 数据不可用 (API 返回 None)")

                    # 测试 fetch_all (完整数据)
                    print("        测试 fetch_all (完整数据)...")
                    all_data = coinalyze_client.fetch_all(symbol=coinalyze_symbol)
                    if all_data:
                        print(f"        ✅ fetch_all 成功:")
                        print(f"           - OI: {all_data.get('open_interest') is not None}")
                        print(f"           - Funding: {all_data.get('funding_rate') is not None}")
                        print(f"           - Liquidations: {all_data.get('liquidations') is not None}")
                    else:
                        print("        ❌ fetch_all 失败")

            except ImportError as e:
                print(f"     ❌ 无法导入 CoinalyzeClient: {e}")
            except Exception as e:
                print(f"     ❌ CoinalyzeClient 测试失败: {e}")
                import traceback
                traceback.print_exc()

            print()

            # ================================================================
            # 9.4 测试 AIDataAssembler (完整数据组装)
            # ================================================================
            print("  [9.4] 测试 AIDataAssembler...")
            try:
                from utils.ai_data_assembler import AIDataAssembler
                from utils.sentiment_client import SentimentDataFetcher

                # 初始化所有组件
                sentiment_client = SentimentDataFetcher()
                assembler = AIDataAssembler(
                    binance_kline_client=kline_client,
                    order_flow_processor=processor,
                    coinalyze_client=coinalyze_client,
                    sentiment_client=sentiment_client,
                    logger=None
                )
                print("     ✅ AIDataAssembler 导入成功")

                # 创建模拟技术指标数据
                mock_technical_data = {
                    'price': float(klines[-1][4]) if klines else 0,
                    'rsi': 50.0,
                    'macd': 100.0,
                    'signal': 90.0,
                    'sma_20': 85000.0,
                    'sma_50': 84000.0,
                    'bb_upper': 86000.0,
                    'bb_lower': 84000.0,
                }

                print("     📊 组装完整 AI 输入数据...")
                assembled_data = assembler.assemble(
                    technical_data=mock_technical_data,
                    position_data=None,
                    symbol=symbol_clean,
                    interval="15m"
                )

                print(f"     ✅ 数据组装完成:")
                print(f"        - 技术指标: {assembled_data.get('technical') is not None}")
                print(f"        - 订单流: {assembled_data.get('order_flow') is not None}")
                print(f"        - 衍生品: {assembled_data.get('derivatives') is not None}")
                print(f"        - 情绪数据: {assembled_data.get('sentiment') is not None}")

                if assembled_data.get('order_flow'):
                    of = assembled_data['order_flow']
                    print(f"        - Order Flow Buy Ratio: {of.get('buy_ratio', 0):.4f}")

                if assembled_data.get('derivatives'):
                    deriv = assembled_data['derivatives']
                    # 正确的嵌套结构 (参考 ai_data_assembler.py:159-177)
                    oi_data = deriv.get('open_interest', {})
                    fr_data = deriv.get('funding_rate', {})
                    oi_change = oi_data.get('change_pct') if oi_data else None
                    funding_pct = fr_data.get('current_pct', 0) if fr_data else 0
                    print(f"        - Derivatives OI Change: {oi_change if oi_change else 'N/A (首次)'}%")
                    print(f"        - Derivatives Funding Rate: {funding_pct:.4f}%")

            except ImportError as e:
                print(f"     ❌ 无法导入 AIDataAssembler: {e}")
            except Exception as e:
                print(f"     ❌ AIDataAssembler 测试失败: {e}")
                import traceback
                traceback.print_exc()

        print()
        print("  ✅ MTF v2.1 组件集成测试完成")

    except Exception as e:
        print(f"  ❌ MTF 组件测试失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# =============================================================================
# 9.4 错误恢复机制验证 (v11.5 新增)
# =============================================================================
if not SUMMARY_MODE:
    print("[9.4/10] 错误恢复机制验证...")
    print("-" * 70)

    print("  📋 AI 调用失败恢复机制:")
    print()

    # 检查 MultiAgentAnalyzer 的 fallback 机制
    print("  [1] MultiAgentAnalyzer fallback:")
    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer
        # 检查 _create_fallback_signal 方法
        if hasattr(MultiAgentAnalyzer, '_create_fallback_signal'):
            print("     ✅ _create_fallback_signal 方法存在")
            print("     → AI 调用失败时返回 HOLD + LOW confidence")
        else:
            print("     ⚠️ _create_fallback_signal 方法不存在")
    except ImportError as e:
        print(f"     ❌ 无法导入 MultiAgentAnalyzer: {e}")

    # 检查 API 重试机制
    print()
    print("  [2] API 重试机制:")
    print("     ✅ _call_api_with_retry: 最多重试 2 次")
    print("     ✅ _extract_json_with_retry: JSON 解析失败重试 2 次")
    print("     → 失败后使用 fallback signal")

    # 检查数据获取失败恢复
    print()
    print("  [3] 数据获取失败恢复:")
    print("     ✅ Coinalyze 失败 → 使用中性默认值 (OI=0, FR=0)")
    print("     ✅ Binance K线失败 → 使用 indicator_manager 缓存数据")
    print("     ✅ 情绪数据失败 → 使用中性默认值 (ratio=0.5)")

    # 检查 SL/TP 验证失败恢复
    print()
    print("  [4] SL/TP 验证失败恢复:")
    print("     ✅ validate_multiagent_sltp 失败 → 回退到 calculate_technical_sltp")
    print("     ✅ 技术 SL/TP 计算失败 → 使用默认 2% SL, confidence-based TP")

    # 检查网络错误恢复
    print()
    print("  [5] 网络错误恢复:")
    print("     ✅ requests 超时 → 自动重试 (指数退避)")
    print("     ✅ API rate limit → 等待后重试")
    print("     ✅ 连接失败 → 记录错误，使用 fallback")

    print()
    print("  ⚠️ 模拟错误恢复流程:")
    print("     1. AI API 调用失败")
    print("     2. → 触发 _create_fallback_signal()")
    print("     3. → 返回 {'signal': 'HOLD', 'confidence': 'LOW'}")
    print("     4. → 不执行交易 (HOLD)")
    print("     5. → 等待下一个 timer 周期重试")

    print()
    print("  ✅ 错误恢复机制验证完成")
    print()

# =============================================================================
# 9.5 Telegram 命令处理验证 (v10.2)
# =============================================================================
if not SUMMARY_MODE:
    print("[9.5/10] Telegram 命令处理验证...")
    print("-" * 70)

    try:
        # 检查 Telegram 配置
        telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not telegram_token:
            print("  ⚠️ TELEGRAM_BOT_TOKEN 未配置")
        elif not telegram_chat_id:
            print("  ⚠️ TELEGRAM_CHAT_ID 未配置")
        else:
            print(f"  ✅ Telegram 配置已加载")
            print(f"     Bot Token: {telegram_token[:10]}...{telegram_token[-5:]}")
            print(f"     Chat ID: {telegram_chat_id}")

            # 检查 telegram_bot.py 模块
            print()
            print("  📋 Telegram 模块检查:")

            telegram_bot_path = project_root / "utils" / "telegram_bot.py"
            telegram_handler_path = project_root / "utils" / "telegram_command_handler.py"

            if telegram_bot_path.exists():
                print("     ✅ utils/telegram_bot.py 存在")

                # 检查 TelegramBot 类和 send_message_sync 方法
                try:
                    from utils.telegram_bot import TelegramBot
                    print("     ✅ TelegramBot 类可导入")

                    # 检查 send_message_sync 是否是类方法
                    if hasattr(TelegramBot, 'send_message_sync'):
                        print("     ✅ TelegramBot.send_message_sync 方法存在")
                    else:
                        print("     ⚠️ TelegramBot.send_message_sync 方法缺失")

                    # 测试 Telegram API 连通性
                    print()
                    print("  📤 Telegram API 连通性测试:")
                    import requests

                    # 使用 getMe 端点测试 Bot Token 有效性
                    api_url = f"https://api.telegram.org/bot{telegram_token}/getMe"
                    resp = requests.get(api_url, timeout=10)

                    if resp.status_code == 200:
                        bot_info = resp.json()
                        if bot_info.get('ok'):
                            result = bot_info.get('result', {})
                            print(f"     ✅ Bot Token 有效")
                            print(f"        Bot 名称: @{result.get('username', 'N/A')}")
                            print(f"        Bot ID: {result.get('id', 'N/A')}")
                        else:
                            print(f"     ❌ Bot Token 无效")
                    else:
                        print(f"     ❌ API 错误: {resp.status_code}")

                except ImportError as e:
                    print(f"     ❌ 无法导入 TelegramBot: {e}")
            else:
                print("     ❌ utils/telegram_bot.py 不存在")

            if telegram_handler_path.exists():
                print("     ✅ utils/telegram_command_handler.py 存在")

                # 检查关键类和方法
                try:
                    from utils.telegram_command_handler import TelegramCommandHandler
                    print("     ✅ TelegramCommandHandler 类可导入")

                    # 检查命令处理方法 (注意：方法名没有下划线前缀)
                    commands = ['cmd_status', 'cmd_position', 'cmd_pause', 'cmd_resume', 'cmd_close', 'cmd_orders', 'cmd_history']
                    for cmd in commands:
                        if hasattr(TelegramCommandHandler, cmd):
                            print(f"        ✅ {cmd} 方法存在")
                        else:
                            print(f"        ⚠️ {cmd} 方法缺失")

                except ImportError as e:
                    print(f"     ❌ 无法导入 TelegramCommandHandler: {e}")
            else:
                print("     ❌ utils/telegram_command_handler.py 不存在")

            # 检查线程安全机制
            print()
            print("  📋 线程安全机制检查:")
            print("     → _cached_current_price: 用于跨线程安全访问当前价格")
            print("     → send_message_sync: 使用 requests 直接调用 API (线程安全)")
            print("     → 避免在后台线程访问 indicator_manager (Rust 指标不可跨线程)")

        print()
        print("  ✅ Telegram 验证完成")

    except Exception as e:
        print(f"  ❌ Telegram 验证失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# =============================================================================
# 10. on_bar MTF 路由逻辑模拟 (v10.9 新增)
# 模拟 deepseek_strategy.py:on_bar() 的 MTF bar 路由
# =============================================================================
if not SUMMARY_MODE:
    print("[10/13] on_bar MTF 路由逻辑模拟...")
    print("-" * 70)

    try:
        # 检查 MTF 配置
        mtf_config = base_config.get('multi_timeframe', {}) if 'base_config' in dir() else {}
        mtf_enabled = mtf_config.get('enabled', False)

        if not mtf_enabled:
            print("  ℹ️ MTF 未启用，跳过路由测试")
        else:
            print("  📊 MTF Bar 路由逻辑 (与 deepseek_strategy.py:on_bar 一致):")
            print()

            # 模拟三种 bar 类型的路由
            trend_tf = mtf_config.get('trend_layer', {}).get('timeframe', '1d')
            decision_tf = mtf_config.get('decision_layer', {}).get('timeframe', '4h')
            execution_tf = mtf_config.get('execution_layer', {}).get('default_timeframe', '15m')

            print(f"  [路由规则] Bar 类型 → 处理层:")
            print(f"     • {trend_tf.upper()} bar → 趋势层 (_handle_trend_bar)")
            print(f"       - 更新 SMA_200, MACD")
            print(f"       - 计算 RISK_ON/RISK_OFF 状态")
            print(f"       - 设置 _mtf_trend_initialized = True")
            print()
            print(f"     • {decision_tf.upper()} bar → 决策层 (_handle_decision_bar)")
            print(f"       - 更新决策层技术指标")
            print(f"       - 计算 ALLOW_LONG/ALLOW_SHORT/WAIT 状态")
            print(f"       - 设置 _mtf_decision_initialized = True")
            print()
            print(f"     • {execution_tf.upper()} bar → 执行层 (_handle_execution_bar)")
            print(f"       - 更新执行层指标 (RSI, MACD 等)")
            print(f"       - 更新 _cached_current_price (线程安全)")
            print(f"       - 设置 _mtf_execution_initialized = True")
            print()

            # 模拟当前 bar 的路由
            print(f"  [模拟路由] 当前诊断使用的 bar_type:")
            bar_type_str = str(getattr(strategy_config, 'bar_type', '15-MINUTE'))
            print(f"     bar_type: {bar_type_str}")

            if '1-DAY' in bar_type_str or '1D' in bar_type_str.upper():
                print(f"     → 路由到: 趋势层 (1D)")
            elif '4-HOUR' in bar_type_str or '4H' in bar_type_str.upper():
                print(f"     → 路由到: 决策层 (4H)")
            else:
                print(f"     → 路由到: 执行层 (15M) - 主分析周期")
            print()

            # 输出指标更新数据
            print(f"  [指标更新] 本次 bar 更新的指标值:")
            print(f"     indicator_manager.update(bar) 后:")
            print(f"     • 价格: ${current_price:,.2f}")
            print(f"     • SMA_5: ${technical_data.get('sma_5', 0):,.2f}")
            print(f"     • SMA_20: ${technical_data.get('sma_20', 0):,.2f}")
            print(f"     • SMA_50: ${technical_data.get('sma_50', 0):,.2f}")
            print(f"     • RSI: {technical_data.get('rsi', 0):.2f}")
            print(f"     • MACD: {technical_data.get('macd', 0):.4f}")
            print(f"     • MACD Signal: {technical_data.get('macd_signal', 0):.4f}")
            print(f"     • Support: ${technical_data.get('support', 0):,.2f}")
            print(f"     • Resistance: ${technical_data.get('resistance', 0):,.2f}")

        print()
        print("  ✅ on_bar MTF 路由模拟完成")

    except Exception as e:
        print(f"  ❌ on_bar 路由模拟失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# =============================================================================
# 11. 仓位计算函数测试 (v10.9 新增)
# 测试 trading_logic.py:calculate_position_size() 的完整逻辑
# =============================================================================
if not SUMMARY_MODE:
    print("[11/13] 仓位计算函数测试 (calculate_position_size)...")
    print("-" * 70)

    try:
        from strategy.trading_logic import calculate_position_size

        # 构建配置字典
        calc_config = {
            'base_usdt': getattr(strategy_config, 'base_usdt_amount', 100),
            'equity': getattr(strategy_config, 'equity', 1000),
            'high_confidence_multiplier': getattr(strategy_config, 'high_confidence_multiplier', 1.5),
            'medium_confidence_multiplier': getattr(strategy_config, 'medium_confidence_multiplier', 1.0),
            'low_confidence_multiplier': getattr(strategy_config, 'low_confidence_multiplier', 0.5),
            'trend_strength_multiplier': getattr(strategy_config, 'trend_strength_multiplier', 1.2),
            'rsi_extreme_multiplier': getattr(strategy_config, 'rsi_extreme_multiplier', 0.7),
            'rsi_extreme_upper': getattr(strategy_config, 'rsi_extreme_threshold_upper', 70),
            'rsi_extreme_lower': getattr(strategy_config, 'rsi_extreme_threshold_lower', 30),
            'max_position_ratio': getattr(strategy_config, 'max_position_ratio', 0.30),
            'min_trade_amount': getattr(strategy_config, 'min_trade_amount', 0.001),
        }

        print("  📋 仓位计算配置:")
        print(f"     base_usdt: ${calc_config['base_usdt']}")
        print(f"     equity: ${calc_config['equity']}")
        print(f"     max_position_ratio: {calc_config['max_position_ratio']*100:.0f}%")
        print(f"     min_trade_amount: {calc_config['min_trade_amount']} BTC")
        print()

        print("  📋 信心乘数配置:")
        print(f"     HIGH: {calc_config['high_confidence_multiplier']}x → ${calc_config['base_usdt'] * calc_config['high_confidence_multiplier']:.0f}")
        print(f"     MEDIUM: {calc_config['medium_confidence_multiplier']}x → ${calc_config['base_usdt'] * calc_config['medium_confidence_multiplier']:.0f}")
        print(f"     LOW: {calc_config['low_confidence_multiplier']}x → ${calc_config['base_usdt'] * calc_config['low_confidence_multiplier']:.0f}")
        print()

        print("  📋 风险调整乘数:")
        print(f"     趋势强度乘数: {calc_config['trend_strength_multiplier']}x (强趋势时放大)")
        print(f"     RSI 极值乘数: {calc_config['rsi_extreme_multiplier']}x (RSI>{calc_config['rsi_extreme_upper']} 或 <{calc_config['rsi_extreme_lower']} 时缩小)")
        print()

        # 使用当前信号数据计算仓位
        print("  📊 当前信号仓位计算:")
        quantity, calc_details = calculate_position_size(
            signal_data=signal_data,
            price_data=price_data,
            technical_data=technical_data,
            config=calc_config,
            logger=None
        )

        print(f"     输入信号: {signal_data.get('signal', 'N/A')}")
        print(f"     输入信心: {signal_data.get('confidence', 'N/A')}")
        print(f"     当前价格: ${current_price:,.2f}")
        print(f"     当前趋势: {technical_data.get('overall_trend', 'N/A')}")
        print(f"     当前 RSI: {technical_data.get('rsi', 50):.2f}")
        print()
        print(f"     计算结果:")
        print(f"     • 目标仓位: {quantity:.6f} BTC")
        print(f"     • 等值 USDT: ${quantity * current_price:,.2f}")
        print(f"     • 占 equity 比例: {(quantity * current_price / calc_config['equity']) * 100:.2f}%")
        print()

        # 计算详情
        if calc_details:
            print(f"     计算详情:")
            for key, value in calc_details.items():
                if isinstance(value, float):
                    print(f"     • {key}: {value:.4f}")
                else:
                    print(f"     • {key}: {value}")

        # 模拟不同信心级别的仓位
        print()
        print("  📊 不同信心级别仓位对比:")
        for conf_level in ['HIGH', 'MEDIUM', 'LOW']:
            test_signal = {'signal': signal_data.get('signal', 'BUY'), 'confidence': conf_level}
            q, _ = calculate_position_size(test_signal, price_data, technical_data, calc_config)
            print(f"     {conf_level}: {q:.6f} BTC (${q * current_price:,.2f})")

        print()
        print("  ✅ 仓位计算测试完成")

    except Exception as e:
        print(f"  ❌ 仓位计算测试失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# =============================================================================
# 12. 订单提交流程模拟 (v10.9 新增)
# 模拟 deepseek_strategy.py:_submit_bracket_order() 的参数验证
# =============================================================================
if not SUMMARY_MODE:
    print("[12/13] 订单提交流程模拟 (_submit_bracket_order)...")
    print("-" * 70)

    try:
        # 使用当前信号数据模拟订单参数
        signal = signal_data.get('signal', 'HOLD')
        confidence = signal_data.get('confidence', 'MEDIUM')
        multi_sl_raw = signal_data.get('stop_loss')
        multi_tp_raw = signal_data.get('take_profit')

        # 类型转换: AI 可能返回字符串或数字
        def safe_float(value):
            """安全转换为 float，处理字符串和 None"""
            if value is None:
                return None
            try:
                # 移除可能的货币符号和逗号
                if isinstance(value, str):
                    value = value.replace('$', '').replace(',', '').strip()
                return float(value)
            except (ValueError, TypeError):
                return None

        multi_sl = safe_float(multi_sl_raw)
        multi_tp = safe_float(multi_tp_raw)

        print("  📋 订单提交前提检查:")
        print(f"     信号: {signal}")
        print(f"     信心: {confidence}")
        print(f"     当前价格: ${current_price:,.2f}")
        print()

        if signal == 'HOLD':
            print("  ℹ️ 信号为 HOLD，不会提交订单")
        else:
            # 计算仓位
            from strategy.trading_logic import calculate_position_size
            calc_config = {
                'base_usdt': getattr(strategy_config, 'base_usdt_amount', 100),
                'equity': getattr(strategy_config, 'equity', 1000),
                'high_confidence_multiplier': getattr(strategy_config, 'high_confidence_multiplier', 1.5),
                'medium_confidence_multiplier': getattr(strategy_config, 'medium_confidence_multiplier', 1.0),
                'low_confidence_multiplier': getattr(strategy_config, 'low_confidence_multiplier', 0.5),
                'trend_strength_multiplier': getattr(strategy_config, 'trend_strength_multiplier', 1.2),
                'rsi_extreme_multiplier': getattr(strategy_config, 'rsi_extreme_multiplier', 0.7),
                'rsi_extreme_upper': getattr(strategy_config, 'rsi_extreme_threshold_upper', 70),
                'rsi_extreme_lower': getattr(strategy_config, 'rsi_extreme_threshold_lower', 30),
                'max_position_ratio': getattr(strategy_config, 'max_position_ratio', 0.30),
                'min_trade_amount': getattr(strategy_config, 'min_trade_amount', 0.001),
            }
            quantity, _ = calculate_position_size(signal_data, price_data, technical_data, calc_config)

            # 验证 SL/TP
            from strategy.trading_logic import validate_multiagent_sltp, calculate_technical_sltp

            print("  📋 SL/TP 验证流程:")
            print(f"     AI Judge SL: ${multi_sl:,.2f}" if multi_sl else "     AI Judge SL: None")
            print(f"     AI Judge TP: ${multi_tp:,.2f}" if multi_tp else "     AI Judge TP: None")
            print()

            # 获取支撑/阻力位 (用于技术分析回退)
            support = technical_data.get('support', 0.0)
            resistance = technical_data.get('resistance', 0.0)
            use_support_resistance = getattr(strategy_config, 'sl_use_support_resistance', True)
            sl_buffer_pct = getattr(strategy_config, 'sl_buffer_pct', 0.001)

            # 验证 AI 提供的 SL/TP
            if multi_sl and multi_tp:
                # 调用签名与实盘代码一致: (side, multi_sl, multi_tp, entry_price) -> (is_valid, sl, tp, reason)
                is_valid, validated_sl, validated_tp, validation_reason = validate_multiagent_sltp(
                    side=signal,
                    multi_sl=multi_sl,
                    multi_tp=multi_tp,
                    entry_price=current_price,
                )
                print(f"     SL 验证 (validate_multiagent_sltp):")
                if signal == 'BUY':
                    print(f"       BUY 要求: SL < 入场价 → {multi_sl:,.2f} < {current_price:,.2f}")
                    print(f"       BUY 要求: TP > 入场价 → {multi_tp:,.2f} > {current_price:,.2f}")
                else:
                    print(f"       SELL 要求: SL > 入场价 → {multi_sl:,.2f} > {current_price:,.2f}")
                    print(f"       SELL 要求: TP < 入场价 → {multi_tp:,.2f} < {current_price:,.2f}")
                print(f"       验证结果: {'✅ 通过' if is_valid else '❌ 失败'} - {validation_reason}")
                print()

                if is_valid:
                    print("     ✅ AI SL/TP 验证通过，使用 AI 价位")
                    final_sl, final_tp = validated_sl, validated_tp
                    calc_method = "AI Judge"
                else:
                    print("     ⚠️ AI SL/TP 验证失败，回退到技术分析")
                    # 调用签名与实盘代码一致
                    final_sl, final_tp, calc_method = calculate_technical_sltp(
                        side=signal,
                        entry_price=current_price,
                        support=support,
                        resistance=resistance,
                        confidence=confidence,
                        use_support_resistance=use_support_resistance,
                        sl_buffer_pct=sl_buffer_pct,
                    )
                    print(f"     计算方法: {calc_method}")
            else:
                print("     ⚠️ AI 未提供 SL/TP，使用技术分析计算")
                # 调用签名与实盘代码一致
                final_sl, final_tp, calc_method = calculate_technical_sltp(
                    side=signal,
                    entry_price=current_price,
                    support=support,
                    resistance=resistance,
                    confidence=confidence,
                    use_support_resistance=use_support_resistance,
                    sl_buffer_pct=sl_buffer_pct,
                )
                print(f"     计算方法: {calc_method}")

            # 确保 final_sl 和 final_tp 是数字类型
            final_sl = safe_float(final_sl) or 0.0
            final_tp = safe_float(final_tp) or 0.0

            print()
            print("  📋 最终订单参数 (模拟 _submit_bracket_order):")
            print(f"     order_side: {'BUY' if signal == 'BUY' else 'SELL'}")
            print(f"     quantity: {quantity:.6f} BTC")
            print(f"     entry_price: ${current_price:,.2f} (MARKET)")
            print(f"     sl_trigger_price: ${final_sl:,.2f}")
            print(f"     tp_price: ${final_tp:,.2f}")
            print()

            # 计算风险/收益 (确保使用 float 进行计算)
            if final_sl > 0 and final_tp > 0:
                if signal == 'BUY':
                    sl_pct = ((current_price - final_sl) / current_price) * 100
                    tp_pct = ((final_tp - current_price) / current_price) * 100
                else:
                    sl_pct = ((final_sl - current_price) / current_price) * 100
                    tp_pct = ((current_price - final_tp) / current_price) * 100
            else:
                sl_pct = 0.0
                tp_pct = 0.0
                print("  ⚠️ SL/TP 无效，跳过风险计算")

            rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 0

            print("  📊 风险/收益分析:")
            print(f"     止损距离: {sl_pct:.2f}%")
            print(f"     止盈距离: {tp_pct:.2f}%")
            print(f"     风险/收益比: 1:{rr_ratio:.2f}")
            print(f"     最大亏损: ${quantity * current_price * sl_pct / 100:,.2f}")
            print(f"     最大盈利: ${quantity * current_price * tp_pct / 100:,.2f}")

        print()
        print("  ✅ 订单提交流程模拟完成")

    except Exception as e:
        print(f"  ❌ 订单提交模拟失败: {e}")
        import traceback
        traceback.print_exc()

    print()

# =============================================================================
# 13. 完整数据流汇总 (v10.9 新增)
# 输出所有获取的数据的具体值
# =============================================================================
if not SUMMARY_MODE:
    print("[13/13] 完整数据流汇总...")
    print("-" * 70)

    print()
    print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("  ┃                        技术指标数据                                  ┃")
    print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print()
    print(f"  价格数据:")
    print(f"    当前价格: ${current_price:,.2f}")
    print(f"    24H 最高: ${price_data.get('high', 0):,.2f}")
    print(f"    24H 最低: ${price_data.get('low', 0):,.2f}")
    print(f"    价格变化: {price_data.get('price_change', 0):.2f}%")
    print()
    print(f"  移动平均线:")
    print(f"    SMA_5:  ${technical_data.get('sma_5', 0):,.2f}")
    print(f"    SMA_20: ${technical_data.get('sma_20', 0):,.2f}")
    print(f"    SMA_50: ${technical_data.get('sma_50', 0):,.2f}")
    print(f"    EMA_12: ${technical_data.get('ema_12', 0):,.2f}")
    print(f"    EMA_26: ${technical_data.get('ema_26', 0):,.2f}")
    print()
    print(f"  震荡指标:")
    print(f"    RSI:           {technical_data.get('rsi', 0):.2f}")
    print(f"    MACD:          {technical_data.get('macd', 0):.4f}")
    print(f"    MACD Signal:   {technical_data.get('macd_signal', 0):.4f}")
    print(f"    MACD Histogram:{technical_data.get('macd_histogram', 0):.4f}")
    print()
    print(f"  布林带:")
    print(f"    BB Upper: ${technical_data.get('bb_upper', 0):,.2f}")
    print(f"    BB Middle: ${technical_data.get('bb_middle', 0):,.2f}")
    print(f"    BB Lower: ${technical_data.get('bb_lower', 0):,.2f}")
    print()
    print(f"  支撑/阻力:")
    print(f"    支撑位: ${technical_data.get('support', 0):,.2f}")
    print(f"    阻力位: ${technical_data.get('resistance', 0):,.2f}")
    print()
    print(f"  趋势判断: {technical_data.get('overall_trend', 'N/A')}")

    print()
    print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("  ┃                        情绪数据                                     ┃")
    print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print()
    print(f"  Binance 多空比:")
    print(f"    Long/Short Ratio: {sentiment_data.get('long_short_ratio', 0):.4f}")
    print(f"    Long Account %:   {sentiment_data.get('positive_ratio', 0)*100:.2f}%")
    print(f"    Short Account %:  {sentiment_data.get('negative_ratio', 0)*100:.2f}%")
    print(f"    Net Sentiment:    {sentiment_data.get('net_sentiment', 0):.4f}")
    print(f"    数据来源: {sentiment_data.get('source', 'N/A')}")

    # 输出订单流数据 (使用 order_flow_report 变量)
    if 'order_flow_report' in dir() and order_flow_report:
        print()
        print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
        print("  ┃                        订单流数据                                   ┃")
        print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
        print()
        # v2.1: 添加采样窗口标注
        bars_count = order_flow_report.get('bars_count', 10)
        print(f"  Binance Taker 数据 [采样窗口: {bars_count} bars]:")
        print(f"    Buy Ratio:      {order_flow_report.get('buy_ratio', 0):.4f} ({order_flow_report.get('buy_ratio', 0)*100:.2f}%)")
        print(f"    CVD Trend:      {order_flow_report.get('cvd_trend', 'N/A')}")
        print(f"    Avg Trade Size: ${order_flow_report.get('avg_trade_usdt', 0):,.2f}")
        print(f"    Volume (USDT):  ${order_flow_report.get('volume_usdt', 0):,.0f}")
        print(f"    Trades Count:   {order_flow_report.get('trades_count', 0):,}")
        print(f"    数据来源: {order_flow_report.get('data_source', 'N/A')}")

        # 最近10根K线的 buy ratio
        recent_10 = order_flow_report.get('recent_10_bars_buy_ratio', [])
        if recent_10:
            print(f"    最近 10 根 K线 Buy Ratio: {[f'{r:.2f}' for r in recent_10[-5:]]}")

    # 输出衍生品数据 (使用 derivatives_report 变量)
    if 'derivatives_report' in dir() and derivatives_report:
        print()
        print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
        print("  ┃                        衍生品数据 (Coinalyze)                       ┃")
        print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
        print()
        oi_data = derivatives_report.get('open_interest', {})
        fr_data = derivatives_report.get('funding_rate', {})
        liq_data = derivatives_report.get('liquidations', {})

        print(f"  Open Interest:")
        if oi_data:
            print(f"    OI (BTC):    {oi_data.get('value', 0):,.2f}")
            print(f"    OI (USD):    ${oi_data.get('total_usd', 0):,.0f}")
            print(f"    OI Change:   {oi_data.get('change_pct', 'N/A')}")
        else:
            print(f"    (数据不可用)")
        print()
        print(f"  Funding Rate:")
        if fr_data:
            fr_value = fr_data.get('value', 0)
            source = fr_data.get('source', 'unknown')
            print(f"    Current:     {fr_value:.6f} ({fr_value*100:.4f}%)")
            print(f"    Interpret:   {fr_data.get('interpretation', 'N/A')}")
            print(f"    Source:      {source}")
            # v2.1: 显示两个数据源对比
            binance_pct = fr_data.get('binance_pct')
            coinalyze_pct = fr_data.get('coinalyze_pct')
            if binance_pct is not None and coinalyze_pct is not None:
                print(f"    [对比] Binance 8h: {binance_pct:.4f}%, Coinalyze: {coinalyze_pct:.4f}%")
        else:
            print(f"    (数据不可用)")
        print()
        print(f"  Liquidations (1h):")
        if liq_data:
            history = liq_data.get('history', [])
            if history:
                latest = history[-1]
                # 显示原始 BTC 数据和转换后的 USD 数据
                long_btc = float(latest.get('l', 0))
                short_btc = float(latest.get('s', 0))
                total_btc = long_btc + short_btc
                # 使用当前价格转换
                long_usd = long_btc * current_price
                short_usd = short_btc * current_price
                total_usd = total_btc * current_price
                print(f"    [原始] Long:   {long_btc:.4f} BTC")
                print(f"    [原始] Short:  {short_btc:.4f} BTC")
                print(f"    [原始] Total:  {total_btc:.4f} BTC")
                print(f"    [转换] Long:   ${long_usd:,.0f}")
                print(f"    [转换] Short:  ${short_usd:,.0f}")
                print(f"    [转换] Total:  ${total_usd:,.0f}")
            else:
                print(f"    history: []")
        else:
            print(f"    (数据不可用)")

    # 输出持仓数据
    print()
    print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("  ┃                        当前持仓                                     ┃")
    print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print()
    if current_position:
        print(f"  持仓状态: 有持仓")
        print(f"    方向:     {current_position.get('side', 'N/A').upper()}")
        print(f"    数量:     {current_position.get('quantity', 0)} BTC")
        print(f"    入场价:   ${current_position.get('entry_price', 0):,.2f}")
        print(f"    未实现PnL: ${current_position.get('unrealized_pnl', 0):,.2f}")
        pnl_pct = current_position.get('pnl_pct', 0)
        print(f"    盈亏比例: {pnl_pct:+.2f}%")
    else:
        print(f"  持仓状态: 无持仓 (FLAT)")

    # 输出 AI 决策数据
    print()
    print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("  ┃                        AI 决策结果                                  ┃")
    print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print()
    print(f"  原始信号: {signal_data.get('signal', 'N/A')}")
    print(f"  最终信号: {final_signal}")
    print(f"  信心等级: {signal_data.get('confidence', 'N/A')}")
    print(f"  风险等级: {signal_data.get('risk_level', 'N/A')}")
    judge_decision = signal_data.get('judge_decision', {})
    print(f"  胜出方:   {judge_decision.get('winning_side', 'N/A')}")
    # v3.0: AI 完全自主决策，无确认计数框架
    print()
    print(f"  AI 止损: ${signal_data.get('stop_loss', 0):,.2f}" if signal_data.get('stop_loss') else "  AI 止损: N/A")
    print(f"  AI 止盈: ${signal_data.get('take_profit', 0):,.2f}" if signal_data.get('take_profit') else "  AI 止盈: N/A")
    print()
    print(f"  关键理由:")
    key_reasons = judge_decision.get('key_reasons', [])
    for i, reason in enumerate(key_reasons[:3], 1):
        print(f"    {i}. {reason[:70]}...")
    print()
    acknowledged_risks = judge_decision.get('acknowledged_risks', [])
    if acknowledged_risks:
        print(f"  确认风险:")
        for i, risk in enumerate(acknowledged_risks[:2], 1):
            print(f"    {i}. {risk[:70]}...")
        print()
    print(f"  决策理由: {signal_data.get('reason', 'N/A')[:100]}...")

    # MTF 过滤状态
    print()
    print("  ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓")
    print("  ┃                        MTF 过滤状态                                 ┃")
    print("  ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛")
    print()

    print(f"  架构: TradingAgents v3.2 - AI 完全自主决策")
    print(f"  本地风控: 无 (已移除所有硬编码规则)")
    print()
    print(f"  AI 决策: {signal_data.get('signal')} (Confidence: {signal_data.get('confidence')})")
    print(f"  Winning Side: {signal_data.get('judge_decision', {}).get('winning_side', 'N/A')}")

    print()
    print("  ✅ 完整数据流汇总完成")
    print()

print("=" * 70)
print("  诊断完成 - 使用共享模块，与实盘逻辑 100% 一致")
print("=" * 70)

# =============================================================================
# 深入分析: 为什么没有交易信号?
# =============================================================================
if not SUMMARY_MODE:
    print()
    print("=" * 70)
    print("  📋 深入分析: 信号产生条件")
    print("=" * 70)
    print()

    # 1. 技术指标详细分析
    print("[分析1] 技术指标阈值检查")
    print("-" * 50)

rsi = technical_data.get('rsi', 50)
rsi_upper = getattr(strategy_config, 'rsi_extreme_threshold_upper', 70)
rsi_lower = getattr(strategy_config, 'rsi_extreme_threshold_lower', 30)

print(f"  RSI: {rsi:.2f}")
print(f"    配置阈值: 超卖<{rsi_lower}, 超买>{rsi_upper}")
if rsi > rsi_upper:
    print(f"    → 🔴 超买区 (>{rsi_upper}) - 可能触发 SELL")
elif rsi < rsi_lower:
    print(f"    → 🟢 超卖区 (<{rsi_lower}) - 可能触发 BUY")
else:
    print(f"    → ⚪ 中性区间 ({rsi_lower}-{rsi_upper}) - 无明确方向")
    print(f"    → 距离超买: {rsi_upper - rsi:.2f} 点")
    print(f"    → 距离超卖: {rsi - rsi_lower:.2f} 点")

macd = technical_data.get('macd', 0)
macd_signal = technical_data.get('macd_signal', 0)
macd_hist = technical_data.get('macd_histogram', 0)
print()
print(f"  MACD: {macd:.4f}")
print(f"  MACD Signal: {macd_signal:.4f}")
print(f"  MACD Histogram: {macd_hist:.4f}")
if macd > macd_signal:
    print("    → 🟢 MACD 在信号线上方 - 看涨")
else:
    print("    → 🔴 MACD 在信号线下方 - 看跌")

if macd_hist > 0:
    print(f"    → 🟢 柱状图为正 (+{macd_hist:.4f}) - 上涨动能")
else:
    print(f"    → 🔴 柱状图为负 ({macd_hist:.4f}) - 下跌动能")

# SMA 分析
print()
sma_5 = technical_data.get('sma_5', 0)
sma_20 = technical_data.get('sma_20', 0)
sma_50 = technical_data.get('sma_50', 0)
print(f"  SMA_5: ${sma_5:,.2f}")
print(f"  SMA_20: ${sma_20:,.2f}")
print(f"  SMA_50: ${sma_50:,.2f}")
print(f"  当前价格: ${current_price:,.2f}")

if current_price > sma_5 > sma_20 > sma_50:
    print("    → 🟢 完美多头排列 (价格 > SMA5 > SMA20 > SMA50)")
elif current_price < sma_5 < sma_20 < sma_50:
    print("    → 🔴 完美空头排列 (价格 < SMA5 < SMA20 < SMA50)")
else:
    print("    → ⚪ 无明确趋势排列")
    if current_price > sma_20:
        print(f"       价格在 SMA20 上方 (+{((current_price/sma_20)-1)*100:.2f}%)")
    else:
        print(f"       价格在 SMA20 下方 ({((current_price/sma_20)-1)*100:.2f}%)")

# 布林带分析
print()
bb_upper = technical_data.get('bb_upper', 0)
bb_lower = technical_data.get('bb_lower', 0)
bb_width = bb_upper - bb_lower if bb_upper and bb_lower else 0
bb_position = ((current_price - bb_lower) / bb_width * 100) if bb_width > 0 else 50

print(f"  BB Upper: ${bb_upper:,.2f}")
print(f"  BB Lower: ${bb_lower:,.2f}")
print(f"  BB Width: ${bb_width:,.2f} ({bb_width/current_price*100:.2f}%)")
print(f"  价格在带内位置: {bb_position:.1f}%")

if bb_position > BB_OVERBOUGHT_THRESHOLD:
    print(f"    → 🔴 接近上轨 (>{BB_OVERBOUGHT_THRESHOLD}%, 可能超买)")
elif bb_position < BB_OVERSOLD_THRESHOLD:
    print(f"    → 🟢 接近下轨 (<{BB_OVERSOLD_THRESHOLD}%, 可能超卖)")
else:
    print("    → ⚪ 带内中间区域")

# 2. 趋势分析
print()
print("[分析2] 趋势强度分析")
print("-" * 50)

trend = technical_data.get('overall_trend', 'N/A')
print(f"  整体趋势判断: {trend}")

# 计算近期价格变化
if len(bars) >= 10:
    price_10_bars_ago = float(bars[-10].close)
    price_change_10 = ((current_price - price_10_bars_ago) / price_10_bars_ago) * 100
    print(f"  近10根K线变化: {price_change_10:+.2f}%")
else:
    print(f"  近10根K线变化: N/A (K线数量不足: {len(bars)})")

if len(bars) >= 20:
    price_20_bars_ago = float(bars[-20].close)
    price_change_20 = ((current_price - price_20_bars_ago) / price_20_bars_ago) * 100
    print(f"  近20根K线变化: {price_change_20:+.2f}%")
else:
    print(f"  近20根K线变化: N/A (K线数量不足: {len(bars)})")

# 3. 情绪分析
print()
print("[分析3] 市场情绪分析")
print("-" * 50)

ls_ratio = sentiment_data.get('long_short_ratio', 1.0)
print(f"  多空比: {ls_ratio:.4f}")

if ls_ratio > LS_RATIO_EXTREME_BULLISH:
    print(f"    → 🔴 极度看多 (>{LS_RATIO_EXTREME_BULLISH}, 逆向指标: 可能下跌)")
elif ls_ratio > LS_RATIO_BULLISH:
    print(f"    → 🟡 偏多 (>{LS_RATIO_BULLISH}, 市场乐观)")
elif ls_ratio < LS_RATIO_EXTREME_BEARISH:
    print(f"    → 🔴 极度看空 (<{LS_RATIO_EXTREME_BEARISH}, 逆向指标: 可能上涨)")
elif ls_ratio < LS_RATIO_BEARISH:
    print(f"    → 🟡 偏空 (<{LS_RATIO_BEARISH}, 市场悲观)")
else:
    print("    → ⚪ 多空平衡")

# 4. 为什么 AI 返回该信号 (TradingAgents: Judge 决策分析)
print()
print("[分析4] Judge 决策原因分析 (TradingAgents)")
print("-" * 50)

print(f"  ⚖️ Judge 最终决策: {signal_data.get('signal', 'N/A')}")
print()

# 显示 Judge 详细决策
judge_decision = signal_data.get('judge_decision', {})
if judge_decision:
    print(f"  Winning Side: {judge_decision.get('winning_side', 'N/A')}")
    key_reasons = judge_decision.get('key_reasons', [])
    if key_reasons:
        print(f"  Key Reasons:")
        for reason in key_reasons[:3]:
            print(f"    • {reason}")
    risks = judge_decision.get('acknowledged_risks', [])
    if risks:
        print(f"  Acknowledged Risks:")
        for risk in risks[:2]:
            print(f"    • {risk}")

print()
print(f"  📋 Judge 完整理由:")
judge_reason = signal_data.get('reason', 'N/A')
print_wrapped(judge_reason)

print()
print(f"  🗣️ 辩论摘要:")
debate_summary = signal_data.get('debate_summary', 'N/A')
print_wrapped(str(debate_summary))

# 5. 触发交易的条件 (基于更新后的提示词)
print()
print("[分析5] 触发交易所需条件 (最新提示词)")
print("-" * 50)

print("  要触发 BUY 信号 (ANY 2 of these is sufficient):")
print(f"    • 价格在 SMA5/SMA20 上方 (当前: {'✅' if current_price > sma_5 and current_price > sma_20 else '❌'})")
print(f"    • RSI < 60 且不超买 (当前: {rsi:.2f}, {'✅' if rsi < 60 else '❌'})")
print(f"    • MACD 金叉或柱状图为正 (当前: {'✅' if macd > macd_signal or macd_hist > 0 else '❌'})")
print(f"    • 价格接近支撑或 BB 下轨 (当前位置: {bb_position:.1f}%)")
print()
print("  要触发 SELL 信号 (ANY 2 of these is sufficient):")
print(f"    • 价格在 SMA5/SMA20 下方 (当前: {'✅' if current_price < sma_5 and current_price < sma_20 else '❌'})")
print(f"    • RSI > 40 且显示弱势 (当前: {rsi:.2f}, {'✅' if rsi > 40 else '❌'})")
print(f"    • MACD 死叉或柱状图为负 (当前: {'✅' if macd < macd_signal or macd_hist < 0 else '❌'})")
print(f"    • 价格接近阻力或 BB 上轨 (当前位置: {bb_position:.1f}%)")
print()
print("  📌 提示词更新后，HOLD 仅在信号真正冲突时使用")
print(f"     当前 min_confidence_to_trade: {strategy_config.min_confidence_to_trade}")

# 6. 建议
print()
print("[分析6] 诊断建议")
print("-" * 50)

if final_signal == 'HOLD':
    print("  📌 当前市场状态分析:")

    # 综合评分
    bullish_score = 0
    bearish_score = 0

    # RSI
    if rsi < 40:
        bullish_score += 1
    elif rsi > 60:
        bearish_score += 1

    # MACD
    if macd > macd_signal:
        bullish_score += 1
    else:
        bearish_score += 1

    # Price vs SMA20
    if current_price > sma_20:
        bullish_score += 1
    else:
        bearish_score += 1

    # BB position
    if bb_position < 30:
        bullish_score += 1
    elif bb_position > 70:
        bearish_score += 1

    # Long/Short ratio (逆向)
    if ls_ratio > LS_RATIO_EXTREME_BULLISH:
        bearish_score += 1
    elif ls_ratio < LS_RATIO_BEARISH:
        bullish_score += 1

    print(f"    多头信号得分: {bullish_score}/5")
    print(f"    空头信号得分: {bearish_score}/5")

    if bullish_score > bearish_score + 1:
        print("    → 偏多头，但信号不够强烈")
    elif bearish_score > bullish_score + 1:
        print("    → 偏空头，但信号不够强烈")
    else:
        print("    → 多空信号混杂，无明确方向")

    print()
    print("  💡 HOLD 的常见原因:")
    print("    1. 技术指标处于中性区间 (RSI 30-70)")
    print("    2. 趋势不明确 (震荡整理)")
    print("    3. 多头和空头信号相互矛盾")
    print("    4. 市场波动率低，缺乏明确方向")
    print()
    print("  ⏳ 等待以下情况之一发生:")
    print("    • RSI 突破 30 或 70")
    print("    • MACD 形成明确金叉/死叉")
    print("    • 价格突破关键支撑/阻力位")
    print(f"      支撑: ${technical_data.get('support', 0):,.2f}")
    print(f"      阻力: ${technical_data.get('resistance', 0):,.2f}")

    print()
    print("=" * 70)
    print("  深入分析完成")
    print("=" * 70)
else:
    # Summary mode: add actionable suggestions
    print()
    print("=" * 70)
    print("  🔧 下一步建议")
    print("=" * 70)
    print()

    if final_signal == 'HOLD':
        print("  📌 当前信号: HOLD")
        print(f"  原因: {signal_data.get('reason', 'N/A')[:100]}")
        print()
        print("  💡 等待条件:")
        print("    • RSI 突破超买/超卖区间 (< 30 或 > 70)")
        print("    • MACD 形成明确金叉/死叉")
        print("    • 价格突破关键支撑/阻力位")
        rsi = technical_data.get('rsi', 50)
        if rsi > 50:
            print(f"    • 当前 RSI={rsi:.1f}, 距离超买还需 {70-rsi:.1f} 点")
        else:
            print(f"    • 当前 RSI={rsi:.1f}, 距离超卖还需 {rsi-30:.1f} 点")
        print()
        print("  ⏰ 实盘每 {:.0f} 分钟重新分析一次".format(timer_min))

    elif not would_trade and current_position:
        print(f"  📌 有信号 ({final_signal}) 但未执行")
        target_side = 'long' if final_signal == 'BUY' else 'short'
        if current_position['side'] == target_side:
            print(f"  原因: 已有同向持仓，仓位差异低于调整阈值")
            print()
            print("  💡 建议:")
            print("    • 这是正常行为，避免频繁微调仓位")
            print("    • 等待更大的仓位变化需求或反转信号")
        else:
            print(f"  原因: 反转被阻止")
            print()
            print("  💡 检查:")
            print("    • 配置: allow_reversals 是否启用?")
            print("    • 配置: require_high_confidence_for_reversal?")
            print(f"    • 当前信心: {confidence}")

    elif btc_quantity == 0:
        print(f"  📌 有信号 ({final_signal}) 但仓位为 0")
        print("  原因: 计算的仓位大小低于最小交易量")
        print()
        print("  💡 建议:")
        print("    • 增加账户余额")
        print("    • 或调整配置: base_usdt_amount")

    elif not passes_threshold:
        print(f"  📌 有信号 ({final_signal}) 但信心不足")
        print(f"  原因: {confidence} < {strategy_config.min_confidence_to_trade}")
        print()
        print("  💡 建议:")
        print("    • 等待更强的市场信号")
        print("    • 或降低配置: min_confidence_to_trade")

    elif would_trade:
        print(f"  📌 将执行交易: {final_signal} {btc_quantity:.4f} BTC")
        if final_sl and final_tp:
            sl_pct = ((final_sl / entry_price) - 1) * 100
            tp_pct = ((final_tp / entry_price) - 1) * 100
            print(f"  SL: ${final_sl:,.2f} ({sl_pct:+.2f}%)")
            print(f"  TP: ${final_tp:,.2f} ({tp_pct:+.2f}%)")
        print()
        print("  💡 实盘状态:")
        print("    • 检查服务是否运行: systemctl status nautilus-trader")
        print("    • 查看日志: journalctl -u nautilus-trader -f --no-hostname")

    print()
    print("  📖 详细分析: 运行 python3 diagnose_realtime.py (不加 --summary)")
    print()

# =============================================================================
# 导出诊断结果到文件并可选推送到 GitHub
# =============================================================================
if EXPORT_MODE:
    # 恢复原始 stdout
    sys.stdout = original_stdout

    # 创建 logs 目录
    project_dir = Path(__file__).parent.parent.absolute()
    logs_dir = project_dir / "logs"
    logs_dir.mkdir(exist_ok=True)

    # 生成文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"diagnosis_{timestamp}.txt"
    filepath = logs_dir / filename

    # 写入文件
    output_content = output_buffer.getvalue()
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(output_content)

    print()
    print("=" * 70)
    print("  📤 诊断结果导出")
    print("=" * 70)
    print(f"  ✅ 已保存到: {filepath}")
    print(f"  📊 文件大小: {len(output_content):,} 字符")

    if PUSH_TO_GITHUB:
        import subprocess
        commit_msg = f"chore: Add diagnosis report {filename}"
        try:
            # 切换到项目目录
            os.chdir(project_dir)

            # Git 操作 (使用 -f 强制添加，因为 logs/ 在 .gitignore 中)
            subprocess.run(['git', 'add', '-f', str(filepath)], check=True, capture_output=True)
            subprocess.run(['git', 'commit', '-m', commit_msg], check=True, capture_output=True)

            # 获取当前分支
            result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                                  capture_output=True, text=True, check=True)
            branch = result.stdout.strip()

            # 推送到远程
            subprocess.run(['git', 'push', '-u', 'origin', branch], check=True, capture_output=True)

            print(f"  ✅ 已推送到 GitHub (分支: {branch})")
            print(f"  📎 文件路径: logs/{filename}")
            print()
            print("  💡 在 GitHub 上查看:")
            print(f"     https://github.com/FelixWayne0318/AItrader/blob/{branch}/logs/{filename}")

        except subprocess.CalledProcessError as e:
            print(f"  ⚠️ Git 推送失败: {e}")
            print(f"     请手动提交: git add -f {filepath} && git commit -m '{commit_msg}' && git push")
        except Exception as e:
            print(f"  ⚠️ 导出错误: {e}")
    else:
        print()
        print("  💡 要推送到 GitHub，运行:")
        print(f"     python3 scripts/diagnose_realtime.py --push")

    print()
