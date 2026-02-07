"""
Teste de Paridade: Features v1 (referência) vs v2 (produção).

⚠️ TESTE CRÍTICO ⚠️
Se este teste falhar, o modelo treinado será invalidado.
Qualquer diferença entre v1 e v2 causa Feature Mismatch.

Tolerância: 1e-6 (float32 precision).

Usa features_v1_reference.py como ground truth.
"""

import numpy as np
import pandas as pd
import pytest

from oracle_trader_v2.core.features import FeatureCalculator
from oracle_trader_v2.core.models import VirtualPosition
from oracle_trader_v2.tests.features_v1_reference import (
    FeatureCalculatorV1,
    SymbolConfigV1,
    PositionV1,
)

TOLERANCE = 1e-6


# ── Dados de teste ───────────────────────────────────────────────────────────

def _make_test_dataframe(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Gera DataFrame de teste determinístico (mesma seed = mesmos dados)."""
    np.random.seed(seed)
    df = pd.DataFrame({
        'time': np.arange(n) * 900,  # M15 intervals
        'open': 1.1000 + np.cumsum(np.random.randn(n) * 0.0001),
        'volume': np.random.randint(100, 1000, n).astype(float),
    })
    df['close'] = df['open'] + np.random.randn(n) * 0.0005
    df['high'] = df[['open', 'close']].max(axis=1) + abs(np.random.randn(n) * 0.0002)
    df['low'] = df[['open', 'close']].min(axis=1) - abs(np.random.randn(n) * 0.0002)
    return df


def _make_v1_config() -> SymbolConfigV1:
    return SymbolConfigV1()


def _make_v2_config() -> dict:
    """Config v2 com mesmos valores default do v1."""
    return {
        'momentum_period': 12,
        'consistency_period': 12,
        'range_period': 20,
        'n_states': 5,
        'roc_period': 10,
        'atr_period': 14,
        'ema_period': 200,
        'volume_ma_period': 20,
    }


# ── HMM Features ────────────────────────────────────────────────────────────

class TestHMMFeaturesParity:
    """Compara calc_hmm_features entre v1 e v2."""

    def test_hmm_shape_identical(self):
        """Shape do output deve ser (1, 3) em ambas versões."""
        df = _make_test_dataframe()
        v1 = FeatureCalculatorV1(_make_v1_config()).calc_hmm_features(df)
        v2 = FeatureCalculator(_make_v2_config()).calc_hmm_features(df)
        assert v1.shape == v2.shape == (1, 3)

    def test_hmm_dtype_identical(self):
        """Dtype deve ser float32 em ambas versões."""
        df = _make_test_dataframe()
        v1 = FeatureCalculatorV1(_make_v1_config()).calc_hmm_features(df)
        v2 = FeatureCalculator(_make_v2_config()).calc_hmm_features(df)
        assert v1.dtype == v2.dtype == np.float32

    def test_hmm_values_identical(self):
        """Valores devem ser idênticos (dentro da tolerância float32)."""
        df = _make_test_dataframe()
        v1 = FeatureCalculatorV1(_make_v1_config()).calc_hmm_features(df)
        v2 = FeatureCalculator(_make_v2_config()).calc_hmm_features(df)
        np.testing.assert_array_almost_equal(v1, v2, decimal=6,
            err_msg="HMM features divergem entre v1 e v2!")

    @pytest.mark.parametrize("seed", [42, 123, 999, 7, 2026])
    def test_hmm_multiple_seeds(self, seed):
        """Paridade deve valer para diferentes dados aleatórios."""
        df = _make_test_dataframe(n=300, seed=seed)
        v1 = FeatureCalculatorV1(_make_v1_config()).calc_hmm_features(df)
        v2 = FeatureCalculator(_make_v2_config()).calc_hmm_features(df)
        np.testing.assert_array_almost_equal(v1, v2, decimal=6,
            err_msg=f"HMM diverge com seed={seed}")

    def test_hmm_short_buffer(self):
        """Com buffer mínimo (50 barras), features não devem ser NaN."""
        df = _make_test_dataframe(n=50)
        v1 = FeatureCalculatorV1(_make_v1_config()).calc_hmm_features(df)
        v2 = FeatureCalculator(_make_v2_config()).calc_hmm_features(df)
        np.testing.assert_array_almost_equal(v1, v2, decimal=6)


# ── RL Features ──────────────────────────────────────────────────────────────

class TestRLFeaturesParity:
    """Compara calc_rl_features entre v1 e v2."""

    def _compare_rl(self, direction=0, size=0.0, pnl=0.0, hmm_state=0, seed=42):
        """Helper: compara RL features entre v1 e v2."""
        df = _make_test_dataframe(n=300, seed=seed)

        # v1
        pos_v1 = PositionV1(direction=direction, size=size, pnl=pnl)
        rl_v1 = FeatureCalculatorV1(_make_v1_config()).calc_rl_features(
            df, hmm_state=hmm_state, position=pos_v1,
        )

        # v2 — VirtualPosition é dataclass, setar atributos diretamente
        pos_v2 = VirtualPosition()
        pos_v2.direction = direction
        pos_v2.current_pnl = pnl
        # Para size: v2 usa property que faz lookup em TRAINING_LOT_SIZES[intensity]
        from oracle_trader_v2.core.constants import TRAINING_LOT_SIZES
        intensity = 0
        for i, lot in enumerate(TRAINING_LOT_SIZES):
            if abs(lot - size) < 1e-6:
                intensity = i
                break
        pos_v2.intensity = intensity

        rl_v2 = FeatureCalculator(_make_v2_config()).calc_rl_features(
            df, hmm_state=hmm_state, position=pos_v2,
        )

        return rl_v1, rl_v2

    def test_rl_flat_position(self):
        """Posição flat (direction=0, size=0, pnl=0)."""
        rl_v1, rl_v2 = self._compare_rl(direction=0, size=0.0, pnl=0.0, hmm_state=0)
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6,
            err_msg="RL features divergem em posição flat!")

    def test_rl_long_position(self):
        """Posição LONG com PnL positivo."""
        rl_v1, rl_v2 = self._compare_rl(direction=1, size=0.01, pnl=15.50, hmm_state=2)
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6,
            err_msg="RL features divergem em LONG!")

    def test_rl_short_position(self):
        """Posição SHORT com PnL negativo."""
        rl_v1, rl_v2 = self._compare_rl(direction=-1, size=0.03, pnl=-8.25, hmm_state=4)
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6,
            err_msg="RL features divergem em SHORT!")

    def test_rl_shape_identical(self):
        """Shape: (1, 6 + n_states + 3) = (1, 14)."""
        rl_v1, rl_v2 = self._compare_rl()
        assert rl_v1.shape == rl_v2.shape == (1, 14)

    def test_rl_dtype_float32(self):
        rl_v1, rl_v2 = self._compare_rl()
        assert rl_v1.dtype == np.float32
        assert rl_v2.dtype == np.float32

    @pytest.mark.parametrize("hmm_state", [0, 1, 2, 3, 4])
    def test_rl_all_hmm_states(self, hmm_state):
        """Paridade para todos os estados HMM."""
        rl_v1, rl_v2 = self._compare_rl(
            direction=1, size=0.01, pnl=5.0, hmm_state=hmm_state,
        )
        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6,
            err_msg=f"RL diverge com hmm_state={hmm_state}")

    def test_rl_one_hot_correct(self):
        """Verifica que one-hot encoding do HMM state está correto."""
        rl_v1, rl_v2 = self._compare_rl(hmm_state=3)
        # Posições 6..10 são one-hot do HMM (indices 6,7,8,9,10 para 5 estados)
        hmm_v1 = rl_v1[0, 6:11]
        hmm_v2 = rl_v2[0, 6:11]
        expected = np.array([0, 0, 0, 1, 0], dtype=np.float32)
        np.testing.assert_array_equal(hmm_v1, expected)
        np.testing.assert_array_equal(hmm_v2, expected)

    @pytest.mark.parametrize("seed", [42, 123, 999])
    def test_rl_multiple_seeds(self, seed):
        """Paridade para diferentes conjuntos de dados."""
        df = _make_test_dataframe(n=300, seed=seed)

        pos_v1 = PositionV1(direction=1, size=0.01, pnl=10.0)
        rl_v1 = FeatureCalculatorV1(_make_v1_config()).calc_rl_features(
            df, hmm_state=2, position=pos_v1,
        )

        pos_v2 = VirtualPosition()
        pos_v2.direction = 1
        pos_v2.intensity = 1  # 0.01 lot
        pos_v2.current_pnl = 10.0

        rl_v2 = FeatureCalculator(_make_v2_config()).calc_rl_features(
            df, hmm_state=2, position=pos_v2,
        )

        np.testing.assert_array_almost_equal(rl_v1, rl_v2, decimal=6,
            err_msg=f"RL diverge com seed={seed}")


# ── ATR ──────────────────────────────────────────────────────────────────────

class TestATRParity:
    """Compara calc_atr entre v1 e v2."""

    def test_atr_identical(self):
        df = _make_test_dataframe()
        from oracle_trader_v2.core.features import calc_atr as calc_atr_v2
        atr_v1 = FeatureCalculatorV1(_make_v1_config()).calc_atr(df)
        atr_v2 = calc_atr_v2(df, period=14)
        assert abs(atr_v1 - atr_v2) < TOLERANCE

    @pytest.mark.parametrize("period", [7, 14, 20, 50])
    def test_atr_different_periods(self, period):
        df = _make_test_dataframe()
        from oracle_trader_v2.core.features import calc_atr as calc_atr_v2
        atr_v1 = FeatureCalculatorV1(_make_v1_config()).calc_atr(df, period=period)
        atr_v2 = calc_atr_v2(df, period=period)
        assert abs(atr_v1 - atr_v2) < TOLERANCE


# ── Position Features Específicos ────────────────────────────────────────────

class TestPositionFeaturesParity:
    """Testa especificamente os 3 campos de posição."""

    def test_pnl_normalization_tanh(self):
        """PnL normalizado deve usar tanh(pnl/100)."""
        for pnl_val in [-200, -50, 0, 15.5, 100, 500]:
            expected = np.tanh(pnl_val / 100.0)

            # v1
            pos_v1 = PositionV1(direction=1, size=0.01, pnl=pnl_val)
            df = _make_test_dataframe()
            rl_v1 = FeatureCalculatorV1(_make_v1_config()).calc_rl_features(
                df, hmm_state=0, position=pos_v1,
            )
            pnl_feature_v1 = rl_v1[0, -1]  # Último feature é PnL normalizado
            assert abs(pnl_feature_v1 - expected) < TOLERANCE, \
                f"v1 PnL norm errado para pnl={pnl_val}: {pnl_feature_v1} != {expected}"

    def test_size_multiplier_10(self):
        """size feature deve ser size * 10."""
        pos_v1 = PositionV1(direction=1, size=0.03, pnl=0)
        df = _make_test_dataframe()
        rl_v1 = FeatureCalculatorV1(_make_v1_config()).calc_rl_features(
            df, hmm_state=0, position=pos_v1,
        )
        size_feature = rl_v1[0, -2]  # Penúltimo feature é size*10
        assert abs(size_feature - 0.3) < TOLERANCE  # 0.03 * 10 = 0.3
