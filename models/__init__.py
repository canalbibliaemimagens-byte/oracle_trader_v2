"""
Oracle Trader v2 - Models

Dataclasses e tipos usados em todo o projeto.
"""

from .enums import (
    VERSION,
    SymbolStatus,
    PaperTradeReason,
    TradeAction,
    SystemStatus,
    Direction,
    OrderType,
    LOT_SIZES_BASE,
    action_to_trade,
    get_direction_from_action,
)

from .position import (
    Position,
    VirtualPosition,
    VirtualStats,
)

from .trade import (
    Trade,
    TradeResult,
)

from .state import (
    SymbolConfig,
    SymbolState,
    SystemState,
)

__all__ = [
    # Enums
    'VERSION',
    'SymbolStatus',
    'PaperTradeReason',
    'TradeAction',
    'SystemStatus',
    'Direction',
    'OrderType',
    
    # Constantes
    'LOT_SIZES_BASE',
    
    # Funções
    'action_to_trade',
    'get_direction_from_action',
    
    # Position
    'Position',
    'VirtualPosition',
    'VirtualStats',
    
    # Trade
    'Trade',
    'TradeResult',
    
    # State
    'SymbolConfig',
    'SymbolState',
    'SystemState',
]
