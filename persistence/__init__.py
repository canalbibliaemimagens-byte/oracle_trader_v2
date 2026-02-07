"""
Oracle Trader v2.0 — Persistence (Memória)
==========================================

Persiste dados críticos em Supabase e localmente.
"""

from .supabase_client import SupabaseClient
from .trade_logger import TradeLogger
from .session_manager import SessionManager, SessionEndReason
from .local_storage import LocalStorage

__all__ = [
    "SupabaseClient", "TradeLogger",
    "SessionManager", "SessionEndReason",
    "LocalStorage",
]
