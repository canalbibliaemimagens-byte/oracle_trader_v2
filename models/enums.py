"""
Oracle Trader v2 - Enums e Constantes
"""

from enum import Enum, auto

__all__ = [
    'SymbolStatus',
    'PaperTradeReason', 
    'TradeAction',
    'SystemStatus',
    'Direction',
    'OrderType',
]


class SymbolStatus(str, Enum):
    """
    Estados possíveis de um símbolo.
    
    v2: WARMUP e QUARANTINE foram unificados em PAPER_TRADE
    """
    NORMAL = "NORMAL"           # Trading real ativo
    PAPER_TRADE = "PAPER_TRADE" # Simulação virtual (substitui WARMUP/QUARANTINE)
    BLOCKED = "BLOCKED"         # Bloqueado manualmente
    NO_MODEL = "NO_MODEL"       # Sem modelo carregado


class PaperTradeReason(str, Enum):
    """
    Motivos para entrar em Paper Trade.
    
    Cada motivo pode ter critérios de saída diferentes.
    """
    STARTUP = "STARTUP"           # Inicialização do sistema
    SL_PROTECTION = "SL_PROTECTION"  # Múltiplos SL hits em janela de tempo
    TP_GLOBAL = "TP_GLOBAL"       # Take Profit global atingido
    DD_LIMIT = "DD_LIMIT"         # Drawdown limit atingido
    MANUAL = "MANUAL"             # Bloqueio/desbloqueio manual


class TradeAction(str, Enum):
    """Ações possíveis do modelo"""
    WAIT = "WAIT"   # Não fazer nada / fechar posição
    BUY = "BUY"     # Comprar (LONG)
    SELL = "SELL"   # Vender (SHORT)


class SystemStatus(str, Enum):
    """Status global do sistema"""
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    STOPPED = "STOPPED"


class Direction(int, Enum):
    """Direção da posição"""
    SHORT = -1
    FLAT = 0
    LONG = 1


class OrderType(str, Enum):
    """Tipo de ordem"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


# =============================================================================
# Constantes
# =============================================================================

VERSION = "2.0.0"

# Lotes base padrão (podem ser multiplicados por símbolo)
LOT_SIZES_BASE = [0.01, 0.03, 0.05]


# =============================================================================
# Funções Utilitárias
# =============================================================================

def action_to_trade(action_idx: int, lot_multiplier: float = 1.0) -> tuple:
    """
    Converte índice de ação do modelo PPO para (TradeAction, lot_size).
    
    Mapeamento:
        0: WAIT (FLAT)
        1: BUY  small
        2: BUY  medium  
        3: BUY  large
        4: SELL small
        5: SELL medium
        6: SELL large
    
    Args:
        action_idx: Índice da ação (0-6)
        lot_multiplier: Multiplicador de lote do símbolo
        
    Returns:
        Tuple (TradeAction, lot_size)
    """
    if action_idx == 0:
        return TradeAction.WAIT, 0.0
    
    if action_idx in [1, 2, 3]:
        base_lot = LOT_SIZES_BASE[action_idx - 1]
        return TradeAction.BUY, round(base_lot * lot_multiplier, 2)
    
    if action_idx in [4, 5, 6]:
        base_lot = LOT_SIZES_BASE[action_idx - 4]
        return TradeAction.SELL, round(base_lot * lot_multiplier, 2)
    
    # Fallback
    return TradeAction.WAIT, 0.0


def get_direction_from_action(action: TradeAction) -> int:
    """Retorna direção numérica da ação"""
    if action == TradeAction.BUY:
        return Direction.LONG.value
    elif action == TradeAction.SELL:
        return Direction.SHORT.value
    return Direction.FLAT.value
