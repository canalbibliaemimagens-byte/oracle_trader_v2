"""
Oracle Trader v2.0 — Paper Account
====================================

Conta simulada que replica exatamente o TradingEnv do notebook.
Spread, slippage e comissão fixos (do treino), sem rejeições.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class PaperPosition:
    """Posição virtual no Paper."""
    symbol: str
    direction: int
    intensity: int
    volume: float
    entry_price: float
    entry_time: float
    current_pnl: float = 0.0


@dataclass
class PaperTrade:
    """Trade fechado no Paper."""
    symbol: str
    direction: int
    intensity: int
    volume: float
    entry_price: float
    exit_price: float
    entry_time: float
    exit_time: float
    pnl: float
    pnl_pips: float
    commission: float
    hmm_state: int


class PaperAccount:
    """
    Conta simulada para Paper Trading.
    Replica a lógica do TradingEnv com parâmetros fixos do treino.
    """

    def __init__(self, initial_balance: float, training_config: dict):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance

        # Parâmetros do treino (fixos)
        self.spread_points = training_config.get("spread_points", 7)
        self.slippage_points = training_config.get("slippage_points", 2)
        self.commission_per_lot = training_config.get("commission_per_lot", 7.0)
        self.point = training_config.get("point", 0.00001)
        self.pip_value = training_config.get("pip_value", 10.0)
        self.lot_sizes = training_config.get("lot_sizes", [0, 0.01, 0.03, 0.05])
        self.digits = training_config.get("digits", 5)
        self.points_per_pip = 10 if self.digits in [5, 3] else 1

        # Estado
        self.positions: Dict[str, PaperPosition] = {}
        self.closed_trades: List[PaperTrade] = []
        self.total_commission = 0.0

    def open_position(
        self,
        symbol: str,
        direction: int,
        intensity: int,
        price: float,
        timestamp: float,
    ) -> bool:
        """
        Abre posição virtual com spread e slippage do treino.

        Returns:
            True se abriu.
        """
        if symbol in self.positions:
            return False

        if intensity < 0 or intensity >= len(self.lot_sizes):
            return False
        volume = self.lot_sizes[intensity]
        if volume <= 0:
            return False

        # Custos de entrada (idêntico ao TradingEnv._open_position)
        spread_cost = self.spread_points * self.point
        slippage = self.slippage_points * self.point

        if direction == 1:
            entry_price = price + spread_cost + slippage
        else:
            entry_price = price - spread_cost - slippage

        # Comissão de entrada (metade)
        commission = (self.commission_per_lot * volume) / 2
        self.balance -= commission
        self.total_commission += commission

        self.positions[symbol] = PaperPosition(
            symbol=symbol,
            direction=direction,
            intensity=intensity,
            volume=volume,
            entry_price=entry_price,
            entry_time=timestamp,
        )
        return True

    def close_position(
        self,
        symbol: str,
        price: float,
        timestamp: float,
        hmm_state: int,
    ) -> Optional[PaperTrade]:
        """
        Fecha posição virtual.

        Returns:
            PaperTrade com resultado, ou None se sem posição.
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        # Slippage de saída
        slippage = self.slippage_points * self.point
        if pos.direction == 1:
            exit_price = price - slippage
        else:
            exit_price = price + slippage

        # PnL (idêntico ao TradingEnv._close_position)
        price_diff = (exit_price - pos.entry_price) * pos.direction
        pips = price_diff / self.point / self.points_per_pip
        pnl = pips * self.pip_value * pos.volume

        # Comissão de saída (metade)
        commission = (self.commission_per_lot * pos.volume) / 2
        pnl -= commission
        self.total_commission += commission

        self.balance += pnl
        self.equity = self.balance

        trade = PaperTrade(
            symbol=symbol,
            direction=pos.direction,
            intensity=pos.intensity,
            volume=pos.volume,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=timestamp,
            pnl=pnl,
            pnl_pips=pips,
            commission=commission * 2,  # Total (entrada + saída)
            hmm_state=hmm_state,
        )

        self.closed_trades.append(trade)
        del self.positions[symbol]
        return trade

    def update_equity(self, prices: Dict[str, float]):
        """Atualiza equity com PnL flutuante."""
        floating_pnl = 0.0
        for symbol, pos in self.positions.items():
            if symbol in prices:
                price_diff = (prices[symbol] - pos.entry_price) * pos.direction
                pips = price_diff / self.point / self.points_per_pip
                pos.current_pnl = pips * self.pip_value * pos.volume
                floating_pnl += pos.current_pnl
        self.equity = self.balance + floating_pnl
