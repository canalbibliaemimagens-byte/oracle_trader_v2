"""
Testes: executor/ — SyncLogic, LotMapper, RiskGuard, CommentBuilder, Executor
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from oracle_trader_v2.executor.sync_logic import Decision, decide, SyncState
from oracle_trader_v2.executor.lot_mapper import (
    SymbolConfig, LotMapper, load_symbol_configs,
)
from oracle_trader_v2.executor.risk_guard import RiskGuard, RiskCheck
from oracle_trader_v2.executor.comment_builder import CommentBuilder
from oracle_trader_v2.executor.executor import Executor, ACK
from oracle_trader_v2.core.models import Signal, Position, AccountInfo, OrderResult
from .helpers import make_signal, make_position, make_account


# ═══════════════════════════════════════════════════════════════════════════
# sync_logic.py — decide()
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncLogicDecide:

    def test_flat_flat_is_noop(self):
        s = make_signal(direction=0, action="WAIT")
        assert decide(s, None) == Decision.NOOP

    def test_flat_positioned_is_wait_sync(self):
        s = make_signal(direction=1, action="LONG_WEAK")
        assert decide(s, None) == Decision.WAIT_SYNC

    def test_same_direction_is_noop(self):
        s = make_signal(direction=1)
        pos = make_position(direction=1)
        assert decide(s, pos) == Decision.NOOP

    def test_real_long_signal_wait_is_close(self):
        s = make_signal(direction=0, action="WAIT")
        pos = make_position(direction=1)
        assert decide(s, pos) == Decision.CLOSE

    def test_real_short_signal_wait_is_close(self):
        s = make_signal(direction=0, action="WAIT")
        pos = make_position(direction=-1)
        assert decide(s, pos) == Decision.CLOSE

    def test_long_vs_short_is_close(self):
        s = make_signal(direction=-1, action="SHORT_WEAK")
        pos = make_position(direction=1)
        assert decide(s, pos) == Decision.CLOSE

    def test_short_vs_long_is_close(self):
        s = make_signal(direction=1, action="LONG_WEAK")
        pos = make_position(direction=-1)
        assert decide(s, pos) == Decision.CLOSE

    def test_decision_has_no_open_value(self):
        values = [d.value for d in Decision]
        assert "OPEN" not in values


# ═══════════════════════════════════════════════════════════════════════════
# sync_logic.py — SyncState (Regra de Borda)
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncState:

    def test_initial_state(self):
        ss = SyncState()
        assert ss.last_signal_dir == 0
        assert not ss.waiting_sync

    def test_wait_sync_enters_waiting(self):
        ss = SyncState()
        s = make_signal(direction=1)
        should_open = ss.update(s, Decision.WAIT_SYNC)
        assert not should_open
        assert ss.waiting_sync

    def test_signal_change_while_waiting_opens(self):
        ss = SyncState()
        s1 = make_signal(direction=1)
        ss.update(s1, Decision.WAIT_SYNC)

        # Signal changes to different direction → can open
        s2 = make_signal(direction=-1, action="SHORT_WEAK")
        should_open = ss.update(s2, Decision.NOOP)
        assert should_open
        assert not ss.waiting_sync

    def test_same_signal_while_waiting_no_open(self):
        ss = SyncState()
        s1 = make_signal(direction=1)
        ss.update(s1, Decision.WAIT_SYNC)

        s2 = make_signal(direction=1)
        should_open = ss.update(s2, Decision.WAIT_SYNC)
        assert not should_open

    def test_waiting_then_wait_signal_no_open(self):
        ss = SyncState()
        s1 = make_signal(direction=1)
        ss.update(s1, Decision.WAIT_SYNC)

        s2 = make_signal(direction=0, action="WAIT")
        should_open = ss.update(s2, Decision.NOOP)
        # Direction changed to 0 → not positioned → should not open
        assert not should_open

    def test_reset(self):
        ss = SyncState()
        s = make_signal(direction=1)
        ss.update(s, Decision.WAIT_SYNC)
        ss.reset()
        assert ss.last_signal_dir == 0
        assert not ss.waiting_sync


# ═══════════════════════════════════════════════════════════════════════════
# lot_mapper.py
# ═══════════════════════════════════════════════════════════════════════════

class TestLotMapper:

    @pytest.fixture
    def mapper(self):
        configs = {
            "EURUSD": SymbolConfig(lot_weak=0.01, lot_moderate=0.03, lot_strong=0.05),
        }
        return LotMapper(configs)

    def test_map_weak(self, mapper):
        assert mapper.map_lot("EURUSD", 1) == 0.01

    def test_map_moderate(self, mapper):
        assert mapper.map_lot("EURUSD", 2) == 0.03

    def test_map_strong(self, mapper):
        assert mapper.map_lot("EURUSD", 3) == 0.05

    def test_map_zero_intensity(self, mapper):
        assert mapper.map_lot("EURUSD", 0) == 0.0

    def test_map_unknown_symbol(self, mapper):
        assert mapper.map_lot("UNKNOWN", 1) == 0.0

    def test_get_config(self, mapper):
        cfg = mapper.get_config("EURUSD")
        assert cfg is not None
        assert cfg.lot_weak == 0.01

    def test_get_config_missing(self, mapper):
        assert mapper.get_config("UNKNOWN") is None


class TestLoadSymbolConfigs:

    def test_loads_json(self, tmp_config):
        configs = load_symbol_configs(tmp_config)
        assert "EURUSD" in configs
        assert "GBPUSD" in configs
        # Underscore keys should be skipped
        assert "_risk" not in configs
        assert "_comment" not in configs

    def test_config_values(self, tmp_config):
        configs = load_symbol_configs(tmp_config)
        cfg = configs["EURUSD"]
        assert cfg.enabled is True
        assert cfg.lot_weak == 0.01
        assert cfg.max_spread_pips == 2.0

    def test_disabled_symbol(self, tmp_config):
        configs = load_symbol_configs(tmp_config)
        assert configs["GBPUSD"].enabled is False


# ═══════════════════════════════════════════════════════════════════════════
# risk_guard.py
# ═══════════════════════════════════════════════════════════════════════════

class TestRiskGuard:

    @pytest.fixture
    def guard(self):
        return RiskGuard({
            "dd_limit_pct": 5.0,
            "dd_emergency_pct": 10.0,
            "initial_balance": 10000,
            "max_consecutive_losses": 3,
        })

    def test_all_pass_normal(self, guard):
        acc = make_account(balance=10000, equity=9800, free_margin=9000)
        cfg = SymbolConfig(max_spread_pips=3.0)
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert result.passed

    def test_drawdown_limit_blocks(self, guard):
        acc = make_account(equity=9400, free_margin=9000)
        cfg = SymbolConfig()
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert not result.passed
        assert "DD_LIMIT" in result.reason

    def test_drawdown_emergency_blocks(self, guard):
        acc = make_account(equity=8900, free_margin=8500)
        cfg = SymbolConfig()
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert not result.passed
        assert "EMERGENCY" in result.reason

    def test_margin_blocks(self, guard):
        acc = make_account(free_margin=0.5)
        cfg = SymbolConfig()
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert not result.passed
        assert "MARGIN" in result.reason

    def test_circuit_breaker_blocks(self, guard):
        for _ in range(3):
            guard.record_trade_result(-10)
        acc = make_account()
        cfg = SymbolConfig()
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert not result.passed
        assert "CIRCUIT_BREAKER" in result.reason

    def test_circuit_breaker_resets_on_win(self, guard):
        guard.record_trade_result(-10)
        guard.record_trade_result(-10)
        guard.record_trade_result(5)  # Win resets
        assert guard.consecutive_losses == 0

    def test_reset_circuit_breaker(self, guard):
        for _ in range(3):
            guard.record_trade_result(-10)
        guard.reset_circuit_breaker()
        assert guard.consecutive_losses == 0

    def test_spread_check_blocks(self, guard):
        guard.update_spread("EURUSD", 5.0)  # High spread
        acc = make_account()
        cfg = SymbolConfig(max_spread_pips=2.0)
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert not result.passed
        assert "SPREAD" in result.reason

    def test_spread_check_passes(self, guard):
        guard.update_spread("EURUSD", 1.5)
        acc = make_account()
        cfg = SymbolConfig(max_spread_pips=2.0)
        result = guard.check_all("EURUSD", 0.01, acc, cfg)
        assert result.passed

    def test_spread_unknown_failopen(self, guard):
        # No spread data → should pass (fail-open)
        acc = make_account()
        cfg = SymbolConfig(max_spread_pips=2.0)
        result = guard._check_spread("NOSPREAD", cfg)
        assert result.passed

    def test_zero_initial_balance_bypasses_dd(self, guard):
        guard.initial_balance = 0
        acc = make_account(equity=5000)
        result = guard._check_drawdown(acc)
        assert result.passed


# ═══════════════════════════════════════════════════════════════════════════
# comment_builder.py
# ═══════════════════════════════════════════════════════════════════════════

class TestCommentBuilder:

    def test_build_format(self):
        comment = CommentBuilder.build(
            hmm_state=3, action_index=2, intensity=1,
            balance=9850.5, drawdown_pct=1.5, virtual_pnl=-3.25,
        )
        assert comment.startswith("O|2.0|")
        assert len(comment) <= 100

    def test_parse_roundtrip(self):
        comment = CommentBuilder.build(
            hmm_state=4, action_index=5, intensity=3,
            balance=10000, drawdown_pct=0.0, virtual_pnl=12.50,
        )
        parsed = CommentBuilder.parse(comment)
        assert parsed["hmm_state"] == 4
        assert parsed["action_index"] == 5
        assert parsed["intensity"] == 3
        assert parsed["balance"] == 10000
        assert parsed["drawdown_pct"] == 0.0
        assert parsed["virtual_pnl"] == 12.50

    def test_parse_invalid_empty(self):
        assert CommentBuilder.parse("") == {}

    def test_parse_invalid_prefix(self):
        assert CommentBuilder.parse("X|1|2|3|4|5|6|7") == {}

    def test_parse_invalid_short(self):
        assert CommentBuilder.parse("O|2.0|1") == {}

    def test_build_truncates_at_100(self):
        comment = CommentBuilder.build(
            hmm_state=999, action_index=999, intensity=999,
            balance=99999999999.99, drawdown_pct=99999.9,
            virtual_pnl=99999999.99,
        )
        assert len(comment) <= 100


# ═══════════════════════════════════════════════════════════════════════════
# executor.py
# ═══════════════════════════════════════════════════════════════════════════

class TestExecutor:

    @pytest.fixture
    def executor(self, mock_connector, tmp_config):
        return Executor(connector=mock_connector, config_path=tmp_config)

    @pytest.mark.asyncio
    async def test_process_signal_no_config(self, executor):
        s = make_signal(symbol="UNKNOWN")
        ack = await executor.process_signal(s)
        assert ack.status == "SKIP"
        assert ack.reason == "NO_CONFIG"

    @pytest.mark.asyncio
    async def test_process_signal_disabled_symbol(self, executor):
        s = make_signal(symbol="GBPUSD")
        ack = await executor.process_signal(s)
        assert ack.status == "SKIP"
        assert ack.reason == "DISABLED"

    @pytest.mark.asyncio
    async def test_process_signal_paused(self, executor):
        executor.pause()
        s = make_signal(symbol="EURUSD")
        ack = await executor.process_signal(s)
        assert ack.status == "SKIP"
        assert ack.reason == "PAUSED"

    @pytest.mark.asyncio
    async def test_pause_resume(self, executor):
        executor.pause()
        assert executor.paused
        executor.resume()
        assert not executor.paused

    @pytest.mark.asyncio
    async def test_process_wait_signal_flat(self, executor):
        s = make_signal(action="WAIT", direction=0, intensity=0)
        ack = await executor.process_signal(s)
        assert ack.status == "OK"
        assert ack.reason == "SYNCED"

    @pytest.mark.asyncio
    async def test_process_signal_wait_sync(self, executor, mock_connector):
        """First positioned signal with no position → WAIT_SYNC."""
        await mock_connector.connect()
        s = make_signal(direction=1, action="LONG_WEAK", intensity=1)
        ack = await executor.process_signal(s)
        assert ack.status == "OK"
        assert ack.reason == "WAITING_SYNC"

    @pytest.mark.asyncio
    async def test_close_position(self, executor, mock_connector):
        """Close existing position."""
        await mock_connector.connect()
        await mock_connector.open_order("EURUSD", 1, 0.01)
        result = await executor.close_position("EURUSD")
        assert result is True

    @pytest.mark.asyncio
    async def test_close_position_no_position(self, executor, mock_connector):
        await mock_connector.connect()
        result = await executor.close_position("EURUSD")
        assert result is False

    @pytest.mark.asyncio
    async def test_close_all(self, executor, mock_connector):
        await mock_connector.connect()
        await mock_connector.open_order("EURUSD", 1, 0.01)
        count = await executor.close_all()
        assert count == 1

    def test_get_state(self, executor):
        state = executor.get_state()
        assert "paused" in state
        assert "symbols" in state
        assert "EURUSD" in state["symbols"]

    def test_action_to_index(self):
        assert Executor._action_to_index("LONG_WEAK") == 1
        assert Executor._action_to_index("WAIT") == 0
        assert Executor._action_to_index("INVALID") == 0

    @pytest.mark.asyncio
    async def test_risk_guard_loaded(self, executor):
        """Verify _risk section from JSON was loaded."""
        assert executor.risk_guard is not None
        assert executor.risk_guard.initial_balance == 10000
        assert executor.risk_guard.dd_limit_pct == 5.0
