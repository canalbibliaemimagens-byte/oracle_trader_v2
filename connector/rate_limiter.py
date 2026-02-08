"""
Oracle Trader v2.0 - Rate Limiter
==================================

Leaky bucket para respeitar limites da cTrader API.

Limites:
  - Trading: 50 req/s
  - Histórico: 5 req/s
"""

import asyncio
import time
from collections import deque


class RateLimiter:
    """Leaky bucket async para rate limiting."""

    def __init__(self, rate: int, per_seconds: float = 1.0):
        """
        Args:
            rate: Número máximo de requisições permitidas.
            per_seconds: Janela de tempo em segundos.
        """
        self.rate = rate
        self.per_seconds = per_seconds
        self.timestamps: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Aguarda até que seja permitido fazer requisição."""
        async with self._lock:
            now = time.time()

            # Remove timestamps antigos (fora da janela)
            while self.timestamps and self.timestamps[0] < now - self.per_seconds:
                self.timestamps.popleft()

            # Se no limite, aguarda
            if len(self.timestamps) >= self.rate:
                wait_time = self.timestamps[0] + self.per_seconds - now
                if wait_time > 0:
                    await asyncio.sleep(wait_time)

            self.timestamps.append(time.time())

    @property
    def current_usage(self) -> int:
        """Número de requisições na janela atual."""
        now = time.time()
        while self.timestamps and self.timestamps[0] < now - self.per_seconds:
            self.timestamps.popleft()
        return len(self.timestamps)
