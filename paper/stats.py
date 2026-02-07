"""
Oracle Trader v2.0 — Paper Stats
==================================

Cálculo de métricas avançadas para trades do Paper.
"""

from typing import List

import numpy as np

from .account import PaperTrade


def calculate_sharpe(
    trades: List[PaperTrade], bars_per_year: int = 20160
) -> float:
    """Calcula Sharpe Ratio anualizado."""
    if len(trades) < 2:
        return 0.0
    returns = [t.pnl for t in trades]
    std = np.std(returns)
    if std == 0:
        return 0.0
    return float(np.mean(returns) / std * np.sqrt(bars_per_year))


def calculate_max_drawdown(
    trades: List[PaperTrade], initial_balance: float
) -> float:
    """Calcula drawdown máximo em %."""
    if not trades:
        return 0.0
    equity = initial_balance
    peak = initial_balance
    max_dd = 0.0
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    return round(max_dd * 100, 2)


def calculate_profit_factor(trades: List[PaperTrade]) -> float:
    """Calcula Profit Factor."""
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = abs(sum(t.pnl for t in trades if t.pnl < 0))
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return round(wins / losses, 2)
