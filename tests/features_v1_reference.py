"""
Oracle Trader v1 - Features Reference
=====================================

ARQUIVO DE REFERÊNCIA - NÃO USAR DIRETAMENTE NO v2!

Este arquivo é a implementação original de features do Oracle v1.
Mantido APENAS para validação de testes - garantir que o v2 produz
saídas idênticas.

Fonte: /mnt/project/features.py (Oracle v1.4.x)
Extraído em: 2026-02-04

REGRA DE OURO:
--------------
O arquivo oracle_v2/core/features.py DEVE produzir saídas IDÊNTICAS
a este arquivo para os mesmos inputs. Qualquer desvio invalida o modelo.

Testes de validação:
- tests/test_features_parity.py compara v1 vs v2
- Tolerância: 1e-6 (float32)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


# =============================================================================
# TIPOS MÍNIMOS (para rodar standalone)
# =============================================================================

@dataclass
class SymbolConfigV1:
    """Config mínima do v1 para referência."""
    # HMM
    hmm_momentum_period: int = 12
    hmm_consistency_period: int = 12
    hmm_range_period: int = 20
    n_states: int = 5
    
    # RL
    rl_roc_period: int = 10
    rl_atr_period: int = 14
    rl_ema_period: int = 200
    rl_range_period: int = 20
    rl_volume_ma_period: int = 20


@dataclass
class PositionV1:
    """Position mínima do v1 para referência."""
    direction: int = 0      # -1, 0, 1
    size: float = 0.0       # volume
    pnl: float = 0.0        # PnL atual


# =============================================================================
# FEATURE CALCULATOR V1 (REFERÊNCIA)
# =============================================================================

class FeatureCalculatorV1:
    """
    Calcula features HMM e RL exatamente como no treinamento.
    
    CÓDIGO ORIGINAL DO V1 - NÃO MODIFICAR!
    """
    
    def __init__(self, config: SymbolConfigV1):
        self.config = config
    
    def calc_hmm_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Features HMM: momentum, consistency, range_position
        Retorna array (1, 3)
        """
        close = df['close']
        high = df['high']
        low = df['low']
        
        # Momentum
        momentum = (close.pct_change()
                   .rolling(self.config.hmm_momentum_period)
                   .sum() * 100.0).clip(-5.0, 5.0)
        
        # Consistency
        returns = close.pct_change()
        up = (returns > 0).rolling(self.config.hmm_consistency_period).sum()
        down = (returns < 0).rolling(self.config.hmm_consistency_period).sum()
        consistency = ((np.maximum(up, down) / self.config.hmm_consistency_period * 2.0 - 1.0) 
                      * np.sign(up - down))
        
        # Range Position
        highest = high.rolling(self.config.hmm_range_period).max()
        lowest = low.rolling(self.config.hmm_range_period).min()
        rng = (highest - lowest).replace(0, np.nan)
        range_pos = (close - lowest) / rng * 2.0 - 1.0
        
        features = np.array([
            momentum.iloc[-1] if not pd.isna(momentum.iloc[-1]) else 0,
            consistency.iloc[-1] if not pd.isna(consistency.iloc[-1]) else 0,
            range_pos.iloc[-1] if not pd.isna(range_pos.iloc[-1]) else 0,
        ], dtype=np.float32)
        
        return features.reshape(1, -1)
    
    def calc_rl_features(self, df: pd.DataFrame, hmm_state: int, position: PositionV1) -> np.ndarray:
        """
        Features RL: 6 base + N estados HMM + 3 posição
        Retorna array (1, 6+N+3)
        """
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)
        
        # 1. Momentum (ROC)
        roc = np.tanh((close - close.shift(self.config.rl_roc_period)) / 
                      close.shift(self.config.rl_roc_period) * 20)
        
        # 2. Volatility (ATR normalizado)
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)
        atr = np.tanh((tr.rolling(self.config.rl_atr_period).mean() / close) * 50)
        
        # 3. Trend (vs EMA)
        ema = close.ewm(span=self.config.rl_ema_period, adjust=False).mean()
        trend = np.tanh(((close - ema) / ema) * 20)
        
        # 4. Range Position
        highest = high.rolling(self.config.rl_range_period).max()
        lowest = low.rolling(self.config.rl_range_period).min()
        rng = (highest - lowest).replace(0, np.nan)
        range_pos = (close - lowest) / rng * 2.0 - 1.0
        
        # 5. Volume relativo
        vol_ma = volume.rolling(self.config.rl_volume_ma_period).mean()
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
        hmm_onehot = [1.0 if i == hmm_state else 0.0 for i in range(self.config.n_states)]
        
        # Position features (CRÍTICO: PnL normalizado com tanh!)
        pos_features = [
            float(position.direction),           # -1, 0, 1
            float(position.size) * 10,           # size * 10
            np.tanh(float(position.pnl) / 100.0) # PnL normalizado
        ]
        
        features = np.array(base + hmm_onehot + pos_features, dtype=np.float32)
        return features.reshape(1, -1)
    
    def calc_atr(self, df: pd.DataFrame, period: int = None) -> float:
        """Calcula ATR atual"""
        if period is None:
            period = self.config.rl_atr_period
        
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


# =============================================================================
# EXEMPLO DE TESTE DE PARIDADE
# =============================================================================

def test_parity_example():
    """
    Exemplo de como testar paridade entre v1 e v2.
    
    Este código deve ser adaptado para tests/test_features_parity.py
    """
    import numpy as np
    
    # Dados de teste
    np.random.seed(42)
    n = 300
    df = pd.DataFrame({
        'time': np.arange(n) * 900,  # 15 min intervals
        'open': 1.1000 + np.cumsum(np.random.randn(n) * 0.0001),
        'high': 0,
        'low': 0,
        'close': 0,
        'volume': np.random.randint(100, 1000, n),
    })
    df['close'] = df['open'] + np.random.randn(n) * 0.0005
    df['high'] = df[['open', 'close']].max(axis=1) + abs(np.random.randn(n) * 0.0002)
    df['low'] = df[['open', 'close']].min(axis=1) - abs(np.random.randn(n) * 0.0002)
    
    # Config
    config = SymbolConfigV1()
    
    # V1
    calc_v1 = FeatureCalculatorV1(config)
    hmm_v1 = calc_v1.calc_hmm_features(df)
    
    position = PositionV1(direction=1, size=0.01, pnl=15.50)
    rl_v1 = calc_v1.calc_rl_features(df, hmm_state=2, position=position)
    
    print("HMM Features (v1):", hmm_v1)
    print("RL Features (v1):", rl_v1)
    print("Shape HMM:", hmm_v1.shape)
    print("Shape RL:", rl_v1.shape)
    
    # Aqui você compararia com v2:
    # from oracle_v2.core.features import FeatureCalculator
    # calc_v2 = FeatureCalculator(config_v2)
    # hmm_v2 = calc_v2.calc_hmm_features(df)
    # np.testing.assert_array_almost_equal(hmm_v1, hmm_v2, decimal=6)


if __name__ == "__main__":
    test_parity_example()
