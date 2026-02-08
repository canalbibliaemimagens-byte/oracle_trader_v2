"""
Oracle Trader v2.0 - Connector Errors
=======================================

Hierarquia de exceções para o módulo Connector.
"""


class ConnectorError(Exception):
    """Erro base do Connector."""
    pass


class AuthenticationError(ConnectorError):
    """Falha na autenticação OAuth2."""
    pass


class BrokerConnectionError(ConnectorError):
    """Falha na conexão TCP/SSL com o broker."""
    pass


class OrderError(ConnectorError):
    """Falha ao enviar ou executar ordem."""
    def __init__(self, message: str, code: int = 0):
        self.code = code
        super().__init__(message)


class RateLimitError(ConnectorError):
    """Rate limit da API excedido."""
    pass


class SymbolNotFoundError(ConnectorError):
    """Símbolo não encontrado no broker."""
    pass
