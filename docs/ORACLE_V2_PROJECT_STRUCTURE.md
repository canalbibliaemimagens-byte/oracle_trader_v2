# 📁 Oracle Trader v2.0 - Estrutura do Projeto

**Versão:** 1.0  
**Data:** 2026-02-04  
**Status:** Planejamento

---

## 📋 Índice

1. [Visão Geral](#1-visão-geral)
2. [Estrutura de Diretórios](#2-estrutura-de-diretórios)
3. [Módulos do Sistema](#3-módulos-do-sistema)
4. [Arquivos de Configuração](#4-arquivos-de-configuração)
5. [Artefatos de Modelo](#5-artefatos-de-modelo)
6. [Migração v1 → v2](#6-migração-v1--v2)

---

## 1. Visão Geral

### 1.1 Arquitetura Atual (v1 - Monolítica)

```
oracle_trader/
├── oracle_trader.py      # 2700 linhas - FAZ TUDO
├── lib/
│   ├── __init__.py
│   ├── constants.py
│   ├── features.py
│   ├── metrics.py
│   ├── models.py
│   ├── session_manager.py
│   ├── supabase_logger.py
│   ├── trading.py          # MT5Trader
│   ├── websocket_client.py
│   ├── websocket_server.py
│   └── ws_commands.py
└── oracle-v7.ipynb         # Notebook de treino
```

**Problemas:**
- `oracle_trader.py` é monolítico (predição + execução + risco misturados)
- Acoplado ao MT5 via `trading.py`
- Preditor não mantém posição virtual isolada
- Difícil testar módulos individualmente

### 1.2 Arquitetura Proposta (v2 - Modular)

```
oracle_v2/
├── core/                   # Núcleo compartilhado
├── connector/              # Interface com broker (cTrader)
├── preditor/               # Cérebro (HMM + PPO)
├── executor/               # Execução de ordens
├── paper/                  # Trading simulado
├── orchestrator/           # Coordenação
├── config/                 # Configurações
├── models/                 # Modelos treinados (.zip)
├── scripts/                # Utilitários
└── training/               # Notebook e utils de treino
```

**Benefícios:**
- Separação clara de responsabilidades
- Preditor isolado (Digital Twin do TradingEnv)
- Testabilidade por módulo
- Fácil troca de broker (só muda Connector)

---

## 2. Estrutura de Diretórios

### 2.1 Árvore Completa

```
oracle_v2/
│
├── 📁 core/                        # Núcleo compartilhado
│   ├── __init__.py
│   ├── constants.py                # Enums, constantes globais
│   ├── models.py                   # Dataclasses compartilhadas
│   ├── features.py                 # Cálculo de features (idêntico ao treino)
│   ├── actions.py                  # Definição das 7 ações
│   └── utils.py                    # Funções utilitárias
│
├── 📁 connector/                   # Interface com Broker
│   ├── __init__.py
│   ├── base.py                     # Interface abstrata
│   ├── ctrader/                    # Implementação cTrader
│   │   ├── __init__.py
│   │   ├── client.py               # cTrader Open API client
│   │   ├── auth.py                 # OAuth2 handler
│   │   └── messages.py             # Protobuf wrappers
│   └── mock/                       # Mock para testes
│       ├── __init__.py
│       └── client.py
│
├── 📁 preditor/                    # Cérebro (HMM + PPO)
│   ├── __init__.py
│   ├── preditor.py                 # Classe principal
│   ├── model_loader.py             # Carrega ZIP, extrai metadata
│   ├── virtual_position.py         # Posição virtual (idêntica ao TradingEnv)
│   ├── buffer.py                   # Buffer FIFO de barras (janela deslizante)
│   └── warmup.py                   # Fast-forward warmup
│
├── 📁 executor/                    # Execução de Ordens
│   ├── __init__.py
│   ├── executor.py                 # Classe principal
│   ├── sync_logic.py               # Critérios de sincronização
│   ├── lot_mapper.py               # Intensidade → Lote real
│   ├── risk_guard.py               # Proteção de risco (DD, margem, spread, circuit breaker)
│   ├── price_converter.py          # ⚠️ Conversão SL/TP USD → preço absoluto
│   └── comment_builder.py          # Monta comentário estruturado
│
├── 📁 paper/                       # Trading Simulado
│   ├── __init__.py
│   ├── paper_trader.py             # Simula execução (TradingEnv)
│   ├── account.py                  # Conta simulada (PaperAccount, PaperTrade)
│   └── stats.py                    # Métricas: Sharpe, Max Drawdown, etc.
│
├── 📁 orchestrator/                # Coordenação
│   ├── __init__.py
│   ├── orchestrator.py             # Classe principal
│   ├── lifecycle.py                # Bootstrap, shutdown, config loading, Twisted bridge setup
│   ├── cli.py                      # Entry point de linha de comando
│   └── health.py                   # Monitoramento de saúde
│
├── 📁 persistence/                 # Persistência
│   ├── __init__.py
│   ├── supabase_client.py          # Cliente Supabase
│   ├── trade_logger.py             # Log de trades
│   ├── local_storage.py            # Cache local e backup offline
│   └── session_manager.py          # Gestão de sessão
│
│   # NOTA: Módulo api/ foi removido do projeto.
│   # Será implementado como serviço externo (Oracle Hub / API Gateway).
│   # Ver: docs/notas/ARCH_PROPOSAL_API_GATEWAY.md
│
├── 📁 config/                      # Configurações
│   ├── default.yaml                # Config padrão
│   ├── executor_symbols.json       # Config por símbolo (lotes, SL, TP)
│   └── credentials.env.example     # Template de credenciais
│
├── 📁 models/                      # Modelos Treinados
│   ├── EURUSD_M15.zip              # Modelo (HMM + PPO + metadata)
│   ├── GBPUSD_M15.zip
│   └── ...
│
├── 📁 scripts/                     # Utilitários
│   ├── sync_models.py              # Baixa modelos do Supabase
│   ├── export_symbol_params.py     # Exporta params do cTrader
│   └── validate_model.py           # Valida estrutura do ZIP
│
├── 📁 training/                    # Treinamento
│   ├── oracle-v8.ipynb             # Notebook principal
│   ├── requirements.txt            # Deps do notebook
│   └── utils/                      # Helpers para notebook
│       ├── data_loader.py
│       └── zip_builder.py
│
├── 📁 tests/                       # Testes
│   ├── __init__.py
│   ├── test_preditor.py
│   ├── test_executor.py
│   ├── test_features.py
│   └── fixtures/                   # Dados de teste
│       ├── sample_bars.csv
│       └── sample_model.zip
│
├── 📄 main.py                      # Entry point
├── 📄 requirements.txt             # Dependências
├── 📄 pyproject.toml               # Configuração do projeto
├── 📄 Dockerfile                   # Container para deploy
├── 📄 docker-compose.yml           # Orquestração local
└── 📄 README.md
```

### 2.2 Descrição dos Diretórios

| Diretório | Responsabilidade | Dependências |
|-----------|------------------|--------------|
| `core/` | Código compartilhado entre todos os módulos | Nenhuma (base) |
| `connector/` | Comunicação com broker (cTrader) | `core/` |
| `preditor/` | Carrega modelos, calcula features, gera sinais | `core/` |
| `executor/` | Recebe sinais, mapeia lotes, envia ordens | `core/`, `connector/` |
| `paper/` | Simula execução para benchmark | `core/`, `preditor/` |
| `orchestrator/` | Coordena módulos, gerencia ciclo de vida | Todos |
| `persistence/` | Supabase, logs, sessões | `core/` |
| `config/` | Arquivos de configuração | - |
| `models/` | Modelos treinados (.zip) | - |
| `scripts/` | Utilitários de linha de comando | Variável |
| `training/` | Notebook e helpers de treino | Independente |
| `tests/` | Testes automatizados | Todos |

---

## 3. Módulos do Sistema

### 3.1 Core (`core/`)

Código compartilhado que não depende de nenhum outro módulo.

```python
# core/constants.py
VERSION = "2.0.0"

class Action(str, Enum):
    WAIT = "WAIT"
    LONG_WEAK = "LONG_WEAK"
    LONG_MODERATE = "LONG_MODERATE"
    LONG_STRONG = "LONG_STRONG"
    SHORT_WEAK = "SHORT_WEAK"
    SHORT_MODERATE = "SHORT_MODERATE"
    SHORT_STRONG = "SHORT_STRONG"

class Direction(int, Enum):
    SHORT = -1
    FLAT = 0
    LONG = 1

# core/actions.py
ACTIONS = {
    0: Action.WAIT,
    1: Action.LONG_WEAK,
    2: Action.LONG_MODERATE,
    3: Action.LONG_STRONG,
    4: Action.SHORT_WEAK,
    5: Action.SHORT_MODERATE,
    6: Action.SHORT_STRONG,
}

def get_direction(action: Action) -> Direction:
    if action.startswith("LONG"):
        return Direction.LONG
    elif action.startswith("SHORT"):
        return Direction.SHORT
    return Direction.FLAT

def get_intensity(action: Action) -> int:
    if action == Action.WAIT:
        return 0
    elif action.endswith("WEAK"):
        return 1
    elif action.endswith("MODERATE"):
        return 2
    elif action.endswith("STRONG"):
        return 3
```

### 3.2 Connector (`connector/`)

Interface abstrata + implementação cTrader.

```python
# connector/base.py
from abc import ABC, abstractmethod

class BaseConnector(ABC):
    @abstractmethod
    async def connect(self) -> bool: ...
    
    @abstractmethod
    async def get_ohlcv(self, symbol: str, timeframe: str, bars: int) -> pd.DataFrame: ...
    
    @abstractmethod
    async def get_account(self) -> AccountInfo: ...
    
    @abstractmethod
    async def get_positions(self) -> List[Position]: ...
    
    @abstractmethod
    async def open_order(self, symbol: str, direction: int, size: float,
                         sl: float, tp: float, comment: str) -> OrderResult: ...
    
    @abstractmethod
    async def close_order(self, ticket: int) -> OrderResult: ...

# connector/ctrader/client.py
class CTraderConnector(BaseConnector):
    def __init__(self, credentials: dict):
        self.credentials = credentials
        self.client = None
    
    async def connect(self) -> bool:
        # OAuth2 + Protobuf connection
        ...
```

### 3.3 Preditor (`preditor/`)

Cérebro isolado que mantém posição virtual.

```python
# preditor/preditor.py
class Preditor:
    def __init__(self):
        self.models: Dict[str, LoadedModel] = {}
        self.virtual_positions: Dict[str, VirtualPosition] = {}
        self.bar_buffers: Dict[str, deque] = {}  # FIFO 350 barras
    
    def load_model(self, zip_path: str) -> bool:
        """Carrega modelo do ZIP, extrai metadata do zip.comment"""
        ...
    
    def process_bar(self, symbol: str, bar: dict) -> Signal:
        """
        1. Atualiza buffer FIFO
        2. Calcula features HMM
        3. Prediz estado HMM
        4. Calcula features RL (com posição virtual)
        5. Prediz ação PPO
        6. Atualiza posição virtual
        7. Retorna Signal
        """
        ...
    
    def _update_virtual_position(self, symbol: str, action: Action):
        """Lógica IDÊNTICA ao TradingEnv._execute_action()"""
        vp = self.virtual_positions[symbol]
        target_dir = get_direction(action)
        target_intensity = get_intensity(action)
        
        # Mesmo tamanho e direção → mantém
        if target_dir == vp.direction and target_intensity == vp.intensity:
            return
        
        # Qualquer mudança → fecha + abre
        if vp.direction != Direction.FLAT:
            self._close_virtual(symbol)
        
        if target_dir != Direction.FLAT:
            self._open_virtual(symbol, target_dir, target_intensity)

# preditor/signal.py
@dataclass
class Signal:
    symbol: str
    action: Action          # WAIT, LONG_WEAK, etc.
    direction: Direction    # -1, 0, 1
    intensity: int          # 0, 1, 2, 3
    hmm_state: int
    virtual_pnl: float
    timestamp: float
```

### 3.4 Executor (`executor/`)

Recebe sinais, aplica regras de sincronização, executa.

```python
# executor/executor.py
class Executor:
    def __init__(self, connector: BaseConnector, config_path: str):
        self.connector = connector
        self.symbol_configs: Dict[str, SymbolConfig] = {}
        self.load_config(config_path)
    
    async def process_signal(self, signal: Signal) -> ACK:
        """
        1. Verifica se símbolo está enabled
        2. Aplica critérios de sincronização
        3. Mapeia intensidade → lote
        4. Valida margem
        5. Executa ordem
        6. Retorna ACK
        """
        config = self.symbol_configs.get(signal.symbol)
        if not config or not config.enabled:
            return ACK(signal.symbol, signal.action, "SKIP", "DISABLED")
        
        # Sincronização
        real_pos = await self.connector.get_position(signal.symbol)
        decision = self._sync_decision(signal, real_pos)
        
        if decision == "NOOP":
            return ACK(signal.symbol, signal.action, "OK", "SYNCED")
        
        # ... executa ordem
    
    def _map_lot(self, symbol: str, intensity: int) -> float:
        """Mapeia intensidade para lote real"""
        config = self.symbol_configs[symbol]
        if intensity == 1:
            return config.lot_weak
        elif intensity == 2:
            return config.lot_moderate
        elif intensity == 3:
            return config.lot_strong
        return 0.0

# executor/sync_logic.py
def sync_decision(signal: Signal, real_position: Position) -> str:
    """
    | Real      | Sinal     | Decisão          |
    |-----------|-----------|------------------|
    | Igual     | Igual     | NOOP (mantém)    |
    | Aberta    | Diferente | CLOSE_IMMEDIATE  |
    | FLAT      | Posição   | WAIT_SYNC        |
    """
    ...
```

### 3.5 Paper (`paper/`)

Executa em paralelo para comparar com real.

```python
# paper/paper_trader.py
class PaperTrader:
    """Simula execução idêntica ao TradingEnv do treino"""
    
    def __init__(self, training_config: dict):
        self.spread_points = training_config['spread_points']
        self.slippage_points = training_config['slippage_points']
        self.commission_per_lot = training_config['commission_per_lot']
        self.positions: Dict[str, PaperPosition] = {}
        self.trades: List[PaperTrade] = []
    
    def process_signal(self, signal: Signal, current_bar: dict) -> PaperTrade:
        """Executa em ambiente simulado"""
        ...
```

### 3.6 Orchestrator (`orchestrator/`)

Coordena todos os módulos.

```python
# orchestrator/orchestrator.py
class Orchestrator:
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.connector = CTraderConnector(self.config['credentials'])
        self.preditor = Preditor()
        self.executor = Executor(self.connector, self.config['executor_config'])
        self.paper = PaperTrader(self.config['training_config'])
        self.running = False
    
    async def start(self):
        """
        1. Conecta ao broker
        2. Carrega modelos
        3. Baixa histórico e faz warmup
        4. Inicia loop principal
        """
        await self.connector.connect()
        
        for model_path in self._discover_models():
            self.preditor.load_model(model_path)
            # Warmup
            df = await self.connector.get_ohlcv(symbol, timeframe, 1000)
            self.preditor.warmup(symbol, df)
        
        self.running = True
        await self._main_loop()
    
    async def _main_loop(self):
        """Ciclo: detecta nova barra → prediz → executa"""
        while self.running:
            # Detecta nova barra (polling ou callback)
            for symbol in self.preditor.list_models():
                bar = await self._get_new_bar(symbol)
                if bar:
                    signal = self.preditor.process_bar(symbol, bar)
                    
                    # Executor (real)
                    ack = await self.executor.process_signal(signal)
                    
                    # Paper (paralelo)
                    self.paper.process_signal(signal, bar)
            
            await asyncio.sleep(0.5)
```

---

## 4. Arquivos de Configuração

### 4.1 Config Principal (`config/default.yaml`)

```yaml
# Oracle Trader v2.0 - Configuração Principal

version: "2.0"

# Conexão com Broker
broker:
  type: "ctrader"
  credentials_file: "credentials.env"
  reconnect_delay: 5
  max_retries: 10

# Preditor
preditor:
  models_dir: "./models"
  warmup_bars: 1000
  stabilization_bars: 350
  buffer_size: 350

# Executor
executor:
  config_file: "./config/executor_symbols.json"
  default_sl_usd: 10.0
  default_tp_usd: 0
  sync_mode: "lazy"  # lazy | immediate

# Paper Trading
paper:
  enabled: true
  use_training_costs: true

# Persistência
persistence:
  supabase_enabled: true
  log_trades: true
  log_cycles: true
  cycle_log_interval: 10

# API (Dashboard)
api:
  websocket_enabled: true
  host: "127.0.0.1"
  port: 8765

# Logs
logging:
  level: "INFO"
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
```

### 4.2 Config de Símbolos (`config/executor_symbols.json`)

```json
{
  "_comment": "Configuração de execução por símbolo",
  "_format_version": "2.0",
  
  "EURUSD": {
    "enabled": true,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 10.0,
    "tp_usd": 0,
    "notes": "Forex padrão"
  },
  
  "US500.cash": {
    "enabled": true,
    "lot_weak": 0.10,
    "lot_moderate": 0.30,
    "lot_strong": 0.50,
    "sl_usd": 50.0,
    "tp_usd": 0,
    "notes": "Índice - lotes 10x"
  },
  
  "XAUUSD": {
    "enabled": false,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 15.0,
    "tp_usd": 0,
    "notes": "Desabilitado - aguardando ajuste"
  }
}
```

### 4.3 Credenciais (`config/credentials.env.example`)

```bash
# cTrader Open API
CTRADER_CLIENT_ID=your_client_id
CTRADER_CLIENT_SECRET=your_client_secret
CTRADER_ACCESS_TOKEN=your_access_token
CTRADER_REFRESH_TOKEN=your_refresh_token
CTRADER_ACCOUNT_ID=your_account_id

# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your_anon_key
```

---

## 5. Artefatos de Modelo

### 5.1 Estrutura do ZIP

```
EURUSD_M15.zip
├── EURUSD_M15_hmm.pkl          # Modelo HMM serializado
└── EURUSD_M15_ppo.zip          # Modelo PPO (stable-baselines3)
```

### 5.2 Metadata no `zip.comment`

```json
{
  "format_version": "2.0",
  "generated_at": "2026-02-03T10:30:00Z",
  
  "symbol": {
    "name": "EURUSD",
    "clean": "EURUSD",
    "timeframe": "M15"
  },
  
  "training_config": {
    "point": 0.00001,
    "pip_value": 10.0,
    "spread_points": 7,
    "slippage_points": 2,
    "commission_per_lot": 7.0,
    "digits": 5,
    "initial_balance": 10000,
    "lot_sizes": [0, 0.01, 0.03, 0.05],
    "total_timesteps": 2000000
  },
  
  "hmm_config": {
    "n_states": 5,
    "momentum_period": 12,
    "consistency_period": 12,
    "range_period": 20
  },
  
  "rl_config": {
    "roc_period": 10,
    "atr_period": 14,
    "ema_period": 200,
    "range_period": 20,
    "volume_ma_period": 20
  },
  
  "actions": {
    "0": {"name": "WAIT", "direction": 0, "intensity": 0},
    "1": {"name": "LONG_WEAK", "direction": 1, "intensity": 1},
    "2": {"name": "LONG_MODERATE", "direction": 1, "intensity": 2},
    "3": {"name": "LONG_STRONG", "direction": 1, "intensity": 3},
    "4": {"name": "SHORT_WEAK", "direction": -1, "intensity": 1},
    "5": {"name": "SHORT_MODERATE", "direction": -1, "intensity": 2},
    "6": {"name": "SHORT_STRONG", "direction": -1, "intensity": 3}
  },
  
  "backtest_oos": {
    "total_trades": 234,
    "win_rate": 0.543,
    "profit_factor": 1.45,
    "sharpe_ratio": 1.23
  },
  
  "hmm_state_analysis": {
    "bull_states": [0, 2],
    "bear_states": [1, 4],
    "range_states": [3]
  },
  
  "data_info": {
    "total_bars": 50000,
    "train_bars": 35000,
    "date_start": "2024-01-01",
    "date_end": "2026-01-31"
  }
}
```

---

## 6. Migração v1 → v2

### 6.1 Mapeamento de Arquivos

| v1 (Atual) | v2 (Novo) | Ação |
|------------|-----------|------|
| `oracle_trader.py` | `orchestrator/orchestrator.py` | Refatorar (extrair módulos) |
| `lib/constants.py` | `core/constants.py` + `core/actions.py` | Expandir |
| `lib/features.py` | `core/features.py` | Manter (já está correto) |
| `lib/models.py` | `core/models.py` | Simplificar |
| `lib/trading.py` (MT5) | `connector/ctrader/` | Reescrever |
| `lib/websocket_server.py` | ~~`api/`~~ → Futuro: Oracle Hub (serviço externo) | Postergado |
| `lib/websocket_client.py` | Remover (era para WS público) | Avaliar necessidade |
| `lib/ws_commands.py` | ~~`api/`~~ → Futuro: Oracle Hub (serviço externo) | Postergado |
| `lib/supabase_logger.py` | `persistence/supabase_client.py` | Refatorar |
| `lib/session_manager.py` | `persistence/session_manager.py` | Mover |
| `lib/metrics.py` | `persistence/trade_logger.py` | Mover |
| `oracle-v7.ipynb` | `training/oracle-v8.ipynb` | Atualizar |
| `symbols_config.json` | `config/executor_symbols.json` | Renomear campos |
| `oracle_config.json` | `config/default.yaml` | Migrar para YAML |

### 6.2 Novos Módulos (Criar do Zero)

| Módulo | Arquivo | Prioridade |
|--------|---------|------------|
| Preditor | `preditor/preditor.py` | Alta |
| VirtualPosition | `preditor/virtual_position.py` | Alta |
| ModelLoader | `preditor/model_loader.py` | Alta |
| Executor | `executor/executor.py` | Alta |
| SyncLogic | `executor/sync_logic.py` | Alta |
| LotMapper | `executor/lot_mapper.py` | Média |
| CTraderConnector | `connector/ctrader/client.py` | Alta |
| PaperTrader | `paper/paper_trader.py` | Média |
| Warmup | `preditor/warmup.py` | Média |

### 6.3 Ordem de Implementação

```
Fase 1: Core + Preditor (pode testar isolado)
  1. core/constants.py
  2. core/actions.py
  3. core/features.py (copiar de v1)
  4. core/models.py
  5. preditor/model_loader.py
  6. preditor/virtual_position.py
  7. preditor/preditor.py
  8. preditor/warmup.py

Fase 2: Connector (abstração + mock para testes)
  1. connector/base.py
  2. connector/mock/client.py
  3. connector/ctrader/client.py
  4. connector/ctrader/auth.py

Fase 3: Executor
  1. executor/sync_logic.py
  2. executor/lot_mapper.py
  3. executor/executor.py
  4. executor/comment_builder.py

Fase 4: Integração
  1. orchestrator/orchestrator.py
  2. orchestrator/lifecycle.py
  3. orchestrator/cli.py
  4. persistence/* (migrar de v1)
  # NOTA: api/ removido — será serviço externo (Oracle Hub)

Fase 5: Paper + Testes
  1. paper/paper_trader.py
  2. tests/*
```

---

## 7. Dependências

### 7.1 requirements.txt (Runtime)

```
# Core
numpy>=1.24.0
pandas>=2.0.0
pyyaml>=6.0

# ML
torch>=2.0.0
stable-baselines3>=2.1.0
hmmlearn>=0.3.0

# Async
asyncio
aiohttp>=3.8.0
websockets>=12.0

# cTrader
# (biblioteca específica - a definir)

# Persistence
supabase>=2.0.0

# Utils
python-dotenv>=1.0.0
```

### 7.2 requirements.txt (Training - Notebook)

```
# Tudo do runtime +
gymnasium>=0.29.0
matplotlib>=3.7.0
scikit-learn>=1.3.0
```

---

*Documento gerado em: 2026-02-04*
