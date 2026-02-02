"""
Oracle Trader v2 - Core

Engine principal e máquina de estados.
"""

from .state_machine import StateMachine, PaperTradeConfig
from .config import ConfigManager, RuntimeConfig, BrokerConfig, WebSocketConfig

__all__ = [
    'StateMachine',
    'PaperTradeConfig',
    'ConfigManager',
    'RuntimeConfig',
    'BrokerConfig',
    'WebSocketConfig',
]
