# 🔌 Módulo CONNECTOR: Especificação Técnica

**Versão:** 1.1  
**Nível:** Interface de Baixo Nível  
**Responsabilidade:** Abstrair a comunicação com o Broker (cTrader). Converter protocolos específicos (Protobuf, FIX, API proprietária) em modelos padrão do `Core`.

---

## 1. Estrutura de Arquivos

```
oracle_v2/connector/
├── __init__.py
├── base.py                 # Classe Abstrata (Protocolo)
├── ctrader/                # Implementação cTrader
│   ├── __init__.py
│   ├── client.py           # Cliente Async
│   ├── auth.py             # OAuth2 Flow
│   ├── symbols.py          # Mapeamento symbol_id
│   └── bar_detector.py     # Detecção de barra fechada
└── mock/                   # Mock para Testes
    ├── __init__.py
    └── client.py
```

---

## 2. Contrato de Interface (`base.py`)

Todo conector deve implementar esta classe abstrata.

```python
from abc import ABC, abstractmethod
from typing import List, Callable, Awaitable, Optional
from datetime import datetime
from ..core.models import Bar, AccountInfo, Position, OrderResult

class BaseConnector(ABC):
    """
    Interface abstrata para conectores de broker.
    Qualquer broker (cTrader, MT5, Interactive Brokers) deve implementar esta interface.
    """
    
    # =========================================================================
    # CONEXÃO
    # =========================================================================
    
    @abstractmethod
    async def connect(self) -> bool:
        """
        Estabelece conexão e autentica com o broker.
        
        Returns:
            True se conectou com sucesso
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Fecha conexão de forma limpa."""
        pass
        
    @abstractmethod
    def is_connected(self) -> bool:
        """Verifica se está conectado."""
        pass

    # =========================================================================
    # DADOS DE MERCADO
    # =========================================================================
    
    @abstractmethod
    async def get_history(self, symbol: str, timeframe: str, bars: int) -> List[Bar]:
        """
        Baixa histórico OHLCV recente.
        
        Args:
            symbol: Nome do símbolo (ex: "EURUSD")
            timeframe: Timeframe (ex: "M15")
            bars: Número de barras a retornar
            
        Returns:
            Lista de Bar ordenada do mais antigo para o mais recente
        """
        pass
        
    @abstractmethod
    async def subscribe_bars(
        self, 
        symbols: List[str], 
        timeframe: str,
        callback: Callable[[Bar], Awaitable[None]]
    ) -> None:
        """
        Assina feed de barras em tempo real.
        Callback é chamado quando uma nova barra FECHA.
        
        Args:
            symbols: Lista de símbolos para assinar
            timeframe: Timeframe desejado
            callback: Função async chamada com cada Bar fechada
        """
        pass

    @abstractmethod
    async def unsubscribe_bars(self, symbols: List[str]) -> None:
        """Cancela assinatura de barras."""
        pass

    # =========================================================================
    # DADOS DE CONTA
    # =========================================================================
    
    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """
        Retorna informações da conta.
        
        Returns:
            AccountInfo com balance, equity, margin, etc.
        """
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Retorna todas as posições abertas.
        
        Returns:
            Lista de Position (pode estar vazia)
        """
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Retorna posição aberta para um símbolo específico.
        
        Args:
            symbol: Nome do símbolo
            
        Returns:
            Position se houver, None se FLAT
        """
        pass

    @abstractmethod
    async def get_order_history(self, since: datetime) -> List[dict]:
        """
        Retorna histórico de ordens desde uma data.
        
        Args:
            since: Data inicial (UTC)
            
        Returns:
            Lista de ordens fechadas
        """
        pass

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
        comment: str = ""
    ) -> OrderResult:
        """
        Envia ordem a mercado.
        
        Args:
            symbol: Nome do símbolo
            direction: 1 para LONG, -1 para SHORT
            volume: Tamanho em lotes
            sl: Stop Loss em USD (0 = sem SL)
            tp: Take Profit em USD (0 = sem TP)
            comment: Comentário da ordem (max 100 chars para cTrader)
            
        Returns:
            OrderResult com ticket se sucesso, erro se falha
        """
        pass

    @abstractmethod
    async def close_order(self, ticket: int, volume: float = 0) -> OrderResult:
        """
        Fecha ordem (parcial ou total).
        
        Args:
            ticket: ID da ordem/posição
            volume: Volume a fechar (0 = fechar tudo)
            
        Returns:
            OrderResult
        """
        pass

    @abstractmethod
    async def modify_order(self, ticket: int, sl: float = 0, tp: float = 0) -> OrderResult:
        """
        Modifica SL/TP de uma ordem existente.
        
        Args:
            ticket: ID da ordem/posição
            sl: Novo Stop Loss em USD (0 = remover)
            tp: Novo Take Profit em USD (0 = remover)
            
        Returns:
            OrderResult
        """
        pass
```

---

## 3. Modelos de Retorno (no Core)

```python
# core/models.py

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Bar:
    """Barra OHLCV imutável."""
    symbol: str
    time: int           # Unix Timestamp (segundos, UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float

@dataclass
class AccountInfo:
    """Informações da conta."""
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float     # % (equity / margin * 100)
    currency: str           # "USD"

@dataclass
class Position:
    """Posição aberta."""
    ticket: int
    symbol: str
    direction: int          # 1 = LONG, -1 = SHORT
    volume: float
    open_price: float
    current_price: float
    pnl: float
    sl: float
    tp: float
    open_time: int          # Unix timestamp
    comment: str

@dataclass
class OrderResult:
    """Resultado de operação."""
    success: bool
    ticket: Optional[int] = None
    price: Optional[float] = None
    error: str = ""
```

---

## 4. Implementação cTrader (`ctrader/`)

### 4.1 Tecnologia

| Item | Especificação |
|------|---------------|
| Protocolo | cTrader Open API v2 (Protobuf sobre TCP/SSL) |
| Biblioteca | Cliente async puro ou wrapper existente |
| SSL | Obrigatório (porta 5035 live, 5036 demo) |
| Autenticação | OAuth 2.0 com refresh token |

### 4.2 Cliente (`client.py`)

```python
from ..base import BaseConnector
from .auth import OAuth2Manager
from .symbols import SymbolMapper
from .bar_detector import BarDetector

class CTraderConnector(BaseConnector):
    """Implementação cTrader Open API."""
    
    def __init__(self, credentials: dict):
        self.credentials = credentials
        self.auth = OAuth2Manager(credentials)
        self.symbols = SymbolMapper()
        self.bar_detector = BarDetector()
        self._connection = None
        self._subscriptions: Dict[str, Callable] = {}
    
    async def connect(self) -> bool:
        # 1. Obtém/renova token OAuth2
        token = await self.auth.get_valid_token()
        if not token:
            return False
        
        # 2. Conecta TCP/SSL
        self._connection = await self._create_connection()
        
        # 3. Autentica na API
        await self._send_auth_request(token)
        
        # 4. Carrega mapeamento de símbolos
        await self.symbols.load(self._connection)
        
        return True
    
    async def get_history(self, symbol: str, timeframe: str, bars: int) -> List[Bar]:
        symbol_id = self.symbols.get_id(symbol)
        # Envia ProtoOAGetTrendbarsReq
        # Converte resposta para List[Bar]
        pass
    
    async def subscribe_bars(self, symbols: List[str], timeframe: str, 
                            callback: Callable[[Bar], Awaitable[None]]) -> None:
        for symbol in symbols:
            symbol_id = self.symbols.get_id(symbol)
            # Assina ProtoOASubscribeSpotsReq
            # Usa BarDetector para detectar fechamento de barra
            self._subscriptions[symbol] = callback
            self.bar_detector.register(symbol, timeframe, callback)
    
    async def open_order(self, symbol: str, direction: int, volume: float,
                        sl: float = 0, tp: float = 0, comment: str = "") -> OrderResult:
        symbol_id = self.symbols.get_id(symbol)
        
        # Converte volume para unidades cTrader (centavos)
        volume_units = int(volume * 100)
        
        # Converte SL/TP de USD para distância em pips
        sl_pips = self._usd_to_pips(symbol, sl) if sl > 0 else 0
        tp_pips = self._usd_to_pips(symbol, tp) if tp > 0 else 0
        
        # Envia ProtoOANewOrderReq
        # ...
        pass
```

### 4.3 Autenticação (`auth.py`)

```python
class OAuth2Manager:
    """Gerencia tokens OAuth2 para cTrader."""
    
    TOKEN_FILE = "tokens.json"
    
    def __init__(self, credentials: dict):
        self.client_id = credentials['client_id']
        self.client_secret = credentials['client_secret']
        self.access_token = credentials.get('access_token')
        self.refresh_token = credentials.get('refresh_token')
        self.expires_at = 0
    
    async def get_valid_token(self) -> Optional[str]:
        """Retorna token válido, renovando se necessário."""
        if self._is_token_valid():
            return self.access_token
        
        if self.refresh_token:
            await self._refresh_token()
            return self.access_token
        
        return None
    
    def _is_token_valid(self) -> bool:
        """Token válido se expira em mais de 5 minutos."""
        import time
        return time.time() < (self.expires_at - 300)
    
    async def _refresh_token(self):
        """Renova token usando refresh_token."""
        # POST para https://openapi.ctrader.com/apps/token
        # Atualiza self.access_token, self.refresh_token, self.expires_at
        # Persiste em tokens.json
        pass
```

### 4.4 Detecção de Barra Fechada (`bar_detector.py`)

cTrader não emite evento "nova barra fechada" diretamente. Precisamos detectar localmente.

```python
from datetime import datetime
from typing import Dict, Callable, Awaitable

class BarDetector:
    """
    Detecta fechamento de barra baseado em ticks.
    
    Estratégia: Monitora timestamp dos ticks.
    Quando timestamp muda de período (ex: 10:14:59 -> 10:15:00),
    considera que a barra anterior fechou.
    """
    
    TIMEFRAME_SECONDS = {
        "M1": 60,
        "M5": 300,
        "M15": 900,
        "M30": 1800,
        "H1": 3600,
        "H4": 14400,
        "D1": 86400,
    }
    
    def __init__(self):
        self._last_bar_time: Dict[str, int] = {}
        self._callbacks: Dict[str, Callable] = {}
        self._timeframes: Dict[str, str] = {}
        self._pending_bars: Dict[str, dict] = {}
    
    def register(self, symbol: str, timeframe: str, callback: Callable):
        """Registra callback para barra fechada."""
        self._callbacks[symbol] = callback
        self._timeframes[symbol] = timeframe
        self._last_bar_time[symbol] = 0
    
    async def on_tick(self, symbol: str, tick_time: int, price: float):
        """
        Processa tick e detecta mudança de barra.
        
        Args:
            symbol: Símbolo
            tick_time: Timestamp do tick (segundos)
            price: Preço do tick
        """
        if symbol not in self._callbacks:
            return
        
        tf_seconds = self.TIMEFRAME_SECONDS[self._timeframes[symbol]]
        current_bar_time = (tick_time // tf_seconds) * tf_seconds
        
        if self._last_bar_time[symbol] == 0:
            self._last_bar_time[symbol] = current_bar_time
            return
        
        # Mudou de barra!
        if current_bar_time > self._last_bar_time[symbol]:
            # Emite barra anterior como fechada
            if symbol in self._pending_bars:
                bar = self._finalize_bar(symbol)
                await self._callbacks[symbol](bar)
            
            self._last_bar_time[symbol] = current_bar_time
        
        # Atualiza barra pendente
        self._update_pending_bar(symbol, tick_time, price)
    
    def _update_pending_bar(self, symbol: str, time: int, price: float):
        """Atualiza OHLC da barra sendo formada."""
        if symbol not in self._pending_bars:
            self._pending_bars[symbol] = {
                'open': price,
                'high': price,
                'low': price,
                'close': price,
                'time': self._last_bar_time[symbol],
                'volume': 0
            }
        else:
            bar = self._pending_bars[symbol]
            bar['high'] = max(bar['high'], price)
            bar['low'] = min(bar['low'], price)
            bar['close'] = price
            bar['volume'] += 1  # Simplificado
```

### 4.5 Rate Limiting

```python
import asyncio
from collections import deque
import time

class RateLimiter:
    """
    Leaky bucket para respeitar limites da cTrader API.
    
    Limites:
    - Trading: 50 req/s
    - Histórico: 5 req/s
    """
    
    def __init__(self, rate: int, per_seconds: float = 1.0):
        self.rate = rate
        self.per_seconds = per_seconds
        self.timestamps: deque = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Aguarda até que seja permitido fazer requisição."""
        async with self._lock:
            now = time.time()
            
            # Remove timestamps antigos
            while self.timestamps and self.timestamps[0] < now - self.per_seconds:
                self.timestamps.popleft()
            
            # Se no limite, aguarda
            if len(self.timestamps) >= self.rate:
                wait_time = self.timestamps[0] + self.per_seconds - now
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            self.timestamps.append(time.time())

# Uso no cliente
class CTraderConnector:
    def __init__(self):
        self._rate_limiter_trading = RateLimiter(50)   # 50/s
        self._rate_limiter_history = RateLimiter(5)    # 5/s
    
    async def open_order(self, ...):
        await self._rate_limiter_trading.acquire()
        # ... envia ordem
    
    async def get_history(self, ...):
        await self._rate_limiter_history.acquire()
        # ... busca histórico
```

---

## 5. Mock Connector (`mock/`)

Implementação em memória para testes.

```python
from ..base import BaseConnector
from ..core.models import Bar, AccountInfo, Position, OrderResult
import random

class MockConnector(BaseConnector):
    """
    Connector mock para testes unitários e de integração.
    Simula latência, slippage e preenchimento de ordens.
    """
    
    def __init__(self, initial_balance: float = 10000):
        self.balance = initial_balance
        self.equity = initial_balance
        self.positions: Dict[str, Position] = {}
        self.next_ticket = 1000
        self._connected = False
        self._bars_data: Dict[str, List[Bar]] = {}  # Para replay de CSV
    
    async def connect(self) -> bool:
        await asyncio.sleep(0.1)  # Simula latência
        self._connected = True
        return True
    
    async def get_history(self, symbol: str, timeframe: str, bars: int) -> List[Bar]:
        await asyncio.sleep(0.05)  # Simula latência
        
        if symbol in self._bars_data:
            return self._bars_data[symbol][-bars:]
        
        # Gera dados aleatórios se não houver CSV
        return self._generate_random_bars(symbol, bars)
    
    async def open_order(self, symbol: str, direction: int, volume: float,
                        sl: float = 0, tp: float = 0, comment: str = "") -> OrderResult:
        await asyncio.sleep(random.uniform(0.01, 0.05))  # Simula latência
        
        # Simula slippage
        slippage = random.uniform(0, 0.0002)
        price = 1.10000 + (slippage if direction == 1 else -slippage)
        
        ticket = self.next_ticket
        self.next_ticket += 1
        
        self.positions[symbol] = Position(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            volume=volume,
            open_price=price,
            current_price=price,
            pnl=0,
            sl=sl,
            tp=tp,
            open_time=int(time.time()),
            comment=comment
        )
        
        return OrderResult(success=True, ticket=ticket, price=price)
    
    def load_csv(self, symbol: str, csv_path: str):
        """Carrega dados de CSV para replay."""
        import pandas as pd
        df = pd.read_csv(csv_path)
        self._bars_data[symbol] = [
            Bar(
                symbol=symbol,
                time=int(row['time']),
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row.get('volume', 0)
            )
            for _, row in df.iterrows()
        ]
```

---

## 6. Tratamento de Erros

```python
class ConnectorError(Exception):
    """Erro base do Connector."""
    pass

class AuthenticationError(ConnectorError):
    """Falha na autenticação."""
    pass

class ConnectionError(ConnectorError):
    """Falha na conexão."""
    pass

class OrderError(ConnectorError):
    """Falha ao enviar ordem."""
    def __init__(self, message: str, code: int = 0):
        self.code = code
        super().__init__(message)

class RateLimitError(ConnectorError):
    """Rate limit excedido."""
    pass
```

---

*Versão 1.1 - Atualizado em 2026-02-04*
