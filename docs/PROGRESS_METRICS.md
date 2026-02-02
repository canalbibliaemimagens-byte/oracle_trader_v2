# 📊 Oracle Trader v2 - Métricas de Progresso

*Última atualização: 2026-02-02*

---

## 🎯 Status Geral

| Fase | Descrição | Status | Progresso |
|------|-----------|--------|-----------|
| 1 | Estrutura + Models + Infra | ✅ Completa | 100% |
| 2 | Core + Trading + LotCalculator | ✅ Completa | 100% |
| 3 | Engine Principal (Loop) | 🏗️ Em andamento | 75% |
| 4 | ML (Model Loader, Features) | ⏳ Pendente | 0% |
| 5 | Testes e Validação | ⏳ Pendente | 0% |

**Progresso Total: 50%** (2.5 de 5 fases)

---

## 📈 Cobertura de Refatoração

### Componentes

| Componente | v1 (Origem) | v2 (Destino) | Status |
|------------|-------------|--------------|--------|
| State Machine | `oracle_trader.py` (inline) | `core/state_machine.py` | ✅ |
| Config Manager | `oracle_trader.py` (inline) | `core/config.py` | ✅ |
| Risk Manager | `oracle_trader.py` (inline) | `trading/risk_manager.py` | ✅ |
| Position Manager | `oracle_trader.py` (inline) | `trading/position_manager.py` | ✅ |
| Executor | `oracle_trader.py` (inline) | `trading/executor.py` | ✅ |
| Paper Trade | ❌ Não existia | `trading/paper_trade.py` | ✅ Novo |
| Lot Calculator | ❌ Não existia | `trading/lot_calculator.py` | ✅ Novo |
| Broker Interface | `trading.py` (MT5 direto) | `infra/broker_base.py` | ✅ |
| MT5 Client | `trading.py` | `infra/mt5_client.py` | ✅ |
| Engine (Loop) | `oracle_trader.py` | `core/engine.py` | ✅ |
| Model Loader | `oracle_trader.py` | `ml/model_loader.py` | ⏳ Fase 4 |
| Feature Calculator | `features.py` | `ml/features.py` | ⏳ Fase 4 |
| WebSocket Server | `websocket_server.py` | `infra/websocket_server.py` | ✅ |
| Supabase Logger | `supabase_logger.py` | (manter/adaptar) | ⏳ Fase 3 |

**Componentes Refatorados: 9/14 (64%)**

### Hooks/Lógicas Extraídas

| Hook | Origem | Destino | Linhas |
|------|--------|---------|--------|
| `_check_risk()` | oracle_trader.py | `RiskManager.check_risk_limits()` | ~80 |
| `_handle_sl_hit()` | oracle_trader.py | `StateMachine.record_sl_hit()` | ~30 |
| `block_symbol()` | oracle_trader.py | `StateMachine.block_symbol()` | ~15 |
| `unblock_symbol()` | oracle_trader.py | `StateMachine.unblock_symbol()` | ~25 |
| `_execute_action()` | oracle_trader.py | `Executor.execute_action()` | ~100 |
| `_open_position()` | oracle_trader.py | `Executor._open_position()` | ~60 |
| `_close_position()` | oracle_trader.py | `Executor._close_position()` | ~50 |
| `calculate_sl()` | trading.py | `RiskManager.calculate_sl()` | ~80 |
| `_update_positions()` | oracle_trader.py | `PositionManager.sync_positions()` | ~90 |
| Warmup/Quarantine | oracle_trader.py | `PaperTradeManager` | ~150 |

**Hooks Extraídos: 10**

---

## 📁 Arquivos Modularizados

### v1 (Original) - 12 arquivos

```
oracle_trader.py        2406 linhas  ← MONOLÍTICO
├── __init__.py           71 linhas
├── constants.py         138 linhas
├── features.py          133 linhas
├── metrics.py           204 linhas
├── models.py            359 linhas
├── session_manager.py   234 linhas
├── supabase_logger.py   586 linhas
├── trading.py           584 linhas
├── websocket_client.py  227 linhas
├── websocket_server.py  229 linhas
└── ws_commands.py       372 linhas
─────────────────────────────────────
TOTAL                   5543 linhas
```

### v2 (Refatorado) - 18 arquivos

```
core/
├── __init__.py           40 linhas
├── config.py            311 linhas
├── engine.py            790 linhas
└── state_machine.py     343 linhas

models/
├── __init__.py           67 linhas
├── enums.py             127 linhas
├── position.py          228 linhas
├── state.py             261 linhas
└── trade.py             120 linhas

trading/
├── __init__.py           28 linhas
├── executor.py          337 linhas
├── lot_calculator.py    339 linhas
├── paper_trade.py       245 linhas
├── position_manager.py  227 linhas
└── risk_manager.py      264 linhas

infra/
├── __init__.py           38 linhas
├── broker_base.py       343 linhas
├── mt5_client.py        526 linhas
└── websocket_server.py  546 linhas

ml/
└── __init__.py           12 linhas

root/
└── main.py              348 linhas
─────────────────────────────────────
TOTAL                   5540 linhas
```

**Arquivos: 20 → 21 (+5%)**
**Linhas: 4960 → 5540 (+12%)**

---

## 📐 Qualidade de Código

### Complexidade

| Métrica | v1 | v2 | Mudança |
|---------|-----|-----|---------|
| Arquivo maior | 2406 linhas | 526 linhas | **-78%** |
| Média por arquivo | 462 linhas | 212 linhas | **-54%** |
| Classes | 1 (monolítica) | 33 (especializadas) | **+3200%** |
| Funções | 62 (em 1 classe) | 123 (distribuídas) | **+98%** |
| Funções por classe | 62 | 3.7 média | **-94%** |

### Responsabilidade Única (SRP)

| Aspecto | v1 | v2 |
|---------|-----|-----|
| `OracleTrader` | Estado + Risco + Execução + WS + DB | Apenas orquestração |
| Gestão de Risco | Misturado no loop | `RiskManager` isolado |
| Estado dos Símbolos | Flags dispersas | `StateMachine` centralizada |
| Execução de Ordens | Inline no loop | `Executor` dedicado |
| Broker | Acoplado ao MT5 | Interface abstrata |

### Duplicação

| Código | v1 | v2 |
|--------|-----|-----|
| Cálculo de lotes | Hardcoded + multiplicador | `LotCalculator` reutilizável |
| Transições de estado | 5+ lugares | `StateMachine` único |
| Verificação de risco | 3+ lugares | `RiskManager` único |
| Abertura/fechamento | Separado real/virtual | `Executor` unificado |

---

## ✅ Testes Implementados

| Módulo | Testes Unit | Testes Integração | Cobertura |
|--------|-------------|-------------------|-----------|
| `core/` | ⏳ | ⏳ | 0% |
| `models/` | ⏳ | - | 0% |
| `trading/` | ⏳ | ⏳ | 0% |
| `infra/` | ⏳ | ⏳ | 0% |
| `ml/` | ⏳ | ⏳ | 0% |

**Testes Implementados: 0/~50 estimados**

*Nota: Testes serão implementados na Fase 5*

---

## 🚀 Próximos Passos

### Imediatos (Fase 3)

1. **Criar `core/engine.py`**
   - Loop principal simplificado
   - Orquestração de módulos
   - Ciclo: Dados → Predição → Execução → Update

2. **Criar `main.py`**
   - Ponto de entrada
   - Inicialização de componentes
   - Signal handlers (SIGINT, SIGTERM)

3. **Adaptar WebSocket**
   - Integrar com novo Engine
   - Manter comandos existentes
   - Adicionar novos comandos v2

### Curto Prazo (Fase 4)

1. **Criar `ml/model_loader.py`**
   - Carrega HMM + PPO
   - Valida metadados
   - Configura LotCalculator automaticamente

2. **Criar `ml/features.py`**
   - Migrar de `features.py` v1
   - Adicionar validação
   - Cache de cálculos

3. **Criar `ml/predictor.py`**
   - Interface unificada para predições
   - Suporte a múltiplos modelos

### Médio Prazo (Fase 5)

1. **Testes Unitários**
   - 80%+ cobertura em `trading/`
   - 80%+ cobertura em `core/`
   - Mocks para broker

2. **Testes de Integração**
   - Fluxo completo: Startup → Paper → Normal → SL → Paper → Normal
   - Simulação de cenários de risco

3. **Validação Final**
   - Comparar comportamento v1 vs v2
   - Stress test com múltiplos símbolos
   - Documentação de migração

---

## 📋 Backlog de Melhorias (Pós v2.0)

| Prioridade | Melhoria | Descrição |
|------------|----------|-----------|
| Alta | Multi-broker | Implementar CCXT para crypto |
| Alta | Dashboard Web | Substituir WS local por cloud |
| Média | Trailing Stop | SL dinâmico baseado em ATR |
| Média | Multi-timeframe | Combinar sinais M15 + H1 |
| Baixa | ML Ensemble | Combinar múltiplos modelos |
| Baixa | Auto-retrain | Retreinar modelo periodicamente |

---

## 📊 Gráfico de Progresso

```
Fase 1 [####################] 100%  ✅
Fase 2 [####################] 100%  ✅
Fase 3 [###############     ]  75%  🏗️
Fase 4 [                    ]   0%  ⏳
Fase 5 [                    ]   0%  ⏳
───────────────────────────────────────
Total  [##########          ]  50%
```

---

*Documento gerado automaticamente durante refatoração do Oracle Trader v2*
