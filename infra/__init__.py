"""
Oracle Trader v2 - Infraestrutura

Módulos de conectividade com brokers e serviços externos.

Brokers implementados:
- MT5Client: MetaTrader 5 (Windows)

Brokers futuros:
- CCXTClient: Exchanges crypto
- WSClient: Brokers via WebSocket
"""

from .broker_base import (
    BrokerBase,
    AccountInfo,
    SymbolInfo,
    Tick,
)

from .mt5_client import MT5Client

__all__ = [
    'BrokerBase',
    'AccountInfo',
    'SymbolInfo',
    'Tick',
    'MT5Client',
]
