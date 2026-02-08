"""
Testes: preditor/ — BarBuffer, VirtualPositionManager, warmup, Preditor
"""

import pytest
import numpy as np

from oracle_trader_v2.preditor.buffer import BarBuffer
from oracle_trader_v2.preditor.virtual_position import VirtualPositionManager
from oracle_trader_v2.core.actions import Action
from oracle_trader_v2.core.models import Bar
from .helpers import make_bar, make_bars


# ═══════════════════════════════════════════════════════════════════════════
# BarBuffer
# ═══════════════════════════════════════════════════════════════════════════

class TestBarBuffer:

    def test_empty_buffer(self):
        buf = BarBuffer(maxlen=350)
        assert len(buf) == 0
        assert not buf.is_ready()
        assert buf.last_bar is None

    def test_append(self):
        buf = BarBuffer(maxlen=5)
        for i in range(5):
            buf.append(make_bar(close=1.1 + i * 0.0001, offset=i))
        assert len(buf) == 5
        assert buf.is_ready()

    def test_fifo_eviction(self):
        buf = BarBuffer(maxlen=3)
        for i in range(5):
            buf.append(make_bar(close=1.1 + i * 0.0001, offset=i))
        assert len(buf) == 3
        # Primeiro bar deve ter sido descartado
        assert buf.last_bar.close == pytest.approx(1.1 + 4 * 0.0001, abs=1e-6)

    def test_extend(self):
        buf = BarBuffer(maxlen=100)
        bars = make_bars(n=50)
        buf.extend(bars)
        assert len(buf) == 50

    def test_to_dataframe(self):
        buf = BarBuffer(maxlen=10)
        bars = make_bars(n=10)
        buf.extend(bars)
        df = buf.to_dataframe()
        assert len(df) == 10
        assert set(df.columns) >= {"time", "open", "high", "low", "close", "volume"}

    def test_to_dataframe_empty(self):
        buf = BarBuffer(maxlen=10)
        df = buf.to_dataframe()
        assert len(df) == 0

    def test_clear(self):
        buf = BarBuffer(maxlen=10)
        buf.extend(make_bars(n=5))
        buf.clear()
        assert len(buf) == 0

    def test_repr(self):
        buf = BarBuffer(maxlen=350)
        r = repr(buf)
        assert "BarBuffer" in r
        assert "ready=False" in r

    def test_is_ready_at_maxlen(self):
        buf = BarBuffer(maxlen=5)
        for i in range(4):
            buf.append(make_bar(offset=i))
        assert not buf.is_ready()
        buf.append(make_bar(offset=4))
        assert buf.is_ready()


# ═══════════════════════════════════════════════════════════════════════════
# VirtualPositionManager
# ═══════════════════════════════════════════════════════════════════════════

class TestVirtualPosition:

    @pytest.fixture
    def vpm(self, training_config):
        return VirtualPositionManager.from_training_config(training_config)

    def test_initial_state(self, vpm):
        assert vpm.direction == 0
        assert vpm.intensity == 0
        assert not vpm.is_open
        assert vpm.size == 0
        assert vpm.direction_name == "FLAT"
        assert vpm.current_pnl == 0.0

    def test_open_long(self, vpm):
        pnl = vpm.update(Action.LONG_WEAK, 1.10000)
        assert pnl == 0.0
        assert vpm.direction == 1
        assert vpm.intensity == 1
        assert vpm.is_open
        assert vpm.size == 0.01
        assert vpm.direction_name == "LONG"

    def test_open_short(self, vpm):
        vpm.update(Action.SHORT_MODERATE, 1.10000)
        assert vpm.direction == -1
        assert vpm.intensity == 2
        assert vpm.size == 0.03

    def test_close_on_wait(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        pnl = vpm.update(Action.WAIT, 1.10100)
        assert vpm.direction == 0
        assert not vpm.is_open
        # PnL should be non-zero (closed with profit minus costs)
        assert isinstance(pnl, float)

    def test_same_action_noop(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        pnl = vpm.update(Action.LONG_WEAK, 1.10050)
        assert pnl == 0.0  # No trade, only floating PnL update
        assert vpm.is_open

    def test_reverse_position(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        pnl = vpm.update(Action.SHORT_MODERATE, 1.10050)
        # Should close LONG and open SHORT
        assert pnl != 0.0
        assert vpm.direction == -1
        assert vpm.intensity == 2

    def test_intensity_change_closes_and_reopens(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        pnl = vpm.update(Action.LONG_STRONG, 1.10050)
        # Changing intensity closes LONG_WEAK and opens LONG_STRONG
        assert pnl != 0.0
        assert vpm.direction == 1
        assert vpm.intensity == 3
        assert vpm.size == 0.05

    def test_commission_applied_on_open(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        # Entry commission = 7.0 * 0.01 / 2 = 0.035
        # current_pnl should be negative (commission only)
        assert vpm.current_pnl < 0

    def test_floating_pnl_updates(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        pnl_before = vpm.current_pnl
        vpm.update(Action.LONG_WEAK, 1.10500)  # Price went up
        assert vpm.current_pnl > pnl_before

    def test_total_realized_pnl_accumulates(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        vpm.update(Action.WAIT, 1.10100)
        pnl1 = vpm.total_realized_pnl

        vpm.update(Action.SHORT_WEAK, 1.10100)
        vpm.update(Action.WAIT, 1.10000)
        pnl2 = vpm.total_realized_pnl

        assert pnl2 != pnl1  # Accumulated

    def test_as_core_virtual_position(self, vpm):
        vpm.update(Action.LONG_MODERATE, 1.10000)
        core_vp = vpm.as_core_virtual_position()
        assert core_vp.direction == 1
        assert core_vp.intensity == 2
        assert core_vp.entry_price > 0

    def test_lot_sizes_from_config(self):
        vpm = VirtualPositionManager.from_training_config({
            "lot_sizes": [0, 0.02, 0.05, 0.10],
        })
        vpm.update(Action.LONG_STRONG, 1.10000)
        assert vpm.size == 0.10

    def test_spread_and_slippage_on_entry(self, vpm):
        vpm.update(Action.LONG_WEAK, 1.10000)
        # LONG entry: price + spread + slippage
        expected = 1.10000 + 7 * 0.00001 + 2 * 0.00001
        assert abs(vpm.entry_price - expected) < 1e-10
