"""
Testes: persistence/ — SupabaseClient (mock), TradeLogger, SessionManager, LocalStorage
"""

import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from oracle_trader_v2.persistence.supabase_client import SupabaseClient
from oracle_trader_v2.persistence.trade_logger import TradeLogger
from oracle_trader_v2.persistence.session_manager import (
    SessionManager, SessionEndReason,
)
from oracle_trader_v2.persistence.local_storage import LocalStorage
from oracle_trader_v2.paper.account import PaperTrade


# ═══════════════════════════════════════════════════════════════════════════
# SupabaseClient (sem conexão real — testa retry queue e lógica)
# ═══════════════════════════════════════════════════════════════════════════

class TestSupabaseClient:

    @pytest.fixture
    def client(self):
        """Client desabilitado (sem conexão real)."""
        return SupabaseClient(url="", key="", enabled=False)

    @pytest.mark.asyncio
    async def test_disabled_client(self, client):
        assert not client.is_connected

    @pytest.mark.asyncio
    async def test_log_trade_disabled(self, client):
        """Should not crash when disabled."""
        await client.log_trade({"symbol": "EURUSD", "pnl": 10})

    @pytest.mark.asyncio
    async def test_log_event_disabled(self, client):
        await client.log_event("TEST", {"data": 1}, "session1")

    def test_pending_count_zero(self, client):
        assert client.pending_count == 0

    @pytest.mark.asyncio
    async def test_retry_pending_empty(self, client):
        result = await client.retry_pending()
        assert result == 0


class TestSupabaseClientDataPop:
    """Testa que S1 fix (data.pop → data.get) funciona."""

    @pytest.mark.asyncio
    async def test_update_preserves_filter_keys(self):
        """Verify _filter keys survive in the data dict after failed update."""
        client = SupabaseClient(url="", key="", enabled=False)

        data = {
            "balance": 10000,
            "_filter_key": "session_id",
            "_filter_val": "abc123",
        }
        original_data = data.copy()

        # Execute should fail (no real client) but data should be intact
        await client._execute("sessions", data, operation="update")

        # CRITICAL: data must still have _filter keys for retry
        assert "_filter_key" in data
        assert "_filter_val" in data
        assert data == original_data


# ═══════════════════════════════════════════════════════════════════════════
# TradeLogger
# ═══════════════════════════════════════════════════════════════════════════

class TestTradeLogger:

    @pytest.fixture
    def logger_instance(self):
        mock_db = AsyncMock()
        mock_db.log_trade = AsyncMock()
        return TradeLogger(supabase_client=mock_db, session_id="test-123")

    @pytest.mark.asyncio
    async def test_log_trade(self, logger_instance):
        await logger_instance.log_trade(
            symbol="EURUSD", direction=1, intensity=1, action="LONG_WEAK",
            volume=0.01, entry_price=1.1, exit_price=1.101,
            pnl=5.0, pnl_pips=10.0, hmm_state=2,
        )
        logger_instance.db.log_trade.assert_called_once()
        call_data = logger_instance.db.log_trade.call_args[0][0]
        assert call_data["session_id"] == "test-123"
        assert call_data["symbol"] == "EURUSD"

    @pytest.mark.asyncio
    async def test_log_paper_trade(self, logger_instance):
        pt = PaperTrade(
            symbol="EURUSD", direction=1, intensity=1, volume=0.01,
            entry_price=1.1, exit_price=1.101, entry_time=0, exit_time=1,
            pnl=5.0, pnl_pips=10.0, commission=0.07, hmm_state=3,
        )
        await logger_instance.log_paper_trade(pt)
        logger_instance.db.log_trade.assert_called_once()
        call_data = logger_instance.db.log_trade.call_args[0][0]
        assert call_data["is_paper"] is True


# ═══════════════════════════════════════════════════════════════════════════
# SessionManager
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionManager:

    @pytest.fixture
    def sm(self, tmp_path):
        mock_db = AsyncMock()
        mock_db._execute = AsyncMock()
        mock_db.log_event = AsyncMock()
        return SessionManager(supabase_client=mock_db, base_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_start_new_session(self, sm):
        sid = await sm.start_session(10000, ["EURUSD"])
        assert len(sid) == 8
        assert sm._running
        assert sm.start_time is not None

    @pytest.mark.asyncio
    async def test_end_session(self, sm):
        await sm.start_session(10000, ["EURUSD"])
        await sm.end_session(
            stats={"balance": 10050, "total_trades": 5, "total_pnl": 50},
            reason=SessionEndReason.NORMAL,
        )
        assert not sm._running

    @pytest.mark.asyncio
    async def test_crash_recovery(self, sm, tmp_path):
        """Simulate crash: state file says RUNNING → recover."""
        state = {
            "session_id": "crashed1",
            "status": "RUNNING",
            "start_time": datetime.now(timezone.utc).isoformat(),
        }
        state_file = tmp_path / ".session_state.json"
        state_file.write_text(json.dumps(state))

        sid = await sm.start_session(10000, ["EURUSD"])
        assert sid == "crashed1"
        assert sm.is_recovered

    def test_heartbeat(self, sm):
        sm._running = True
        sm.session_id = "test"
        sm.update_heartbeat(balance=10050)
        state = sm._load_state()
        assert state is not None
        assert "last_heartbeat" in state

    def test_check_day_boundary_no_change(self, sm):
        sm.day_start = SessionManager._get_day_start()
        assert not sm.check_day_boundary()

    def test_check_day_boundary_first_call(self, sm):
        # First call sets day_start
        assert not sm.check_day_boundary()
        assert sm.day_start is not None

    @pytest.mark.asyncio
    async def test_state_file_cleared_on_end(self, sm, tmp_path):
        await sm.start_session(10000, ["EURUSD"])
        state_file = tmp_path / ".session_state.json"
        assert state_file.exists()
        await sm.end_session(stats={}, reason=SessionEndReason.MANUAL)
        assert not state_file.exists()

    @pytest.mark.asyncio
    async def test_end_session_idempotent(self, sm):
        """Calling end_session when not running should be safe."""
        await sm.end_session(stats={})
        # Should not raise


# ═══════════════════════════════════════════════════════════════════════════
# LocalStorage
# ═══════════════════════════════════════════════════════════════════════════

class TestLocalStorage:

    @pytest.fixture
    def storage(self, tmp_path):
        return LocalStorage(base_dir=tmp_path)

    def test_save_and_load_pending(self, storage):
        storage.save_pending([{"symbol": "EURUSD", "pnl": 10}])
        loaded = storage.load_pending()
        assert len(loaded) == 1
        assert loaded[0]["symbol"] == "EURUSD"

    def test_save_pending_appends(self, storage):
        storage.save_pending([{"id": 1}])
        storage.save_pending([{"id": 2}])
        loaded = storage.load_pending()
        assert len(loaded) == 2

    def test_load_pending_empty(self, storage):
        assert storage.load_pending() == []

    def test_clear_pending(self, storage):
        storage.save_pending([{"id": 1}])
        storage.clear_pending()
        assert storage.load_pending() == []

    def test_cache_bars(self, storage):
        bars = [{"time": 1, "close": 1.1}, {"time": 2, "close": 1.2}]
        storage.cache_bars("EURUSD", bars)
        loaded = storage.load_cached_bars("EURUSD")
        assert len(loaded) == 2

    def test_load_cached_bars_missing(self, storage):
        assert storage.load_cached_bars("NONEXISTENT") == []

    def test_cache_dir_created(self, storage, tmp_path):
        assert (tmp_path / "cache").is_dir()
