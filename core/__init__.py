"""
Oracle Trader v2 - Core

Módulos centrais de controle e configuração.
"""

from .config import (
    ConfigManager,
    RuntimeConfig,
    BrokerConfig,
    WebSocketConfig,
)

from .state_machine import (
    StateMachine,
    PaperTradeConfig,
)

from .engine import (
    OracleEngine,
    setup_signal_handlers,
    VERSION,
)

__all__ = [
    # Config
    'ConfigManager',
    'RuntimeConfig',
    'BrokerConfig',
    'WebSocketConfig',
    
    # State Machine
    'StateMachine',
    'PaperTradeConfig',
    
    # Engine
    'OracleEngine',
    'setup_signal_handlers',
    'VERSION',
]
