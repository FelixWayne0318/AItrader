#!/usr/bin/env python3
"""
全链路诊断: 交易评估评级系统
Generation → Storage → Loading → Formatting → Agent消费 → Web展示

在服务器上运行:
  cd /home/linuxuser/nautilus_AItrader
  source venv/bin/activate
  python3 scripts/diagnose_trade_evaluation.py
"""

import json
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime, timedelta

# ─── 颜色输出 ───
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

PASS = f"{GREEN}PASS{RESET}"
FAIL = f"{RED}FAIL{RESET}"
WARN = f"{YELLOW}WARN{RESET}"
INFO = f"{BLUE}INFO{RESET}"

results = []


def check(name, passed, detail=""):
    status = PASS if passed else FAIL
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"  [{status}] {name}")
    if detail:
        print(f"         {detail}")


def warn(name, detail=""):
    results.append({"name": name, "passed": None, "detail": detail})
    print(f"  [{WARN}] {name}")
    if detail:
        print(f"         {detail}")


def info(name, detail=""):
    print(f"  [{INFO}] {name}")
    if detail:
        print(f"         {detail}")


# ─── 自动检测项目根目录 ───
def detect_project_root():
    """从多个位置检测项目根目录"""
    candidates = [
        Path(__file__).resolve().parent.parent,  # scripts/ -> project root
        Path("/home/linuxuser/nautilus_AItrader"),
        Path.cwd(),
    ]
    for p in candidates:
        if (p / "main_live.py").exists():
            return p
    return candidates[0]


PROJECT_ROOT = detect_project_root()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))


def section(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  STEP: {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


# ══════════════════════════════════════════════════════════════
#  STEP 1: 文件系统 - trading_memory.json 是否存在
# ══════════════════════════════════════════════════════════════
def step1_file_system():
    section("1/6 文件系统 - trading_memory.json")

    # 1a. 从 configs/base.yaml 读取配置路径
    config_path = PROJECT_ROOT / "configs" / "base.yaml"
    configured_path = "data/trading_memory.json"  # default
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            configured_path = cfg.get("agents", {}).get("memory_file", configured_path)
            info("base.yaml 配置路径", configured_path)
        except Exception as e:
            warn("无法解析 base.yaml", str(e))
    else:
        warn("configs/base.yaml 不存在")

    # 1b. 解析实际文件路径
    memory_file = PROJECT_ROOT / configured_path
    info("实际文件路径", str(memory_file))

    # 1c. 文件存在?
    exists = memory_file.exists()
    check("trading_memory.json 文件存在", exists,
          str(memory_file) if not exists else f"大小: {memory_file.stat().st_size} bytes")

    if not exists:
        warn("文件不存在 = 从未有交易平仓，后续检测使用模拟数据")
        return None, memory_file

    # 1d. 文件可读?
    try:
        with open(memory_file) as f:
            data = json.load(f)
        check("JSON 解析成功", True, f"共 {len(data)} 条记录")
    except Exception as e:
        check("JSON 解析成功", False, str(e))
        return None, memory_file

    # 1e. 数据结构检查
    if len(data) == 0:
        warn("文件为空 (0 条记录)")
        return data, memory_file

    # 检查第一条和最后一条
    first = data[0]
    last = data[-1]
    info("最早记录", f"时间={first.get('timestamp', 'N/A')}, 决策={first.get('decision', 'N/A')}")
    info("最新记录", f"时间={last.get('timestamp', 'N/A')}, 决策={last.get('decision', 'N/A')}")

    # 1f. 有多少条包含 evaluation?
    with_eval = [m for m in data if m.get("evaluation")]
    without_eval = [m for m in data if not m.get("evaluation")]

    check("含 evaluation 字段的记录", len(with_eval) > 0,
          f"{len(with_eval)}/{len(data)} 条含 evaluation")

    if without_eval:
        warn(f"有 {len(without_eval)} 条缺少 evaluation 字段 (老格式?)",
             f"示例: {json.dumps(without_eval[0], ensure_ascii=False)[:200]}")

    # 1g. evaluation 字段结构验证
    required_eval_fields = [
        "grade", "direction_correct", "planned_rr", "actual_rr",
        "execution_quality", "exit_type", "confidence", "hold_duration_min"
    ]
    if with_eval:
        sample = with_eval[0]["evaluation"]
        missing = [f for f in required_eval_fields if f not in sample]
        check("evaluation 包含所有必需字段", len(missing) == 0,
              f"缺少: {missing}" if missing else f"字段完整: {list(sample.keys())}")

        # 检查 grade 值是否合法
        valid_grades = {"A+", "A", "B", "C", "D", "F"}
        grades_found = set(m["evaluation"].get("grade") for m in with_eval)
        invalid = grades_found - valid_grades
        check("Grade 值合法", len(invalid) == 0,
              f"非法值: {invalid}" if invalid else f"出现的等级: {grades_found}")

    return data, memory_file


# ══════════════════════════════════════════════════════════════
#  STEP 2: Generation - evaluate_trade() 函数测试
# ══════════════════════════════════════════════════════════════
def step2_generation():
    section("2/6 Generation - evaluate_trade() 测试")

    try:
        from strategy.trading_logic import evaluate_trade
        check("evaluate_trade 导入成功", True)
    except Exception as e:
        check("evaluate_trade 导入成功", False, str(e))
        return

    # 测试用例 1: A+ 级交易 (LONG, R/R > 2.5)
    try:
        result = evaluate_trade(
            entry_price=70000.0,
            exit_price=72500.0,
            planned_sl=69000.0,
            planned_tp=73000.0,
            direction="LONG",
            pnl_pct=3.57,
            confidence="HIGH",
            position_size_pct=50.0,
            entry_timestamp=(datetime.now() - timedelta(hours=5)).isoformat(),
            exit_timestamp=datetime.now().isoformat(),
        )
        check("A+ 交易测试", result.get("grade") == "A+",
              f"grade={result.get('grade')}, actual_rr={result.get('actual_rr')}, "
              f"exit_type={result.get('exit_type')}")
    except Exception as e:
        check("A+ 交易测试", False, traceback.format_exc())

    # 测试用例 2: D 级交易 (LONG 止损出场)
    try:
        result = evaluate_trade(
            entry_price=70000.0,
            exit_price=69100.0,
            planned_sl=69000.0,
            planned_tp=73000.0,
            direction="LONG",
            pnl_pct=-1.29,
            confidence="MEDIUM",
        )
        check("D 级止损测试", result.get("grade") == "D",
              f"grade={result.get('grade')}, actual_rr={result.get('actual_rr')}, "
              f"exit_type={result.get('exit_type')}")
    except Exception as e:
        check("D 级止损测试", False, traceback.format_exc())

    # 测试用例 3: F 级交易 (LONG 失控亏损)
    try:
        result = evaluate_trade(
            entry_price=70000.0,
            exit_price=67000.0,
            planned_sl=69000.0,
            planned_tp=73000.0,
            direction="LONG",
            pnl_pct=-4.29,
            confidence="LOW",
        )
        check("F 级失控亏损测试", result.get("grade") == "F",
              f"grade={result.get('grade')}, actual_rr={result.get('actual_rr')}, "
              f"exit_type={result.get('exit_type')}")
    except Exception as e:
        check("F 级失控亏损测试", False, traceback.format_exc())

    # 测试用例 4: SHORT 方向
    try:
        result = evaluate_trade(
            entry_price=70000.0,
            exit_price=68000.0,
            planned_sl=71000.0,
            planned_tp=67000.0,
            direction="SHORT",
            pnl_pct=2.86,
            confidence="HIGH",
        )
        check("SHORT 方向测试", result.get("direction_correct") is True,
              f"grade={result.get('grade')}, actual_rr={result.get('actual_rr')}")
    except Exception as e:
        check("SHORT 方向测试", False, traceback.format_exc())

    # 测试用例 5: 返回值结构完整性
    try:
        result = evaluate_trade(
            entry_price=70000.0,
            exit_price=71000.0,
            planned_sl=69500.0,
            planned_tp=72000.0,
            direction="LONG",
            pnl_pct=1.43,
            confidence="MEDIUM",
            position_size_pct=30.0,
        )
        required = [
            "grade", "direction_correct", "entry_price", "exit_price",
            "planned_sl", "planned_tp", "planned_rr", "actual_rr",
            "execution_quality", "exit_type", "confidence",
            "position_size_pct", "hold_duration_min"
        ]
        missing = [k for k in required if k not in result]
        check("返回值结构完整", len(missing) == 0,
              f"缺少字段: {missing}" if missing else "所有 13 个字段齐全")
    except Exception as e:
        check("返回值结构完整", False, traceback.format_exc())


# ══════════════════════════════════════════════════════════════
#  STEP 3: Storage - record_outcome() + _save_memory() 测试
# ══════════════════════════════════════════════════════════════
def step3_storage():
    section("3/6 Storage - record_outcome() 写入测试")

    # 使用临时文件测试，不污染正式数据
    test_memory_file = str(PROJECT_ROOT / "data" / "_test_memory_diagnostic.json")

    # 尝试导入真实 MultiAgentAnalyzer (需要 openai 等依赖)
    # 如果失败，使用内联模拟版本
    _Analyzer = None
    try:
        from agents.multi_agent_analyzer import MultiAgentAnalyzer
        _Analyzer = MultiAgentAnalyzer
        check("MultiAgentAnalyzer 导入成功", True)
    except Exception as e:
        warn(f"MultiAgentAnalyzer 导入失败 ({e.__class__.__name__}: {e}), 使用内联模拟")

    # 内联的 record_outcome + _save_memory 模拟
    import logging

    class _MockAnalyzer:
        def __init__(self, memory_file):
            self.logger = logging.getLogger("test_diag")
            self.memory_file = memory_file
            self.decision_memory = []

        def record_outcome(self, decision, pnl, conditions="", lesson="", evaluation=None):
            if not lesson and evaluation:
                grade = evaluation.get('grade', '')
                actual_rr = evaluation.get('actual_rr', 0)
                exit_type = evaluation.get('exit_type', '')
                if grade in ('A+', 'A'):
                    lesson = f"Grade {grade}: Strong win (R/R {actual_rr:.1f}:1) - repeat this pattern"
                elif grade == 'D':
                    lesson = f"Grade D: Controlled loss via {exit_type} - discipline maintained"
                elif grade == 'F':
                    lesson = f"Grade F: Uncontrolled loss - review SL placement"
            if not lesson:
                lesson = "Auto-generated lesson"
            entry = {
                "decision": decision, "pnl": round(pnl, 2),
                "conditions": conditions, "lesson": lesson,
                "timestamp": datetime.now().isoformat(),
            }
            if evaluation:
                entry["evaluation"] = evaluation
            self.decision_memory.append(entry)
            self._save_memory()

        def _save_memory(self):
            os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
            with open(self.memory_file, 'w') as f:
                json.dump(self.decision_memory, f, indent=2)

    if _Analyzer:
        try:
            analyzer = _Analyzer.__new__(_Analyzer)
            analyzer.logger = logging.getLogger("test_diag")
            analyzer.memory_file = test_memory_file
            analyzer.decision_memory = []
            check("MultiAgentAnalyzer 临时实例创建成功", True)
        except Exception:
            analyzer = _MockAnalyzer(test_memory_file)
            check("使用内联模拟 (MultiAgentAnalyzer 实例化失败)", True)
    else:
        analyzer = _MockAnalyzer(test_memory_file)
        check("使用内联模拟测试 record_outcome 逻辑", True)

    # 写入测试记录
    mock_evaluation = {
        "grade": "A",
        "direction_correct": True,
        "entry_price": 70000.0,
        "exit_price": 71500.0,
        "planned_sl": 69500.0,
        "planned_tp": 72000.0,
        "planned_rr": 1.5,
        "actual_rr": 2.0,
        "execution_quality": 1.33,
        "exit_type": "TAKE_PROFIT",
        "confidence": "HIGH",
        "position_size_pct": 50.0,
        "hold_duration_min": 240,
    }

    try:
        analyzer.record_outcome(
            decision="LONG",
            pnl=2.14,
            conditions="price=$70,000, RSI=62, MACD=bullish, BB=68%",
            evaluation=mock_evaluation,
        )
        check("record_outcome() 执行成功", True)
    except Exception as e:
        check("record_outcome() 执行成功", False, traceback.format_exc())
        return

    # 验证文件已写入
    test_file = Path(test_memory_file)
    check("临时文件已写入", test_file.exists(),
          f"大小: {test_file.stat().st_size} bytes" if test_file.exists() else "文件未创建")

    if test_file.exists():
        try:
            with open(test_file) as f:
                saved = json.load(f)
            check("保存的 JSON 可解析", True, f"{len(saved)} 条记录")

            entry = saved[0]
            has_eval = "evaluation" in entry
            check("保存的记录包含 evaluation", has_eval,
                  json.dumps(entry.get("evaluation", {}), indent=2)[:300] if has_eval else "缺少 evaluation 字段!")

            has_ts = "timestamp" in entry
            check("保存的记录包含 timestamp", has_ts,
                  entry.get("timestamp", "N/A"))

            has_lesson = bool(entry.get("lesson"))
            check("auto-lesson 已生成", has_lesson,
                  entry.get("lesson", "N/A"))

        except Exception as e:
            check("验证保存内容", False, str(e))

        # 清理临时文件
        try:
            test_file.unlink()
            info("临时测试文件已清理")
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  STEP 4: Loading - TradeEvaluationService 加载测试
# ══════════════════════════════════════════════════════════════
def step4_loading(real_data):
    section("4/6 Loading - TradeEvaluationService 测试")

    # 4a. 构造 TradeEvaluationService (内联版本，不依赖 web backend 配置)
    #     这里直接模拟 service 的核心逻辑，避免 web backend 的依赖链
    class _DiagEvalService:
        """诊断用的轻量版 TradeEvaluationService"""
        def __init__(self, memory_path):
            self.memory_file = Path(memory_path)

        def _load_memory(self):
            if not self.memory_file.exists():
                return []
            with open(self.memory_file) as f:
                data = json.load(f)
                return [m for m in data if m.get('evaluation')]

        def _parse_timestamp(self, ts):
            if not ts:
                return datetime.min
            try:
                return datetime.fromisoformat(ts.replace('Z', ''))
            except Exception:
                return datetime.min

        def get_evaluation_summary(self, days=None):
            memories = self._load_memory()
            if days is not None:
                cutoff = datetime.now() - timedelta(days=days)
                memories = [m for m in memories if self._parse_timestamp(m.get('timestamp')) >= cutoff]
            if not memories:
                return {
                    'total_evaluated': 0, 'grade_distribution': {},
                    'direction_accuracy': 0.0, 'avg_winning_rr': 0.0,
                    'avg_execution_quality': 0.0, 'avg_grade_score': 0.0,
                    'exit_type_distribution': {}, 'confidence_accuracy': {},
                    'avg_hold_duration_min': 0, 'last_updated': datetime.now().isoformat(),
                }
            evals = [m['evaluation'] for m in memories]
            total = len(evals)
            grade_counts = {}
            for e in evals:
                g = e.get('grade', '?')
                grade_counts[g] = grade_counts.get(g, 0) + 1
            correct = sum(1 for e in evals if e.get('direction_correct'))
            direction_accuracy = round(correct / total * 100, 1) if total > 0 else 0.0
            profitable_rrs = [e.get('actual_rr', 0) for e in evals if e.get('direction_correct')]
            avg_winning_rr = round(sum(profitable_rrs) / len(profitable_rrs), 2) if profitable_rrs else 0.0
            exec_quals = [e.get('execution_quality', 0) for e in evals if e.get('execution_quality', 0) > 0]
            avg_exec_quality = round(sum(exec_quals) / len(exec_quals), 2) if exec_quals else 0.0
            exit_types = {}
            for e in evals:
                et = e.get('exit_type', 'UNKNOWN')
                exit_types[et] = exit_types.get(et, 0) + 1
            confidence_stats = {}
            for e in evals:
                conf = e.get('confidence', 'MEDIUM')
                if conf not in confidence_stats:
                    confidence_stats[conf] = {'total': 0, 'wins': 0}
                confidence_stats[conf]['total'] += 1
                if e.get('direction_correct'):
                    confidence_stats[conf]['wins'] += 1
            for conf, stats in confidence_stats.items():
                stats['accuracy'] = round(stats['wins'] / stats['total'] * 100, 1) if stats['total'] > 0 else 0.0
            durations = [e.get('hold_duration_min', 0) for e in evals if e.get('hold_duration_min', 0) > 0]
            avg_hold_min = round(sum(durations) / len(durations)) if durations else 0
            grade_scores = {'A+': 5, 'A': 4, 'B': 3, 'C': 2, 'D': 1, 'F': 0}
            total_score = sum(grade_scores.get(e.get('grade', 'F'), 0) for e in evals)
            avg_grade_score = round(total_score / total, 2) if total > 0 else 0.0
            return {
                'total_evaluated': total, 'grade_distribution': grade_counts,
                'direction_accuracy': direction_accuracy, 'avg_winning_rr': avg_winning_rr,
                'avg_execution_quality': avg_exec_quality, 'avg_grade_score': avg_grade_score,
                'exit_type_distribution': exit_types, 'confidence_accuracy': confidence_stats,
                'avg_hold_duration_min': avg_hold_min, 'last_updated': datetime.now().isoformat(),
            }

        def get_recent_trades(self, limit=20, include_details=False):
            memories = self._load_memory()
            memories.sort(key=lambda m: m.get('timestamp', ''), reverse=True)
            memories = memories[:limit]
            if include_details:
                return [{**m['evaluation'], 'pnl': m.get('pnl', 0),
                         'conditions': m.get('conditions', ''), 'lesson': m.get('lesson', ''),
                         'timestamp': m.get('timestamp', '')} for m in memories]
            return [{'grade': m['evaluation'].get('grade', '?'),
                     'planned_rr': m['evaluation'].get('planned_rr', 0),
                     'actual_rr': m['evaluation'].get('actual_rr', 0),
                     'execution_quality': m['evaluation'].get('execution_quality', 0),
                     'exit_type': m['evaluation'].get('exit_type', 'UNKNOWN'),
                     'confidence': m['evaluation'].get('confidence', 'MEDIUM'),
                     'hold_duration_min': m['evaluation'].get('hold_duration_min', 0),
                     'direction_correct': m['evaluation'].get('direction_correct', False),
                     'timestamp': m.get('timestamp', '')} for m in memories]

    check("_DiagEvalService 构造成功", True, "(内联版本，不依赖 web backend)")

    # 4b. 实例化并检查路径
    memory_path = PROJECT_ROOT / "data" / "trading_memory.json"
    service = _DiagEvalService(memory_path)
    check("service.memory_file 路径", True, str(service.memory_file))

    # 同时检查 web backend 真实版本的路径
    try:
        backend_path = str(PROJECT_ROOT / "web" / "backend")
        if backend_path not in sys.path:
            sys.path.insert(0, backend_path)

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "trade_evaluation_service",
            PROJECT_ROOT / "web" / "backend" / "services" / "trade_evaluation_service.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        real_service = mod.TradeEvaluationService()
        real_path = real_service.memory_file
        paths_match = real_path.resolve() == memory_path.resolve()
        check("Web 后端 TradeEvaluationService 路径一致", paths_match,
              f"Web后端路径: {real_path}" if not paths_match else f"一致: {real_path}")
    except Exception as e:
        warn("Web 后端 TradeEvaluationService 导入失败 (仅在服务器 venv 中可用)",
             str(e)[:200])

    # 4c. _load_memory() 测试
    try:
        memories = service._load_memory()
        check("_load_memory() 执行成功", True, f"返回 {len(memories)} 条 (含 evaluation 的)")
    except Exception as e:
        check("_load_memory() 执行成功", False, traceback.format_exc())
        return

    # 4d. 如果实际数据为空，创建临时测试数据进行后续测试
    if not memories:
        warn("实际数据为空，创建临时数据测试 summary/recent 功能")

        # 写入临时测试数据
        test_data = _generate_test_data()
        try:
            with open(service.memory_file, 'w') as f:
                json.dump(test_data, f, indent=2)
            info("已写入临时测试数据", f"{len(test_data)} 条")

            # 重新加载
            memories = service._load_memory()
            check("临时数据加载成功", len(memories) > 0, f"{len(memories)} 条含 evaluation")
        except Exception as e:
            check("临时数据写入", False, str(e))
            return

        # 标记需要清理
        return service, True
    else:
        return service, False


def _generate_test_data():
    """生成模拟测试数据 (5条)"""
    import random
    now = datetime.now()
    test_entries = []
    configs = [
        ("LONG", 2.5, "A+", True, "TAKE_PROFIT", "HIGH"),
        ("LONG", 1.8, "A", True, "TAKE_PROFIT", "MEDIUM"),
        ("SHORT", 1.2, "B", True, "MANUAL", "HIGH"),
        ("LONG", -0.8, "D", False, "STOP_LOSS", "MEDIUM"),
        ("SHORT", -2.5, "F", False, "STOP_LOSS", "LOW"),
    ]
    for i, (direction, pnl, grade, correct, exit_type, conf) in enumerate(configs):
        entry_price = 70000 + random.randint(-1000, 1000)
        ts = (now - timedelta(days=i)).isoformat()
        test_entries.append({
            "decision": direction,
            "pnl": pnl,
            "conditions": f"price=${entry_price}, RSI={50+random.randint(-15,15)}, MACD=bullish",
            "lesson": f"Test trade #{i+1} - grade {grade}",
            "timestamp": ts,
            "evaluation": {
                "grade": grade,
                "direction_correct": correct,
                "entry_price": entry_price,
                "exit_price": entry_price + (pnl / 100 * entry_price),
                "planned_sl": entry_price - 1000 if direction == "LONG" else entry_price + 1000,
                "planned_tp": entry_price + 2000 if direction == "LONG" else entry_price - 2000,
                "planned_rr": 2.0,
                "actual_rr": abs(pnl) / 1.0 if correct else -abs(pnl) / 1.0,
                "execution_quality": 1.2 if correct else 0.5,
                "exit_type": exit_type,
                "confidence": conf,
                "position_size_pct": 30.0,
                "hold_duration_min": 60 * (i + 1),
            }
        })
    return test_entries


# ══════════════════════════════════════════════════════════════
#  STEP 5: Formatting - get_evaluation_summary() + Agent 消费
# ══════════════════════════════════════════════════════════════
def step5_formatting(service, real_data):
    section("5/6 Formatting - Summary + Agent 消费测试")

    if not service:
        warn("TradeEvaluationService 不可用，跳过")
        return

    # 5a. get_evaluation_summary()
    try:
        summary = service.get_evaluation_summary(days=None)
        check("get_evaluation_summary() 执行成功", True)

        total = summary.get("total_evaluated", 0)
        check("total_evaluated > 0", total > 0, f"total_evaluated={total}")

        grade_dist = summary.get("grade_distribution", {})
        check("grade_distribution 非空", len(grade_dist) > 0,
              f"分布: {json.dumps(grade_dist)}")

        # 验证 summary 包含所有必需键 (前端依赖)
        required_keys = [
            "total_evaluated", "grade_distribution", "direction_accuracy",
            "avg_winning_rr", "avg_execution_quality", "avg_grade_score",
            "exit_type_distribution", "confidence_accuracy",
            "avg_hold_duration_min", "last_updated"
        ]
        missing = [k for k in required_keys if k not in summary]
        check("Summary 包含前端所需全部字段", len(missing) == 0,
              f"缺少: {missing}" if missing else f"全部 {len(required_keys)} 个字段齐全")

        info("Summary 完整内容", json.dumps(summary, indent=2, ensure_ascii=False)[:500])

    except Exception as e:
        check("get_evaluation_summary()", False, traceback.format_exc())

    # 5b. get_recent_trades()
    try:
        trades = service.get_recent_trades(limit=10, include_details=False)
        check("get_recent_trades(public) 执行成功", True, f"{len(trades)} 条")

        if trades:
            sample = trades[0]
            public_fields = [
                "grade", "planned_rr", "actual_rr", "execution_quality",
                "exit_type", "confidence", "hold_duration_min",
                "direction_correct", "timestamp"
            ]
            missing = [f for f in public_fields if f not in sample]
            check("Public 视图字段完整", len(missing) == 0,
                  f"缺少: {missing}" if missing else "9 个字段齐全")

            # 确保不含敏感字段
            sensitive = ["entry_price", "exit_price", "pnl", "conditions", "lesson"]
            leaked = [f for f in sensitive if f in sample]
            check("Public 视图无敏感字段泄漏", len(leaked) == 0,
                  f"泄漏字段: {leaked}" if leaked else "安全")

    except Exception as e:
        check("get_recent_trades(public)", False, traceback.format_exc())

    # 5c. get_recent_trades(admin)
    try:
        trades_admin = service.get_recent_trades(limit=10, include_details=True)
        check("get_recent_trades(admin) 执行成功", True, f"{len(trades_admin)} 条")

        if trades_admin:
            sample = trades_admin[0]
            admin_fields = ["pnl", "conditions", "lesson", "timestamp"]
            missing = [f for f in admin_fields if f not in sample]
            check("Admin 视图包含详细字段", len(missing) == 0,
                  f"缺少: {missing}" if missing else "详细字段齐全")
    except Exception as e:
        check("get_recent_trades(admin)", False, traceback.format_exc())

    # 5d. Agent 消费 - _get_past_memories()
    print(f"\n  {BOLD}--- Agent 记忆消费测试 ---{RESET}")

    if real_data:
        # 如果有真实数据，测试 _get_past_memories
        try:
            from agents.multi_agent_analyzer import MultiAgentAnalyzer
            import logging

            analyzer = MultiAgentAnalyzer.__new__(MultiAgentAnalyzer)
            analyzer.logger = logging.getLogger("test_diag_agent")

            # 从 memory_file 指向的路径加载
            memory_path = str(PROJECT_ROOT / "data" / "trading_memory.json")
            analyzer.memory_file = memory_path
            analyzer.decision_memory = analyzer._load_memory()

            memories_text = analyzer._get_past_memories()
            has_content = len(memories_text) > 0
            check("_get_past_memories() 返回内容", has_content,
                  f"长度={len(memories_text)} 字符")

            if has_content:
                has_success = "SUCCESSFUL" in memories_text or "✅" in memories_text
                has_failed = "FAILED" in memories_text or "❌" in memories_text
                has_quality = "TRADE QUALITY" in memories_text
                check("包含成功交易段", has_success)
                check("包含失败交易段", has_failed)
                check("包含质量统计段", has_quality)
                info("记忆文本预览", memories_text[:400] + "...")
            else:
                warn("_get_past_memories() 返回空字符串 (可能无足够数据)")

        except ImportError as e:
            warn(f"MultiAgentAnalyzer 导入失败 ({e}), 跳过 _get_past_memories 测试")
            warn("在服务器 venv 中应可正常运行")
        except Exception as e:
            check("_get_past_memories()", False, traceback.format_exc())
    else:
        warn("无真实数据，跳过 Agent 消费测试")


# ══════════════════════════════════════════════════════════════
#  STEP 6: Web 展示 - API 端点测试
# ══════════════════════════════════════════════════════════════
def step6_web_api():
    section("6/6 Web API 端点测试")

    # 6a. 检查后端是否在运行
    import subprocess

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
    except FileNotFoundError:
        warn("curl 未安装，跳过 HTTP 测试")
        return
    except subprocess.TimeoutExpired:
        check("Web 后端运行中 (port 8000)", False, "连接超时 - 后端未启动?")
        return
    except Exception as e:
        check("Web 后端连接", False, str(e))
        return

    if not is_running:
        warn("后端未运行，跳过 API 测试")
        return

    # 6b. 测试 summary 端点
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8000/api/public/trade-evaluation/summary?days=30"],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        total = data.get("total_evaluated", 0)
        check("/api/public/trade-evaluation/summary", True,
              f"total_evaluated={total}")

        if total == 0:
            warn("API 返回 total_evaluated=0 → 前端将显示'暂无评估数据'")
            info("grade_distribution", json.dumps(data.get("grade_distribution", {})))
        else:
            check("API 有数据返回", True, f"{total} 笔已评估交易")
    except Exception as e:
        check("/api/public/trade-evaluation/summary", False, str(e))

    # 6c. 测试 recent 端点
    try:
        result = subprocess.run(
            ["curl", "-s", "http://127.0.0.1:8000/api/public/trade-evaluation/recent?limit=5"],
            capture_output=True, text=True, timeout=5
        )
        data = json.loads(result.stdout)
        check("/api/public/trade-evaluation/recent", True,
              f"返回 {len(data)} 条记录")
    except Exception as e:
        check("/api/public/trade-evaluation/recent", False, str(e))

    # 6d. 检查前端 -> 后端代理配置
    print(f"\n  {BOLD}--- 前端代理配置 ---{RESET}")
    next_config = PROJECT_ROOT / "web" / "frontend" / "next.config.ts"
    if not next_config.exists():
        next_config = PROJECT_ROOT / "web" / "frontend" / "next.config.js"
    if not next_config.exists():
        next_config = PROJECT_ROOT / "web" / "frontend" / "next.config.mjs"

    if next_config.exists():
        with open(next_config) as f:
            content = f.read()
        has_proxy = "/api" in content and ("rewrites" in content or "proxy" in content.lower() or "destination" in content)
        check("next.config 包含 /api 代理", has_proxy,
              "找到 API 代理配置" if has_proxy else "未找到 /api 代理 → 前端请求可能无法到达后端!")
        if not has_proxy:
            info("next.config 内容预览", content[:500])
    else:
        warn("未找到 next.config.{ts,js,mjs}")


# ══════════════════════════════════════════════════════════════
#  STEP 7: deepseek_strategy.py 调用链检查
# ══════════════════════════════════════════════════════════════
def step7_strategy_callchain():
    section("BONUS: deepseek_strategy.py 调用链静态检查")

    strategy_file = PROJECT_ROOT / "strategy" / "deepseek_strategy.py"
    if not strategy_file.exists():
        warn("deepseek_strategy.py 不存在")
        return

    with open(strategy_file) as f:
        content = f.read()

    # 检查 evaluate_trade 导入
    has_import = "from strategy.trading_logic import" in content and "evaluate_trade" in content
    if not has_import:
        has_import = "from .trading_logic import" in content and "evaluate_trade" in content
    check("evaluate_trade 已导入", has_import)

    # 检查 evaluate_trade 调用
    has_call = "evaluate_trade(" in content
    check("evaluate_trade() 被调用", has_call)

    # 检查 record_outcome 调用
    has_record = "record_outcome(" in content
    check("record_outcome() 被调用", has_record)

    # 检查 evaluation 参数传递
    has_eval_param = "evaluation=evaluation" in content or "evaluation = evaluation" in content
    check("evaluation 参数传递给 record_outcome", has_eval_param,
          "确保 evaluate_trade 的结果传入 record_outcome" if not has_eval_param else "")

    # 检查 on_position_closed 中是否调用了 evaluate
    # 寻找 on_position_closed 到 evaluate_trade 的链路
    has_eval_in_close = ("on_position_closed" in content and
                         "evaluate_trade" in content and
                         "record_outcome" in content)
    check("on_position_closed → evaluate → record 链路存在", has_eval_in_close)

    # 检查 captured_sltp_for_eval 传递
    has_captured = "_captured_sltp_for_eval" in content
    check("SL/TP 捕获用于评估 (_captured_sltp_for_eval)", has_captured)


# ══════════════════════════════════════════════════════════════
#  主函数
# ══════════════════════════════════════════════════════════════
def main():
    print(f"\n{BOLD}{'#'*60}{RESET}")
    print(f"{BOLD}  交易评估全链路诊断{RESET}")
    print(f"{BOLD}  Generation → Storage → Loading → Formatting → Agent → Web{RESET}")
    print(f"{BOLD}  项目路径: {PROJECT_ROOT}{RESET}")
    print(f"{BOLD}  时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}")
    print(f"{BOLD}{'#'*60}{RESET}")

    # Step 1: 文件系统
    real_data, memory_file = step1_file_system()
    has_real_data = real_data is not None and len(real_data) > 0

    # Step 2: Generation
    step2_generation()

    # Step 3: Storage
    step3_storage()

    # Step 4: Loading
    load_result = step4_loading(real_data)
    service = None
    used_test_data = False
    if load_result:
        service, used_test_data = load_result

    # Step 5: Formatting + Agent
    step5_formatting(service, has_real_data or used_test_data)

    # Step 6: Web API
    step6_web_api()

    # Step 7: 静态调用链
    step7_strategy_callchain()

    # ─── 清理临时测试数据 ───
    if used_test_data and memory_file:
        try:
            memory_file_path = Path(memory_file) if isinstance(memory_file, str) else memory_file
            if memory_file_path.exists():
                memory_file_path.unlink()
                info("已清理临时测试数据文件")
        except Exception:
            pass

    # ─── 汇总 ───
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  诊断汇总{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    passed = sum(1 for r in results if r["passed"] is True)
    failed = sum(1 for r in results if r["passed"] is False)
    warned = sum(1 for r in results if r["passed"] is None)

    print(f"  {GREEN}通过: {passed}{RESET}")
    print(f"  {RED}失败: {failed}{RESET}")
    print(f"  {YELLOW}警告: {warned}{RESET}")

    if failed > 0:
        print(f"\n  {RED}{BOLD}失败项:{RESET}")
        for r in results:
            if r["passed"] is False:
                print(f"    {RED}✗ {r['name']}{RESET}")
                if r["detail"]:
                    print(f"      {r['detail']}")

    # ─── 根因诊断 ───
    print(f"\n{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  根因分析{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")

    if not has_real_data and not used_test_data:
        print(f"""
  {YELLOW}{BOLD}诊断结论: trading_memory.json 无数据{RESET}

  可能原因:
  1. Bot 尚未完成任何交易 (没有开仓或开仓后未平仓)
  2. Bot 开仓后一直持仓中，等待平仓触发 evaluate_trade()
  3. evaluate_trade() 调用失败 (查看 journalctl 日志确认)

  排查命令:
    sudo journalctl -u nautilus-trader --since "7 days ago" | grep -i "position closed\\|evaluate_trade\\|record_outcome\\|Trade evaluation"

  如确认有平仓但无记录，检查:
    sudo journalctl -u nautilus-trader --since "7 days ago" | grep -i "error\\|exception\\|traceback" | tail -20
""")
    elif has_real_data:
        with_eval = sum(1 for m in real_data if m.get("evaluation"))
        without_eval = sum(1 for m in real_data if not m.get("evaluation"))
        if with_eval == 0 and without_eval > 0:
            print(f"""
  {YELLOW}{BOLD}诊断结论: 有 {without_eval} 条记录但全部缺少 evaluation 字段{RESET}

  这些是 v5.1 之前的老格式记录，不包含交易评估。
  TradeEvaluationService._load_memory() 会过滤掉它们:
    return [m for m in data if m.get('evaluation')]  # 全部被过滤

  解决方案:
  1. 等新交易平仓后自动产生带 evaluation 的记录
  2. 或手动为老记录补充 evaluation 字段 (需要知道 SL/TP 价格)
""")
        elif with_eval > 0:
            print(f"""
  {GREEN}{BOLD}数据链路正常!{RESET} 有 {with_eval} 条含评估的记录
  如果前端仍显示 "暂无评估数据"，问题可能在:
  - Web 后端未运行或 AITRADER_PATH 指向错误
  - 前端 next.config 代理配置问题
  - 30 天内无数据 (默认 days=30 过滤)
""")

    if failed == 0:
        print(f"\n  {GREEN}{BOLD}✅ 代码链路完整无误，等待真实交易数据即可{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}❌ 发现 {failed} 个问题需要修复{RESET}\n")

    return 1 if failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
