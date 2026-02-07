"""
Oracle Trader v2.0 - Connector
================================

Interface abstrata + implementações para comunicação com brokers.
"""

from .base import BaseConnector
from .rate_limiter import RateLimiter
from .errors import (
    ConnectorError, AuthenticationError, BrokerConnectionError,
    OrderError, RateLimitError, SymbolNotFoundError,
)

__all__ = [
    "BaseConnector", "RateLimiter",
    "ConnectorError", "AuthenticationError", "BrokerConnectionError",
    "OrderError", "RateLimitError", "SymbolNotFoundError",
]
