"""
Oracle Trader v2.0 — Executor (As "Mãos")
==========================================

Traduz sinais do Preditor em ordens seguras no broker.
"""

from .executor import ACK, Executor
from .sync_logic import Decision, SyncState, decide
from .lot_mapper import LotMapper, SymbolConfig, load_symbol_configs
from .price_converter import PriceConverter
from .risk_guard import RiskCheck, RiskGuard
from .comment_builder import CommentBuilder

__all__ = [
    "Executor", "ACK",
    "Decision", "SyncState", "decide",
    "LotMapper", "SymbolConfig", "load_symbol_configs",
    "PriceConverter",
    "RiskGuard", "RiskCheck",
    "CommentBuilder",
]
