"""
Oracle Trader v2.0 - Connector Base (Interface Abstrata)
=========================================================

Todo conector de broker deve implementar esta interface.
Garante que Preditor, Executor e Paper não dependem de broker específico.

Implementações:
  - ctrader/client.py: Produção (cTrader Open API)
  - mock/client.py: Testes e desenvolvimento
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

from core.models import AccountInfo, Bar, OrderResult, Position


class BaseConnector(ABC):
    """
    Interface abstrata para conectores de broker.
    Qualquer broker (cTrader, MT5, Interactive Brokers) deve implementar.
    """

    # =========================================================================
    # CONEXÃO
    # =========================================================================

    @abstractmethod
    async def connect(self) -> bool:
        """
        Estabelece conexão e autentica com o broker.

        Returns:
            True se conectou com sucesso.
        """
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Fecha conexão de forma limpa."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        ...

    # =========================================================================
    # DADOS DE MERCADO
    # =========================================================================

    @abstractmethod
    async def get_history(self, symbol: str, timeframe: str, bars: int) -> List[Bar]:
        """
        Baixa histórico OHLCV recente.

        Args:
            symbol: Nome do símbolo (ex: "EURUSD").
            timeframe: Timeframe (ex: "M15").
            bars: Número de barras a retornar.

        Returns:
            Lista de Bar ordenada do mais antigo para o mais recente.
        """
        ...

    @abstractmethod
    async def subscribe_bars(
        self,
        symbols: List[str],
        timeframe: str,
        callback: Callable[[Bar], Awaitable[None]],
    ) -> None:
        """
        Assina feed de barras em tempo real.
        Callback é chamado quando uma nova barra FECHA.

        Args:
            symbols: Lista de símbolos para assinar.
            timeframe: Timeframe desejado.
            callback: Função async chamada com cada Bar fechada.
        """
        ...

    @abstractmethod
    async def unsubscribe_bars(self, symbols: List[str]) -> None:
        """Cancela assinatura de barras."""
        ...

    # =========================================================================
    # DADOS DE CONTA
    # =========================================================================

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Retorna informações da conta."""
        ...

    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Retorna todas as posições abertas."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Retorna posição aberta para um símbolo específico.

        Returns:
            Position se houver, None se FLAT.
        """
        ...

    @abstractmethod
    async def get_order_history(self, since: datetime) -> List[dict]:
        """Retorna histórico de ordens desde uma data."""
        ...

    # =========================================================================
    # EXECUÇÃO
    # =========================================================================

    @abstractmethod
    async def open_order(
        self,
        symbol: str,
        direction: int,
        volume: float,
        sl: float = 0,
        tp: float = 0,
        comment: str = "",
    ) -> OrderResult:
        """
        Envia ordem a mercado.

        Args:
            symbol: Nome do símbolo.
            direction: 1 para LONG, -1 para SHORT.
            volume: Tamanho em lotes.
            sl: Stop Loss em USD (0 = sem SL).
            tp: Take Profit em USD (0 = sem TP).
            comment: Comentário da ordem (max 100 chars para cTrader).

        Returns:
            OrderResult com ticket se sucesso, erro se falha.
        """
        ...

    @abstractmethod
    async def close_order(self, ticket: int, volume: float = 0) -> OrderResult:
        """
        Fecha ordem (parcial ou total).

        Args:
            ticket: ID da ordem/posição.
            volume: Volume a fechar (0 = fechar tudo).
        """
        ...

    @abstractmethod
    async def modify_order(self, ticket: int, sl: float = 0, tp: float = 0) -> OrderResult:
        """
        Modifica SL/TP de uma ordem existente.

        Args:
            ticket: ID da ordem/posição.
            sl: Novo Stop Loss em USD (0 = remover).
            tp: Novo Take Profit em USD (0 = remover).
        """
        ...

    # =========================================================================
    # SÍMBOLO INFO
    # =========================================================================

    @abstractmethod
    async def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Retorna informações do símbolo (point, digits, spread, etc).

        Returns:
            Dict com info do símbolo ou None se não encontrado.
        """
        ...
