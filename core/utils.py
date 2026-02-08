"""
Oracle Trader v2.0 - Funções Auxiliares
=======================================

Funções puras de utilidade. Sem I/O, sem estado, sem efeitos colaterais.
"""

from datetime import datetime, timezone
from typing import List

import pandas as pd

from .models import Bar


def bars_to_dataframe(bars: List[Bar]) -> pd.DataFrame:
    """
    Converte lista de Bar para DataFrame no formato esperado pelo FeatureCalculator.

    Args:
        bars: Lista de objetos Bar (ordenados do mais antigo para mais recente).

    Returns:
        DataFrame com colunas [time, open, high, low, close, volume].
    """
    if not bars:
        return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

    return pd.DataFrame([
        {
            'time': b.time,
            'open': b.open,
            'high': b.high,
            'low': b.low,
            'close': b.close,
            'volume': b.volume,
        }
        for b in bars
    ])


def timestamp_to_datetime(ts: int) -> datetime:
    """Converte Unix timestamp (segundos) para datetime UTC."""
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def datetime_to_timestamp(dt: datetime) -> int:
    """Converte datetime para Unix timestamp (segundos)."""
    return int(dt.timestamp())


def round_lot(volume: float, lot_step: float = 0.01) -> float:
    """
    Arredonda volume para o lot_step mais próximo.

    Args:
        volume: Volume desejado.
        lot_step: Incremento mínimo de lote.

    Returns:
        Volume arredondado.
    """
    if lot_step <= 0:
        return volume
    return round(volume / lot_step) * lot_step


def pips_to_price(pips: float, point: float, digits: int) -> float:
    """
    Converte pips para variação de preço.

    Args:
        pips: Número de pips.
        point: Valor do point (ex: 0.00001 para EURUSD).
        digits: Número de casas decimais do preço.

    Returns:
        Variação de preço correspondente.
    """
    pip_multiplier = 10 if digits in (3, 5) else 1
    return pips * point * pip_multiplier
