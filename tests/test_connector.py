"""
Oracle Trader v2.0 - Testes do Connector (Fase 3)
===================================================

Testa:
  - MockConnector (connect, history, open/close orders, account)
  - BarDetector (detecção de barra fechada via ticks)
  - RateLimiter (controle de taxa)
"""

import pytest
from datetime import datetime, timezone

from oracle_trader_v2.core.models import Bar, AccountInfo, Position, OrderResult
from oracle_trader_v2.connector.mock.client import MockConnector
from oracle_trader_v2.connector.ctrader.bar_detector import BarDetector
from oracle_trader_v2.connector.rate_limiter import RateLimiter


# =============================================================================
# TESTES: MockConnector
# =============================================================================

class TestMockConnector:

    @pytest.mark.asyncio
    async def test_connect_disconnect(self):
        mc = MockConnector()
        assert not mc.is_connected()
        await mc.connect()
        assert mc.is_connected()
        await mc.disconnect()
        assert not mc.is_connected()

    @pytest.mark.asyncio
    async def test_get_account(self):
        mc = MockConnector(initial_balance=5000)
        await mc.connect()
        account = await mc.get_account()
        assert isinstance(account, AccountInfo)
        assert account.balance == 5000
        assert account.currency == "USD"

    @pytest.mark.asyncio
    async def test_get_history_random(self):
        mc = MockConnector()
        await mc.connect()
        bars = await mc.get_history("EURUSD", "M15", 100)
        assert len(bars) == 100
        assert all(isinstance(b, Bar) for b in bars)
        for i in range(1, len(bars)):
            assert bars[i].time > bars[i - 1].time

    @pytest.mark.asyncio
    async def test_get_history_loaded_bars(self):
        mc = MockConnector()
        loaded = [
            Bar("EURUSD", 1000, 1.1, 1.2, 1.0, 1.15, 100),
            Bar("EURUSD", 1900, 1.15, 1.25, 1.05, 1.20, 200),
            Bar("EURUSD", 2800, 1.20, 1.30, 1.10, 1.25, 150),
        ]
        mc.load_bars("EURUSD", loaded)
        await mc.connect()
        bars = await mc.get_history("EURUSD", "M15", 2)
        assert len(bars) == 2
        assert bars[0].time == 1900
        assert bars[1].time == 2800

    @pytest.mark.asyncio
    async def test_open_order(self):
        mc = MockConnector()
        await mc.connect()
        result = await mc.open_order("EURUSD", 1, 0.01, sl=10.0, comment="test")
        assert isinstance(result, OrderResult)
        assert result.success
        assert result.ticket is not None
        assert result.price is not None

    @pytest.mark.asyncio
    async def test_open_creates_position(self):
        mc = MockConnector()
        mc.set_price("EURUSD", 1.10000)
        await mc.connect()
        await mc.open_order("EURUSD", 1, 0.03, comment="O|V1")
        positions = await mc.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "EURUSD"
        assert positions[0].direction == 1
        assert positions[0].volume == 0.03

    @pytest.mark.asyncio
    async def test_close_order(self):
        mc = MockConnector()
        mc.set_price("EURUSD", 1.10000)
        await mc.connect()
        open_result = await mc.open_order("EURUSD", 1, 0.01)
        close_result = await mc.close_order(open_result.ticket)
        assert close_result.success
        positions = await mc.get_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_close_nonexistent_ticket(self):
        mc = MockConnector()
        await mc.connect()
        result = await mc.close_order(99999)
        assert not result.success
        assert "não encontrado" in result.error

    @pytest.mark.asyncio
    async def test_modify_order(self):
        mc = MockConnector()
        mc.set_price("EURUSD", 1.10000)
        await mc.connect()
        open_result = await mc.open_order("EURUSD", 1, 0.01)
        mod_result = await mc.modify_order(open_result.ticket, sl=5.0, tp=10.0)
        assert mod_result.success
        pos = await mc.get_position("EURUSD")
        assert pos.sl == 5.0
        assert pos.tp == 10.0

    @pytest.mark.asyncio
    async def test_get_position_none(self):
        mc = MockConnector()
        await mc.connect()
        pos = await mc.get_position("EURUSD")
        assert pos is None

    @pytest.mark.asyncio
    async def test_set_price_updates_pnl(self):
        mc = MockConnector()
        mc.set_price("EURUSD", 1.10000)
        await mc.connect()
        await mc.open_order("EURUSD", 1, 0.01)
        mc.set_price("EURUSD", 1.10100)
        pos = await mc.get_position("EURUSD")
        assert pos.current_price == 1.10100
        assert pos.pnl != 0

    @pytest.mark.asyncio
    async def test_emit_bar(self):
        mc = MockConnector()
        await mc.connect()
        received = []

        async def on_bar(bar: Bar):
            received.append(bar)

        await mc.subscribe_bars(["EURUSD"], "M15", on_bar)
        bar = Bar("EURUSD", 1000, 1.1, 1.2, 1.0, 1.15, 100)
        await mc.emit_bar(bar)
        assert len(received) == 1
        assert received[0].close == 1.15

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        mc = MockConnector()
        await mc.connect()
        received = []

        async def on_bar(bar: Bar):
            received.append(bar)

        await mc.subscribe_bars(["EURUSD"], "M15", on_bar)
        await mc.unsubscribe_bars(["EURUSD"])
        bar = Bar("EURUSD", 1000, 1.1, 1.2, 1.0, 1.15, 100)
        await mc.emit_bar(bar)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_get_symbol_info(self):
        mc = MockConnector()
        info = await mc.get_symbol_info("EURUSD")
        assert info is not None
        assert info["point"] == 0.00001
        assert info["digits"] == 5

    @pytest.mark.asyncio
    async def test_order_history(self):
        mc = MockConnector()
        mc.set_price("EURUSD", 1.10000)
        await mc.connect()
        result = await mc.open_order("EURUSD", 1, 0.01)
        await mc.close_order(result.ticket)
        history = await mc.get_order_history(datetime(2020, 1, 1, tzinfo=timezone.utc))
        assert len(history) == 1
        assert history[0]['ticket'] == result.ticket


# =============================================================================
# TESTES: BarDetector
# =============================================================================

class TestBarDetector:

    @pytest.mark.asyncio
    async def test_register_unregister(self):
        bd = BarDetector()
        async def cb(bar): pass
        bd.register("EURUSD", "M15", cb)
        assert "EURUSD" in bd._callbacks
        bd.unregister("EURUSD")
        assert "EURUSD" not in bd._callbacks

    @pytest.mark.asyncio
    async def test_first_tick_no_bar(self):
        bd = BarDetector()
        received = []

        async def cb(bar):
            received.append(bar)

        bd.register("EURUSD", "M15", cb)
        result = await bd.on_tick("EURUSD", 1000, 1.10000, 1.10010)
        assert result is None
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_same_period_no_bar(self):
        bd = BarDetector()
        received = []

        async def cb(bar):
            received.append(bar)

        bd.register("EURUSD", "M15", cb)
        await bd.on_tick("EURUSD", 100, 1.10000, 1.10010)
        await bd.on_tick("EURUSD", 200, 1.10020, 1.10030)
        await bd.on_tick("EURUSD", 500, 1.09980, 1.09990)
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_period_change_emits_bar(self):
        bd = BarDetector()
        received = []

        async def cb(bar):
            received.append(bar)

        bd.register("EURUSD", "M15", cb)
        await bd.on_tick("EURUSD", 0, 1.10000, 1.10010)
        await bd.on_tick("EURUSD", 300, 1.10050, 1.10060)
        await bd.on_tick("EURUSD", 600, 1.09950, 1.09960)
        result = await bd.on_tick("EURUSD", 900, 1.10020, 1.10030)
        assert len(received) == 1
        bar = received[0]
        assert isinstance(bar, Bar)
        assert bar.symbol == "EURUSD"
        assert bar.time == 0
        assert bar.open == pytest.approx(1.10005, abs=1e-5)
        assert bar.close == pytest.approx(1.09955, abs=1e-5)

    @pytest.mark.asyncio
    async def test_multiple_bars(self):
        bd = BarDetector()
        received = []

        async def cb(bar):
            received.append(bar)

        bd.register("EURUSD", "M15", cb)
        await bd.on_tick("EURUSD", 100, 1.10000, 1.10010)
        await bd.on_tick("EURUSD", 950, 1.10050, 1.10060)
        await bd.on_tick("EURUSD", 1850, 1.10100, 1.10110)
        assert len(received) == 2
        assert received[0].time == 0
        assert received[1].time == 900

    @pytest.mark.asyncio
    async def test_unregistered_symbol_ignored(self):
        bd = BarDetector()
        result = await bd.on_tick("UNKNOWN", 100, 1.10000, 1.10010)
        assert result is None

    @pytest.mark.asyncio
    async def test_pending_bar(self):
        bd = BarDetector()
        async def cb(bar): pass
        bd.register("EURUSD", "M15", cb)
        await bd.on_tick("EURUSD", 100, 1.10000, 1.10010)
        pending = bd.get_pending_bar("EURUSD")
        assert pending is not None
        assert pending['symbol'] == "EURUSD"


# =============================================================================
# TESTES: RateLimiter
# =============================================================================

class TestRateLimiter:

    @pytest.mark.asyncio
    async def test_basic_acquire(self):
        rl = RateLimiter(10, per_seconds=1.0)
        await rl.acquire()
        assert rl.current_usage == 1

    @pytest.mark.asyncio
    async def test_multiple_acquires_under_limit(self):
        rl = RateLimiter(10, per_seconds=1.0)
        for _ in range(5):
            await rl.acquire()
        assert rl.current_usage == 5

    @pytest.mark.asyncio
    async def test_current_usage(self):
        rl = RateLimiter(100)
        assert rl.current_usage == 0
        await rl.acquire()
        assert rl.current_usage == 1


# =============================================================================
# TESTES: Errors
# =============================================================================

class TestConnectorErrors:

    def test_hierarchy(self):
        from oracle_trader_v2.connector.errors import (
            ConnectorError, AuthenticationError, BrokerConnectionError,
            OrderError, RateLimitError, SymbolNotFoundError,
        )
        assert issubclass(AuthenticationError, ConnectorError)
        assert issubclass(BrokerConnectionError, ConnectorError)
        assert issubclass(OrderError, ConnectorError)
        assert issubclass(RateLimitError, ConnectorError)
        assert issubclass(SymbolNotFoundError, ConnectorError)

    def test_order_error_code(self):
        from oracle_trader_v2.connector.errors import OrderError
        err = OrderError("Margin insuficiente", code=42)
        assert err.code == 42
        assert "Margin" in str(err)
