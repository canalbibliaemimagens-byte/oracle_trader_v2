"""
Oracle Trader v2 - Modelos de Posição
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .enums import Direction

__all__ = ['Position', 'VirtualPosition']


@dataclass
class Position:
    """
    Representa uma posição real no broker.
    """
    ticket: int = 0
    symbol: str = ""
    direction: int = 0  # -1=SHORT, 0=FLAT, 1=LONG
    size: float = 0.0
    open_price: float = 0.0
    open_time: Optional[datetime] = None
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_pips: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    magic: int = 0
    comment: str = ""
    
    @property
    def is_open(self) -> bool:
        """Retorna True se há posição aberta"""
        return self.direction != 0
    
    @property
    def direction_str(self) -> str:
        """Retorna direção como string"""
        if self.direction == Direction.LONG.value:
            return "LONG"
        elif self.direction == Direction.SHORT.value:
            return "SHORT"
        return "FLAT"
    
    def to_dict(self) -> dict:
        """Converte para dicionário"""
        return {
            'ticket': self.ticket,
            'symbol': self.symbol,
            'direction': self.direction,
            'direction_str': self.direction_str,
            'size': self.size,
            'open_price': self.open_price,
            'current_price': self.current_price,
            'pnl': round(self.pnl, 2),
            'pnl_pips': round(self.pnl_pips, 1),
            'sl': self.sl,
            'tp': self.tp,
        }


@dataclass
class VirtualPosition:
    """
    Representa uma posição virtual (Paper Trade).
    
    Usada quando o símbolo está em modo PAPER_TRADE para:
    - Simular operações sem executar
    - Rastrear performance virtual
    - Decidir quando voltar ao trading real
    """
    symbol: str = ""
    direction: int = 0
    size: float = 0.0
    open_price: float = 0.0
    open_time: Optional[datetime] = None
    current_price: float = 0.0
    
    # Estatísticas virtuais
    virtual_pnl: float = 0.0
    virtual_pnl_pips: float = 0.0
    
    @property
    def is_open(self) -> bool:
        return self.direction != 0
    
    @property
    def direction_str(self) -> str:
        if self.direction == Direction.LONG.value:
            return "LONG"
        elif self.direction == Direction.SHORT.value:
            return "SHORT"
        return "FLAT"
    
    def update_pnl(self, current_price: float, point: float, pip_value: float):
        """
        Atualiza PnL virtual baseado no preço atual.
        
        Args:
            current_price: Preço atual do ativo
            point: Valor do ponto (ex: 0.00001 para EURUSD)
            pip_value: Valor do pip por lote (ex: 10 para forex)
        """
        if not self.is_open:
            return
        
        self.current_price = current_price
        
        # Calcula diferença de preço
        price_diff = (current_price - self.open_price) * self.direction
        
        # Converte para pips (assumindo 10 pontos = 1 pip para 5 dígitos)
        points_per_pip = 10 if point < 0.001 else 1
        self.virtual_pnl_pips = price_diff / point / points_per_pip
        
        # Calcula PnL em dinheiro
        self.virtual_pnl = self.virtual_pnl_pips * pip_value * self.size
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'direction_str': self.direction_str,
            'size': self.size,
            'open_price': self.open_price,
            'current_price': self.current_price,
            'virtual_pnl': round(self.virtual_pnl, 2),
            'virtual_pnl_pips': round(self.virtual_pnl_pips, 1),
            'is_virtual': True,
        }


@dataclass 
class VirtualStats:
    """
    Estatísticas de Paper Trade para um símbolo.
    
    Usado para decidir quando sair do Paper Trade.
    """
    symbol: str = ""
    
    # Contadores
    virtual_trades: int = 0
    virtual_wins: int = 0
    virtual_losses: int = 0
    
    # Streak (sequência)
    current_streak: int = 0  # Positivo = wins, Negativo = losses
    max_win_streak: int = 0
    max_loss_streak: int = 0
    
    # PnL acumulado
    total_virtual_pnl: float = 0.0
    total_virtual_pips: float = 0.0
    
    # Melhor/Pior trade virtual
    best_virtual_trade: float = 0.0
    worst_virtual_trade: float = 0.0
    
    @property
    def win_rate(self) -> float:
        """Taxa de acerto virtual"""
        if self.virtual_trades == 0:
            return 0.0
        return self.virtual_wins / self.virtual_trades * 100
    
    def record_trade(self, pnl: float, pips: float):
        """
        Registra um trade virtual fechado.
        
        Args:
            pnl: Lucro/prejuízo em dinheiro
            pips: Lucro/prejuízo em pips
        """
        self.virtual_trades += 1
        self.total_virtual_pnl += pnl
        self.total_virtual_pips += pips
        
        is_win = pnl > 0
        
        if is_win:
            self.virtual_wins += 1
            self.best_virtual_trade = max(self.best_virtual_trade, pnl)
            
            # Atualiza streak
            if self.current_streak >= 0:
                self.current_streak += 1
            else:
                self.current_streak = 1
            self.max_win_streak = max(self.max_win_streak, self.current_streak)
        else:
            self.virtual_losses += 1
            self.worst_virtual_trade = min(self.worst_virtual_trade, pnl)
            
            # Atualiza streak
            if self.current_streak <= 0:
                self.current_streak -= 1
            else:
                self.current_streak = -1
            self.max_loss_streak = max(self.max_loss_streak, abs(self.current_streak))
    
    def reset(self):
        """Reseta estatísticas"""
        self.virtual_trades = 0
        self.virtual_wins = 0
        self.virtual_losses = 0
        self.current_streak = 0
        self.max_win_streak = 0
        self.max_loss_streak = 0
        self.total_virtual_pnl = 0.0
        self.total_virtual_pips = 0.0
        self.best_virtual_trade = 0.0
        self.worst_virtual_trade = 0.0
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'virtual_trades': self.virtual_trades,
            'virtual_wins': self.virtual_wins,
            'virtual_losses': self.virtual_losses,
            'win_rate': round(self.win_rate, 1),
            'current_streak': self.current_streak,
            'max_win_streak': self.max_win_streak,
            'total_virtual_pnl': round(self.total_virtual_pnl, 2),
            'total_virtual_pips': round(self.total_virtual_pips, 1),
        }
