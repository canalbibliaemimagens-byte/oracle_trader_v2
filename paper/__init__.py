"""
Oracle Trader v2.0 — Paper (Benchmark)
=======================================

Simula execução em paralelo ao real para medir drift.
"""

from .paper_trader import PaperTrader
from .account import PaperAccount, PaperPosition, PaperTrade
from .stats import calculate_sharpe, calculate_max_drawdown, calculate_profit_factor

__all__ = [
    "PaperTrader", "PaperAccount", "PaperPosition", "PaperTrade",
    "calculate_sharpe", "calculate_max_drawdown", "calculate_profit_factor",
]
