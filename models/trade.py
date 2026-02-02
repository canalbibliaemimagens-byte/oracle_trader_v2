"""
Oracle Trader v2 - Modelos de Trade
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid

__all__ = ['Trade', 'TradeResult']


@dataclass
class Trade:
    """
    Registro de uma operação (abertura ou fechamento).
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    symbol: str = ""
    direction: int = 0
    action: str = ""  # OPEN, CLOSE, PARTIAL, SL_HIT, TP_HIT, REVERSE
    size: float = 0.0
    price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    pnl: float = 0.0
    pnl_pips: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    timestamp: Optional[datetime] = None
    bar_time: Optional[datetime] = None
    
    # Contexto do modelo
    hmm_state: int = 0
    model_action_idx: int = 0
    confidence: float = 0.0
    
    # Estado da conta no momento
    balance_before: float = 0.0
    balance_after: float = 0.0
    equity_before: float = 0.0
    drawdown_pct: float = 0.0
    
    # Metadados
    comment: str = ""
    is_virtual: bool = False  # True se for Paper Trade
    magic: int = 0
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
    
    @property
    def is_winner(self) -> bool:
        return self.pnl > 0
    
    @property
    def direction_str(self) -> str:
        if self.direction == 1:
            return "LONG"
        elif self.direction == -1:
            return "SHORT"
        return "FLAT"
    
    def to_dict(self) -> dict:
        """Converte para dicionário (para Supabase/WebSocket)"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'direction': self.direction,
            'direction_str': self.direction_str,
            'action': self.action,
            'size': self.size,
            'price': self.price,
            'sl': self.sl,
            'tp': self.tp,
            'pnl': round(self.pnl, 2),
            'pnl_pips': round(self.pnl_pips, 1),
            'commission': round(self.commission, 2),
            'swap': round(self.swap, 2),
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'hmm_state': self.hmm_state,
            'model_action_idx': self.model_action_idx,
            'balance_after': round(self.balance_after, 2),
            'drawdown_pct': round(self.drawdown_pct, 2),
            'comment': self.comment,
            'is_virtual': self.is_virtual,
        }


@dataclass
class TradeResult:
    """
    Resultado de uma operação de trading.
    
    Retornado pelo Executor após tentar abrir/fechar posição.
    """
    success: bool = False
    trade: Optional[Trade] = None
    message: str = ""
    error_code: int = 0
    
    # Detalhes da execução
    requested_price: float = 0.0
    executed_price: float = 0.0
    slippage_points: float = 0.0
    
    @property
    def slippage_pips(self) -> float:
        """Slippage em pips (assumindo 10 pontos = 1 pip)"""
        return self.slippage_points / 10
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'trade': self.trade.to_dict() if self.trade else None,
            'message': self.message,
            'error_code': self.error_code,
            'slippage_pips': round(self.slippage_pips, 1),
        }
