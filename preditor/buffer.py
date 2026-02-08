"""
Oracle Trader v2.0 - Buffer FIFO de Barras
===========================================

Janela deslizante que mantém as últimas N barras em memória.
Usado pelo Preditor para alimentar o FeatureCalculator.

O buffer garante que:
  - Sempre mantém no máximo `maxlen` barras (FIFO: a mais antiga é descartada)
  - Converte para DataFrame no formato esperado pelo FeatureCalculator
  - Reporta `is_ready` quando atingiu a capacidade mínima
"""

from collections import deque
from typing import List

import pandas as pd

from core.models import Bar


class BarBuffer:
    """Buffer FIFO para barras OHLCV."""

    def __init__(self, maxlen: int = 350):
        """
        Args:
            maxlen: Capacidade máxima do buffer (mínimo para predição).
        """
        self.maxlen = maxlen
        self._buffer: deque[Bar] = deque(maxlen=maxlen)

    def append(self, bar: Bar) -> None:
        """Adiciona barra ao buffer. Se cheio, descarta a mais antiga."""
        self._buffer.append(bar)

    def extend(self, bars: List[Bar]) -> None:
        """Adiciona múltiplas barras ao buffer."""
        for bar in bars:
            self._buffer.append(bar)

    def is_ready(self) -> bool:
        """True se tem barras suficientes para predição."""
        return len(self._buffer) >= self.maxlen

    def to_dataframe(self) -> pd.DataFrame:
        """
        Converte buffer para DataFrame.

        Returns:
            DataFrame com colunas [time, open, high, low, close, volume].
            DataFrame vazio se buffer estiver vazio.
        """
        if not self._buffer:
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
            for b in self._buffer
        ])

    @property
    def last_bar(self) -> Bar | None:
        """Retorna a barra mais recente ou None."""
        return self._buffer[-1] if self._buffer else None

    def __len__(self) -> int:
        return len(self._buffer)

    def clear(self) -> None:
        """Limpa o buffer."""
        self._buffer.clear()

    def __repr__(self) -> str:
        return f"BarBuffer(len={len(self)}, maxlen={self.maxlen}, ready={self.is_ready()})"
