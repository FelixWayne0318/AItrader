"""
Position Check Module

Checks Binance account positions and balance.

v4.8 Updates:
- Get leverage from Binance API instead of hardcoded value
- Display cumulative position info for add-on scenarios
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
        """Process and display position data."""
        side = 'long' if pos_amt > 0 else 'short'

        # Calculate PnL if API returns 0 but we have prices
        if unrealized_pnl == 0 and entry_price > 0 and self.ctx.current_price > 0:
            if side == 'long':
                unrealized_pnl = (self.ctx.current_price - entry_price) * abs(pos_amt)
            else:
                unrealized_pnl = (entry_price - self.ctx.current_price) * abs(pos_amt)

        # Calculate PnL percentage
        pnl_pct = 0.0
        if entry_price > 0 and abs(pos_amt) > 0:
            pnl_pct = (unrealized_pnl / (entry_price * abs(pos_amt))) * 100

        # v4.8: Use real leverage from Binance
        maintenance_margin_ratio = 0.004  # Binance standard for 20x tier
        liquidation_price = None
        liquidation_buffer_pct = None
        is_liquidation_risk_high = False

        if entry_price > 0 and leverage > 0:
            if side == 'long':
                liquidation_price = entry_price * (1 - 1/leverage + maintenance_margin_ratio)
                if self.ctx.current_price and liquidation_price > 0:
                    liquidation_buffer_pct = ((self.ctx.current_price - liquidation_price) / self.ctx.current_price) * 100
            else:  # short
                liquidation_price = entry_price * (1 + 1/leverage - maintenance_margin_ratio)
                if self.ctx.current_price and liquidation_price > 0:
                    liquidation_buffer_pct = ((liquidation_price - self.ctx.current_price) / self.ctx.current_price) * 100

            if liquidation_buffer_pct is not None:
                liquidation_buffer_pct = round(max(0, liquidation_buffer_pct), 2)
                is_liquidation_risk_high = liquidation_buffer_pct < 10

        # v4.8: Calculate position value for cumulative mode display
        position_value = abs(pos_amt) * self.ctx.current_price if self.ctx.current_price else 0

        self.ctx.current_position = {
            'side': side,
            'quantity': abs(pos_amt),
            'entry_price': entry_price,
            'avg_px': entry_price,  # Compatibility
            'unrealized_pnl': unrealized_pnl,
            'pnl_pct': pnl_pct,
            # v4.7: Liquidation Risk Fields (CRITICAL)
            'liquidation_price': liquidation_price,
            'liquidation_buffer_pct': liquidation_buffer_pct,
            'is_liquidation_risk_high': is_liquidation_risk_high,
            # v4.7: Funding rate (will be updated later if available)
            'funding_rate_current': None,
            'daily_funding_cost_usd': None,
            # v4.7: Drawdown (cannot calculate without history)
            'max_drawdown_pct': None,
            'peak_pnl_pct': pnl_pct if pnl_pct > 0 else 0,
            # v4.8: Position value for cumulative mode
            'position_value_usdt': position_value,
        }

        print(f"  ⚠️ 检测到现有持仓!")
        print(f"     方向: {side.upper()}")
        print(f"     数量: {abs(pos_amt):.4f} BTC")
        print(f"     持仓价值: ${position_value:,.2f}")
        print(f"     入场价: ${entry_price:,.2f}")
        print(f"     未实现盈亏: ${unrealized_pnl:,.2f}")
        print(f"     盈亏比例: {pnl_pct:+.2f}%")

        # v4.7: Display liquidation risk
        if liquidation_price is not None:
            risk_emoji = "🔴" if is_liquidation_risk_high else "🟢"
            print(f"     爆仓价: ${liquidation_price:,.2f}")
            print(f"     爆仓距离: {risk_emoji} {liquidation_buffer_pct:.1f}%")
            if is_liquidation_risk_high:
                print(f"     ⚠️ 警告: 爆仓风险高 (<10%)")

    def _get_account_balance(self, account_fetcher, leverage: int = 10) -> None:
        """Get and display account balance."""
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

            # v4.8: Calculate max_usdt for position sizing display
            max_position_ratio = 0.30  # Default from base.yaml
            max_usdt = total_balance * max_position_ratio * leverage
            print()
            print(f"  📊 v4.8 仓位计算参数:")
            print(f"     equity: ${total_balance:,.2f}")
            print(f"     leverage: {leverage}x")
            print(f"     max_position_ratio: {max_position_ratio*100:.0f}%")
            print(f"     max_usdt: ${max_usdt:,.2f}")

            # v4.7: Build account_context for AI
            used_margin_pct = ((total_balance - available_balance) / total_balance * 100) if total_balance > 0 else 0
            can_add_position = used_margin_pct < 80  # 80% threshold

            # Get liquidation buffer from position if available
            liq_buffer_min = None
            if self.ctx.current_position:
                liq_buffer_min = self.ctx.current_position.get('liquidation_buffer_pct')

            can_add_safely = can_add_position and (liq_buffer_min is None or liq_buffer_min > 15)

            # v4.8: Calculate remaining capacity for cumulative mode
            current_position_value = 0
            if self.ctx.current_position:
                current_position_value = self.ctx.current_position.get('position_value_usdt', 0)
            remaining_capacity = max(0, max_usdt - current_position_value)

            self.ctx.account_context = {
                'equity': total_balance,
                'available_margin': available_balance,
                'used_margin_pct': round(used_margin_pct, 2),
                'leverage': leverage,  # v4.8: Use real leverage
                'can_add_position': can_add_position,
                # v4.7: Portfolio risk fields
                'total_unrealized_pnl_usd': account_unrealized_pnl,
                'liquidation_buffer_portfolio_min_pct': liq_buffer_min,
                'total_daily_funding_cost_usd': None,  # Would need funding rate data
                'total_cumulative_funding_paid_usd': None,
                'can_add_position_safely': can_add_safely,
                # v4.8: Cumulative position sizing fields
                'max_usdt': max_usdt,
                'current_position_value': current_position_value,
                'remaining_capacity': remaining_capacity,
            }

            # v4.8: Display cumulative mode capacity
            if self.ctx.current_position:
                print()
                print(f"  📊 v4.8 累加模式状态:")
                print(f"     当前持仓价值: ${current_position_value:,.2f}")
                print(f"     剩余可加仓: ${remaining_capacity:,.2f}")
                capacity_pct = (current_position_value / max_usdt * 100) if max_usdt > 0 else 0
                print(f"     已用容量: {capacity_pct:.1f}%")
                if remaining_capacity <= 0:
                    print(f"     ⚠️ 已达 max_usdt 上限，无法加仓")

            # v4.7: Display portfolio risk
            print()
            print("  ⚠️ 组合风险:")
            print(f"     已用保证金比例: {used_margin_pct:.1f}%")
            if liq_buffer_min is not None:
                risk_emoji = "🔴" if liq_buffer_min < 10 else "🟡" if liq_buffer_min < 15 else "🟢"
                print(f"     最小爆仓距离: {risk_emoji} {liq_buffer_min:.1f}%")
            safety_emoji = "✅" if can_add_safely else "⚠️"
            safety_text = "可安全加仓" if can_add_safely else "加仓需谨慎"
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
            print(f"     ⚠️ multi_agent 未初始化")

    def should_skip(self) -> bool:
        return self.ctx.summary_mode
