"""
Oracle Trader v2.0 — Paper Trader
===================================

Simula execução de sinais em paralelo ao Executor real.
Usa exatamente os mesmos parâmetros do treino para medir drift.
"""

import logging
from typing import Dict, List, Optional

from core.models import Bar, Signal
from .account import PaperAccount, PaperTrade

logger = logging.getLogger("Paper")


class PaperTrader:
    """
    Simula execução em paralelo ao real.
    Cada símbolo tem sua PaperAccount com parâmetros do treino.
    """

    def __init__(self, initial_balance: float = 10000):
        self.initial_balance = initial_balance
        self.accounts: Dict[str, PaperAccount] = {}

    def load_config(self, symbol: str, training_config: dict):
        """
        Carrega configuração de treino para um símbolo.
        Deve ser chamado após carregar modelo no Preditor.
        """
        self.accounts[symbol] = PaperAccount(self.initial_balance, training_config)
        logger.info(
            f"[{symbol}] Paper config: spread={training_config.get('spread_points')}, "
            f"lots={training_config.get('lot_sizes')}"
        )

    def process_signal(
        self, signal: Signal, current_bar: Bar
    ) -> Optional[PaperTrade]:
        """
        Processa sinal do Preditor.

        Returns:
            PaperTrade se fechou posição, None caso contrário.
        """
        symbol = signal.symbol
        if symbol not in self.accounts:
            return None

        account = self.accounts[symbol]
        price = current_bar.close
        timestamp = current_bar.time

        target_dir = signal.direction
        target_intensity = signal.intensity

        current_pos = account.positions.get(symbol)
        current_dir = current_pos.direction if current_pos else 0

        # Mesma direção → verifica se intensidade mudou
        if current_dir == target_dir:
            # Se intensidade mudou e posição está aberta → fechar e reabrir
            # (idêntico ao TradingEnv que fecha/reabre em qualquer mudança de action)
            if current_pos and current_pos.intensity != target_intensity and target_dir != 0:
                trade = account.close_position(
                    symbol, price, timestamp, signal.hmm_state
                )
                account.open_position(
                    symbol, target_dir, target_intensity, price, timestamp
                )
                return trade
            return None

        trade = None

        # Fecha posição existente
        if current_dir != 0:
            trade = account.close_position(
                symbol, price, timestamp, signal.hmm_state
            )

        # Abre nova posição
        if target_dir != 0 and target_intensity > 0:
            account.open_position(
                symbol, target_dir, target_intensity, price, timestamp
            )

        return trade

    def get_metrics(self) -> dict:
        """Retorna métricas consolidadas de todos os símbolos."""
        all_trades = []
        total_balance = 0

        for account in self.accounts.values():
            all_trades.extend(account.closed_trades)
            total_balance += account.balance

        if not all_trades:
            return {
                "total_trades": 0,
                "total_pnl": 0,
                "win_rate": 0,
                "avg_balance": self.initial_balance,
                "total_commission": 0,
            }

        wins = [t for t in all_trades if t.pnl > 0]
        total_pnl = sum(t.pnl for t in all_trades)

        return {
            "total_trades": len(all_trades),
            "total_pnl": round(total_pnl, 2),
            "win_rate": round(len(wins) / len(all_trades) * 100, 1),
            "avg_balance": round(total_balance / max(len(self.accounts), 1), 2),
            "total_commission": round(
                sum(a.total_commission for a in self.accounts.values()), 2
            ),
        }

    def get_trades(self, symbol: Optional[str] = None) -> List[PaperTrade]:
        """Retorna trades fechados."""
        if symbol:
            account = self.accounts.get(symbol)
            return account.closed_trades if account else []

        all_trades = []
        for account in self.accounts.values():
            all_trades.extend(account.closed_trades)
        return sorted(all_trades, key=lambda t: t.exit_time)

    def compare_with_real(self, real_trades: list) -> dict:
        """Compara trades Paper vs Real para drift report."""
        paper_trades = self.get_trades()

        paper_pnl = sum(t.pnl for t in paper_trades)
        real_pnl = sum(t.get("pnl", 0) for t in real_trades)

        paper_wins = len([t for t in paper_trades if t.pnl > 0])
        real_wins = len([t for t in real_trades if t.get("pnl", 0) > 0])

        return {
            "paper_trades": len(paper_trades),
            "real_trades": len(real_trades),
            "paper_pnl": round(paper_pnl, 2),
            "real_pnl": round(real_pnl, 2),
            "pnl_drift": round(paper_pnl - real_pnl, 2),
            "pnl_drift_pct": (
                round((paper_pnl - real_pnl) / abs(paper_pnl) * 100, 1)
                if paper_pnl != 0
                else 0
            ),
            "paper_win_rate": (
                round(paper_wins / len(paper_trades) * 100, 1)
                if paper_trades
                else 0
            ),
            "real_win_rate": (
                round(real_wins / len(real_trades) * 100, 1) if real_trades else 0
            ),
        }
