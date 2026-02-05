# 💾 Módulo PERSISTENCE: Especificação Técnica

**Versão:** 1.1  
**Nível:** Infraestrutura de Dados  
**Responsabilidade:** Persistir dados críticos (trades, logs de sistema, estado de sessão) em banco de dados remoto (Supabase) e arquivos locais (logs/cache).

---

## 1. Estrutura de Arquivos

```
oracle_v2/persistence/
├── __init__.py
├── supabase_client.py     # Wrapper Async Supabase
├── trade_logger.py        # Log de Execução
├── session_manager.py     # Estado e Recuperação
└── local_storage.py       # Gestão de arquivos locais
```

---

## 2. Componentes

### 2.1 SupabaseClient (`supabase_client.py`)

Cliente assíncrono para Supabase com resiliência a falhas.

```python
import asyncio
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from collections import deque

logger = logging.getLogger("Persistence.Supabase")

class SupabaseClient:
    """
    Cliente assíncrono para Supabase.
    Implementa fila de retry para resiliência.
    """
    
    def __init__(self, url: str, key: str, enabled: bool = True):
        self.url = url
        self.key = key
        self.enabled = enabled and url and key
        self.client = None
        self._retry_queue: deque = deque(maxlen=1000)
        self._connected = False
        
        if self.enabled:
            self._init_client()
    
    def _init_client(self):
        """Inicializa cliente Supabase."""
        try:
            from supabase import create_client
            self.client = create_client(self.url, self.key)
            self._connected = True
            logger.info("Supabase conectado")
        except Exception as e:
            logger.error(f"Supabase erro: {e}")
            self.enabled = False
    
    async def _execute(self, table: str, data: dict, operation: str = "insert") -> bool:
        """
        Executa operação com retry.
        
        Args:
            table: Nome da tabela
            data: Dados a inserir/atualizar
            operation: "insert" ou "upsert"
            
        Returns:
            True se sucesso
        """
        if not self.enabled or not self.client:
            return False
        
        try:
            if operation == "insert":
                await asyncio.to_thread(
                    lambda: self.client.table(table).insert(data).execute()
                )
            elif operation == "upsert":
                await asyncio.to_thread(
                    lambda: self.client.table(table).upsert(data).execute()
                )
            return True
            
        except Exception as e:
            logger.warning(f"Supabase {operation} falhou ({table}): {e}")
            # Adiciona à fila de retry
            self._retry_queue.append({
                'table': table,
                'data': data,
                'operation': operation,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            return False
    
    async def _query(self, table: str, select: str = "*", 
                     filters: Dict = None, order: str = None,
                     limit: int = None) -> List[dict]:
        """
        Executa query.
        
        Args:
            table: Nome da tabela
            select: Campos a selecionar
            filters: Dicionário de filtros {campo: valor} ou {campo: (operador, valor)}
            order: Campo para ordenação
            limit: Limite de resultados
            
        Returns:
            Lista de registros
        """
        if not self.enabled or not self.client:
            return []
        
        try:
            query = self.client.table(table).select(select)
            
            if filters:
                for key, value in filters.items():
                    if isinstance(value, tuple):
                        op, val = value
                        if op == 'gt':
                            query = query.gt(key, val)
                        elif op == 'gte':
                            query = query.gte(key, val)
                        elif op == 'lt':
                            query = query.lt(key, val)
                        elif op == 'lte':
                            query = query.lte(key, val)
                        elif op == 'eq':
                            query = query.eq(key, val)
                    else:
                        query = query.eq(key, value)
            
            if order:
                desc = order.startswith('-')
                field = order[1:] if desc else order
                query = query.order(field, desc=desc)
            
            if limit:
                query = query.limit(limit)
            
            response = await asyncio.to_thread(lambda: query.execute())
            return response.data or []
            
        except Exception as e:
            logger.error(f"Supabase query erro ({table}): {e}")
            return []
    
    async def log_trade(self, trade_data: dict):
        """Insere trade na tabela 'trades'."""
        data = {
            "session_id": trade_data.get('session_id', ''),
            "trade_id": trade_data.get('id', ''),
            "symbol": trade_data.get('symbol', ''),
            "direction": trade_data.get('direction', 0),
            "intensity": trade_data.get('intensity', 0),
            "action": trade_data.get('action', ''),
            "volume": trade_data.get('volume', 0),
            "entry_price": trade_data.get('entry_price', 0),
            "exit_price": trade_data.get('exit_price', 0),
            "pnl": trade_data.get('pnl', 0),
            "pnl_pips": trade_data.get('pnl_pips', 0),
            "commission": trade_data.get('commission', 0),
            "hmm_state": trade_data.get('hmm_state', 0),
            "is_paper": trade_data.get('is_paper', False),
            "comment": trade_data.get('comment', ''),
            "timestamp": trade_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
        }
        await self._execute("trades", data)
    
    async def log_event(self, event_type: str, data: dict = None, session_id: str = ""):
        """Insere evento na tabela 'events'."""
        record = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "data": json.dumps(data or {}),
        }
        await self._execute("events", record)
    
    async def get_trades(self, session_id: str = None, 
                         is_paper: bool = None,
                         symbol: str = None,
                         limit: int = 100) -> List[dict]:
        """Query trades com filtros."""
        filters = {}
        if session_id:
            filters['session_id'] = session_id
        if is_paper is not None:
            filters['is_paper'] = is_paper
        if symbol:
            filters['symbol'] = symbol
        
        return await self._query(
            "trades", 
            filters=filters, 
            order="-timestamp",
            limit=limit
        )
    
    async def retry_pending(self) -> int:
        """
        Tenta reenviar operações pendentes.
        
        Returns:
            Número de operações bem-sucedidas
        """
        if not self._retry_queue:
            return 0
        
        success = 0
        failed = []
        
        while self._retry_queue:
            item = self._retry_queue.popleft()
            try:
                if item['operation'] == 'insert':
                    await asyncio.to_thread(
                        lambda: self.client.table(item['table']).insert(item['data']).execute()
                    )
                success += 1
            except Exception:
                failed.append(item)
        
        # Re-adiciona os que falharam
        for item in failed:
            self._retry_queue.append(item)
        
        if success > 0:
            logger.info(f"Retry: {success} operações bem-sucedidas, {len(failed)} pendentes")
        
        return success
    
    @property
    def pending_count(self) -> int:
        """Número de operações pendentes."""
        return len(self._retry_queue)
```

### 2.2 TradeLogger (`trade_logger.py`)

Abstração de alto nível para registrar operações.

```python
from typing import Optional
from datetime import datetime, timezone
import uuid

class TradeLogger:
    """
    Logger de alto nível para trades.
    Abstrai diferença entre Real e Paper.
    """
    
    def __init__(self, supabase_client: 'SupabaseClient', session_id: str):
        self.db = supabase_client
        self.session_id = session_id
    
    async def log_trade(
        self,
        symbol: str,
        direction: int,
        intensity: int,
        action: str,
        volume: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_pips: float,
        hmm_state: int,
        commission: float = 0,
        comment: str = "",
        is_paper: bool = False
    ):
        """
        Registra trade (real ou paper).
        
        Args:
            is_paper: True para trade simulado, False para real
        """
        trade_data = {
            'id': str(uuid.uuid4())[:8],
            'session_id': self.session_id,
            'symbol': symbol,
            'direction': direction,
            'intensity': intensity,
            'action': action,
            'volume': volume,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl': round(pnl, 2),
            'pnl_pips': round(pnl_pips, 1),
            'commission': commission,
            'hmm_state': hmm_state,
            'comment': comment,
            'is_paper': is_paper,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
        
        await self.db.log_trade(trade_data)
    
    async def log_real_trade(self, trade_data: dict):
        """Registra trade real (vindo do Executor)."""
        trade_data['is_paper'] = False
        trade_data['session_id'] = self.session_id
        await self.db.log_trade(trade_data)
    
    async def log_paper_trade(self, paper_trade: 'PaperTrade'):
        """Registra trade do Paper Trader."""
        await self.log_trade(
            symbol=paper_trade.symbol,
            direction=paper_trade.direction,
            intensity=paper_trade.intensity,
            action="CLOSE",
            volume=paper_trade.volume,
            entry_price=paper_trade.entry_price,
            exit_price=paper_trade.exit_price,
            pnl=paper_trade.pnl,
            pnl_pips=paper_trade.pnl_pips,
            hmm_state=paper_trade.hmm_state,
            commission=paper_trade.commission,
            is_paper=True
        )
```

### 2.3 SessionManager (`session_manager.py`)

Gerencia o ciclo de vida da sessão e recuperação de crash.

```python
import json
import asyncio
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

class SessionEndReason(Enum):
    """Motivos de encerramento de sessão."""
    NORMAL = "NORMAL"
    EMERGENCY = "EMERGENCY"
    DAY_CHANGE = "DAY_CHANGE"
    RECOVERED = "RECOVERED"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class SessionManager:
    """
    Gerencia estado da sessão com heartbeat e recuperação.
    """
    
    STATE_FILE = ".session_state.json"
    
    def __init__(self, supabase_client: 'SupabaseClient', base_dir: Path = None):
        self.db = supabase_client
        self.base_dir = base_dir or Path.cwd()
        self.state_file = self.base_dir / self.STATE_FILE
        
        self.session_id: str = ""
        self.start_time: Optional[datetime] = None
        self.is_recovered: bool = False
        self.day_start: Optional[datetime] = None
        
        self._running = False
    
    async def start_session(self, initial_balance: float, symbols: list) -> str:
        """
        Inicia ou recupera sessão.
        
        Returns:
            session_id (novo ou recuperado)
        """
        import uuid
        
        # Verifica se há sessão anterior não fechada
        recovered_state = self._load_state()
        
        if recovered_state and recovered_state.get("status") == "RUNNING":
            # Recupera sessão anterior
            self.session_id = recovered_state.get("session_id", "")
            self.is_recovered = True
            
            await self.db.log_event("SESSION_RECOVERED", {
                "old_session_id": self.session_id,
                "recovered_at": datetime.now(timezone.utc).isoformat()
            }, self.session_id)
            
            self._running = True
            return self.session_id
        
        # Nova sessão
        self.session_id = str(uuid.uuid4())[:8]
        self.start_time = datetime.now(timezone.utc)
        self.day_start = self._get_day_start()
        self.is_recovered = False
        
        # Salva estado local
        self._save_state({
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "initial_balance": initial_balance,
            "symbols": symbols,
            "status": "RUNNING"
        })
        
        # Log no Supabase
        await self.db._execute("sessions", {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "initial_balance": initial_balance,
            "symbols": symbols,
            "status": "RUNNING"
        })
        
        self._running = True
        return self.session_id
    
    async def end_session(self, stats: dict, reason: SessionEndReason = SessionEndReason.NORMAL):
        """Encerra sessão com estatísticas."""
        if not self._running:
            return
        
        self._running = False
        
        # Atualiza no Supabase
        update_data = {
            "end_time": datetime.now(timezone.utc).isoformat(),
            "final_balance": stats.get('balance', 0),
            "total_trades": stats.get('total_trades', 0),
            "total_pnl": stats.get('total_pnl', 0),
            "end_reason": reason.value,
            "status": "STOPPED"
        }
        
        try:
            await asyncio.to_thread(
                lambda: self.db.client.table("sessions")
                    .update(update_data)
                    .eq("session_id", self.session_id)
                    .execute()
            )
        except Exception as e:
            pass  # Ignora erro no encerramento
        
        # Remove arquivo de estado
        self._clear_state()
    
    def update_heartbeat(self, balance: float = 0):
        """Atualiza heartbeat (chamar periodicamente)."""
        if not self._running:
            return
        
        state = self._load_state() or {}
        state.update({
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "current_balance": balance,
            "status": "RUNNING"
        })
        self._save_state(state)
    
    def check_day_boundary(self) -> bool:
        """Verifica se virou o dia (UTC)."""
        if not self.day_start:
            self.day_start = self._get_day_start()
            return False
        
        current_day = self._get_day_start()
        if current_day > self.day_start:
            self.day_start = current_day
            return True
        
        return False
    
    def _save_state(self, state: dict):
        """Salva estado em arquivo local."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass
    
    def _load_state(self) -> Optional[dict]:
        """Carrega estado do arquivo local."""
        if not self.state_file.exists():
            return None
        
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _clear_state(self):
        """Remove arquivo de estado."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass
    
    def _get_day_start(self) -> datetime:
        """Retorna início do dia atual (UTC)."""
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
```

### 2.4 LocalStorage (`local_storage.py`)

Gestão de arquivos locais para cache e backup.

```python
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

class LocalStorage:
    """
    Gestão de arquivos locais.
    Usado para backup offline e cache.
    """
    
    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or Path.cwd()
        self.pending_file = self.base_dir / "pending_uploads.json"
        self.cache_dir = self.base_dir / "cache"
        self.cache_dir.mkdir(exist_ok=True)
    
    def save_pending(self, data: List[dict]):
        """Salva dados pendentes de upload."""
        existing = self.load_pending()
        existing.extend(data)
        
        with open(self.pending_file, 'w') as f:
            json.dump(existing, f, indent=2)
    
    def load_pending(self) -> List[dict]:
        """Carrega dados pendentes de upload."""
        if not self.pending_file.exists():
            return []
        
        try:
            with open(self.pending_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []
    
    def clear_pending(self):
        """Limpa dados pendentes após upload bem-sucedido."""
        if self.pending_file.exists():
            self.pending_file.unlink()
    
    def cache_bars(self, symbol: str, bars: List[dict]):
        """Cache de barras OHLCV."""
        cache_file = self.cache_dir / f"{symbol}_bars.json"
        with open(cache_file, 'w') as f:
            json.dump(bars, f)
    
    def load_cached_bars(self, symbol: str) -> List[dict]:
        """Carrega barras do cache."""
        cache_file = self.cache_dir / f"{symbol}_bars.json"
        if not cache_file.exists():
            return []
        
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception:
            return []
```

---

## 3. Schema do Banco (Supabase)

```sql
-- Tabela de sessões
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT UNIQUE NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    initial_balance FLOAT,
    final_balance FLOAT,
    total_trades INT DEFAULT 0,
    total_pnl FLOAT DEFAULT 0,
    symbols TEXT[],
    status TEXT DEFAULT 'RUNNING',
    end_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de trades
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT NOT NULL,
    trade_id TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    direction INT,
    intensity INT,
    action TEXT,
    volume FLOAT,
    entry_price FLOAT,
    exit_price FLOAT,
    pnl FLOAT,
    pnl_pips FLOAT,
    commission FLOAT DEFAULT 0,
    hmm_state INT,
    is_paper BOOLEAN DEFAULT FALSE,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tabela de eventos
CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    data JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_sessions_session_id ON sessions(session_id);
CREATE INDEX idx_trades_session ON trades(session_id);
CREATE INDEX idx_trades_symbol ON trades(symbol);
CREATE INDEX idx_trades_is_paper ON trades(is_paper);
CREATE INDEX idx_trades_timestamp ON trades(timestamp);
CREATE INDEX idx_events_session ON events(session_id);
CREATE INDEX idx_events_type ON events(event_type);
```

---

## 4. Resiliência (Offline Mode)

O sistema de persistência nunca deve bloquear o trading.

```python
# orchestrator.py - Exemplo de uso

class Orchestrator:
    async def _persistence_worker(self):
        """Worker que tenta reenviar dados pendentes."""
        while self.running:
            await asyncio.sleep(60)  # A cada minuto
            
            # Tenta reenviar pendentes do Supabase
            await self.persistence.db.retry_pending()
            
            # Tenta enviar pendentes do arquivo local
            pending = self.local_storage.load_pending()
            if pending:
                success = 0
                for item in pending:
                    if await self.persistence.db._execute(item['table'], item['data']):
                        success += 1
                
                if success == len(pending):
                    self.local_storage.clear_pending()
```

---

*Versão 1.1 - Atualizado em 2026-02-04*
