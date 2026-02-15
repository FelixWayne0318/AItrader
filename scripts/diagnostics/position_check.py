"""
Position Check Module

Checks Binance account positions and balance.

v4.8 Updates:
- Get leverage from Binance API instead of hardcoded value
- Display cumulative position info for add-on scenarios

v4.8.1 Updates:
- Complete position fields to match production _get_current_position_data() (25 fields)
- Fix field name consistency (pnl_pct → pnl_percentage)
- Complete account_context fields to match production _get_account_context() (13 fields)
- Fix field names (max_usdt → max_position_value, remaining_capacity → available_capacity)
"""

from typing import Dict, Optional

from .base import DiagnosticContext, DiagnosticStep


class PositionChecker(DiagnosticStep):
    """
    Check current Binance positions.

    Uses BinanceAccountFetcher to get real position data.
    """

    name = "检查 Binance 真实持仓"

    def run(self) -> bool:
        print("-" * 70)

        try:
            from utils.binance_account import BinanceAccountFetcher

            account_fetcher = BinanceAccountFetcher()
            positions = account_fetcher.get_positions(symbol=self.ctx.symbol)

            # v4.8: Get real leverage from Binance
            binance_leverage = account_fetcher.get_leverage(self.ctx.symbol)
            self.ctx.binance_leverage = binance_leverage
            print(f"  📊 杠杆倍数 (from Binance): {binance_leverage}x")

            if positions:
                pos = positions[0]
                pos_amt = float(pos.get('positionAmt', 0))
                entry_price = float(pos.get('entryPrice', 0))
                unrealized_pnl = float(pos.get('unRealizedProfit', 0))

                if pos_amt != 0:
                    self._process_position(pos_amt, entry_price, unrealized_pnl, binance_leverage)
                else:
                    print("  ✅ 无持仓")
            else:
                print("  ✅ 无持仓")

            # Get account balance
            self._get_account_balance(account_fetcher, binance_leverage)

            return True

        except Exception as e:
            self.ctx.add_warning(f"持仓检查失败: {e}")
            print("  → 继续假设无持仓")
            return True  # Non-critical

    def _process_position(
        self,
        pos_amt: float,
        entry_price: float,
        unrealized_pnl: float,
        leverage: int = 10
    ) -> None:
        """
        Process and display position data.

        v4.8.1: Complete all 25 fields to match production _get_current_position_data()
        """
        side = 'long' if pos_amt > 0 else 'short'
        quantity = abs(pos_amt)
        avg_px = entry_price
        current_price = self.ctx.current_price

        # Calculate PnL if API returns 0 but we have prices
        if unrealized_pnl == 0 and entry_price > 0 and current_price > 0:
            if side == 'long':
                unrealized_pnl = (current_price - entry_price) * quantity
            else:
                unrealized_pnl = (entry_price - current_price) * quantity

        # === Tier 1: pnl_percentage (名称与生产代码一致) ===
        pnl_percentage = 0.0
        if avg_px > 0 and current_price:
            if side == 'long':
                pnl_percentage = ((current_price - avg_px) / avg_px) * 100
            else:
                pnl_percentage = ((avg_px - current_price) / avg_px) * 100

        # === Tier 1: duration_minutes, entry_timestamp ===
        # 诊断脚本无法获取入场时间，标记为 None
        duration_minutes = None  # 需要 NautilusTrader position.ts_opened
        entry_timestamp = None

        # === Tier 1: sl_price, tp_price, risk_reward_ratio ===
        # 诊断脚本无法获取 trailing_stop_state，标记为 None
        sl_price = None
        tp_price = None
        risk_reward_ratio = None

        # === Tier 2: peak_pnl_pct, worst_pnl_pct ===
        # 诊断脚本无法获取历史极值，使用当前 PnL 作为估计
        peak_pnl_pct = round(pnl_percentage, 2) if pnl_percentage > 0 else 0.0
        worst_pnl_pct = round(pnl_percentage, 2) if pnl_percentage < 0 else 0.0

        # === Tier 2: entry_confidence ===
        # 诊断脚本无法获取上次信号，标记为 None
        entry_confidence = None

        # === Tier 2: margin_used_pct ===
        margin_used_pct = None
        equity = getattr(self.ctx, 'account_balance', {}).get('total_balance', 0)
        position_value = quantity * current_price if current_price else 0
        if equity and equity > 0 and current_price:
            margin_used_pct = round((position_value / equity) * 100, 2)

        # === v4.7: Liquidation Risk Fields (CRITICAL) ===
        maintenance_margin_ratio = 0.004  # Binance standard for 20x tier
        liquidation_price = None
        liquidation_buffer_pct = None
        is_liquidation_risk_high = False

        if avg_px > 0 and leverage > 0:
            if side == 'long':
                liquidation_price = avg_px * (1 - 1/leverage + maintenance_margin_ratio)
                if current_price and liquidation_price > 0:
                    liquidation_buffer_pct = ((current_price - liquidation_price) / current_price) * 100
            else:  # short
                liquidation_price = avg_px * (1 + 1/leverage - maintenance_margin_ratio)
                if current_price and liquidation_price > 0:
                    liquidation_buffer_pct = ((liquidation_price - current_price) / current_price) * 100

            if liquidation_buffer_pct is not None:
                liquidation_buffer_pct = round(max(0, liquidation_buffer_pct), 2)
                is_liquidation_risk_high = liquidation_buffer_pct < 10

        # === v4.7: Funding Rate Fields (CRITICAL) ===
        # 从 Binance funding rate 数据获取 (如果可用)
        funding_rate_current = None
        funding_rate_cumulative_usd = None
        effective_pnl_after_funding = None
        daily_funding_cost_usd = None

        if self.ctx.binance_funding_rate:
            fr_data = self.ctx.binance_funding_rate
            funding_rate_current = fr_data.get('funding_rate', 0)

            if funding_rate_current and position_value > 0:
                # Daily funding cost = position_value * |rate| * 3 settlements/day
                daily_funding_cost_usd = round(position_value * abs(funding_rate_current) * 3, 2)

                # 无法计算累计 funding (需要持仓时间)
                # funding_rate_cumulative_usd 和 effective_pnl_after_funding 保持 None

        # === v4.7: Drawdown Attribution Fields (RECOMMENDED) ===
        max_drawdown_pct = None
        max_drawdown_duration_bars = None
        consecutive_lower_lows = 0  # 默认 0

        # 如果有 peak 和 current PnL，计算 drawdown
        if peak_pnl_pct is not None and pnl_percentage is not None:
            if peak_pnl_pct > pnl_percentage:
                max_drawdown_pct = round(peak_pnl_pct - pnl_percentage, 2)
            else:
                max_drawdown_pct = 0.0

        # v4.8.1: Complete 25 fields matching production _get_current_position_data()
        self.ctx.current_position = {
            # === Basic (4 fields) ===
            'side': side,
            'quantity': quantity,
            'avg_px': avg_px,
            'unrealized_pnl': unrealized_pnl,
            # === Tier 1 (6 fields) ===
            'pnl_percentage': round(pnl_percentage, 2),  # 名称修正: pnl_pct → pnl_percentage
            'duration_minutes': duration_minutes,
            'entry_timestamp': entry_timestamp,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'risk_reward_ratio': risk_reward_ratio,
            # === Tier 2 (5 fields) ===
            'peak_pnl_pct': peak_pnl_pct,
            'worst_pnl_pct': worst_pnl_pct,
            'entry_confidence': entry_confidence,
            'margin_used_pct': margin_used_pct,
            'current_price': float(current_price) if current_price else None,
            # === v4.7: Liquidation Risk (3 fields) ===
            'liquidation_price': round(liquidation_price, 2) if liquidation_price else None,
            'liquidation_buffer_pct': liquidation_buffer_pct,
            'is_liquidation_risk_high': is_liquidation_risk_high,
            # === v4.7: Funding Rate (4 fields) ===
            'funding_rate_current': funding_rate_current,
            'funding_rate_cumulative_usd': funding_rate_cumulative_usd,
            'effective_pnl_after_funding': effective_pnl_after_funding,
            'daily_funding_cost_usd': daily_funding_cost_usd,
            # === v4.7: Drawdown Attribution (3 fields) ===
            'max_drawdown_pct': max_drawdown_pct,
            'max_drawdown_duration_bars': max_drawdown_duration_bars,
            'consecutive_lower_lows': consecutive_lower_lows,
            # === v4.8: Extra for diagnostic display ===
            'position_value_usdt': position_value,
        }

        print(f"  ⚠️ 检测到现有持仓!")
        print(f"     方向: {side.upper()}")
        bc = self.ctx.base_currency
        print(f"     数量: ${position_value:,.0f} ({quantity:.4f} {bc})")
        print(f"     持仓价值: ${position_value:,.2f}")
        print(f"     入场价: ${avg_px:,.2f}")
        print(f"     未实现盈亏: ${unrealized_pnl:,.2f}")
        print(f"     盈亏比例: {pnl_percentage:+.2f}%")

        # v4.5 Tier 2: margin_used_pct
        if margin_used_pct is not None:
            print(f"     保证金占用: {margin_used_pct:.1f}%")

        # v4.7: Display liquidation risk
        if liquidation_price is not None:
            risk_emoji = "🔴" if is_liquidation_risk_high else "🟢"
            print(f"     爆仓价: ${liquidation_price:,.2f}")
            print(f"     爆仓距离: {risk_emoji} {liquidation_buffer_pct:.1f}%")
            if is_liquidation_risk_high:
                print(f"     ⚠️ 警告: 爆仓风险高 (<10%)")

        # v5.1: Display funding rate impact (settled rate)
        if funding_rate_current is not None:
            fr_pct = funding_rate_current * 100
            print(f"     已结算费率: {fr_pct:+.4f}%")
            if daily_funding_cost_usd:
                print(f"     日资金费用: ${daily_funding_cost_usd:,.2f}")

    def _get_account_balance(self, account_fetcher, leverage: int = 10) -> None:
        """
        Get and display account balance.

        v4.8.1: Complete all 13 fields to match production _get_account_context()
        Field names fixed to match what _format_account() expects:
        - max_usdt → max_position_value
        - remaining_capacity → available_capacity
        - Added: max_position_ratio, capacity_used_pct
        """
        print()
        print("  📊 账户资金详情:")

        try:
            balance_data = account_fetcher.get_balance()
            self.ctx.account_balance = balance_data

            total_balance = balance_data.get('total_balance', 0)
            available_balance = balance_data.get('available_balance', 0)
            account_unrealized_pnl = balance_data.get('unrealized_pnl', 0)

            used_margin = total_balance - available_balance
            margin_ratio = (
                (available_balance / total_balance * 100)
                if total_balance > 0 else 0
            )

            print(f"     总余额:       ${total_balance:,.2f}")
            print(f"     可用余额:     ${available_balance:,.2f}")
            print(f"     已用保证金:   ${used_margin:,.2f}")
            print(f"     保证金率:     {margin_ratio:.1f}%")
            print(f"     总未实现PnL:  ${account_unrealized_pnl:,.2f}")

            # v4.8: Calculate max_position_value for position sizing display
            max_position_ratio = 0.30  # Default from base.yaml
            equity = total_balance
            max_position_value = equity * max_position_ratio * leverage

            print()
            print(f"  📊 v4.8 仓位计算参数:")
            print(f"     equity: ${equity:,.2f}")
            print(f"     leverage: {leverage}x")
            print(f"     max_position_ratio: {max_position_ratio*100:.0f}%")
            print(f"     max_position_value: ${max_position_value:,.2f}")

            # v4.8: Calculate capacity metrics
            current_position_value = 0
            if self.ctx.current_position:
                current_position_value = self.ctx.current_position.get('position_value_usdt', 0)

            available_capacity = max(0, max_position_value - current_position_value)
            capacity_used_pct = 0.0
            if max_position_value > 0:
                capacity_used_pct = (current_position_value / max_position_value) * 100

            # Determine if can add position (at least 10% capacity remaining)
            can_add_position = capacity_used_pct < 90

            # Get liquidation buffer from position if available
            liq_buffer_min = None
            if self.ctx.current_position:
                liq_buffer_min = self.ctx.current_position.get('liquidation_buffer_pct')

            # v4.7: Safer check - also consider liquidation buffer
            can_add_position_safely = can_add_position and (
                liq_buffer_min is None or liq_buffer_min > 15
            )

            # v4.7: Calculate funding costs from position data
            total_daily_funding_cost_usd = None
            total_cumulative_funding_paid_usd = None

            if self.ctx.current_position:
                daily_cost = self.ctx.current_position.get('daily_funding_cost_usd')
                if daily_cost is not None:
                    total_daily_funding_cost_usd = daily_cost
                cumulative = self.ctx.current_position.get('funding_rate_cumulative_usd')
                if cumulative is not None:
                    total_cumulative_funding_paid_usd = cumulative

            # v4.8.1: Complete 13 fields matching production _get_account_context()
            # Field names fixed to match what _format_account() expects
            self.ctx.account_context = {
                # === Core fields (8 fields) ===
                'equity': round(equity, 2),
                'leverage': leverage,
                'max_position_ratio': max_position_ratio,  # v4.8.1: Added
                'max_position_value': round(max_position_value, 2),  # 名称修正: max_usdt → max_position_value
                'current_position_value': round(current_position_value, 2),
                'available_capacity': round(available_capacity, 2),  # 名称修正: remaining_capacity → available_capacity
                'capacity_used_pct': round(capacity_used_pct, 1),  # v4.8.1: Added
                'can_add_position': can_add_position,
                # === v4.7: Portfolio-Level Risk Fields (5 fields) ===
                'total_unrealized_pnl_usd': round(account_unrealized_pnl, 2),
                'liquidation_buffer_portfolio_min_pct': round(liq_buffer_min, 2) if liq_buffer_min is not None else None,
                'total_daily_funding_cost_usd': round(total_daily_funding_cost_usd, 2) if total_daily_funding_cost_usd is not None else None,
                'total_cumulative_funding_paid_usd': round(total_cumulative_funding_paid_usd, 2) if total_cumulative_funding_paid_usd is not None else None,
                'can_add_position_safely': can_add_position_safely,
            }

            # v4.8: Display cumulative mode capacity
            if self.ctx.current_position:
                print()
                print(f"  📊 v4.8 累加模式状态:")
                print(f"     当前持仓价值: ${current_position_value:,.2f}")
                print(f"     剩余可加仓: ${available_capacity:,.2f}")
                print(f"     已用容量: {capacity_used_pct:.1f}%")
                if available_capacity <= 0:
                    print(f"     ⚠️ 已达 max_position_value 上限，无法加仓")

            # v4.7: Display portfolio risk
            print()
            print("  ⚠️ 组合风险:")
            print(f"     容量使用率: {capacity_used_pct:.1f}%")
            if liq_buffer_min is not None:
                risk_emoji = "🔴" if liq_buffer_min < 10 else "🟡" if liq_buffer_min < 15 else "🟢"
                print(f"     最小爆仓距离: {risk_emoji} {liq_buffer_min:.1f}%")
            if total_daily_funding_cost_usd:
                print(f"     日资金费用: ${total_daily_funding_cost_usd:,.2f}")
            safety_emoji = "✅" if can_add_position_safely else "⚠️"
            safety_text = "可安全加仓" if can_add_position_safely else "加仓需谨慎"
            print(f"     加仓建议: {safety_emoji} {safety_text}")

        except Exception as e:
            self.ctx.add_warning(f"无法获取账户余额: {e}")


class MemorySystemChecker(DiagnosticStep):
    """
    Check AI learning memory system (v3.12).

    Validates memory file loading, saving, and format.
    """

    name = "记忆系统健康检查 (v3.12 AI Learning)"

    def run(self) -> bool:
        print("-" * 70)

        try:
            import json
            from pathlib import Path

            memory_file = "data/trading_memory.json"
            memory_path = self.ctx.project_root / memory_file

            print(f"  📂 记忆文件路径: {memory_path}")

            if memory_path.exists():
                self._check_memory_file(memory_path)
            else:
                print(f"  ⚠️ 记忆文件不存在 (系统刚启动)")
                print(f"     → 首次交易后将自动创建")

            # Check MultiAgentAnalyzer memory system
            self._check_analyzer_memory()

            print()
            print("  ✅ 记忆系统健康检查完成")
            return True

        except Exception as e:
            self.ctx.add_warning(f"记忆系统检查失败: {e}")
            return True  # Non-critical

    def _check_memory_file(self, memory_path) -> None:
        """Check memory file content."""
        import json

        print(f"  ✅ 记忆文件存在")

        with open(memory_path, 'r', encoding='utf-8') as f:
            memories = json.load(f)

        print(f"  📊 记忆条目数量: {len(memories)}")

        if memories:
            successes = [m for m in memories if m.get('pnl', 0) > 0]
            failures = [m for m in memories if m.get('pnl', 0) <= 0]

            print(f"     ✅ 成功交易: {len(successes)} 条")
            print(f"     ❌ 失败交易: {len(failures)} 条")

            # Show recent 3 memories
            print()
            print("  📝 最近 3 条记忆:")
            for mem in memories[-3:]:
                decision = mem.get('decision', 'N/A')
                pnl = mem.get('pnl', 0)
                conditions = str(mem.get('conditions', 'N/A') or 'N/A')[:50]
                timestamp = str(mem.get('timestamp', 'N/A') or 'N/A')[:19]
                emoji = '✅' if pnl > 0 else '❌'
                print(f"     {emoji} [{timestamp}] {decision} → {pnl:+.2f}%")
                print(f"        Conditions: {conditions}...")

            # Validate format
            print()
            print("  🔍 记忆格式验证:")
            required_fields = ['decision', 'pnl', 'conditions', 'lesson', 'timestamp']
            latest = memories[-1] if memories else {}
            for field in required_fields:
                has_field = field in latest
                status = '✅ 存在' if has_field else '❌ 缺失'
                print(f"     {status}: {field}")
        else:
            print("  ℹ️ 记忆为空 (系统刚启动，尚无交易记录)")

    def _check_analyzer_memory(self) -> None:
        """Check MultiAgentAnalyzer memory system."""
        print()
        print("  🧠 MultiAgentAnalyzer 记忆系统状态:")

        # v2.4.8: Initialize multi_agent if needed (just for memory check, no API call)
        if self.ctx.multi_agent is None:
            try:
                from agents.multi_agent_analyzer import MultiAgentAnalyzer as MAAnalyzer
                import os

                api_key = os.getenv('DEEPSEEK_API_KEY')
                if api_key:
                    # Create instance just for memory check (won't make API calls)
                    self.ctx.multi_agent = MAAnalyzer(
                        api_key=api_key,
                        model="deepseek-chat",
                        temperature=0.3,
                        debate_rounds=2,
                        memory_file="data/trading_memory.json",
                    )
            except Exception as e:
                print(f"     ⚠️ multi_agent 初始化失败: {e}")

        if self.ctx.multi_agent is not None:
            mem_count = len(getattr(self.ctx.multi_agent, 'decision_memory', []))
            mem_file = getattr(self.ctx.multi_agent, 'memory_file', 'N/A')
            print(f"     → 已加载记忆: {mem_count} 条")
            print(f"     → 记忆文件: {mem_file}")

            if hasattr(self.ctx.multi_agent, '_get_past_memories'):
                past_memories = self.ctx.multi_agent._get_past_memories()
                if past_memories:
                    print(f"     → 传给 AI 的记忆摘要: {len(past_memories)} 字符")
                    preview = past_memories[:200].replace('\n', ' ')
                    print(f"     → 预览: {preview}...")
                else:
                    print(f"     → 传给 AI 的记忆摘要: (空 - 无历史交易)")
        else:
            print(f"     ⚠️ multi_agent 未初始化 (缺少 DEEPSEEK_API_KEY?)")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
