"""
Oracle Trader v2 - Modelos de Estado
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections import deque
from typing import Optional, List

from .enums import SymbolStatus, PaperTradeReason, TradeAction, SystemStatus
from .position import Position, VirtualPosition, VirtualStats

__all__ = ['SymbolState', 'SystemState', 'SymbolConfig']


@dataclass
class SymbolConfig:
    """
    Configuração de um símbolo (carregada do modelo treinado).
    """
    symbol: str = ""
    timeframe: str = "M15"
    model_name: str = ""
    
    # Informações do broker
    point: float = 0.00001
    digits: int = 5
    pip_value: float = 10.0
    min_lot: float = 0.01
    lot_step: float = 0.01
    spread_points: int = 10
    
    # Parâmetros HMM
    hmm_momentum_period: int = 12
    hmm_consistency_period: int = 12
    hmm_range_period: int = 20
    n_states: int = 5
    
    # Parâmetros RL
    rl_roc_period: int = 10
    rl_atr_period: int = 14
    rl_ema_period: int = 200
    rl_range_period: int = 20
    rl_volume_ma_period: int = 20
    
    # Multiplicador de lote (específico do símbolo)
    lot_multiplier: float = 1.0
    
    # SL máximo específico (None = usa global)
    sl_max_pips: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'model_name': self.model_name,
            'point': self.point,
            'digits': self.digits,
            'pip_value': self.pip_value,
            'min_lot': self.min_lot,
            'lot_multiplier': self.lot_multiplier,
            'sl_max_pips': self.sl_max_pips,
            'n_states': self.n_states,
        }


@dataclass
class SymbolState:
    """
    Estado completo de um símbolo.
    
    Inclui posição real, posição virtual (paper), estatísticas, etc.
    """
    symbol: str = ""
    config: Optional[SymbolConfig] = None
    
    # Status atual
    status: SymbolStatus = SymbolStatus.PAPER_TRADE
    paper_trade_reason: Optional[PaperTradeReason] = PaperTradeReason.STARTUP
    
    # Cache OHLCV (últimas N barras)
    bars: deque = field(default_factory=lambda: deque(maxlen=350))
    last_bar_time: int = 0
    last_update: float = 0
    
    # Posição REAL (quando status == NORMAL)
    position: Position = field(default_factory=Position)
    
    # Posição VIRTUAL (quando status == PAPER_TRADE)
    virtual_position: VirtualPosition = field(default_factory=VirtualPosition)
    virtual_stats: VirtualStats = field(default_factory=VirtualStats)
    
    # Última predição do modelo
    last_action: TradeAction = TradeAction.WAIT
    last_lot_size: float = 0.0
    last_hmm_state: int = 0
    last_model_action_idx: int = 0
    last_prediction_time: float = 0
    
    # Estatísticas da sessão (trading real)
    trades_count: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    total_pips: float = 0.0
    max_win: float = 0.0
    max_loss: float = 0.0
    current_streak: int = 0
    
    # SL Protection
    sl_hit_times: List[float] = field(default_factory=list)
    sl_hits_in_window: int = 0
    
    # Controle de erros
    failures: int = 0
    last_failure_time: float = 0
    
    def __post_init__(self):
        if self.virtual_stats.symbol == "":
            self.virtual_stats.symbol = self.symbol
    
    @property
    def is_trading_real(self) -> bool:
        """Retorna True se está em modo de trading real"""
        return self.status == SymbolStatus.NORMAL
    
    @property
    def is_paper_trading(self) -> bool:
        """Retorna True se está em modo Paper Trade"""
        return self.status == SymbolStatus.PAPER_TRADE
    
    @property
    def has_position(self) -> bool:
        """Retorna True se tem posição aberta (real ou virtual)"""
        if self.is_trading_real:
            return self.position.is_open
        return self.virtual_position.is_open
    
    @property
    def win_rate(self) -> float:
        """Taxa de acerto (trading real)"""
        if self.trades_count == 0:
            return 0.0
        return self.wins / self.trades_count * 100
    
    def get_stats_dict(self) -> dict:
        """Retorna estatísticas para dashboard"""
        return {
            'trades': self.trades_count,
            'wins': self.wins,
            'losses': self.losses,
            'win_rate': round(self.win_rate, 1),
            'total_pnl': round(self.total_pnl, 2),
            'total_pips': round(self.total_pips, 1),
            'max_win': round(self.max_win, 2),
            'max_loss': round(self.max_loss, 2),
            'current_streak': self.current_streak,
            'sl_hits_in_window': self.sl_hits_in_window,
        }
    
    def to_dict(self) -> dict:
        """Estado completo para WebSocket"""
        return {
            'symbol': self.symbol,
            'status': self.status.value,
            'paper_trade_reason': self.paper_trade_reason.value if self.paper_trade_reason else None,
            'timeframe': self.config.timeframe if self.config else None,
            'position': self.position.to_dict() if self.position.is_open else None,
            'virtual_position': self.virtual_position.to_dict() if self.virtual_position.is_open else None,
            'virtual_stats': self.virtual_stats.to_dict() if self.is_paper_trading else None,
            'prediction': {
                'action': self.last_action.value,
                'lot_size': self.last_lot_size,
                'hmm_state': self.last_hmm_state,
            },
            'stats': self.get_stats_dict(),
            'cache_bars': len(self.bars),
        }


@dataclass
class SystemState:
    """
    Estado global do sistema.
    """
    status: SystemStatus = SystemStatus.INITIALIZING
    start_time: Optional[datetime] = None
    
    # Conta
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    
    # Risco
    initial_balance: float = 0.0
    peak_balance: float = 0.0
    current_dd: float = 0.0  # Positivo = lucro flutuante, Negativo = perda
    max_dd: float = 0.0
    max_dd_pct: float = 0.0
    daily_pnl: float = 0.0
    daily_start_balance: float = 0.0
    risk_limit_active: bool = False
    
    # Estatísticas globais
    total_trades: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_pnl: float = 0.0
    total_pips: float = 0.0
    total_commission: float = 0.0
    total_swap: float = 0.0
    
    # Ciclos
    cycle_count: int = 0
    last_cycle_time: float = 0
    avg_cycle_duration: float = 0.0
    
    # Erros
    error_count: int = 0
    last_error: str = ""
    last_error_time: float = 0
    
    def __post_init__(self):
        if self.start_time is None:
            self.start_time = datetime.now(timezone.utc)
    
    @property
    def uptime_seconds(self) -> int:
        """Tempo de execução em segundos"""
        if not self.start_time:
            return 0
        return int((datetime.now(timezone.utc) - self.start_time).total_seconds())
    
    @property
    def win_rate(self) -> float:
        """Taxa de acerto global"""
        if self.total_trades == 0:
            return 0.0
        return self.total_wins / self.total_trades * 100
    
    def get_summary_dict(self) -> dict:
        """Resumo para dashboard"""
        return {
            'status': self.status.value,
            'uptime': self.uptime_seconds,
            'balance': round(self.balance, 2),
            'equity': round(self.equity, 2),
            'dd_pct': round(self.current_dd, 2),
            'max_dd_pct': round(self.max_dd_pct, 2),
            'risk_limit': self.risk_limit_active,
            'trades': self.total_trades,
            'wins': self.total_wins,
            'losses': self.total_losses,
            'win_rate': round(self.win_rate, 1),
            'pnl': round(self.total_pnl, 2),
            'pips': round(self.total_pips, 1),
            'cycles': self.cycle_count,
            'errors': self.error_count,
        }
