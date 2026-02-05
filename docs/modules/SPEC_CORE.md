# 📦 Módulo CORE: Especificação Técnica

**Versão:** 1.1  
**Nível:** Compartilhado (Dependência Zero)  
**Responsabilidade:** Definições fundamentais, contratos de dados e lógica puramente matemática/funcional. NENHUMA dependência de I/O, rede ou libs externas complexas (exceto numpy/pandas).

---

## 1. Estrutura de Arquivos

```
oracle_v2/core/
├── __init__.py
├── constants.py       # Enums e Constantes Globais
├── models.py          # Dataclasses (Contratos de Dados)
├── actions.py         # Lógica de Ações e Intensidade
├── features.py        # Cálculo de Features (Idêntico ao Treino)
└── utils.py           # Funções auxiliares puras
```

---

## 2. Componentes

### 2.1 Constants (`constants.py`)

Definições imutáveis do sistema.

```python
from enum import Enum

VERSION = "2.0.0"

class Direction(int, Enum):
    """Direção de posição."""
    SHORT = -1
    FLAT = 0
    LONG = 1

class Timeframe(str, Enum):
    """Timeframes suportados."""
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

# Mapeamento de timeframe para segundos
TIMEFRAME_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}

# Mapeamento de timeframe para barras por ano (forex, 5d/semana)
TIMEFRAME_BARS_PER_YEAR = {
    Timeframe.M1: 252 * 20 * 60,
    Timeframe.M5: 252 * 20 * 12,
    Timeframe.M15: 252 * 20 * 4,
    Timeframe.M30: 252 * 20 * 2,
    Timeframe.H1: 252 * 20,
    Timeframe.H4: 252 * 5,
    Timeframe.D1: 252,
}

# Lotes internos usados no treino (NUNCA mudar)
TRAINING_LOT_SIZES = [0, 0.01, 0.03, 0.05]

# Buffer mínimo para predição
MIN_BARS_FOR_PREDICTION = 350
```

### 2.2 Models (`models.py`)

Data Transfer Objects (DTOs) usados entre módulos.

```python
from dataclasses import dataclass, field
from typing import Optional, List
from .constants import Direction

@dataclass(frozen=True)
class Bar:
    """
    Barra OHLCV imutável.
    Usada para transferir dados de mercado entre módulos.
    """
    symbol: str
    time: int           # Unix Timestamp (segundos, UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Signal:
    """
    Sinal emitido pelo Preditor.
    Contém ação, intensidade e metadados para logging.
    """
    symbol: str
    action: str             # "WAIT", "LONG_WEAK", etc.
    direction: int          # -1, 0, 1
    intensity: int          # 0, 1, 2, 3
    hmm_state: int          # 0-4 (estado HMM)
    virtual_pnl: float      # PnL da posição virtual
    timestamp: float        # Unix timestamp
    
    @property
    def is_entry(self) -> bool:
        """Verifica se é sinal de entrada."""
        return self.direction != 0
    
    @property
    def is_exit(self) -> bool:
        """Verifica se é sinal de saída (WAIT)."""
        return self.direction == 0


@dataclass
class AccountInfo:
    """Informações da conta de trading."""
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float     # % (equity / margin * 100)
    currency: str = "USD"


@dataclass
class Position:
    """Posição aberta no broker."""
    ticket: int
    symbol: str
    direction: int          # 1 = LONG, -1 = SHORT
    volume: float
    open_price: float
    current_price: float
    pnl: float
    sl: float
    tp: float
    open_time: int          # Unix timestamp
    comment: str = ""


@dataclass
class OrderResult:
    """Resultado de operação de ordem."""
    success: bool
    ticket: Optional[int] = None
    price: Optional[float] = None
    error: str = ""


@dataclass
class VirtualPosition:
    """
    Posição virtual mantida pelo Preditor.
    NÃO representa posição real - apenas para cálculo de features.
    """
    direction: int = 0          # -1, 0, 1
    intensity: int = 0          # 0, 1, 2, 3
    entry_price: float = 0.0
    current_pnl: float = 0.0
    
    @property
    def is_open(self) -> bool:
        return self.direction != 0
    
    @property
    def direction_name(self) -> str:
        if self.direction == 1:
            return "LONG"
        elif self.direction == -1:
            return "SHORT"
        return "FLAT"
```

### 2.3 Actions (`actions.py`)

Centraliza a definição das 7 ações do espaço de ação do RL.

```python
from enum import Enum
from .constants import Direction

class Action(str, Enum):
    """
    Ações do modelo PPO.
    
    Nomenclatura:
    - WAIT: Ficar fora (não confundir com FLAT que é estado de posição)
    - WEAK/MODERATE/STRONG: Intensidade do sinal (1/2/3)
    """
    WAIT = "WAIT"
    LONG_WEAK = "LONG_WEAK"
    LONG_MODERATE = "LONG_MODERATE"
    LONG_STRONG = "LONG_STRONG"
    SHORT_WEAK = "SHORT_WEAK"
    SHORT_MODERATE = "SHORT_MODERATE"
    SHORT_STRONG = "SHORT_STRONG"


# Mapeamento de índice PPO para Action
ACTIONS_MAP = {
    0: Action.WAIT,
    1: Action.LONG_WEAK,
    2: Action.LONG_MODERATE,
    3: Action.LONG_STRONG,
    4: Action.SHORT_WEAK,
    5: Action.SHORT_MODERATE,
    6: Action.SHORT_STRONG,
}

# Mapeamento inverso
ACTION_TO_INDEX = {action: idx for idx, action in ACTIONS_MAP.items()}


def action_from_index(idx: int) -> Action:
    """
    Converte índice PPO (0-6) para Action.
    
    Args:
        idx: Índice retornado pelo modelo PPO
        
    Returns:
        Action correspondente
    """
    return ACTIONS_MAP.get(idx, Action.WAIT)


def get_direction(action: Action) -> Direction:
    """
    Extrai direção de uma Action.
    
    Args:
        action: Action do modelo
        
    Returns:
        Direction (-1, 0, 1)
    """
    if action.value.startswith("LONG"):
        return Direction.LONG
    elif action.value.startswith("SHORT"):
        return Direction.SHORT
    return Direction.FLAT


def get_intensity(action: Action) -> int:
    """
    Extrai intensidade de uma Action.
    
    Args:
        action: Action do modelo
        
    Returns:
        Intensidade (0, 1, 2, 3)
    """
    if action == Action.WAIT:
        return 0
    elif action.value.endswith("WEAK"):
        return 1
    elif action.value.endswith("MODERATE"):
        return 2
    elif action.value.endswith("STRONG"):
        return 3
    return 0


def get_action_properties(action_idx: int) -> tuple:
    """
    Converte índice de ação para (Direction, Intensity).
    
    Args:
        action_idx: Índice da ação (0-6)
        
    Returns:
        Tupla (Direction, int intensity)
    """
    action = action_from_index(action_idx)
    return get_direction(action), get_intensity(action)
```

### 2.4 Features (`features.py`)

**CRÍTICO:** Este arquivo deve ser uma cópia **exata** da lógica usada no notebook de treinamento (`oracle-v8.ipynb`). Qualquer desvio causa *Feature Mismatch* e invalida o modelo.

```python
import numpy as np
import pandas as pd
from typing import Tuple
from .models import VirtualPosition

class FeatureCalculator:
    """
    Calcula features HMM e RL.
    DEVE ser idêntico ao TradingEnv do notebook de treino.
    """
    
    def __init__(self, config: dict):
        """
        Args:
            config: Dicionário com parâmetros (de hmm_config e rl_config)
        """
        # HMM params
        self.hmm_momentum_period = config.get('momentum_period', 12)
        self.hmm_consistency_period = config.get('consistency_period', 12)
        self.hmm_range_period = config.get('range_period', 20)
        
        # RL params
        self.rl_roc_period = config.get('roc_period', 10)
        self.rl_atr_period = config.get('atr_period', 14)
        self.rl_ema_period = config.get('ema_period', 200)
        self.rl_range_period = config.get('range_period', 20)
        self.rl_volume_ma_period = config.get('volume_ma_period', 20)
        
        # Número de estados HMM (para one-hot encoding)
        self.n_states = config.get('n_states', 5)
    
    def calc_hmm_features(self, df: pd.DataFrame) -> np.ndarray:
        """
        Calcula features para input do HMM.
        
        Features: [momentum, consistency, range_position]
        
        Args:
            df: DataFrame com colunas [open, high, low, close, volume]
            
        Returns:
            Array shape (1, 3) para predição
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
        
        # Pega última linha
        features = np.array([
            momentum.iloc[-1] if not pd.isna(momentum.iloc[-1]) else 0,
            consistency.iloc[-1] if not pd.isna(consistency.iloc[-1]) else 0,
            range_pos.iloc[-1] if not pd.isna(range_pos.iloc[-1]) else 0,
        ], dtype=np.float32)
        
        return features.reshape(1, -1)
    
    def calc_rl_features(self, df: pd.DataFrame, hmm_state: int, 
                         position: VirtualPosition) -> np.ndarray:
        """
        Calcula features para input do PPO.
        
        Features: [6 mercado] + [N estados HMM one-hot] + [3 posição]
        
        Args:
            df: DataFrame com colunas [time, open, high, low, close, volume]
            hmm_state: Estado HMM atual (0 a N-1)
            position: Posição virtual atual
            
        Returns:
            Array shape (1, 6+N+3) para predição
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
            float(position.direction),           # -1, 0, 1
            float(position.intensity) * 10,      # intensity * 10 (ou size * 10 no treino)
            np.tanh(float(position.current_pnl) / 100.0)  # PnL normalizado
        ]
        
        features = np.array(base + hmm_onehot + pos_features, dtype=np.float32)
        return features.reshape(1, -1)


def calc_atr(df: pd.DataFrame, period: int = 14) -> float:
    """
    Calcula ATR atual (útil para SL dinâmico).
    
    Args:
        df: DataFrame OHLCV
        period: Período do ATR
        
    Returns:
        Valor do ATR
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
```

### 2.5 Utils (`utils.py`)

Funções auxiliares puras.

```python
from datetime import datetime, timezone
from typing import List
from .models import Bar

def bars_to_dataframe(bars: List[Bar]) -> 'pd.DataFrame':
    """
    Converte lista de Bar para DataFrame.
    
    Args:
        bars: Lista de objetos Bar
        
    Returns:
        DataFrame com colunas [time, open, high, low, close, volume]
    """
    import pandas as pd
    
    if not bars:
        return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])
    
    return pd.DataFrame([
        {
            'time': b.time,
            'open': b.open,
            'high': b.high,
            'low': b.low,
            'close': b.close,
            'volume': b.volume
        }
        for b in bars
    ])


def timestamp_to_datetime(ts: int) -> datetime:
    """Converte Unix timestamp para datetime UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def datetime_to_timestamp(dt: datetime) -> int:
    """Converte datetime para Unix timestamp."""
    return int(dt.timestamp())


def round_lot(volume: float, lot_step: float = 0.01) -> float:
    """
    Arredonda volume para o lot_step mais próximo.
    
    Args:
        volume: Volume desejado
        lot_step: Incremento mínimo de lote
        
    Returns:
        Volume arredondado
    """
    return round(volume / lot_step) * lot_step


def pips_to_price(pips: float, point: float, digits: int) -> float:
    """
    Converte pips para variação de preço.
    
    Args:
        pips: Número de pips
        point: Valor do point (ex: 0.00001)
        digits: Número de casas decimais
        
    Returns:
        Variação de preço
    """
    pip_multiplier = 10 if digits in [3, 5] else 1
    return pips * point * pip_multiplier
```

---

## 3. Regras de Desenvolvimento

1. **Sem I/O:** O Core nunca lê arquivos nem acessa rede.
2. **Pureza:** Funções devem ser puras (output depende apenas dos inputs).
3. **Tipagem:** Uso estrito de Type Hints.
4. **Imutabilidade:** Preferir dataclasses `frozen=True` quando possível.
5. **Testes:** Cobertura de 100% para `features.py` comparando com saídas do notebook.

---

## 4. Validação de Features (Testes)

O arquivo `features.py` é crítico. Qualquer desvio do notebook invalida o modelo.

```python
# tests/test_features.py

import numpy as np
import pandas as pd
from oracle_v2.core.features import FeatureCalculator
from oracle_v2.core.models import VirtualPosition

def test_hmm_features_match_notebook():
    """Verifica se features HMM são idênticas ao notebook."""
    # Carregar dados de referência do notebook
    df = pd.read_csv("tests/fixtures/sample_ohlcv.csv")
    expected = np.load("tests/fixtures/hmm_features_expected.npy")
    
    config = {
        'momentum_period': 12,
        'consistency_period': 12,
        'range_period': 20,
    }
    calc = FeatureCalculator(config)
    result = calc.calc_hmm_features(df)
    
    np.testing.assert_array_almost_equal(result, expected, decimal=6)


def test_rl_features_match_notebook():
    """Verifica se features RL são idênticas ao notebook."""
    df = pd.read_csv("tests/fixtures/sample_ohlcv.csv")
    expected = np.load("tests/fixtures/rl_features_expected.npy")
    
    config = {
        'roc_period': 10,
        'atr_period': 14,
        'ema_period': 200,
        'range_period': 20,
        'volume_ma_period': 20,
        'n_states': 5,
    }
    calc = FeatureCalculator(config)
    
    position = VirtualPosition(direction=1, intensity=1, current_pnl=50.0)
    result = calc.calc_rl_features(df, hmm_state=2, position=position)
    
    np.testing.assert_array_almost_equal(result, expected, decimal=6)
```

---

## 5. Glossário

| Termo | Significado | Contexto |
|-------|-------------|----------|
| **FLAT** | Estado de posição = sem posição aberta | Feature `direction=0` |
| **WAIT** | Sinal/Ação = "não operar agora" | Ação índice 0 do modelo |
| **Intensidade** | Força do sinal (1=fraco, 2=moderado, 3=forte) | Mapeado para lotes no Executor |
| **Virtual Position** | Posição simulada no Preditor | Nunca afeta conta real |
| **Feature Mismatch** | Diferença entre features do treino e execução | Invalida o modelo |

---

*Versão 1.1 - Atualizado em 2026-02-04*
