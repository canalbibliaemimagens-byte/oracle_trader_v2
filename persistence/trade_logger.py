"""
Oracle Trader v2.0 — Trade Logger
===================================

Abstração de alto nível para registrar trades reais e paper.
"""

import uuid
from datetime import datetime, timezone


class TradeLogger:
    """Logger de alto nível para trades (real e paper)."""

    def __init__(self, supabase_client: "SupabaseClient", session_id: str):
        self.db = supabase_client
        self.session_id = session_id

    async def log_trade(
        self,
        symbol: str,
        direction: int,
        intensity: int,
        action: str,
        volume: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pips: float,
        hmm_state: int,
        commission: float = 0,
        comment: str = "",
        is_paper: bool = False,
    ):
        """Registra trade (real ou paper)."""
        trade_data = {
            "id": str(uuid.uuid4())[:8],
            "session_id": self.session_id,
            "symbol": symbol,
            "direction": direction,
            "intensity": intensity,
            "action": action,
            "volume": volume,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pnl": round(pnl, 2),
            "pnl_pips": round(pnl_pips, 1),
            "commission": commission,
            "hmm_state": hmm_state,
            "comment": comment,
            "is_paper": is_paper,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.db.log_trade(trade_data)

    async def log_paper_trade(self, paper_trade):
        """Registra trade do PaperTrader."""
        await self.log_trade(
            symbol=paper_trade.symbol,
            direction=paper_trade.direction,
            intensity=paper_trade.intensity,
            action="CLOSE",
            volume=paper_trade.volume,
            entry_price=paper_trade.entry_price,
            exit_price=paper_trade.exit_price,
            pnl=paper_trade.pnl,
            pnl_pips=paper_trade.pnl_pips,
            hmm_state=paper_trade.hmm_state,
            commission=paper_trade.commission,
            is_paper=True,
        )
