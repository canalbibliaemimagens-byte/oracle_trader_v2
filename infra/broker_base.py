"""
Oracle Trader v2 - Interface Abstrata de Broker

Esta classe define o contrato que qualquer implementação de broker deve seguir.
Permite trocar de broker (MT5, CCXT, etc.) sem alterar a lógica de trading.

Implementações disponíveis:
- mt5_client.py: MetaTrader 5 (Windows)
- (futuro) ccxt_client.py: Exchanges de crypto
- (futuro) ws_client.py: Brokers via WebSocket
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd

from models import Position, Trade, TradeResult, SymbolConfig


@dataclass
class AccountInfo:
    """Informações da conta do broker"""
    login: int = 0
    server: str = ""
    balance: float = 0.0
    equity: float = 0.0
    margin: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    currency: str = "USD"
    leverage: int = 100


@dataclass
class SymbolInfo:
    """Informações de um símbolo no broker"""
    symbol: str = ""
    point: float = 0.00001
    digits: int = 5
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    spread: int = 0
    trade_allowed: bool = True


@dataclass
class Tick:
    """Tick atual de um símbolo"""
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    time: int = 0


class BrokerBase(ABC):
    """
    Interface abstrata para conexão com brokers.
    
    Todas as implementações de broker devem herdar desta classe
    e implementar os métodos abstratos.
    
    Exemplo de uso:
        broker = MT5Client(config)  # ou CCXTClient(config)
        await broker.connect()
        account = broker.get_account_info()
        positions = broker.get_positions()
    """
    
    def __init__(self, config: dict = None):
        """
        Args:
            config: Configurações específicas do broker
        """
        self.config = config or {}
        self.connected = False
    
    # =========================================================================
    # Conexão
    # =========================================================================
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Estabelece conexão com o broker.
        
        Returns:
            True se conectou com sucesso
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Encerra conexão com o broker"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Retorna True se está conectado"""
        pass
    
    # =========================================================================
    # Informações da Conta
    # =========================================================================
    
    @abstractmethod
    def get_account_info(self) -> Optional[AccountInfo]:
        """
        Retorna informações da conta.
        
        Returns:
            AccountInfo ou None se erro
        """
        pass
    
    @abstractmethod
    def get_terminal_info(self) -> Dict:
        """
        Retorna informações do terminal/plataforma.
        
        Returns:
            Dict com nome, versão, etc.
        """
        pass
    
    # =========================================================================
    # Informações de Símbolos
    # =========================================================================
    
    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """
        Retorna informações de um símbolo.
        
        Args:
            symbol: Nome do símbolo (ex: "EURUSD")
            
        Returns:
            SymbolInfo ou None se símbolo não existe
        """
        pass
    
    @abstractmethod
    def get_tick(self, symbol: str) -> Optional[Tick]:
        """
        Retorna tick atual de um símbolo.
        
        Args:
            symbol: Nome do símbolo
            
        Returns:
            Tick ou None se erro
        """
        pass
    
    # =========================================================================
    # Dados Históricos
    # =========================================================================
    
    @abstractmethod
    def get_bars(
        self, 
        symbol: str, 
        timeframe: str, 
        count: int = 300
    ) -> Optional[pd.DataFrame]:
        """
        Obtém barras OHLCV históricas.
        
        Args:
            symbol: Nome do símbolo
            timeframe: Timeframe (M1, M5, M15, M30, H1, H4, D1)
            count: Número de barras
            
        Returns:
            DataFrame com colunas [time, open, high, low, close, volume]
            ou None se erro
        """
        pass
    
    # =========================================================================
    # Posições
    # =========================================================================
    
    @abstractmethod
    def get_positions(self, magic: int = None) -> List[Dict]:
        """
        Retorna posições abertas.
        
        Args:
            magic: Filtrar por magic number (opcional)
            
        Returns:
            Lista de dicts com informações das posições
        """
        pass
    
    @abstractmethod
    async def open_position(
        self,
        symbol: str,
        direction: int,
        lots: float,
        sl: float = 0,
        tp: float = 0,
        magic: int = 0,
        comment: str = "",
    ) -> TradeResult:
        """
        Abre uma posição.
        
        Args:
            symbol: Símbolo
            direction: 1 (LONG) ou -1 (SHORT)
            lots: Volume
            sl: Stop Loss (0 = sem SL)
            tp: Take Profit (0 = sem TP)
            magic: Magic number
            comment: Comentário
            
        Returns:
            TradeResult com sucesso/falha e detalhes
        """
        pass
    
    @abstractmethod
    async def close_position(
        self,
        symbol: str,
        ticket: int,
        volume: float,
        direction: int,
        magic: int = 0,
    ) -> TradeResult:
        """
        Fecha uma posição (total ou parcial).
        
        Args:
            symbol: Símbolo
            ticket: ID da posição
            volume: Volume a fechar
            direction: Direção original (para fechar no sentido inverso)
            magic: Magic number
            
        Returns:
            TradeResult com sucesso/falha e detalhes
        """
        pass
    
    @abstractmethod
    async def modify_position(
        self,
        ticket: int,
        sl: float = None,
        tp: float = None,
    ) -> TradeResult:
        """
        Modifica SL/TP de uma posição.
        
        Args:
            ticket: ID da posição
            sl: Novo SL (None = não alterar)
            tp: Novo TP (None = não alterar)
            
        Returns:
            TradeResult com sucesso/falha
        """
        pass
    
    # =========================================================================
    # Histórico
    # =========================================================================
    
    @abstractmethod
    def get_closed_position_info(self, ticket: int) -> Optional[Dict]:
        """
        Obtém informações de uma posição fechada.
        
        Args:
            ticket: ID da posição
            
        Returns:
            Dict com pnl, commission, swap, motivo de fechamento, etc.
            ou None se não encontrar
        """
        pass
    
    # =========================================================================
    # Utilitários
    # =========================================================================
    
    def normalize_lots(
        self, 
        lots: float, 
        symbol_info: SymbolInfo
    ) -> float:
        """
        Normaliza volume de acordo com regras do broker.
        
        Args:
            lots: Volume desejado
            symbol_info: Informações do símbolo
            
        Returns:
            Volume normalizado
        """
        # Arredonda para step
        lots = round(lots / symbol_info.volume_step) * symbol_info.volume_step
        
        # Aplica limites
        lots = max(symbol_info.volume_min, lots)
        lots = min(symbol_info.volume_max, lots)
        
        return round(lots, 2)
    
    def calculate_sl_price(
        self,
        direction: int,
        entry_price: float,
        sl_distance: float,
        digits: int = 5,
    ) -> float:
        """
        Calcula preço do Stop Loss.
        
        Args:
            direction: 1 (LONG) ou -1 (SHORT)
            entry_price: Preço de entrada
            sl_distance: Distância do SL em preço
            digits: Dígitos para arredondamento
            
        Returns:
            Preço do SL
        """
        if direction == 1:  # LONG
            sl = entry_price - sl_distance
        else:  # SHORT
            sl = entry_price + sl_distance
        
        return round(sl, digits)
