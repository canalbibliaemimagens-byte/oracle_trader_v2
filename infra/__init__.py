"""
Oracle Trader v2 - Infraestrutura

Módulos de conectividade com brokers e serviços externos.

Brokers implementados:
- MT5Client: MetaTrader 5 (Windows)

Serviços:
- WebSocketServer: Comunicação com Dashboard

Futuros:
- CCXTClient: Exchanges crypto
- SupabaseLogger: Persistência no Supabase
"""

from .broker_base import (
    BrokerBase,
    AccountInfo,
    SymbolInfo,
    Tick,
)

from .mt5_client import MT5Client

from .websocket_server import (
    WebSocketServer,
    handle_command,
    get_commands_help,
    AVAILABLE_COMMANDS,
)

__all__ = [
    # Broker
    'BrokerBase',
    'AccountInfo',
    'SymbolInfo',
    'Tick',
    'MT5Client',
    
    # WebSocket
    'WebSocketServer',
    'handle_command',
    'get_commands_help',
    'AVAILABLE_COMMANDS',
]
