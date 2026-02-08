# Oracle Trader v2.0 - Plano de Implementação

**Objetivo:** Construir um sistema de trading modular e de alta disponibilidade para cTrader, garantindo paridade exata de features com o ambiente de treinamento.

**Princípio Guia:** Cada fase deve terminar com código **testável e funcionando isoladamente** antes de avançar.

---

## Visão Geral das Fases

```
┌─────────────────────────────────────────────────────────────────┐
│  FASE 1: Core          ← Fundação (sem dependências externas)   │
├─────────────────────────────────────────────────────────────────┤
│  FASE 2: Preditor      ← Cérebro (depende só do Core)           │
├─────────────────────────────────────────────────────────────────┤
│  FASE 3: Connector     ← Olhos (depende só do Core)             │
├─────────────────────────────────────────────────────────────────┤
│  FASE 4: Executor      ← Mãos (depende de Core + Connector)     │
├─────────────────────────────────────────────────────────────────┤
│  FASE 5: Persistence   ← Memória (depende de Core)              │
│          + Paper       ← Benchmark (depende de Core + Preditor) │
├─────────────────────────────────────────────────────────────────┤
│  FASE 6: Orchestrator  ← Cola tudo + CLI                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Fase 1: Core & Fundação (A "Verdade")

**Meta:** Implementar o núcleo matemático e verificá-lo contra a referência V1.  
**Dependências:** Nenhuma (apenas numpy, pandas).  
**Estimativa:** 1-2 dias  
**Risco:** BAIXO (código puro, sem I/O)

### 1.1 Setup do Projeto

```bash
oracle_v2/
├── pyproject.toml          # Poetry config
├── .env.example            # Template de variáveis
├── config/
│   ├── default.yaml
│   └── executor_symbols.json
├── oracle_v2/
│   ├── __init__.py
│   ├── core/
│   ├── preditor/
│   ├── connector/
│   ├── executor/
│   ├── paper/
│   ├── persistence/
│   └── orchestrator/
├── tests/
│   ├── fixtures/           # Dados de teste
│   └── reference/          # features_v1_reference.py
└── models/                  # ZIPs dos modelos treinados
```

- [ ] Inicializar projeto com `poetry init`
- [ ] Configurar dependências base:
  ```toml
  [tool.poetry.dependencies]
  python = "^3.10"
  numpy = "^1.24"
  pandas = "^2.0"
  pydantic = "^2.0"
  pyyaml = "^6.0"
  ```
- [ ] Configurar dependências de ML (grupo separado):
  ```toml
  [tool.poetry.group.ml.dependencies]
  hmmlearn = "^0.3"
  stable-baselines3 = "^2.1"
  torch = "^2.0"
  ```
- [ ] Configurar pytest e coverage
- [ ] Criar `.gitignore` e `.env.example`

### 1.2 Módulo Core

| Arquivo | Responsabilidade | LOC Est. |
|---------|------------------|----------|
| `constants.py` | Enums, constantes globais | ~80 |
| `models.py` | DTOs (Bar, Signal, Position, etc.) | ~150 |
| `actions.py` | Mapeamento de ações PPO | ~60 |
| `features.py` | **CRÍTICO** - Cálculo de features | ~120 |
| `utils.py` | Funções auxiliares puras | ~50 |

- [ ] `core/constants.py`
  - [ ] Enum `Direction` (-1, 0, 1)
  - [ ] Enum `Timeframe` (M1, M5, M15, M30, H1, H4, D1)
  - [ ] Dict `TIMEFRAME_SECONDS`
  - [ ] Constante `TRAINING_LOT_SIZES = [0, 0.01, 0.03, 0.05]`
  - [ ] Constante `MIN_BARS_FOR_PREDICTION = 350`

- [ ] `core/models.py`
  - [ ] `Bar` (frozen dataclass)
  - [ ] `Signal` (com propriedades `is_entry`, `is_exit`)
  - [ ] `AccountInfo`
  - [ ] `Position`
  - [ ] `OrderResult`
  - [ ] `VirtualPosition`

- [ ] `core/actions.py`
  - [ ] Enum `Action` (7 ações)
  - [ ] Dict `ACTIONS_MAP` (índice → Action)
  - [ ] Função `action_from_index(idx) → Action`
  - [ ] Função `get_direction(action) → Direction`
  - [ ] Função `get_intensity(action) → int`

- [ ] `core/features.py` ⚠️ **CRÍTICO**
  - [ ] Classe `FeatureCalculator`
  - [ ] Método `calc_hmm_features(df) → ndarray(1,3)`
  - [ ] Método `calc_rl_features(df, hmm_state, position) → ndarray(1, 6+N+3)`
  - [ ] Função auxiliar `calc_atr(df, period) → float`

- [ ] `core/utils.py`
  - [ ] `bars_to_dataframe(List[Bar]) → DataFrame`
  - [ ] `round_lot(volume, step) → float`
  - [ ] `pips_to_price(pips, point, digits) → float`

### 1.3 Verificação: Paridade de Features

**GATE DE QUALIDADE - NÃO AVANÇAR SEM PASSAR**

- [ ] Copiar `features_v1_reference.py` para `tests/reference/`
- [ ] Criar `tests/fixtures/sample_ohlcv.csv` (300 barras reais)
- [ ] Criar `tests/test_features_parity.py`:
  ```python
  def test_hmm_features_parity():
      """HMM features V2 == V1 (tolerância 1e-6)"""
      
  def test_rl_features_parity():
      """RL features V2 == V1 (tolerância 1e-6)"""
      
  def test_rl_features_with_position():
      """Features com posição aberta"""
      
  def test_features_edge_cases():
      """NaN handling, volume zero, etc."""
  ```
- [ ] **Critério:** `pytest tests/test_features_parity.py` passa com 100%

### Entregável Fase 1
```bash
$ pytest tests/ -v
tests/test_features_parity.py::test_hmm_features_parity PASSED
tests/test_features_parity.py::test_rl_features_parity PASSED
tests/test_features_parity.py::test_rl_features_with_position PASSED
tests/test_features_parity.py::test_features_edge_cases PASSED
```

---

## Fase 2: Preditor (O "Cérebro")

**Meta:** Carregar modelos e gerar sinais em isolamento ("Digital Twin").  
**Dependências:** Core, hmmlearn, stable-baselines3  
**Estimativa:** 2-3 dias  
**Risco:** MÉDIO (integração com libs de ML)

### 2.1 Módulo Preditor

| Arquivo | Responsabilidade | LOC Est. |
|---------|------------------|----------|
| `model_loader.py` | Descompacta ZIP, lê metadata | ~100 |
| `buffer.py` | Janela FIFO de barras | ~50 |
| `virtual_position.py` | Posição simulada (igual TradingEnv) | ~80 |
| `warmup.py` | Fast-forward inicial | ~40 |
| `preditor.py` | Engine principal | ~150 |

- [ ] `preditor/model_loader.py`
  - [ ] Função `load_model(zip_path) → ModelBundle`
  - [ ] Ler metadata de `zipfile.ZipFile.comment`
  - [ ] Extrair `{symbol}_{tf}_hmm.pkl`
  - [ ] Extrair `{symbol}_{tf}_ppo.zip`
  - [ ] Validar versão do formato

- [ ] `preditor/buffer.py`
  - [ ] Classe `BarBuffer(maxlen=350)`
  - [ ] Método `append(bar)`
  - [ ] Método `to_dataframe() → DataFrame`
  - [ ] Propriedade `is_ready → bool`

- [ ] `preditor/virtual_position.py`
  - [ ] Classe `VirtualPositionManager`
  - [ ] Método `update(action, current_price) → float` (retorna PnL)
  - [ ] Lógica **idêntica** ao `TradingEnv._execute_action`
  - [ ] Propriedade `as_features → tuple` (dir, intensity, pnl_normalized)

- [ ] `preditor/warmup.py`
  - [ ] Função `warmup_model(preditor, bars: List[Bar])`
  - [ ] Fast-forward sem emitir sinais

- [ ] `preditor/preditor.py`
  - [ ] Classe `Preditor`
  - [ ] Método `load_model(zip_path)`
  - [ ] Método `process_bar(symbol, bar) → Signal | None`
  - [ ] Método `warmup(symbol, bars)`
  - [ ] Método `list_models() → List[str]`
  - [ ] Gerenciamento de múltiplos símbolos

### 2.2 Verificação

- [ ] Criar `tests/fixtures/EURUSD_M15.zip` (modelo de teste)
- [ ] Criar `tests/test_preditor.py`:
  ```python
  def test_load_model():
      """Carrega ZIP e extrai metadata"""
      
  def test_warmup():
      """Warmup com 350 barras"""
      
  def test_signal_generation():
      """Gera sinais após warmup"""
      
  def test_virtual_position_tracking():
      """Virtual position atualiza corretamente"""
  ```

### Entregável Fase 2
```bash
$ python -c "
from oracle_v2.preditor import Preditor
p = Preditor()
p.load_model('models/EURUSD_M15.zip')
print(p.list_models())  # ['EURUSD']
"
```

---

## Fase 3: Connector (Os "Olhos")

**Meta:** Abstrair comunicação com broker.  
**Dependências:** Core, asyncio, aiohttp  
**Estimativa:** 3-4 dias  
**Risco:** ALTO (API externa, OAuth2, rate limits)

### 3.1 Interface Base

- [ ] `connector/base.py`
  - [ ] Classe abstrata `BaseConnector`
  - [ ] Métodos: `connect`, `disconnect`, `get_account`, `get_positions`
  - [ ] Métodos: `get_history`, `subscribe_bars`, `open_order`, `close_order`

### 3.2 Mock Connector (para testes)

- [ ] `connector/mock/client.py`
  - [ ] Classe `MockConnector(BaseConnector)`
  - [ ] Gera barras sintéticas
  - [ ] Simula execução instantânea
  - [ ] Útil para testes de integração

### 3.3 cTrader Connector

- [ ] `connector/ctrader/auth.py`
  - [ ] Classe `OAuth2Manager`
  - [ ] Token refresh automático
  - [ ] Persistência de tokens

- [ ] `connector/ctrader/rate_limiter.py`
  - [ ] Classe `RateLimiter` (leaky bucket)
  - [ ] 50 req/s trading, 5 req/s histórico

- [ ] `connector/ctrader/bar_detector.py`
  - [ ] Classe `BarDetector`
  - [ ] Detecta fechamento de barra via ticks
  - [ ] Callback `on_bar_close`

- [ ] `connector/ctrader/client.py`
  - [ ] Classe `CTraderConnector(BaseConnector)`
  - [ ] Implementa todos os métodos da interface
  - [ ] Reconexão automática

### 3.4 Verificação

- [ ] Criar `tests/test_connector_mock.py`
- [ ] Criar `tests/test_connector_ctrader.py` (requer conta demo)
- [ ] Testar OAuth2 flow completo
- [ ] Testar recebimento de barras em tempo real

### Entregável Fase 3
```bash
$ python -c "
from oracle_v2.connector.ctrader import CTraderConnector
c = CTraderConnector(config)
await c.connect()
print(await c.get_account())  # AccountInfo(balance=10000, ...)
"
```

---

## Fase 4: Executor (As "Mãos")

**Meta:** Traduzir sinais em ordens seguras.  
**Dependências:** Core, Connector  
**Estimativa:** 2-3 dias  
**Risco:** MÉDIO (lógica de negócio crítica)

### 4.1 Config

- [ ] `config/loader.py`
  - [ ] Função `load_yaml_config(path) → dict`
  - [ ] Função `load_json_config(path) → dict`
  - [ ] Expansão de variáveis de ambiente `${VAR}`

- [ ] `config/validator.py`
  - [ ] Validação com Pydantic
  - [ ] Erros claros para config inválida

### 4.2 Módulo Executor

| Arquivo | Responsabilidade | LOC Est. |
|---------|------------------|----------|
| `sync_logic.py` | State machine de sincronização | ~100 |
| `risk_guard.py` | Validações de risco | ~80 |
| `lot_mapper.py` | Intensidade → lotes | ~40 |
| `comment_builder.py` | Trilha de auditoria | ~30 |
| `executor.py` | Engine principal | ~150 |

- [ ] `executor/sync_logic.py`
  - [ ] Enum `SyncDecision` (NOOP, OPEN, CLOSE, WAIT_SYNC)
  - [ ] Função `decide(real_position, signal) → SyncDecision`
  - [ ] **Regra de Borda:** Nunca abre se perdeu a barra de entrada

- [ ] `executor/risk_guard.py`
  - [ ] Classe `RiskGuard`
  - [ ] Check: Drawdown limit
  - [ ] Check: Margin disponível
  - [ ] Check: Spread máximo
  - [ ] Check: Circuit breaker (losses consecutivos)

- [ ] `executor/lot_mapper.py`
  - [ ] Função `map_intensity_to_lots(symbol, intensity, config) → float`
  - [ ] Lê de `executor_symbols.json`

- [ ] `executor/comment_builder.py`
  - [ ] Função `build_comment(version, hmm, action, intensity, balance, dd, vpnl) → str`
  - [ ] Formato: `O|2.0|3|1|1|10234|0.5|0.00` (≤32 chars)

- [ ] `executor/executor.py`
  - [ ] Classe `Executor`
  - [ ] Método `process_signal(signal) → ExecutionAck`
  - [ ] Método `close_all()`
  - [ ] Integração com RiskGuard

### 4.3 Verificação

- [ ] Criar `tests/test_sync_logic.py` (todas as combinações)
- [ ] Criar `tests/test_risk_guard.py`
- [ ] Criar `tests/test_executor.py` (com MockConnector)

### Entregável Fase 4
```bash
$ pytest tests/test_sync_logic.py -v
# Todas as 9 combinações de estado testadas
```

---

## Fase 5: Persistence & Paper

**Meta:** Salvar dados e medir drift de performance.  
**Dependências:** Core, Supabase  
**Estimativa:** 2 dias  
**Risco:** BAIXO

### 5.1 Persistence

- [ ] `persistence/supabase_client.py`
  - [ ] Cliente async com retry queue
  - [ ] Métodos: `log_trade`, `log_event`, `log_session`

- [ ] `persistence/session_manager.py`
  - [ ] Heartbeat periódico
  - [ ] Detecção de crash/recovery
  - [ ] Detecção de virada de dia

- [ ] `persistence/local_storage.py`
  - [ ] Backup offline quando Supabase falha
  - [ ] Retry automático

### 5.2 Paper Trader

- [ ] `paper/account.py`
  - [ ] Classe `PaperAccount`
  - [ ] Spread/slippage/comissão do treino

- [ ] `paper/paper_trader.py`
  - [ ] Classe `PaperTrader`
  - [ ] Método `process_signal(signal, bar) → PaperTrade | None`
  - [ ] Método `compare_with_real(real_trades) → DriftReport`

### Entregável Fase 5
```bash
# Drift report mostrando Paper vs Real
$ python -m oracle_v2.paper.report
Paper PnL: $1,234.56
Real PnL:  $1,198.23
Drift:     $36.33 (2.9%)
```

---

## Fase 6: Orchestrator & Lançamento

**Meta:** Unir tudo em um sistema robusto.  
**Dependências:** Todos os módulos  
**Estimativa:** 2-3 dias  
**Risco:** MÉDIO (integração)

### 6.1 Orchestrator

- [ ] `orchestrator/lifecycle.py`
  - [ ] Sequência de startup (ordem importa!)
  - [ ] Sequência de shutdown gracioso

- [ ] `orchestrator/health.py`
  - [ ] Classe `HealthMonitor`
  - [ ] Heartbeats por símbolo
  - [ ] Alertas de memória/CPU

- [ ] `orchestrator/orchestrator.py`
  - [ ] Classe `Orchestrator`
  - [ ] Main loop assíncrono
  - [ ] Signal handlers (SIGINT, SIGTERM)

- [ ] `orchestrator/cli.py`
  - [ ] Entry point `python -m oracle_v2`
  - [ ] Args: `--config`, `--log-level`, `--dry-run`

### 6.2 Testes de Integração

- [ ] `tests/integration/test_full_mock.py`
  - [ ] Sistema completo com MockConnector
  - [ ] 100 barras simuladas
  - [ ] Verifica trades executados

- [ ] `tests/integration/test_full_demo.py`
  - [ ] Sistema completo com conta cTrader Demo
  - [ ] 10 minutos de operação real
  - [ ] Verifica logs no Supabase

### Entregável Fase 6
```bash
$ python -m oracle_v2 --config config/demo.yaml
============================================================
  ORACLE TRADER v2.0
============================================================
✓ Config carregada
✓ Persistence inicializado
✓ Preditor inicializado (3 modelos)
✓ Executor inicializado
✓ Paper Trader inicializado
✓ Connector conectado (cTrader Demo)
✓ Estado sincronizado
✓ Warmup concluído
✓ Sessão iniciada: a1b2c3d4
============================================================
  Sistema PRONTO
============================================================
[14:35:01] [EURUSD] LONG_MODERATE | HMM:3 | VPnL:$0.00 | Exec:OK
[14:35:01] [GBPUSD] WAIT | HMM:1 | VPnL:$12.50 | Exec:NOOP
...
```

---

## Cronograma Sugerido

| Fase | Duração | Acumulado |
|------|---------|-----------|
| 1. Core | 1-2 dias | 2 dias |
| 2. Preditor | 2-3 dias | 5 dias |
| 3. Connector | 3-4 dias | 9 dias |
| 4. Executor | 2-3 dias | 12 dias |
| 5. Persistence + Paper | 2 dias | 14 dias |
| 6. Orchestrator | 2-3 dias | 17 dias |

**Total estimado:** 2-3 semanas

---

## Checklist de Qualidade por Fase

Antes de avançar para próxima fase:

- [ ] Todos os testes passando (`pytest`)
- [ ] Cobertura mínima de 80% (`pytest --cov`)
- [ ] Sem warnings de tipo (`mypy`)
- [ ] Código formatado (`black`, `isort`)
- [ ] Documentação de funções públicas

---

## Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Feature mismatch | Alta | Crítico | Testes de paridade rigorosos |
| cTrader API instável | Média | Alto | Mock para dev, retry robusto |
| Supabase offline | Baixa | Médio | Local storage + retry queue |
| Modelo não carrega | Média | Alto | Validação de metadata no load |
| Memory leak em produção | Baixa | Alto | Health monitor, limites de buffer |

---

## Próximos Passos Imediatos

1. **AGORA:** Criar estrutura de diretórios e `pyproject.toml`
2. **HOJE:** Implementar `core/constants.py` e `core/models.py`
3. **AMANHÃ:** Implementar `core/features.py` e rodar testes de paridade

Começamos?
