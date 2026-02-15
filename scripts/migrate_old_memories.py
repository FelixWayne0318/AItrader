#!/usr/bin/env python3
"""
一次性迁移脚本: 为老格式 trading_memory 记录补充 evaluation 字段

老记录只有: decision, pnl, conditions, lesson, timestamp
缺少: evaluation (grade, actual_rr, exit_type 等)

本脚本从 conditions 字符串解析可用数据，生成近似评估。
由于老记录无 SL/TP 数据，R/R 和 execution_quality 无法精确计算，
但 grade 和 direction_correct 可以准确判断。

运行:
  cd /home/linuxuser/nautilus_AItrader
  source venv/bin/activate
  python3 scripts/migrate_old_memories.py
"""

import json
import re
import shutil
import sys
from pathlib import Path
from datetime import datetime

# ─── 颜色 ───
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ─── 路径 ───
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MEMORY_FILE = PROJECT_ROOT / "data" / "trading_memory.json"
BACKUP_FILE = PROJECT_ROOT / "data" / "trading_memory.json.bak"


def parse_conditions(conditions: str) -> dict:
    """
    从 conditions 字符串解析可用数据.

    示例: "price=$64,060, RSI=56, MACD=bullish, BB=65%, conf=HIGH, winner=BEAR"
    """
    result = {
        "price": 0.0,
        "rsi": 50.0,
        "confidence": "MEDIUM",
    }

    # 解析 price=$XX,XXX
    price_match = re.search(r"price=\$?([\d,]+(?:\.\d+)?)", conditions)
    if price_match:
        result["price"] = float(price_match.group(1).replace(",", ""))

    # 解析 RSI=XX
    rsi_match = re.search(r"RSI=(\d+(?:\.\d+)?)", conditions)
    if rsi_match:
        result["rsi"] = float(rsi_match.group(1))

    # 解析 conf=HIGH/MEDIUM/LOW
    conf_match = re.search(r"conf=(\w+)", conditions)
    if conf_match:
        result["confidence"] = conf_match.group(1).upper()

    return result


def create_evaluation_for_old_record(record: dict) -> dict:
    """
    为缺少 evaluation 的老记录生成近似评估.

    限制:
    - 无 SL/TP → actual_rr=0, planned_rr=0, execution_quality=0
    - 无 exit_price → 从 entry_price + pnl 推算
    - exit_type 统一标记为 MANUAL (无法判断)

    评分规则 (无 R/R 数据的简化版):
    - 盈利: Grade C (有盈利但 R/R 未知)
    - 小亏损 (< 1%): Grade D (受控亏损)
    - 大亏损 (>= 1%): Grade D (假设有 SL 纪律，但无法验证)
    - HOLD 决策 pnl=0: Grade C (未交易)
    """
    decision = record.get("decision", "HOLD")
    pnl = record.get("pnl", 0.0)
    conditions = record.get("conditions", "")
    parsed = parse_conditions(conditions)

    entry_price = parsed["price"]
    confidence = parsed["confidence"]
    direction_correct = pnl > 0

    # 推算 exit_price
    if entry_price > 0:
        exit_price = round(entry_price * (1 + pnl / 100), 2)
    else:
        exit_price = 0.0

    # 简化评分 (无 SL/TP 数据)
    if pnl > 0:
        grade = "C"  # 盈利但 R/R 未知
    elif pnl == 0:
        grade = "C"  # 持平
    else:
        # 所有亏损标记为 D (受控) - 老记录亏损都很小 (<1%)
        grade = "D"

    return {
        "grade": grade,
        "direction_correct": direction_correct,
        "entry_price": round(entry_price, 2),
        "exit_price": exit_price,
        "planned_sl": None,   # 老记录无此数据
        "planned_tp": None,   # 老记录无此数据
        "planned_rr": 0.0,    # 无法计算
        "actual_rr": 0.0,     # 无法计算
        "execution_quality": 0.0,  # 无法计算
        "exit_type": "MANUAL",     # 无法判断
        "confidence": confidence,
        "position_size_pct": 0.0,  # 未知
        "hold_duration_min": 0,    # 未知
        "_migrated": True,         # 标记为迁移数据，区别于真实评估
    }


def main():
    print(f"\n{BOLD}══════════════════════════════════════════{RESET}")
    print(f"{BOLD}  trading_memory 老记录迁移工具{RESET}")
    print(f"{BOLD}══════════════════════════════════════════{RESET}\n")

    # 1. 检查文件
    if not MEMORY_FILE.exists():
        print(f"{RED}  trading_memory.json 不存在: {MEMORY_FILE}{RESET}")
        return 1

    with open(MEMORY_FILE) as f:
        data = json.load(f)

    total = len(data)
    with_eval = [m for m in data if m.get("evaluation")]
    without_eval = [m for m in data if not m.get("evaluation")]

    print(f"  总记录数: {total}")
    print(f"  已有 evaluation: {len(with_eval)}")
    print(f"  需要迁移: {len(without_eval)}")

    if not without_eval:
        print(f"\n{GREEN}  所有记录都已有 evaluation，无需迁移!{RESET}")
        return 0

    # 2. 备份
    shutil.copy2(MEMORY_FILE, BACKUP_FILE)
    print(f"\n  备份已创建: {BACKUP_FILE}")

    # 3. 迁移
    print(f"\n{BOLD}  开始迁移...{RESET}\n")
    migrated = 0
    skipped = 0

    for record in data:
        if record.get("evaluation"):
            continue  # 已有 evaluation，跳过

        decision = record.get("decision", "HOLD")

        # 跳过 HOLD 决策 (非真实交易)
        if decision == "HOLD" and record.get("pnl", 0) == 0:
            skipped += 1
            ts = record.get("timestamp", "N/A")[:19]
            print(f"  {YELLOW}跳过{RESET} HOLD pnl=0 @ {ts}")
            continue

        evaluation = create_evaluation_for_old_record(record)
        record["evaluation"] = evaluation
        migrated += 1

        ts = record.get("timestamp", "N/A")[:19]
        pnl = record.get("pnl", 0)
        grade = evaluation["grade"]
        price = evaluation["entry_price"]
        print(f"  {GREEN}迁移{RESET} {decision:5s} pnl={pnl:+.2f}% → Grade {grade} | price=${price:,.0f} @ {ts}")

    # 4. 保存
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # 5. 验证
    with open(MEMORY_FILE) as f:
        verify = json.load(f)
    verify_eval = sum(1 for m in verify if m.get("evaluation"))

    print(f"\n{BOLD}══════════════════════════════════════════{RESET}")
    print(f"  迁移完成: {migrated} 条")
    print(f"  跳过: {skipped} 条 (HOLD/无效)")
    print(f"  验证: {verify_eval}/{len(verify)} 条含 evaluation")
    print(f"  备份: {BACKUP_FILE}")

    if verify_eval > 0:
        print(f"\n{GREEN}{BOLD}  Web 端 '交易质量评分' 应可正常显示数据了!{RESET}")
        print(f"  注: 老记录标记 _migrated=true, 无 R/R 数据 (显示 0.0)")
        print(f"  新交易平仓后将自动产生完整评估数据。")
    else:
        print(f"\n{RED}  迁移后仍无 evaluation 数据，请检查!{RESET}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
