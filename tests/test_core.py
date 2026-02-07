"""
Oracle Trader v2.0 - Testes de Paridade de Features
====================================================

GATE DE QUALIDADE: NÃO avançar para Fase 2 sem 100% de aprovação.

Compara saídas do FeatureCalculator v2 (core/features.py) contra
FeatureCalculatorV1 (tests/features_v1_reference.py).

Tolerância: 1e-6 (float32)
"""

import numpy as np
import pandas as pd
import pytest

from oracle_trader_v2.core.features import FeatureCalculator, calc_atr
from oracle_trader_v2.core.models import VirtualPosition
from oracle_trader_v2.tests.features_v1_reference import FeatureCalculatorV1, SymbolConfigV1, PositionV1


# =============================================================================
# FIXTURES: Dados de teste reprodutíveis
# =============================================================================

@pytest.fixture
def sample_df():
    """DataFrame OHLCV sintético com 300 barras (seed fixo para reprodutibilidade)."""
    np.random.seed(42)
    n = 300
    df = pd.DataFrame({
        'time': np.arange(n) * 900,  # 15 min intervals
        'open': 1.1000 + np.cumsum(np.random.randn(n) * 0.0001),
        'high': 0.0,
        'low': 0.0,
        'close': 0.0,
        'volume': np.random.randint(100, 1000, n).astype(float),
    })
    df['close'] = df['open'] + np.random.randn(n) * 0.0005
    df['high'] = df[['open', 'close']].max(axis=1) + abs(np.random.randn(n) * 0.0002)
    df['low'] = df[['open', 'close']].min(axis=1) - abs(np.random.randn(n) * 0.0002)
    return df


@pytest.fixture
def default_config():
    return {
        'momentum_period': 12, 'consistency_period': 12,
        'range_period': 20, 'n_states': 5,
        'roc_period': 10, 'atr_period': 14,
        'ema_period': 200, 'volume_ma_period': 20,
    }


@pytest.fixture
def v1_config():
    return SymbolConfigV1()


@pytest.fixture
def calc_v2(default_config):
    return FeatureCalculator(default_config)


@pytest.fixture
def calc_v1(v1_config):
    return FeatureCalculatorV1(v1_config)


# =============================================================================
# TESTES DE PARIDADE HMM
# =============================================================================

class TestHMMFeaturesParity:

    def test_hmm_features_basic(self, calc_v1, calc_v2, sample_df):
        hmm_v1 = calc_v1.calc_hmm_features(sample_df)
        hmm_v2 = calc_v2.calc_hmm_features(sample_df)
        assert hmm_v1.shape == hmm_v2.shape == (1, 3)
        np.testing.assert_array_almost_equal(hmm_v1, hmm_v2, decimal=6)

    def test_hmm_features_shape(self, calc_v2, sample_df):
        result = calc_v2.calc_hmm_features(sample_df)
        assert result.shape == (1, 3)
        assert result.dtype == np.float32

    def test_hmm_features_range(self, calc_v2, sample_df):
        result = calc_v2.calc_hmm_features(sample_df)
        momentum, consistency, range_pos = result[0]
        assert -5.0 <= momentum <= 5.0
        assert -1.0 <= consistency <= 1.0
        assert -1.0 <= range_pos <= 1.0

    def test_hmm_features_multiple_slices(self, calc_v1, calc_v2, sample_df):
        for end in [100, 150, 200, 250, 300]:
            df_slice = sample_df.iloc[:end].reset_index(drop=True)
            hmm_v1 = calc_v1.calc_hmm_features(df_slice)
            hmm_v2 = calc_v2.calc_hmm_features(df_slice)
            np.testing.assert_array_almost_equal(
                hmm_v1, hmm_v2, decimal=6,
                err_msg=f"Divergência com {end} barras"
            )


# =============================================================================
# TESTES DE PARIDADE RL
# =============================================================================

class TestRLFeaturesParity:

    def test_rl_features_flat_position(self, calc_v1, calc_v2, sample_df):
        pos_v1 = PositionV1(direction=0, size=0.0, pnl=0.0)
        pos_v2 = VirtualPosition(direction=0, intensity=0, current_pnl=0.0)
        rl_v1 = calc_v1.calc_rl_features(sample_df, hmm_state=2, position=pos_v1)
        rl_v2 = calc_v2.calc_rl_features(sample_df, hmm_state=2, position=pos_v2)
        assert rl_v1.shape == rl_v2.shape
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6)

    def test_rl_features_long_position(self, calc_v1, calc_v2, sample_df):
        pos_v1 = PositionV1(direction=1, size=0.01, pnl=15.50)
        pos_v2 = VirtualPosition(direction=1, intensity=1, current_pnl=15.50)
        rl_v1 = calc_v1.calc_rl_features(sample_df, hmm_state=3, position=pos_v1)
        rl_v2 = calc_v2.calc_rl_features(sample_df, hmm_state=3, position=pos_v2)
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6)

    def test_rl_features_short_position(self, calc_v1, calc_v2, sample_df):
        pos_v1 = PositionV1(direction=-1, size=0.05, pnl=-22.30)
        pos_v2 = VirtualPosition(direction=-1, intensity=3, current_pnl=-22.30)
        rl_v1 = calc_v1.calc_rl_features(sample_df, hmm_state=0, position=pos_v1)
        rl_v2 = calc_v2.calc_rl_features(sample_df, hmm_state=0, position=pos_v2)
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6)

    def test_rl_features_moderate_intensity(self, calc_v1, calc_v2, sample_df):
        pos_v1 = PositionV1(direction=1, size=0.03, pnl=50.0)
        pos_v2 = VirtualPosition(direction=1, intensity=2, current_pnl=50.0)
        rl_v1 = calc_v1.calc_rl_features(sample_df, hmm_state=1, position=pos_v1)
        rl_v2 = calc_v2.calc_rl_features(sample_df, hmm_state=1, position=pos_v2)
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6)

    def test_rl_features_shape(self, calc_v2, sample_df):
        pos = VirtualPosition()
        result = calc_v2.calc_rl_features(sample_df, hmm_state=0, position=pos)
        expected_cols = 6 + 5 + 3
        assert result.shape == (1, expected_cols)
        assert result.dtype == np.float32

    def test_rl_features_all_hmm_states(self, calc_v1, calc_v2, sample_df):
        pos_v1 = PositionV1(direction=0, size=0.0, pnl=0.0)
        pos_v2 = VirtualPosition(direction=0, intensity=0, current_pnl=0.0)
        for state in range(5):
            rl_v1 = calc_v1.calc_rl_features(sample_df, hmm_state=state, position=pos_v1)
            rl_v2 = calc_v2.calc_rl_features(sample_df, hmm_state=state, position=pos_v2)
            np.testing.assert_array_almost_equal(
                rl_v1, rl_v2, decimal=6,
                err_msg=f"Divergência no HMM state {state}"
            )

    def test_rl_onehot_encoding(self, calc_v2, sample_df):
        pos = VirtualPosition()
        for state in range(5):
            result = calc_v2.calc_rl_features(sample_df, hmm_state=state, position=pos)
            onehot = result[0, 6:11]
            expected = np.zeros(5, dtype=np.float32)
            expected[state] = 1.0
            np.testing.assert_array_equal(onehot, expected)

    def test_rl_position_features(self, calc_v2, sample_df):
        pos = VirtualPosition(direction=1, intensity=1, current_pnl=100.0)
        result = calc_v2.calc_rl_features(sample_df, hmm_state=0, position=pos)
        pos_feats = result[0, -3:]
        assert pos_feats[0] == 1.0
        assert pos_feats[1] == pytest.approx(0.1)
        assert pos_feats[2] == pytest.approx(np.tanh(100.0 / 100.0))


# =============================================================================
# TESTES DE EDGE CASES
# =============================================================================

class TestFeaturesEdgeCases:

    def test_small_dataframe(self, calc_v2):
        df = pd.DataFrame({
            'time': [0, 900, 1800],
            'open': [1.1, 1.1001, 1.1002],
            'high': [1.1005, 1.1006, 1.1007],
            'low': [1.0995, 1.0996, 1.0997],
            'close': [1.1002, 1.1003, 1.1004],
            'volume': [100.0, 200.0, 150.0],
        })
        hmm = calc_v2.calc_hmm_features(df)
        assert hmm.shape == (1, 3)
        assert not np.any(np.isnan(hmm))

    def test_zero_volume(self, calc_v2, sample_df):
        df = sample_df.copy()
        df['volume'] = 0.0
        pos = VirtualPosition()
        result = calc_v2.calc_rl_features(df, hmm_state=0, position=pos)
        assert not np.any(np.isnan(result))

    def test_constant_price(self, calc_v2):
        n = 50
        df = pd.DataFrame({
            'time': np.arange(n) * 900,
            'open': np.full(n, 1.1),
            'high': np.full(n, 1.1),
            'low': np.full(n, 1.1),
            'close': np.full(n, 1.1),
            'volume': np.full(n, 100.0),
        })
        hmm = calc_v2.calc_hmm_features(df)
        assert not np.any(np.isnan(hmm))

    def test_no_time_column(self, calc_v2, sample_df):
        df = sample_df.drop(columns=['time'])
        pos = VirtualPosition()
        result = calc_v2.calc_rl_features(df, hmm_state=0, position=pos)
        session_val = result[0, 5]
        assert session_val == 0.0

    def test_large_pnl_normalization(self, calc_v2, sample_df):
        pos = VirtualPosition(direction=1, intensity=3, current_pnl=999999.0)
        result = calc_v2.calc_rl_features(sample_df, hmm_state=0, position=pos)
        pnl_feat = result[0, -1]
        assert -1.0 <= pnl_feat <= 1.0


# =============================================================================
# TESTES DO calc_atr
# =============================================================================

class TestCalcATR:

    def test_atr_basic(self, sample_df):
        atr = calc_atr(sample_df, period=14)
        assert atr > 0

    def test_atr_small_df(self):
        df = pd.DataFrame({'high': [1.1], 'low': [1.0], 'close': [1.05]})
        atr = calc_atr(df, period=14)
        assert atr == 0


# =============================================================================
# TESTES DE ACTIONS (core/actions.py)
# =============================================================================

class TestActions:

    def test_action_from_index_all(self):
        from oracle_trader_v2.core.actions import action_from_index, Action
        assert action_from_index(0) == Action.WAIT
        assert action_from_index(1) == Action.LONG_WEAK
        assert action_from_index(2) == Action.LONG_MODERATE
        assert action_from_index(3) == Action.LONG_STRONG
        assert action_from_index(4) == Action.SHORT_WEAK
        assert action_from_index(5) == Action.SHORT_MODERATE
        assert action_from_index(6) == Action.SHORT_STRONG

    def test_action_from_invalid_index(self):
        from oracle_trader_v2.core.actions import action_from_index, Action
        assert action_from_index(99) == Action.WAIT
        assert action_from_index(-1) == Action.WAIT

    def test_get_direction(self):
        from oracle_trader_v2.core.actions import get_direction, Action
        from oracle_trader_v2.core.constants import Direction
        assert get_direction(Action.WAIT) == Direction.FLAT
        assert get_direction(Action.LONG_WEAK) == Direction.LONG
        assert get_direction(Action.LONG_STRONG) == Direction.LONG
        assert get_direction(Action.SHORT_WEAK) == Direction.SHORT
        assert get_direction(Action.SHORT_STRONG) == Direction.SHORT

    def test_get_intensity(self):
        from oracle_trader_v2.core.actions import get_intensity, Action
        assert get_intensity(Action.WAIT) == 0
        assert get_intensity(Action.LONG_WEAK) == 1
        assert get_intensity(Action.LONG_MODERATE) == 2
        assert get_intensity(Action.LONG_STRONG) == 3
        assert get_intensity(Action.SHORT_WEAK) == 1
        assert get_intensity(Action.SHORT_MODERATE) == 2
        assert get_intensity(Action.SHORT_STRONG) == 3

    def test_get_action_properties(self):
        from oracle_trader_v2.core.actions import get_action_properties
        from oracle_trader_v2.core.constants import Direction
        d, i = get_action_properties(0)
        assert d == Direction.FLAT and i == 0
        d, i = get_action_properties(2)
        assert d == Direction.LONG and i == 2
        d, i = get_action_properties(5)
        assert d == Direction.SHORT and i == 2

    def test_action_to_index_roundtrip(self):
        from oracle_trader_v2.core.actions import ACTIONS_MAP, ACTION_TO_INDEX
        for idx, action in ACTIONS_MAP.items():
            assert ACTION_TO_INDEX[action] == idx


# =============================================================================
# TESTES DE MODELS (core/models.py)
# =============================================================================

class TestModels:

    def test_bar_immutable(self):
        from oracle_trader_v2.core.models import Bar
        bar = Bar(symbol="EURUSD", time=123, open=1.1, high=1.2, low=1.0, close=1.15)
        with pytest.raises(AttributeError):
            bar.close = 1.20

    def test_signal_properties(self):
        from oracle_trader_v2.core.models import Signal
        sig_entry = Signal("EURUSD", "LONG_WEAK", 1, 1, 2, 0.0, 0.0)
        assert sig_entry.is_entry is True
        assert sig_entry.is_exit is False
        sig_exit = Signal("EURUSD", "WAIT", 0, 0, 2, 0.0, 0.0)
        assert sig_exit.is_entry is False
        assert sig_exit.is_exit is True

    def test_virtual_position_size(self):
        from oracle_trader_v2.core.models import VirtualPosition
        assert VirtualPosition(direction=1, intensity=1).size == 0.01
        assert VirtualPosition(direction=1, intensity=2).size == 0.03
        assert VirtualPosition(direction=-1, intensity=3).size == 0.05
        assert VirtualPosition(direction=0, intensity=0).size == 0.0

    def test_virtual_position_direction_name(self):
        from oracle_trader_v2.core.models import VirtualPosition
        assert VirtualPosition(direction=1).direction_name == "LONG"
        assert VirtualPosition(direction=-1).direction_name == "SHORT"
        assert VirtualPosition(direction=0).direction_name == "FLAT"


# =============================================================================
# TESTES DE UTILS (core/utils.py)
# =============================================================================

class TestUtils:

    def test_bars_to_dataframe(self):
        from oracle_trader_v2.core.utils import bars_to_dataframe
        from oracle_trader_v2.core.models import Bar
        bars = [
            Bar("EURUSD", 1000, 1.1, 1.2, 1.0, 1.15, 100),
            Bar("EURUSD", 1900, 1.15, 1.25, 1.05, 1.20, 200),
        ]
        df = bars_to_dataframe(bars)
        assert len(df) == 2
        assert list(df.columns) == ['time', 'open', 'high', 'low', 'close', 'volume']
        assert df['close'].iloc[0] == 1.15

    def test_bars_to_dataframe_empty(self):
        from oracle_trader_v2.core.utils import bars_to_dataframe
        df = bars_to_dataframe([])
        assert len(df) == 0
        assert 'close' in df.columns

    def test_round_lot(self):
        from oracle_trader_v2.core.utils import round_lot
        assert round_lot(0.0123, 0.01) == 0.01
        assert round_lot(0.035, 0.01) == 0.04
        assert round_lot(0.045, 0.01) == 0.04  # banker's rounding

    def test_pips_to_price(self):
        from oracle_trader_v2.core.utils import pips_to_price
        result = pips_to_price(10, 0.00001, 5)
        assert result == pytest.approx(0.001)

    def test_timestamp_roundtrip(self):
        from oracle_trader_v2.core.utils import timestamp_to_datetime, datetime_to_timestamp
        ts = 1706961600
        dt = timestamp_to_datetime(ts)
        assert datetime_to_timestamp(dt) == ts
