"""
Oracle Trader v2.0 - Modelos de Dados (DTOs)
=============================================

Dataclasses usadas como contratos entre módulos.
Nenhum comportamento complexo - apenas dados e propriedades derivadas.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Bar:
    """
    Barra OHLCV imutável.
    Formato padrão para transferência de dados de mercado.
    """
    symbol: str
    time: int           # Unix Timestamp (segundos, UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass
class Signal:
    """
    Sinal emitido pelo Preditor.
    Contém ação, intensidade e metadados para logging.
    """
    symbol: str
    action: str             # "WAIT", "LONG_WEAK", "LONG_MODERATE", etc.
    direction: int          # -1, 0, 1
    intensity: int          # 0, 1, 2, 3
    hmm_state: int          # 0 a N-1 (estado HMM atual)
    virtual_pnl: float      # PnL da posição virtual
    timestamp: float        # Unix timestamp do momento da emissão

    @property
    def is_entry(self) -> bool:
        """True se é sinal de entrada (posicionado)."""
        return self.direction != 0

    @property
    def is_exit(self) -> bool:
        """True se é sinal de saída (WAIT)."""
        return self.direction == 0


@dataclass
class AccountInfo:
    """Informações da conta de trading."""
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float     # % (equity / margin * 100)
    currency: str = "USD"


@dataclass
class Position:
    """Posição aberta no broker."""
    ticket: int
    symbol: str
    direction: int          # 1 = LONG, -1 = SHORT
    volume: float
    open_price: float
    current_price: float
    pnl: float
    sl: float = 0.0
    tp: float = 0.0
    open_time: int = 0
    comment: str = ""


@dataclass(frozen=True)
class TickData:
    """Tick de mercado."""
    symbol: str
    time: int
    bid: float
    ask: float


@dataclass
class OrderResult:
    """Resultado de operação de ordem."""
    success: bool
    ticket: Optional[int] = None
    price: Optional[float] = None
    error: str = ""


@dataclass
class OrderUpdate:
    """Atualização de status de ordem."""
    id: str
    status: str
    filled_quantity: float
    average_price: float


@dataclass
class VirtualPosition:
    """
    Posição virtual mantida pelo Preditor.
    NÃO representa posição real - apenas para cálculo de features.

    O campo 'size' é o lote real (lot_sizes[intensity]) injetado pelo
    VirtualPositionManager ao converter via as_core_virtual_position().
    """
    direction: int = 0          # -1, 0, 1
    intensity: int = 0          # 0, 1, 2, 3
    entry_price: float = 0.0
    current_pnl: float = 0.0
    size: float = 0.0           # Lote real (injetado pelo VPM)

    @property
    def is_open(self) -> bool:
        """True se há posição aberta."""
        return self.direction != 0

    @property
    def direction_name(self) -> str:
        """Nome legível da direção."""
        if self.direction == 1:
            return "LONG"
        elif self.direction == -1:
            return "SHORT"
        return "FLAT"
