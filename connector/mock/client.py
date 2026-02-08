"""
Oracle Trader v2.0 - Mock Connector
=====================================

Implementação em memória para testes unitários, de integração
e desenvolvimento sem broker real.

Features:
  - Simula latência configurável
  - Slippage simulado
  - Replay de dados CSV
  - Geração de dados aleatórios para testes rápidos
"""

import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

import numpy as np

from core.models import AccountInfo, Bar, OrderResult, Position
from ..base import BaseConnector

logger = logging.getLogger("Connector.Mock")


class MockConnector(BaseConnector):
    """
    Connector mock para testes.
    Simula latência, slippage e preenchimento de ordens.
    """

    def __init__(self, config: dict = None):
        """
        Args:
            config: Dict de configuração (igual ao CTraderConnector).
                    Campos opcionais: initial_balance, latency, slippage_min, slippage_max
        """
        config = config or {}
        
        # Extrair configurações do dict (compatível com orchestrator)
        initial_balance = config.get("initial_balance", 10000.0)
        latency = config.get("latency", 0.0)
        slippage_min = config.get("slippage_min", 0.0)
        slippage_max = config.get("slippage_max", 0.0)
        
        self.balance = initial_balance
        self.equity = initial_balance
        self.positions: Dict[str, Position] = {}
        self.closed_orders: List[dict] = []
        self.next_ticket = 1000
        self._connected = False
        self._bars_data: Dict[str, List[Bar]] = {}
        self._callbacks: Dict[str, Callable[[Bar], Awaitable[None]]] = {}
        self._latency = latency
        self._slippage_range = (slippage_min, slippage_max)
        self._last_prices: Dict[str, float] = {}

    # =========================================================================
    # CONEXÃO
    # =========================================================================

    async def connect(self) -> bool:
        if self._latency > 0:
            await asyncio.sleep(self._latency)
        self._connected = True
        logger.info("Mock connector conectado")
        return True

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("Mock connector desconectado")

    def is_connected(self) -> bool:
        return self._connected

    # =========================================================================
    # DADOS DE MERCADO
    # =========================================================================

    async def get_history(self, symbol: str, timeframe: str, bars: int) -> List[Bar]:
        if self._latency > 0:
            await asyncio.sleep(self._latency)

        if symbol in self._bars_data:
            data = self._bars_data[symbol]
            result = data[-bars:] if len(data) >= bars else data
            if result:
                self._last_prices[symbol] = result[-1].close
            return result

        # Gera dados aleatórios
        return self._generate_random_bars(symbol, timeframe, bars)

    async def subscribe_bars(
        self,
        symbols: List[str],
        timeframe: str,
        callback: Callable[[Bar], Awaitable[None]],
    ) -> None:
        for symbol in symbols:
            self._callbacks[symbol] = callback
            logger.debug(f"Subscrito para {symbol} ({timeframe})")

    async def unsubscribe_bars(self, symbols: List[str]) -> None:
        for symbol in symbols:
            self._callbacks.pop(symbol, None)

    # =========================================================================
    # DADOS DE CONTA
    # =========================================================================

    async def get_account(self) -> AccountInfo:
        total_pnl = sum(p.pnl for p in self.positions.values())
        self.equity = self.balance + total_pnl
        margin = sum(p.volume * 100000 * 0.01 for p in self.positions.values())  # Approx
        free_margin = self.equity - margin
        margin_level = (self.equity / margin * 100) if margin > 0 else 0

        return AccountInfo(
            balance=self.balance,
            equity=self.equity,
            margin=margin,
            free_margin=free_margin,
            margin_level=margin_level,
            currency="USD",
        )

    async def get_positions(self) -> List[Position]:
        return list(self.positions.values())

    async def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    async def get_order_history(self, since: datetime) -> List[dict]:
        since_ts = int(since.timestamp())
        return [o for o in self.closed_orders if o.get('close_time', 0) >= since_ts]

    # =========================================================================
    # EXECUÇÃO
    # =========================================================================

    async def open_order(
        self,
        symbol: str,
        direction: int,
        volume: float,
        sl: float = 0,
        tp: float = 0,
        comment: str = "",
    ) -> OrderResult:
        if self._latency > 0:
            await asyncio.sleep(self._latency)

        # Preço base
        base_price = self._last_prices.get(symbol, 1.10000)

        # Slippage simulado
        slip = random.uniform(*self._slippage_range) if any(self._slippage_range) else 0
        price = base_price + (slip if direction == 1 else -slip)

        ticket = self.next_ticket
        self.next_ticket += 1

        pos = Position(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=price,
            current_price=price,
            pnl=0.0,
            sl=sl,
            tp=tp,
            open_time=int(time.time()),
            comment=comment,
        )
        self.positions[symbol] = pos

        logger.debug(f"Ordem aberta: {symbol} {'LONG' if direction == 1 else 'SHORT'} "
                     f"{volume} @ {price:.5f} T#{ticket}")

        return OrderResult(success=True, ticket=ticket, price=price)

    async def close_order(self, ticket: int, volume: float = 0) -> OrderResult:
        if self._latency > 0:
            await asyncio.sleep(self._latency)

        # Encontra posição pelo ticket
        pos = None
        symbol = None
        for s, p in self.positions.items():
            if p.ticket == ticket:
                pos = p
                symbol = s
                break

        if pos is None:
            return OrderResult(success=False, error=f"Ticket {ticket} não encontrado")

        close_price = self._last_prices.get(symbol, pos.current_price)
        pnl = pos.pnl  # Simplified

        # Registra no histórico
        self.closed_orders.append({
            'ticket': ticket,
            'symbol': symbol,
            'direction': pos.direction,
            'volume': pos.volume,
            'open_price': pos.open_price,
            'close_price': close_price,
            'pnl': pnl,
            'close_time': int(time.time()),
        })

        # Remove posição
        self.balance += pnl
        del self.positions[symbol]

        logger.debug(f"Ordem fechada: T#{ticket} PnL=${pnl:.2f}")
        return OrderResult(success=True, ticket=ticket, price=close_price)

    async def modify_order(self, ticket: int, sl: float = 0, tp: float = 0) -> OrderResult:
        for pos in self.positions.values():
            if pos.ticket == ticket:
                pos.sl = sl
                pos.tp = tp
                return OrderResult(success=True, ticket=ticket)
        return OrderResult(success=False, error=f"Ticket {ticket} não encontrado")

    async def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Retorna info genérica de símbolo para testes."""
        defaults = {
            "EURUSD": {"point": 0.00001, "digits": 5, "pip_value": 10.0, "spread_points": 7},
            "GBPUSD": {"point": 0.00001, "digits": 5, "pip_value": 10.0, "spread_points": 10},
            "USDJPY": {"point": 0.001, "digits": 3, "pip_value": 6.7, "spread_points": 8},
        }
        return defaults.get(symbol, {
            "point": 0.00001, "digits": 5, "pip_value": 10.0, "spread_points": 10,
        })

    # =========================================================================
    # MÉTODOS MOCK (para testes)
    # =========================================================================

    def load_bars(self, symbol: str, bars: List[Bar]) -> None:
        """Carrega barras para replay."""
        self._bars_data[symbol] = bars
        if bars:
            self._last_prices[symbol] = bars[-1].close

    def set_price(self, symbol: str, price: float) -> None:
        """Define preço atual para um símbolo."""
        self._last_prices[symbol] = price
        # Atualiza PnL das posições abertas
        if symbol in self.positions:
            pos = self.positions[symbol]
            diff = (price - pos.open_price) * pos.direction
            pos.current_price = price
            pos.pnl = diff * pos.volume * 100000  # Simplified forex calc

    async def emit_bar(self, bar: Bar) -> None:
        """
        Emite uma barra manualmente (para testes de integração).
        Chama o callback registrado para o símbolo.
        """
        self._last_prices[bar.symbol] = bar.close
        callback = self._callbacks.get(bar.symbol)
        if callback:
            await callback(bar)

    def _generate_random_bars(self, symbol: str, timeframe: str, n: int) -> List[Bar]:
        """Gera barras aleatórias para testes rápidos."""
        np.random.seed(42)
        tf_seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
                      "H1": 3600, "H4": 14400, "D1": 86400}.get(timeframe, 900)

        base_time = int(time.time()) - n * tf_seconds
        price = 1.10000
        bars = []

        for i in range(n):
            change = np.random.randn() * 0.0005
            o = price
            c = price + change
            h = max(o, c) + abs(np.random.randn() * 0.0002)
            lo = min(o, c) - abs(np.random.randn() * 0.0002)
            v = float(np.random.randint(100, 1000))

            bars.append(Bar(
                symbol=symbol,
                time=base_time + i * tf_seconds,
                open=round(o, 5), high=round(h, 5),
                low=round(lo, 5), close=round(c, 5),
                volume=v,
            ))
            price = c

        if bars:
            self._last_prices[symbol] = bars[-1].close
        return bars
