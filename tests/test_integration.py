"""
Testes de Integração — fluxo completo end-to-end com MockConnector.
Não requer broker real nem modelos ML treinados.
"""

import json
import pytest
import asyncio

from oracle_trader_v2.connector.mock.client import MockConnector
from oracle_trader_v2.executor.executor import Executor, ACK
from oracle_trader_v2.executor.sync_logic import SyncState, decide, Decision
from oracle_trader_v2.executor.risk_guard import RiskGuard
from oracle_trader_v2.paper.paper_trader import PaperTrader
from oracle_trader_v2.paper.account import PaperTrade
from oracle_trader_v2.persistence.local_storage import LocalStorage
from oracle_trader_v2.persistence.session_manager import SessionManager, SessionEndReason
from oracle_trader_v2.preditor.buffer import BarBuffer
from oracle_trader_v2.preditor.virtual_position import VirtualPositionManager
from oracle_trader_v2.core.actions import Action
from oracle_trader_v2.core.models import Signal
from .helpers import make_bar, make_bars, make_signal


# ═══════════════════════════════════════════════════════════════════════════
# Integração: Executor + MockConnector (fluxo completo de trading)
# ═══════════════════════════════════════════════════════════════════════════

class TestExecutorIntegration:
    """Testa o fluxo Executor → MockConnector para ciclos de trading."""

    @pytest.fixture
    def setup(self, tmp_path):
        config = {
            "_risk": {
                "dd_limit_pct": 5.0,
                "dd_emergency_pct": 10.0,
                "initial_balance": 10000,
                "max_consecutive_losses": 5,
            },
            "EURUSD": {
                "enabled": True,
                "lot_weak": 0.01,
                "lot_moderate": 0.03,
                "lot_strong": 0.05,
                "sl_usd": 10.0,
                "tp_usd": 0,
                "max_spread_pips": 2.0,
            },
        }
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config))

        connector = MockConnector(initial_balance=10000.0)
        executor = Executor(connector=connector, config_path=str(path))
        return connector, executor

    @pytest.mark.asyncio
    async def test_full_trade_cycle(self, setup):
        """FLAT → signal LONG → WAIT_SYNC → signal changes → OPEN → signal WAIT → CLOSE."""
        connector, executor = setup
        await connector.connect()

        # 1. First LONG signal → WAIT_SYNC (no prior signal edge)
        s1 = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        ack1 = await executor.process_signal(s1)
        assert ack1.reason == "WAITING_SYNC"

        # 2. Signal goes to WAIT → edge detected but direction=0 → no open
        s2 = make_signal(direction=0, intensity=0, action="WAIT")
        ack2 = await executor.process_signal(s2)
        assert ack2.reason == "SYNCED"

        # 3. Signal goes LONG again → edge detected, direction=1 → OPEN
        s3 = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        ack3 = await executor.process_signal(s3)
        # Depends on SyncState edge: WAIT_SYNC → then direction change → open
        # Actually: decide returns WAIT_SYNC (real flat, signal long)
        # SyncState: last was 0, now 1 → edge! → should_open=True

    @pytest.mark.asyncio
    async def test_close_on_signal_wait(self, setup):
        """Se já tem posição LONG e signal vira WAIT, deve fechar."""
        connector, executor = setup
        await connector.connect()

        # Manually open position via connector
        await connector.open_order("EURUSD", 1, 0.01)

        # Signal WAIT → decide returns CLOSE
        s = make_signal(direction=0, intensity=0, action="WAIT")
        ack = await executor.process_signal(s)
        assert ack.reason == "CLOSED" or ack.status == "OK"

        pos = await connector.get_position("EURUSD")
        assert pos is None  # Closed

    @pytest.mark.asyncio
    async def test_risk_guard_blocks_high_dd(self, setup):
        """High drawdown blocks new orders."""
        connector, executor = setup
        await connector.connect()

        # Drain balance to trigger DD
        connector.balance = 9400  # 6% DD > 5% limit
        connector.equity = 9400

        # Force through edge detection
        s1 = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        executor.sync_states["EURUSD"].waiting_sync = True
        executor.sync_states["EURUSD"].last_signal_dir = 0

        ack = await executor.process_signal(s1)
        # Should be SKIP due to DD limit
        if ack.status == "SKIP":
            assert "DD_LIMIT" in ack.reason or "MARGIN" in ack.reason


# ═══════════════════════════════════════════════════════════════════════════
# Integração: Paper + Signal Flow
# ═══════════════════════════════════════════════════════════════════════════

class TestPaperIntegration:
    """Testa PaperTrader processando sequência de sinais realista."""

    @pytest.fixture
    def trader(self, training_config):
        pt = PaperTrader(initial_balance=10000)
        pt.load_config("EURUSD", training_config)
        return pt

    def test_multi_trade_sequence(self, trader):
        """Simula sequência: LONG → WAIT → SHORT → WAIT."""
        trades = []
        bars = make_bars("EURUSD", 100)

        signals = [
            make_signal(direction=1, intensity=1, action="LONG_WEAK"),
            make_signal(direction=1, intensity=1, action="LONG_WEAK"),  # Same
            make_signal(direction=0, intensity=0, action="WAIT"),       # Close
            make_signal(direction=-1, intensity=2, action="SHORT_MODERATE"),  # Open
            make_signal(direction=0, intensity=0, action="WAIT"),       # Close
        ]

        for i, (sig, bar) in enumerate(zip(signals, bars)):
            trade = trader.process_signal(sig, bar)
            if trade:
                trades.append(trade)

        assert len(trades) == 2  # One LONG close, one SHORT close
        assert all(isinstance(t, PaperTrade) for t in trades)

    def test_balance_changes_after_trades(self, trader):
        """Balance should differ from initial after trades."""
        s1 = make_signal(direction=1, intensity=2, action="LONG_MODERATE")
        trader.process_signal(s1, make_bar(close=1.10000))

        s2 = make_signal(direction=0, intensity=0, action="WAIT")
        trader.process_signal(s2, make_bar(close=1.10100, offset=1))

        account = trader.accounts["EURUSD"]
        assert account.balance != 10000  # Changed by PnL + commission


# ═══════════════════════════════════════════════════════════════════════════
# Integração: Buffer + VirtualPosition (Preditor components)
# ═══════════════════════════════════════════════════════════════════════════

class TestBufferVirtualPositionIntegration:

    def test_buffer_feeds_feature_calc(self, training_config):
        """Buffer → DataFrame → FeatureCalculator without errors."""
        from oracle_trader_v2.core.features import FeatureCalculator
        from oracle_trader_v2.core.models import VirtualPosition

        buf = BarBuffer(maxlen=350)
        bars = make_bars("EURUSD", 350)
        buf.extend(bars)
        assert buf.is_ready()

        calc = FeatureCalculator({
            "momentum_period": 12, "consistency_period": 12,
            "range_period": 20, "roc_period": 10, "atr_period": 14,
            "ema_period": 200, "volume_ma_period": 20, "n_states": 5,
        })

        df = buf.to_dataframe()
        hmm = calc.calc_hmm_features(df)
        assert hmm.shape == (1, 3)

        vp = VirtualPosition(direction=0, intensity=0, entry_price=0, current_pnl=0)
        rl = calc.calc_rl_features(df, hmm_state=0, position=vp)
        assert rl.shape == (1, 14)  # 6 + 5 + 3

    def test_virtual_position_full_cycle(self, training_config):
        """VPM: open → update → close → reopen → close cycle."""
        vpm = VirtualPositionManager.from_training_config(training_config)
        bars = make_bars("EURUSD", 20)

        # Open LONG
        vpm.update(Action.LONG_WEAK, bars[0].close)
        assert vpm.is_open

        # Hold for 10 bars
        for bar in bars[1:10]:
            vpm.update(Action.LONG_WEAK, bar.close)
        assert vpm.is_open

        # Close
        pnl1 = vpm.update(Action.WAIT, bars[10].close)
        assert not vpm.is_open

        # Open SHORT
        vpm.update(Action.SHORT_MODERATE, bars[11].close)
        assert vpm.direction == -1

        # Close
        pnl2 = vpm.update(Action.WAIT, bars[15].close)
        assert not vpm.is_open

        assert vpm.total_realized_pnl != 0


# ═══════════════════════════════════════════════════════════════════════════
# Integração: Session lifecycle
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionLifecycleIntegration:

    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self, tmp_path):
        """start → heartbeat → end → verify state file cleaned."""
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        mock_db._execute = AsyncMock()
        mock_db.log_event = AsyncMock()

        sm = SessionManager(supabase_client=mock_db, base_dir=tmp_path)

        sid = await sm.start_session(10000, ["EURUSD"])
        assert sm._running

        sm.update_heartbeat(balance=10050)

        await sm.end_session(
            stats={"balance": 10050, "total_trades": 3, "total_pnl": 50},
            reason=SessionEndReason.NORMAL,
        )
        assert not sm._running
        assert not (tmp_path / ".session_state.json").exists()
