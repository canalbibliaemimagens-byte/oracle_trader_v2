"""
Oracle Trader v2.0 - Constantes e Enums Globais
================================================

Definições imutáveis compartilhadas por todos os módulos.
NENHUMA dependência de I/O ou libs externas.
"""

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
TIMEFRAME_SECONDS: dict[Timeframe, int] = {
    Timeframe.M1: 60,
    Timeframe.M5: 300,
    Timeframe.M15: 900,
    Timeframe.M30: 1800,
    Timeframe.H1: 3600,
    Timeframe.H4: 14400,
    Timeframe.D1: 86400,
}

# Barras por ano (forex, ~252 dias úteis, ~20h/dia)
TIMEFRAME_BARS_PER_YEAR: dict[Timeframe, int] = {
    Timeframe.M1: 252 * 20 * 60,    # 302.400
    Timeframe.M5: 252 * 20 * 12,    # 60.480
    Timeframe.M15: 252 * 20 * 4,    # 20.160
    Timeframe.M30: 252 * 20 * 2,    # 10.080
    Timeframe.H1: 252 * 20,         # 5.040
    Timeframe.H4: 252 * 5,          # 1.260
    Timeframe.D1: 252,              # 252
}

# Lotes internos usados no treino (NUNCA mudar - identidade treino-execução)
TRAINING_LOT_SIZES: list[float] = [0, 0.01, 0.03, 0.05]

# Buffer mínimo de barras para iniciar predição
MIN_BARS_FOR_PREDICTION: int = 350

# Barras carregadas no warmup (histórico completo)
WARMUP_BARS: int = 1000
