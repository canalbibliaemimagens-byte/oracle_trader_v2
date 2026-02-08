"""
Oracle Trader v2.0 - Testes do Preditor (Fase 2)
==================================================

Testa componentes que NÃO dependem de hmmlearn/stable-baselines3:
  - BarBuffer
  - VirtualPositionManager
  - ModelLoader (validação de metadata)
  - Preditor (estrutura e estado)
"""

import json
import zipfile
import tempfile
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

from oracle_trader_v2.core.models import Bar, VirtualPosition
from oracle_trader_v2.core.actions import Action


# =============================================================================
# TESTES: BarBuffer
# =============================================================================

class TestBarBuffer:

    def _make_bar(self, i: int) -> Bar:
        return Bar(
            symbol="EURUSD", time=i * 900,
            open=1.1 + i * 0.0001, high=1.1 + i * 0.0001 + 0.0005,
            low=1.1 + i * 0.0001 - 0.0003, close=1.1 + i * 0.0001 + 0.0002,
            volume=float(100 + i)
        )

    def test_append_and_len(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=5)
        assert len(buf) == 0
        buf.append(self._make_bar(0))
        assert len(buf) == 1

    def test_fifo_overflow(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=3)
        for i in range(5):
            buf.append(self._make_bar(i))
        assert len(buf) == 3
        df = buf.to_dataframe()
        assert df['time'].iloc[0] == 2 * 900

    def test_is_ready(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=3)
        assert not buf.is_ready()
        for i in range(3):
            buf.append(self._make_bar(i))
        assert buf.is_ready()

    def test_to_dataframe_columns(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=5)
        for i in range(3):
            buf.append(self._make_bar(i))
        df = buf.to_dataframe()
        assert list(df.columns) == ['time', 'open', 'high', 'low', 'close', 'volume']
        assert len(df) == 3

    def test_to_dataframe_empty(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=5)
        df = buf.to_dataframe()
        assert len(df) == 0
        assert 'close' in df.columns

    def test_extend(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=10)
        bars = [self._make_bar(i) for i in range(5)]
        buf.extend(bars)
        assert len(buf) == 5

    def test_last_bar(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=5)
        assert buf.last_bar is None
        bar = self._make_bar(42)
        buf.append(bar)
        assert buf.last_bar == bar

    def test_clear(self):
        from oracle_trader_v2.preditor.buffer import BarBuffer
        buf = BarBuffer(maxlen=5)
        buf.extend([self._make_bar(i) for i in range(3)])
        buf.clear()
        assert len(buf) == 0
        assert not buf.is_ready()


# =============================================================================
# TESTES: VirtualPositionManager
# =============================================================================

class TestVirtualPositionManager:

    def _make_vpm(self, **overrides) -> "VirtualPositionManager":
        from oracle_trader_v2.preditor.virtual_position import VirtualPositionManager
        defaults = {
            'spread_points': 7.0, 'slippage_points': 2.0,
            'commission_per_lot': 7.0, 'point': 0.00001,
            'pip_value': 10.0, 'lot_sizes': [0, 0.01, 0.03, 0.05],
        }
        defaults.update(overrides)
        return VirtualPositionManager(**defaults)

    def test_initial_state(self):
        vpm = self._make_vpm()
        assert vpm.direction == 0
        assert vpm.intensity == 0
        assert vpm.is_open is False
        assert vpm.current_pnl == 0.0
        assert vpm.direction_name == "FLAT"

    def test_open_long(self):
        vpm = self._make_vpm()
        realized = vpm.update(Action.LONG_WEAK, 1.10000)
        assert realized == 0.0
        assert vpm.direction == 1
        assert vpm.intensity == 1
        assert vpm.is_open is True
        assert vpm.direction_name == "LONG"
        assert vpm.entry_price == pytest.approx(1.10009, abs=1e-6)

    def test_open_short(self):
        vpm = self._make_vpm()
        vpm.update(Action.SHORT_STRONG, 1.10000)
        assert vpm.direction == -1
        assert vpm.intensity == 3
        assert vpm.entry_price == pytest.approx(1.09991, abs=1e-6)

    def test_noop_same_position(self):
        vpm = self._make_vpm()
        vpm.update(Action.LONG_WEAK, 1.10000)
        old_entry = vpm.entry_price
        realized = vpm.update(Action.LONG_WEAK, 1.10050)
        assert realized == 0.0
        assert vpm.entry_price == old_entry
        assert vpm.current_pnl != 0.0

    def test_close_on_wait(self):
        vpm = self._make_vpm()
        vpm.update(Action.LONG_WEAK, 1.10000)
        realized = vpm.update(Action.WAIT, 1.10100)
        assert vpm.direction == 0
        assert vpm.is_open is False
        assert realized != 0.0

    def test_reversal(self):
        vpm = self._make_vpm()
        vpm.update(Action.LONG_WEAK, 1.10000)
        realized = vpm.update(Action.SHORT_MODERATE, 1.10050)
        assert vpm.direction == -1
        assert vpm.intensity == 2
        assert realized != 0.0

    def test_intensity_change_closes_and_reopens(self):
        vpm = self._make_vpm()
        vpm.update(Action.LONG_WEAK, 1.10000)
        realized = vpm.update(Action.LONG_STRONG, 1.10000)
        assert vpm.direction == 1
        assert vpm.intensity == 3
        assert realized != 0.0

    def test_from_training_config(self):
        from oracle_trader_v2.preditor.virtual_position import VirtualPositionManager
        config = {
            'point': 0.01, 'pip_value': 1.0, 'spread_points': 5,
            'slippage_points': 1, 'commission_per_lot': 3.0,
            'lot_sizes': [0, 0.1, 0.3, 0.5],
        }
        vpm = VirtualPositionManager.from_training_config(config)
        assert vpm.point == 0.01
        assert vpm.pip_value == 1.0
        assert vpm.spread_points == 5
        assert vpm.lot_sizes == [0, 0.1, 0.3, 0.5]

    def test_as_core_virtual_position(self):
        vpm = self._make_vpm()
        vpm.update(Action.LONG_MODERATE, 1.10000)
        core_vp = vpm.as_core_virtual_position()
        assert core_vp.direction == 1
        assert core_vp.intensity == 2
        assert core_vp.entry_price == vpm.entry_price

    def test_total_realized_pnl_accumulates(self):
        vpm = self._make_vpm()
        vpm.update(Action.LONG_WEAK, 1.10000)
        vpm.update(Action.WAIT, 1.10100)
        first_pnl = vpm.total_realized_pnl
        assert first_pnl != 0.0
        vpm.update(Action.SHORT_WEAK, 1.10100)
        vpm.update(Action.WAIT, 1.10000)
        assert vpm.total_realized_pnl != first_pnl

    def test_size_property(self):
        vpm = self._make_vpm()
        assert vpm.size == 0.0
        vpm.update(Action.LONG_WEAK, 1.10000)
        assert vpm.size == 0.01
        vpm.update(Action.LONG_MODERATE, 1.10000)
        assert vpm.size == 0.03


# =============================================================================
# TESTES: ModelLoader (validação de metadata, sem libs ML)
# =============================================================================

class TestModelLoaderValidation:

    def test_validate_metadata_valid(self):
        from oracle_trader_v2.preditor.model_loader import ModelLoader
        metadata = {
            "format_version": "2.0",
            "symbol": {"name": "EURUSD", "timeframe": "M15"},
            "training_config": {}, "hmm_config": {},
            "rl_config": {}, "actions": {},
        }
        assert ModelLoader.validate_metadata(metadata) is True

    def test_validate_metadata_missing_field(self):
        from oracle_trader_v2.preditor.model_loader import ModelLoader
        metadata = {"format_version": "2.0", "symbol": {"name": "EURUSD"}}
        assert ModelLoader.validate_metadata(metadata) is False

    def test_load_metadata_only_valid_zip(self):
        from oracle_trader_v2.preditor.model_loader import ModelLoader
        metadata = {
            "format_version": "2.0",
            "symbol": {"name": "TEST", "timeframe": "M15"},
            "training_config": {"point": 0.00001},
            "hmm_config": {"n_states": 5},
            "rl_config": {"roc_period": 10},
            "actions": {},
        }
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            with zipfile.ZipFile(tmp.name, 'w') as zf:
                zf.comment = json.dumps(metadata).encode('utf-8')
                zf.writestr("dummy.txt", "placeholder")
            result = ModelLoader.load_metadata_only(tmp.name)
        assert result is not None
        assert result["symbol"]["name"] == "TEST"
        Path(tmp.name).unlink()

    def test_load_metadata_only_no_comment(self):
        from oracle_trader_v2.preditor.model_loader import ModelLoader
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            with zipfile.ZipFile(tmp.name, 'w') as zf:
                zf.writestr("dummy.txt", "placeholder")
            result = ModelLoader.load_metadata_only(tmp.name)
        assert result is None
        Path(tmp.name).unlink()

    def test_load_metadata_only_nonexistent(self):
        from oracle_trader_v2.preditor.model_loader import ModelLoader
        result = ModelLoader.load_metadata_only("/nonexistent/path.zip")
        assert result is None

    def test_load_nonexistent_zip(self):
        from oracle_trader_v2.preditor.model_loader import ModelLoader
        result = ModelLoader.load("/nonexistent/model.zip")
        assert result is None


# =============================================================================
# TESTES: Preditor (estrutura, sem modelos ML)
# =============================================================================

class TestPreditorStructure:

    def test_initial_state(self):
        from oracle_trader_v2.preditor.preditor import Preditor
        p = Preditor()
        assert p.list_models() == []
        state = p.get_state()
        assert state["models"] == []
        assert state["positions"] == {}
        assert state["buffers"] == {}

    def test_process_bar_unknown_symbol(self):
        from oracle_trader_v2.preditor.preditor import Preditor
        p = Preditor()
        bar = Bar("UNKNOWN", 0, 1.1, 1.2, 1.0, 1.15)
        result = p.process_bar("UNKNOWN", bar)
        assert result is None

    def test_get_virtual_position_unknown(self):
        from oracle_trader_v2.preditor.preditor import Preditor
        p = Preditor()
        assert p.get_virtual_position("UNKNOWN") is None
