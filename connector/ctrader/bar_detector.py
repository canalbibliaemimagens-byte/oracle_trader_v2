"""
Oracle Trader v2.0 - Bar Detector
==================================

cTrader não emite evento "nova barra fechada" diretamente.
Este módulo detecta localmente baseado em timestamps de ticks.

Estratégia:
  - Monitora timestamp dos ticks
  - Quando timestamp muda de período (ex: 10:14:59 → 10:15:00),
    considera que a barra anterior fechou
  - Emite callback com a barra finalizada
"""

import logging
from typing import Awaitable, Callable, Dict, Optional

from core.constants import TIMEFRAME_SECONDS, Timeframe
from core.models import Bar

logger = logging.getLogger("Connector.BarDetector")


class BarDetector:
    """Detecta fechamento de barra baseado em ticks."""

    def __init__(self):
        self._last_bar_time: Dict[str, int] = {}
        self._callbacks: Dict[str, Callable[[Bar], Awaitable[None]]] = {}
        self._timeframes: Dict[str, Timeframe] = {}
        self._pending_bars: Dict[str, dict] = {}

    def register(
        self,
        symbol: str,
        timeframe: str,
        callback: Callable[[Bar], Awaitable[None]],
    ) -> None:
        """Registra callback para barra fechada de um símbolo."""
        tf = Timeframe(timeframe) if isinstance(timeframe, str) else timeframe
        self._callbacks[symbol] = callback
        self._timeframes[symbol] = tf
        self._last_bar_time[symbol] = -1  # Sentinel: -1 = não inicializado

    def unregister(self, symbol: str) -> None:
        """Remove callback."""
        self._callbacks.pop(symbol, None)
        self._timeframes.pop(symbol, None)
        self._last_bar_time.pop(symbol, None)
        self._pending_bars.pop(symbol, None)

    async def on_tick(self, symbol: str, tick_time: int, bid: float, ask: float, volume: float = 0) -> Optional[Bar]:
        """
        Processa tick e detecta mudança de barra.

        Args:
            symbol: Símbolo.
            tick_time: Timestamp do tick (segundos UTC).
            bid: Preço bid.
            ask: Preço ask.
            volume: Volume do tick (0 se indisponível).

        Returns:
            Bar finalizada se houve mudança de período, None caso contrário.
        """
        if symbol not in self._callbacks:
            return None

        tf = self._timeframes[symbol]
        tf_seconds = TIMEFRAME_SECONDS[tf]
        current_bar_time = (tick_time // tf_seconds) * tf_seconds
        mid_price = (bid + ask) / 2

        # Primeiro tick: apenas inicializa
        if self._last_bar_time[symbol] == -1:
            self._last_bar_time[symbol] = current_bar_time
            self._update_pending_bar(symbol, current_bar_time, mid_price, volume)
            return None

        # Mudou de barra!
        if current_bar_time > self._last_bar_time[symbol]:
            completed_bar = None

            if symbol in self._pending_bars:
                completed_bar = self._finalize_bar(symbol)
                # Chama callback
                await self._callbacks[symbol](completed_bar)

            self._last_bar_time[symbol] = current_bar_time
            # Inicia nova barra pendente
            self._pending_bars.pop(symbol, None)
            self._update_pending_bar(symbol, current_bar_time, mid_price, volume)

            return completed_bar

        # Mesmo período: atualiza barra pendente
        self._update_pending_bar(symbol, current_bar_time, mid_price, volume)
        return None

    def _update_pending_bar(self, symbol: str, bar_time: int, price: float, volume: float) -> None:
        """Atualiza OHLC da barra sendo formada."""
        if symbol not in self._pending_bars:
            self._pending_bars[symbol] = {
                'symbol': symbol,
                'time': bar_time,
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'volume': volume,
            }
        else:
            bar = self._pending_bars[symbol]
            bar['high'] = max(bar['high'], price)
            bar['low'] = min(bar['low'], price)
            bar['close'] = price
            bar['volume'] += volume

    def _finalize_bar(self, symbol: str) -> Bar:
        """Converte barra pendente para Bar imutável."""
        data = self._pending_bars[symbol]
        return Bar(
            symbol=data['symbol'],
            time=data['time'],
            open=data['open'],
            high=data['high'],
            low=data['low'],
            close=data['close'],
            volume=data['volume'],
        )

    def get_pending_bar(self, symbol: str) -> Optional[dict]:
        """Retorna barra pendente (em formação) para debug."""
        return self._pending_bars.get(symbol)
