"""
Testes: core/ — actions, constants, models, utils, features
"""

import numpy as np
import pandas as pd
import pytest

from oracle_trader_v2.core.constants import (
    Direction, Timeframe, TIMEFRAME_SECONDS, TIMEFRAME_BARS_PER_YEAR,
    TRAINING_LOT_SIZES, MIN_BARS_FOR_PREDICTION, WARMUP_BARS, VERSION,
)
from oracle_trader_v2.core.actions import (
    Action, ACTIONS_MAP, ACTION_TO_INDEX,
    action_from_index, get_direction, get_intensity, get_action_properties,
)
from oracle_trader_v2.core.models import (
    Bar, Signal, AccountInfo, Position, OrderResult, VirtualPosition,
)
from oracle_trader_v2.core.utils import (
    bars_to_dataframe, timestamp_to_datetime, datetime_to_timestamp,
    round_lot, pips_to_price,
)
from oracle_trader_v2.core.features import FeatureCalculator, calc_atr
from .helpers import make_bar, make_bars


# ═══════════════════════════════════════════════════════════════════════════
# constants.py
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_version_is_string(self):
        assert isinstance(VERSION, str) and VERSION.startswith("2.")

    def test_direction_values(self):
        assert Direction.SHORT == -1
        assert Direction.FLAT == 0
        assert Direction.LONG == 1

    def test_timeframe_seconds_completeness(self):
        for tf in Timeframe:
            assert tf in TIMEFRAME_SECONDS

    def test_timeframe_bars_per_year_completeness(self):
        for tf in Timeframe:
            assert tf in TIMEFRAME_BARS_PER_YEAR

    def test_training_lot_sizes(self):
        assert TRAINING_LOT_SIZES[0] == 0
        assert len(TRAINING_LOT_SIZES) == 4
        assert all(l >= 0 for l in TRAINING_LOT_SIZES)

    def test_min_bars_and_warmup(self):
        assert WARMUP_BARS > MIN_BARS_FOR_PREDICTION


# ═══════════════════════════════════════════════════════════════════════════
# actions.py
# ═══════════════════════════════════════════════════════════════════════════

class TestActions:
    def test_action_enum_has_7_values(self):
        assert len(Action) == 7

    def test_actions_map_completeness(self):
        for i in range(7):
            assert i in ACTIONS_MAP

    def test_action_to_index_inverse(self):
        for idx, action in ACTIONS_MAP.items():
            assert ACTION_TO_INDEX[action] == idx

    @pytest.mark.parametrize("idx,expected", [
        (0, Action.WAIT),
        (1, Action.LONG_WEAK),
        (4, Action.SHORT_WEAK),
        (6, Action.SHORT_STRONG),
    ])
    def test_action_from_index(self, idx, expected):
        assert action_from_index(idx) == expected

    def test_action_from_index_invalid(self):
        assert action_from_index(99) == Action.WAIT
        assert action_from_index(-1) == Action.WAIT

    @pytest.mark.parametrize("action,expected", [
        (Action.WAIT, Direction.FLAT),
        (Action.LONG_WEAK, Direction.LONG),
        (Action.LONG_STRONG, Direction.LONG),
        (Action.SHORT_WEAK, Direction.SHORT),
        (Action.SHORT_MODERATE, Direction.SHORT),
    ])
    def test_get_direction(self, action, expected):
        assert get_direction(action) == expected

    @pytest.mark.parametrize("action,expected", [
        (Action.WAIT, 0),
        (Action.LONG_WEAK, 1),
        (Action.LONG_MODERATE, 2),
        (Action.LONG_STRONG, 3),
        (Action.SHORT_WEAK, 1),
        (Action.SHORT_STRONG, 3),
    ])
    def test_get_intensity(self, action, expected):
        assert get_intensity(action) == expected

    def test_get_action_properties(self):
        d, i = get_action_properties(2)
        assert d == Direction.LONG
        assert i == 2


# ═══════════════════════════════════════════════════════════════════════════
# models.py
# ═══════════════════════════════════════════════════════════════════════════

class TestModels:
    def test_bar_frozen(self):
        bar = make_bar()
        with pytest.raises(AttributeError):
            bar.close = 1.2

    def test_signal_fields(self):
        s = Signal(
            symbol="EURUSD", action="LONG_WEAK", direction=1,
            intensity=1, hmm_state=2, virtual_pnl=0.0, timestamp=0,
        )
        assert s.symbol == "EURUSD"
        assert s.intensity == 1

    def test_account_info(self):
        a = AccountInfo(
            balance=10000, equity=9900, margin=500,
            free_margin=9400, margin_level=1980.0, currency="USD",
        )
        assert a.free_margin == 9400

    def test_position_fields(self):
        p = Position(
            ticket=1, symbol="X", direction=1, volume=0.01,
            open_price=1.1, current_price=1.1, pnl=0, sl=0, tp=0,
            open_time=0, comment="",
        )
        assert p.ticket == 1

    def test_order_result_success(self):
        r = OrderResult(success=True, ticket=1001, price=1.1)
        assert r.success and r.ticket == 1001

    def test_order_result_failure(self):
        r = OrderResult(success=False, error="rejected")
        assert not r.success and r.error == "rejected"

    def test_virtual_position(self):
        vp = VirtualPosition(direction=1, intensity=2, entry_price=1.1, current_pnl=5.0)
        assert vp.size == 0.03  # lot_sizes[intensity=2] = 0.03


# ═══════════════════════════════════════════════════════════════════════════
# utils.py
# ═══════════════════════════════════════════════════════════════════════════

class TestUtils:
    def test_bars_to_dataframe(self, sample_bars):
        df = bars_to_dataframe(sample_bars)
        assert len(df) == 400
        assert set(df.columns) >= {"time", "open", "high", "low", "close", "volume"}

    def test_bars_to_dataframe_empty(self):
        df = bars_to_dataframe([])
        assert len(df) == 0

    def test_timestamp_roundtrip(self):
        ts = 1700000000
        dt = timestamp_to_datetime(ts)
        assert datetime_to_timestamp(dt) == ts

    @pytest.mark.parametrize("volume,step,expected", [
        (0.025, 0.01, 0.02),  # Python banker rounding: round(2.5)=2
        (0.014, 0.01, 0.01),
        (0.05, 0.01, 0.05),
        (0.0, 0.01, 0.0),
    ])
    def test_round_lot(self, volume, step, expected):
        assert abs(round_lot(volume, step) - expected) < 1e-10

    def test_round_lot_zero_step(self):
        assert round_lot(0.025, 0) == 0.025

    def test_pips_to_price_5digit(self):
        result = pips_to_price(1.0, 0.00001, 5)
        assert abs(result - 0.0001) < 1e-10

    def test_pips_to_price_3digit(self):
        result = pips_to_price(1.0, 0.001, 3)
        assert abs(result - 0.01) < 1e-10


# ═══════════════════════════════════════════════════════════════════════════
# features.py
# ═══════════════════════════════════════════════════════════════════════════

class TestFeatures:
    @pytest.fixture
    def calc(self):
        return FeatureCalculator({
            "momentum_period": 12, "consistency_period": 12,
            "range_period": 20, "roc_period": 10, "atr_period": 14,
            "ema_period": 200, "volume_ma_period": 20, "n_states": 5,
        })

    @pytest.fixture
    def df(self, sample_bars):
        return bars_to_dataframe(sample_bars)

    def test_hmm_features_shape(self, calc, df):
        result = calc.calc_hmm_features(df)
        assert result.shape == (1, 3)
        assert result.dtype == np.float32

    def test_hmm_features_no_nan(self, calc, df):
        result = calc.calc_hmm_features(df)
        assert not np.isnan(result).any()

    def test_rl_features_shape(self, calc, df):
        vp = VirtualPosition(direction=1, intensity=1, entry_price=1.1, current_pnl=5.0)
        result = calc.calc_rl_features(df, hmm_state=2, position=vp)
        expected_features = 6 + 5 + 3  # market + hmm_onehot + position
        assert result.shape == (1, expected_features)
        assert result.dtype == np.float32

    def test_rl_features_no_nan(self, calc, df):
        vp = VirtualPosition(direction=0, intensity=0, entry_price=0, current_pnl=0)
        result = calc.calc_rl_features(df, hmm_state=0, position=vp)
        assert not np.isnan(result).any()

    def test_rl_features_hmm_onehot(self, calc, df):
        vp = VirtualPosition(direction=0, intensity=0, entry_price=0, current_pnl=0)
        result = calc.calc_rl_features(df, hmm_state=3, position=vp)
        # HMM onehot is features[6:11] for n_states=5
        onehot = result[0, 6:11]
        assert onehot[3] == 1.0
        assert sum(onehot) == 1.0

    def test_calc_atr(self, df):
        atr = calc_atr(df, period=14)
        assert atr > 0

    def test_calc_atr_short_data(self):
        df = pd.DataFrame({
            "high": [1.1], "low": [1.0], "close": [1.05],
        })
        atr = calc_atr(df, period=14)
        assert atr == 0  # Not enough data → NaN → 0
