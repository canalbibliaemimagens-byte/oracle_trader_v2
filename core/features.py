"""
Oracle Trader v2.0 - Cálculo de Features
=========================================

⚠️ ARQUIVO CRÍTICO ⚠️

Este módulo DEVE produzir saídas IDÊNTICAS ao TradingEnv do notebook
de treinamento (oracle-v8 / oracle_v2_notebook_1.0).

Qualquer desvio causa Feature Mismatch e invalida o modelo treinado.

Validação:
  - tests/test_features_parity.py compara v1 (referência) vs v2 (este arquivo)
  - Tolerância: 1e-6 (float32)

REGRA DE OURO: Não otimize, não refatore, não "melhore".
Mantenha a lógica EXATAMENTE igual ao treino.
"""

import numpy as np
import pandas as pd
from .models import VirtualPosition


class FeatureCalculator:
    """
    Calcula features HMM e RL.
    DEVE ser idêntico ao TradingEnv do notebook de treino.
    """

    def __init__(self, config: dict):
        """
        Args:
            config: Dicionário com parâmetros (de hmm_config + rl_config do metadata).
                    Campos esperados:
                      HMM: momentum_period, consistency_period, range_period, n_states
                      RL:  roc_period, atr_period, ema_period, range_period, volume_ma_period
        """
        # HMM params
        self.hmm_momentum_period: int = config.get('momentum_period', 12)
        self.hmm_consistency_period: int = config.get('consistency_period', 12)
        self.hmm_range_period: int = config.get('range_period', 20)

        # RL params
        self.rl_roc_period: int = config.get('roc_period', 10)
        self.rl_atr_period: int = config.get('atr_period', 14)
        self.rl_ema_period: int = config.get('ema_period', 200)
        self.rl_range_period: int = config.get('range_period', 20)
        self.rl_volume_ma_period: int = config.get('volume_ma_period', 20)

        # Número de estados HMM (para one-hot encoding)
        self.n_states: int = config.get('n_states', 5)

    def calc_hmm_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Calcula features para input do HMM.

        Features: [momentum, consistency, range_position]

        Args:
            df: DataFrame com colunas [open, high, low, close, volume].

        Returns:
            Array shape (1, 3) dtype float32.
        """
        close = df['close']
        high = df['high']
        low = df['low']

        # Momentum
        momentum = (close.pct_change()
                    .rolling(self.hmm_momentum_period)
                    .sum() * 100.0).clip(-5.0, 5.0)

        # Consistency
        returns = close.pct_change()
        up = (returns > 0).rolling(self.hmm_consistency_period).sum()
        down = (returns < 0).rolling(self.hmm_consistency_period).sum()
        consistency = ((np.maximum(up, down) / self.hmm_consistency_period * 2.0 - 1.0)
                       * np.sign(up - down))

        # Range Position
        highest = high.rolling(self.hmm_range_period).max()
        lowest = low.rolling(self.hmm_range_period).min()
        rng = (highest - lowest).replace(0, np.nan)
        range_pos = (close - lowest) / rng * 2.0 - 1.0

        # Pega última linha, substitui NaN por 0
        features = np.array([
            momentum.iloc[-1] if not pd.isna(momentum.iloc[-1]) else 0,
            consistency.iloc[-1] if not pd.isna(consistency.iloc[-1]) else 0,
            range_pos.iloc[-1] if not pd.isna(range_pos.iloc[-1]) else 0,
        ], dtype=np.float32)

        return features.reshape(1, -1)

    def calc_rl_features(
        self,
        df: pd.DataFrame,
        hmm_state: int,
        position: VirtualPosition,
    ) -> np.ndarray:
        """
        Calcula features para input do PPO.

        Features: [6 mercado] + [N estados HMM one-hot] + [3 posição]
        Total: 6 + n_states + 3

        Args:
            df: DataFrame com colunas [time, open, high, low, close, volume].
            hmm_state: Estado HMM atual (0 a N-1).
            position: Posição virtual atual.

        Returns:
            Array shape (1, 6+N+3) dtype float32.
        """
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)

        # 1. Momentum (ROC)
        roc = np.tanh((close - close.shift(self.rl_roc_period)) /
                      close.shift(self.rl_roc_period) * 20)

        # 2. Volatility (ATR normalizado)
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        atr = np.tanh((tr.rolling(self.rl_atr_period).mean() / close) * 50)

        # 3. Trend (vs EMA)
        ema = close.ewm(span=self.rl_ema_period, adjust=False).mean()
        trend = np.tanh(((close - ema) / ema) * 20)

        # 4. Range Position
        highest = high.rolling(self.rl_range_period).max()
        lowest = low.rolling(self.rl_range_period).min()
        rng = (highest - lowest).replace(0, np.nan)
        range_pos = (close - lowest) / rng * 2.0 - 1.0

        # 5. Volume relativo
        vol_ma = volume.rolling(self.rl_volume_ma_period).mean()
        vol_rel = np.tanh((volume / vol_ma.replace(0, 1) - 1) * 2)

        # 6. Session (hora do dia)
        if 'time' in df.columns:
            dt = pd.to_datetime(df['time'], unit='s')
            session = np.sin(2 * np.pi * dt.dt.hour / 24)
        else:
            session = pd.Series(0, index=df.index)

        # Base features (última linha)
        base = [
            roc.iloc[-1] if not pd.isna(roc.iloc[-1]) else 0,
            atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0,
            trend.iloc[-1] if not pd.isna(trend.iloc[-1]) else 0,
            range_pos.iloc[-1] if not pd.isna(range_pos.iloc[-1]) else 0,
            vol_rel.iloc[-1] if not pd.isna(vol_rel.iloc[-1]) else 0,
            session.iloc[-1] if not pd.isna(session.iloc[-1]) else 0,
        ]

        # HMM state one-hot encoding
        hmm_onehot = [1.0 if i == hmm_state else 0.0 for i in range(self.n_states)]

        # Position features (CRÍTICO: PnL normalizado com tanh!)
        pos_features = [
            float(position.direction),              # -1, 0, 1
            float(position.size) * 10,              # size * 10 (lote do treino)
            np.tanh(float(position.current_pnl) / 100.0)  # PnL normalizado
        ]

        features = np.array(base + hmm_onehot + pos_features, dtype=np.float32)
        return features.reshape(1, -1)


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calcula ATR atual (útil para SL dinâmico no Executor).

    Args:
        df: DataFrame OHLCV.
        period: Período do ATR.

    Returns:
        Valor do ATR. 0 se NaN.
    """
    high = df['high']
    low = df['low']
    close = df['close']

    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]
    return atr if not pd.isna(atr) else 0
