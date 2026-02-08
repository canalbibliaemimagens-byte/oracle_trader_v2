# 🎼 Módulo ORCHESTRATOR: Especificação Técnica

**Versão:** 1.1  
**Nível:** Coordenação e Infraestrutura  
**Responsabilidade:** Inicialização (bootstrap), gerenciamento do ciclo de vida dos processos, comunicação entre módulos e monitoramento de saúde (Health Check).

---

## 1. Estrutura de Arquivos

```
oracle_v2/orchestrator/
├── __init__.py
├── orchestrator.py    # Classe Principal / Entry Point
├── lifecycle.py       # Startup e Shutdown
├── health.py          # Watchdog e Monitoramento
└── cli.py             # Interface de Linha de Comando
```

---

## 2. Arquitetura

O sistema roda como um **único processo Python assíncrono** (`asyncio`), mas estruturado de forma que os módulos sejam independentes.

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                     Event Loop (asyncio)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│     ┌────────────────────────┼────────────────────────┐         │
│     │                        │                        │         │
│     ▼                        ▼                        ▼         │
│  ┌──────────┐          ┌──────────┐           ┌──────────┐     │
│  │ CONNECTOR│◄────────►│ PREDITOR │◄─────────►│ EXECUTOR │     │
│  │ (cTrader)│  Bars    │ (Cérebro)│  Signals  │  (Mãos)  │     │
│  └──────────┘          └──────────┘           └──────────┘     │
│       │                      │                      │           │
│       │                      ▼                      │           │
│       │                ┌──────────┐                 │           │
│       │                │  PAPER   │◄────────────────┘           │
│       │                │(Simulado)│  (Mesmo Signal)             │
│       │                └──────────┘                             │
│       │                      │                                   │
│       └──────────────────────┼───────────────────────────────►  │
│                              ▼                                   │
│                       ┌──────────┐                              │
│                       │PERSISTENCE│                             │
│                       │(Supabase) │                             │
│                       └──────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Componentes

### 3.1 Orchestrator (`orchestrator.py`)

Classe principal que coordena todos os módulos.

```python
import asyncio
import signal
import logging
from pathlib import Path
from typing import Optional, List

from ..core.models import Bar, Signal
from ..connector.ctrader.client import CTraderConnector
from ..preditor.preditor import Preditor
from ..executor.executor import Executor
from ..paper.paper_trader import PaperTrader
from ..persistence.supabase_client import SupabaseClient
from ..persistence.session_manager import SessionManager, SessionEndReason
from ..persistence.trade_logger import TradeLogger
from .health import HealthMonitor

logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """
    Coordena todos os módulos do sistema.
    Ponto de entrada principal.
    """
    
    def __init__(self, config_path: str = "config/default.yaml"):
        self.config_path = config_path
        self.config = None
        
        # Módulos
        self.connector: Optional[CTraderConnector] = None
        self.preditor: Optional[Preditor] = None
        self.executor: Optional[Executor] = None
        self.paper: Optional[PaperTrader] = None
        self.persistence: Optional[SupabaseClient] = None
        self.session_manager: Optional[SessionManager] = None
        self.trade_logger: Optional[TradeLogger] = None
        self.health: Optional[HealthMonitor] = None
        
        # Estado
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: List[asyncio.Task] = []
    
    async def start(self):
        """
        Inicia o sistema.
        Sequência de bootstrap é crítica.
        """
        logger.info("=" * 60)
        logger.info("  ORACLE TRADER v2.0")
        logger.info("=" * 60)
        
        try:
            # 1. Carrega configuração
            self.config = self._load_config()
            logger.info("✓ Config carregada")
            
            # 2. Inicializa Persistence (primeiro, para logs)
            await self._init_persistence()
            logger.info("✓ Persistence inicializado")
            
            # 3. Inicializa Preditor (carrega modelos, lento)
            await self._init_preditor()
            logger.info(f"✓ Preditor inicializado ({len(self.preditor.list_models())} modelos)")
            
            # 4. Inicializa Executor
            await self._init_executor()
            logger.info("✓ Executor inicializado")
            
            # 5. Inicializa Paper Trader
            await self._init_paper()
            logger.info("✓ Paper Trader inicializado")
            
            # 6. Conecta ao Broker
            await self._init_connector()
            logger.info("✓ Connector conectado")
            
            # 7. Sincroniza estado inicial
            await self._sync_initial_state()
            logger.info("✓ Estado sincronizado")
            
            # 8. Warmup dos modelos
            await self._warmup_models()
            logger.info("✓ Warmup concluído")
            
            # 9. Inicia Session
            session_id = await self.session_manager.start_session(
                initial_balance=self.config.get('initial_balance', 10000),
                symbols=self.preditor.list_models()
            )
            logger.info(f"✓ Sessão iniciada: {session_id}")
            
            # 10. Inicia Health Monitor
            self.health = HealthMonitor(self)
            
            # 11. Inicia tasks
            self.running = True
            await self._start_tasks()
            
            logger.info("=" * 60)
            logger.info("  Sistema PRONTO")
            logger.info("=" * 60)
            
            # Aguarda shutdown
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Erro fatal na inicialização: {e}")
            raise
        
        finally:
            await self.stop()
    
    async def stop(self, reason: SessionEndReason = SessionEndReason.NORMAL):
        """Para o sistema de forma limpa."""
        if not self.running:
            return
        
        logger.info("Encerrando sistema...")
        self.running = False
        
        # 1. Cancela tasks
        for task in self._tasks:
            task.cancel()
        
        # 2. Fecha posições se configurado
        if self.config.get('close_on_exit', False):
            await self.executor.close_all()
            logger.info("✓ Posições fechadas")
        
        # 3. Encerra sessão
        if self.session_manager:
            stats = self._get_session_stats()
            await self.session_manager.end_session(stats, reason)
            logger.info("✓ Sessão encerrada")
        
        # 4. Desconecta broker
        if self.connector:
            await self.connector.disconnect()
            logger.info("✓ Connector desconectado")
        
        logger.info("Sistema encerrado")
    
    async def _start_tasks(self):
        """Inicia todas as tasks assíncronas."""
        self._tasks = [
            asyncio.create_task(self._main_loop()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._health_loop()),
            asyncio.create_task(self._persistence_retry_loop()),
        ]
    
    async def _main_loop(self):
        """
        Loop principal - processa barras e emite sinais.
        """
        symbols = self.preditor.list_models()
        
        # Callback para novas barras
        async def on_bar(bar: Bar):
            if not self.running:
                return
            
            await self._process_bar(bar)
        
        # Assina barras para todos os símbolos
        await self.connector.subscribe_bars(
            symbols=symbols,
            timeframe=self.config.get('timeframe', 'M15'),
            callback=on_bar
        )
        
        # Mantém vivo
        while self.running:
            await asyncio.sleep(1)
    
    async def _process_bar(self, bar: Bar):
        """
        Processa uma nova barra.
        Flow: Bar -> Preditor -> Signal -> Executor + Paper
        """
        symbol = bar.symbol
        
        try:
            # 1. Preditor gera sinal
            signal = self.preditor.process_bar(symbol, bar)
            
            if signal is None:
                return  # Ainda em warmup
            
            # 2. Executor processa (real)
            executor_task = asyncio.create_task(
                self.executor.process_signal(signal)
            )
            
            # 3. Paper processa (simulado) - em paralelo
            paper_trade = self.paper.process_signal(signal, bar)
            
            # 4. Aguarda executor
            ack = await executor_task
            
            # 5. Loga trade do paper se houver
            if paper_trade:
                await self.trade_logger.log_paper_trade(paper_trade)
            
            # 6. Log
            logger.info(
                f"[{symbol}] {signal.action} | "
                f"HMM:{signal.hmm_state} | "
                f"VPnL:${signal.virtual_pnl:.2f} | "
                f"Exec:{ack.status}"
            )
            
            # 7. Health heartbeat
            self.health.update(symbol)
            
        except Exception as e:
            logger.error(f"[{symbol}] Erro processando barra: {e}")
    
    async def _heartbeat_loop(self):
        """Atualiza heartbeat periodicamente."""
        while self.running:
            await asyncio.sleep(60)
            
            if self.session_manager:
                account = await self.connector.get_account()
                self.session_manager.update_heartbeat(account.balance)
                
                # Verifica virada de dia
                if self.session_manager.check_day_boundary():
                    logger.info("Virada de dia detectada")
                    await self._handle_day_change()
    
    async def _health_loop(self):
        """Monitora saúde do sistema."""
        while self.running:
            await asyncio.sleep(30)
            
            if self.health:
                report = self.health.check()
                if not report['healthy']:
                    logger.warning(f"Health check falhou: {report['issues']}")
    
    async def _persistence_retry_loop(self):
        """Tenta reenviar dados pendentes."""
        while self.running:
            await asyncio.sleep(300)  # A cada 5 minutos
            
            if self.persistence:
                await self.persistence.retry_pending()
    
    async def _handle_day_change(self):
        """Trata virada de dia (opcional: fecha posições)."""
        if self.config.get('close_on_day_change', False):
            await self.executor.close_all()
            
            # Encerra sessão atual e inicia nova
            stats = self._get_session_stats()
            await self.session_manager.end_session(stats, SessionEndReason.DAY_CHANGE)
            
            account = await self.connector.get_account()
            await self.session_manager.start_session(
                initial_balance=account.balance,
                symbols=self.preditor.list_models()
            )
    
    # =========================================================================
    # Inicialização dos Módulos
    # =========================================================================
    
    def _load_config(self) -> dict:
        """Carrega configuração YAML."""
        import yaml
        with open(self.config_path) as f:
            return yaml.safe_load(f)
    
    async def _init_persistence(self):
        """Inicializa módulo de persistência."""
        self.persistence = SupabaseClient(
            url=self.config.get('supabase_url', ''),
            key=self.config.get('supabase_key', ''),
            enabled=self.config.get('persistence_enabled', True)
        )
        
        self.session_manager = SessionManager(self.persistence)
        self.trade_logger = TradeLogger(self.persistence, "")
    
    async def _init_preditor(self):
        """Inicializa Preditor e carrega modelos."""
        self.preditor = Preditor()
        
        models_dir = Path(self.config.get('models_dir', './models'))
        for model_file in models_dir.glob("*.zip"):
            self.preditor.load_model(str(model_file))
    
    async def _init_executor(self):
        """Inicializa Executor."""
        self.executor = Executor(
            connector=self.connector,
            config_path=self.config.get('executor_config', 'config/executor_symbols.json')
        )
    
    async def _init_paper(self):
        """Inicializa Paper Trader."""
        self.paper = PaperTrader(
            initial_balance=self.config.get('initial_balance', 10000)
        )
        
        # Carrega configs de treino para cada modelo
        for symbol in self.preditor.list_models():
            model = self.preditor.models[symbol]
            self.paper.load_config(symbol, model.metadata.get('training_config', {}))
    
    async def _init_connector(self):
        """Inicializa e conecta ao broker."""
        from ..connector.ctrader.client import CTraderConnector
        
        self.connector = CTraderConnector(self.config.get('broker', {}))
        
        if not await self.connector.connect():
            raise RuntimeError("Falha ao conectar ao broker")
    
    async def _sync_initial_state(self):
        """Sincroniza estado inicial com broker."""
        # Verifica posições abertas
        positions = await self.connector.get_positions()
        
        for pos in positions:
            symbol = pos.symbol
            if symbol in self.preditor.list_models():
                logger.info(f"[{symbol}] Posição existente: {pos.direction} @ {pos.open_price}")
            else:
                logger.warning(f"[{symbol}] Posição ÓRFÃ detectada (sem modelo)")
    
    async def _warmup_models(self):
        """Warmup de todos os modelos com histórico."""
        for symbol in self.preditor.list_models():
            model = self.preditor.models[symbol]
            timeframe = model.metadata.get('symbol', {}).get('timeframe', 'M15')
            
            # Busca histórico
            bars = await self.connector.get_history(symbol, timeframe, 1000)
            
            # Warmup
            self.preditor.warmup(symbol, bars)
            logger.info(f"[{symbol}] Warmup: {len(bars)} barras")
    
    def _get_session_stats(self) -> dict:
        """Coleta estatísticas da sessão."""
        return {
            'balance': 0,  # TODO: obter do connector
            'total_trades': 0,  # TODO: contar trades
            'total_pnl': 0,
        }
    
    # =========================================================================
    # Signal Handlers
    # =========================================================================
    
    def setup_signal_handlers(self):
        """Configura handlers para sinais do SO."""
        loop = asyncio.get_event_loop()
        
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_signal())
            )
    
    async def _handle_signal(self):
        """Trata sinal de encerramento."""
        logger.info("Sinal de encerramento recebido")
        self._shutdown_event.set()
```

### 3.2 HealthMonitor (`health.py`)

Monitora saúde dos componentes.

```python
import time
from typing import Dict, List
from dataclasses import dataclass, field

@dataclass
class ComponentHealth:
    """Estado de saúde de um componente."""
    name: str
    last_heartbeat: float = 0
    error_count: int = 0
    last_error: str = ""


class HealthMonitor:
    """
    Monitora saúde dos componentes do sistema.
    """
    
    # Tempo máximo sem heartbeat antes de considerar unhealthy
    HEARTBEAT_TIMEOUT = 300  # 5 minutos
    
    def __init__(self, orchestrator: 'Orchestrator'):
        self.orchestrator = orchestrator
        self.components: Dict[str, ComponentHealth] = {}
        self._symbol_heartbeats: Dict[str, float] = {}
    
    def update(self, symbol: str):
        """Atualiza heartbeat de um símbolo."""
        self._symbol_heartbeats[symbol] = time.time()
    
    def check(self) -> dict:
        """
        Verifica saúde do sistema.
        
        Returns:
            Dict com status e issues
        """
        issues = []
        now = time.time()
        
        # Verifica connector
        if not self.orchestrator.connector.is_connected():
            issues.append("Connector desconectado")
        
        # Verifica heartbeats dos símbolos
        for symbol, last_hb in self._symbol_heartbeats.items():
            if now - last_hb > self.HEARTBEAT_TIMEOUT:
                issues.append(f"{symbol}: sem heartbeat há {int(now - last_hb)}s")
        
        # Verifica memória
        import psutil
        memory = psutil.Process().memory_info().rss / 1024 / 1024
        if memory > 1000:  # > 1GB
            issues.append(f"Memória alta: {memory:.0f}MB")
        
        # Verifica pending do persistence
        if self.orchestrator.persistence.pending_count > 100:
            issues.append(f"Persistence: {self.orchestrator.persistence.pending_count} pendentes")
        
        return {
            'healthy': len(issues) == 0,
            'issues': issues,
            'memory_mb': round(memory, 1),
            'uptime': now - self.orchestrator.session_manager.start_time.timestamp() if self.orchestrator.session_manager.start_time else 0
        }
    
    def reset_symbol(self, symbol: str):
        """Reseta estado de um símbolo."""
        if symbol in self._symbol_heartbeats:
            del self._symbol_heartbeats[symbol]
```

### 3.3 CLI (`cli.py`)

Interface de linha de comando.

```python
import argparse
import asyncio
import logging
import sys

def main():
    """Entry point da CLI."""
    parser = argparse.ArgumentParser(description="Oracle Trader v2.0")
    
    parser.add_argument(
        "--config", "-c",
        default="config/default.yaml",
        help="Caminho para arquivo de configuração"
    )
    parser.add_argument(
        "--log-level", "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de log"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo dry-run (não executa ordens reais)"
    )
    
    args = parser.parse_args()
    
    # Configura logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    # Cria e executa orchestrator
    from .orchestrator import Orchestrator
    
    orchestrator = Orchestrator(config_path=args.config)
    orchestrator.setup_signal_handlers()
    
    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

---

## 4. Ordem de Inicialização

A sequência de bootstrap é **crítica**:

```
1. Config          # Carrega YAML
2. Persistence     # Para poder logar erros desde o início
3. Preditor        # Carrega modelos (pode demorar)
4. Executor        # Carrega config de símbolos
5. Paper           # Carrega configs de treino
6. Connector       # Conecta ao broker
7. Sync            # Verifica estado (posições abertas)
8. Warmup          # Alimenta buffers com histórico
9. Session         # Inicia ou recupera sessão
10. Tasks          # Inicia loops assíncronos
```

---

## 5. Ordem de Shutdown

```
1. Stop Tasks      # Cancela loops
2. Close Positions # Opcional, se configurado
3. End Session     # Salva estatísticas
4. Disconnect      # Desconecta broker
5. Flush Logs      # Garante que tudo foi salvo
```

---

## 6. Configuração (`config/default.yaml`)

```yaml
version: "2.0"

# Broker
broker:
  type: "ctrader"
  client_id: "${CT_CLIENT_ID}"
  client_secret: "${CT_CLIENT_SECRET}"
  access_token: "${CT_ACCESS_TOKEN}"
  account_id: "${CT_ACCOUNT_ID}"
  environment: "demo"  # demo | live

# Paths
models_dir: "./models"
executor_config: "./config/executor_symbols.json"

# Trading
timeframe: "M15"
initial_balance: 10000
close_on_exit: false
close_on_day_change: false

# Persistence
persistence_enabled: true
supabase_url: "${SUPABASE_URL}"
supabase_key: "${SUPABASE_KEY}"

# Logging
log_level: "INFO"
log_file: "./logs/oracle.log"
```

---

## 7. Variáveis de Ambiente

```bash
# .env (exemplo)

# cTrader
CT_CLIENT_ID=your_client_id
CT_CLIENT_SECRET=your_client_secret
CT_ACCESS_TOKEN=your_access_token
CT_ACCOUNT_ID=123456

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

## 8. Execução

```bash
# Desenvolvimento
python -m oracle_v2.orchestrator.cli --config config/dev.yaml --log-level DEBUG

# Produção
python -m oracle_v2.orchestrator.cli --config config/prod.yaml

# Dry-run (sem ordens reais)
python -m oracle_v2.orchestrator.cli --dry-run
```

---

*Versão 1.1 - Atualizado em 2026-02-04*
