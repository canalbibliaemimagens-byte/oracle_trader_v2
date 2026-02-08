"""
Testes: connector/ — MockConnector, RateLimiter, errors
"""

import asyncio
import time
import pytest

from oracle_trader_v2.connector.mock.client import MockConnector
from oracle_trader_v2.connector.rate_limiter import RateLimiter
from oracle_trader_v2.connector.errors import (
    ConnectorError, AuthenticationError, BrokerConnectionError,
    OrderError, RateLimitError, SymbolNotFoundError,
)
from oracle_trader_v2.core.models import Bar, AccountInfo, Position, OrderResult
from .helpers import make_bar, make_bars


# ═══════════════════════════════════════════════════════════════════════════
# MockConnector
# ═══════════════════════════════════════════════════════════════════════════

class TestMockConnector:

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, mock_connector):
        assert not mock_connector.is_connected()
        result = await mock_connector.connect()
        assert result is True
        assert mock_connector.is_connected()
        await mock_connector.disconnect()
        assert not mock_connector.is_connected()

    @pytest.mark.asyncio
    async def test_get_history_random(self, mock_connector):
        bars = await mock_connector.get_history("EURUSD", "M15", 100)
        assert len(bars) == 100
        assert all(isinstance(b, Bar) for b in bars)

    @pytest.mark.asyncio
    async def test_get_history_loaded(self, mock_connector):
        loaded = make_bars("EURUSD", 50)
        mock_connector.load_bars("EURUSD", loaded)
        bars = await mock_connector.get_history("EURUSD", "M15", 30)
        assert len(bars) == 30
        assert bars[-1].close == loaded[-1].close

    @pytest.mark.asyncio
    async def test_get_account(self, mock_connector):
        acc = await mock_connector.get_account()
        assert isinstance(acc, AccountInfo)
        assert acc.balance == 10000.0

    @pytest.mark.asyncio
    async def test_open_order(self, mock_connector):
        result = await mock_connector.open_order("EURUSD", 1, 0.01)
        assert result.success
        assert result.ticket >= 1000

    @pytest.mark.asyncio
    async def test_open_and_get_position(self, mock_connector):
        await mock_connector.open_order("EURUSD", 1, 0.01)
        pos = await mock_connector.get_position("EURUSD")
        assert pos is not None
        assert pos.direction == 1

    @pytest.mark.asyncio
    async def test_close_order(self, mock_connector):
        result = await mock_connector.open_order("EURUSD", 1, 0.01)
        close_result = await mock_connector.close_order(result.ticket)
        assert close_result.success
        pos = await mock_connector.get_position("EURUSD")
        assert pos is None

    @pytest.mark.asyncio
    async def test_close_invalid_ticket(self, mock_connector):
        result = await mock_connector.close_order(999999)
        assert not result.success

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, mock_connector):
        positions = await mock_connector.get_positions()
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_multiple(self, mock_connector):
        await mock_connector.open_order("EURUSD", 1, 0.01)
        await mock_connector.open_order("GBPUSD", -1, 0.02)
        positions = await mock_connector.get_positions()
        assert len(positions) == 2

    @pytest.mark.asyncio
    async def test_modify_order(self, mock_connector):
        result = await mock_connector.open_order("EURUSD", 1, 0.01)
        mod = await mock_connector.modify_order(result.ticket, sl=1.09, tp=1.12)
        assert mod.success
        pos = await mock_connector.get_position("EURUSD")
        assert pos.sl == 1.09
        assert pos.tp == 1.12

    @pytest.mark.asyncio
    async def test_modify_invalid_ticket(self, mock_connector):
        result = await mock_connector.modify_order(999999, sl=1.0)
        assert not result.success

    @pytest.mark.asyncio
    async def test_get_symbol_info(self, mock_connector):
        info = await mock_connector.get_symbol_info("EURUSD")
        assert info is not None
        assert "point" in info

    @pytest.mark.asyncio
    async def test_set_price_updates_pnl(self, mock_connector):
        await mock_connector.open_order("EURUSD", 1, 0.01)
        mock_connector.set_price("EURUSD", 1.11000)
        pos = await mock_connector.get_position("EURUSD")
        assert pos.pnl != 0  # PnL should be recalculated

    @pytest.mark.asyncio
    async def test_emit_bar_calls_callback(self, mock_connector):
        received = []

        async def on_bar(bar):
            received.append(bar)

        await mock_connector.subscribe_bars(["EURUSD"], "M15", on_bar)
        bar = make_bar()
        await mock_connector.emit_bar(bar)
        assert len(received) == 1
        assert received[0].symbol == "EURUSD"

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_callback(self, mock_connector):
        received = []

        async def on_bar(bar):
            received.append(bar)

        await mock_connector.subscribe_bars(["EURUSD"], "M15", on_bar)
        await mock_connector.unsubscribe_bars(["EURUSD"])
        await mock_connector.emit_bar(make_bar())
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_get_order_history(self, mock_connector):
        from datetime import datetime, timezone
        result = await mock_connector.open_order("EURUSD", 1, 0.01)
        await mock_connector.close_order(result.ticket)
        history = await mock_connector.get_order_history(
            datetime(2020, 1, 1, tzinfo=timezone.utc)
        )
        assert len(history) == 1

    @pytest.mark.asyncio
    async def test_latency_simulation(self):
        connector = MockConnector(latency=0.01)
        t0 = time.time()
        await connector.connect()
        assert time.time() - t0 >= 0.01


# ═══════════════════════════════════════════════════════════════════════════
# RateLimiter
# ═══════════════════════════════════════════════════════════════════════════

class TestRateLimiter:

    @pytest.mark.asyncio
    async def test_allows_under_limit(self):
        rl = RateLimiter(rate=10, per_seconds=1.0)
        for _ in range(10):
            await rl.acquire()
        assert rl.current_usage <= 10

    @pytest.mark.asyncio
    async def test_throttles_over_limit(self):
        rl = RateLimiter(rate=3, per_seconds=0.1)
        for _ in range(3):
            await rl.acquire()
        t0 = time.time()
        await rl.acquire()
        elapsed = time.time() - t0
        assert elapsed >= 0.05  # Should have waited

    @pytest.mark.asyncio
    async def test_usage_resets(self):
        rl = RateLimiter(rate=5, per_seconds=0.05)
        for _ in range(5):
            await rl.acquire()
        await asyncio.sleep(0.06)
        assert rl.current_usage == 0


# ═══════════════════════════════════════════════════════════════════════════
# Errors
# ═══════════════════════════════════════════════════════════════════════════

class TestConnectorErrors:
    def test_hierarchy(self):
        assert issubclass(AuthenticationError, ConnectorError)
        assert issubclass(BrokerConnectionError, ConnectorError)
        assert issubclass(OrderError, ConnectorError)
        assert issubclass(RateLimitError, ConnectorError)
        assert issubclass(SymbolNotFoundError, ConnectorError)

    def test_raise_and_catch(self):
        with pytest.raises(ConnectorError):
            raise AuthenticationError("bad token")
