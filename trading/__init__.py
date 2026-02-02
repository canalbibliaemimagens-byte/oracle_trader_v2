"""
Oracle Trader v2 - Trading

Lógica de execução e gerenciamento de risco.
"""

from .paper_trade import PaperTradeManager
from .risk_manager import RiskManager, RiskConfig
from .position_manager import PositionManager
from .executor import Executor
from .lot_calculator import (
    LotCalculator,
    AssetClass,
    AssetClassConfig,
    DEFAULT_ASSET_CONFIGS,
)

__all__ = [
    'PaperTradeManager',
    'RiskManager',
    'RiskConfig',
    'PositionManager',
    'Executor',
    'LotCalculator',
    'AssetClass',
    'AssetClassConfig',
    'DEFAULT_ASSET_CONFIGS',
]
