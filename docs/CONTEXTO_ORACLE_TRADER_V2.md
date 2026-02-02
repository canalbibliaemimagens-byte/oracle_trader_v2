# PROMPT DE RECUPERAÇÃO DE CONTEXTO - Oracle Trader v2

**Data da última atualização**: 02/02/2026  
**Sessão atual**: [ATUALIZAR A CADA NOVA SESSÃO]  
**Progresso geral**: 40% (Fase 2 de 5 completa)

---

## 🎯 OBJETIVO DESTA SESSÃO

[DESCREVER O OBJETIVO ESPECÍFICO DA SESSÃO ATUAL]

**IMPORTANTE**: Use objetivos granulares para garantir qualidade e permitir revisões entre sessões.

### Exemplos de objetivos (abordagem recomendada):

**✅ Granular (Recomendado)**:
- "Fase 3 Parte 1 - Engine e Entry Point: Criar core/engine.py e main.py"
- "Fase 3 Parte 2 - WebSocket: Adaptar websocket_server.py e integrar com Engine"
- "Fase 4 Parte 1 - Model Loader: Criar ml/model_loader.py com validação"

**⚠️ Ambicioso (Use com cautela)**:
- "Concluir Fase 3 completa (engine + main + websocket)"
- "Implementar toda Fase 4 (model_loader + features + predictor)"

**Dica**: Fases grandes (3-5 arquivos ou 500+ linhas) são melhor divididas em 2-3 sessões.

---

## 📋 INFORMAÇÕES DO PROJETO

### Identificação
- **Nome**: Oracle Trader v2.0
- **Descrição**: Sistema autônomo de trading com Reinforcement Learning (HMM + PPO)
- **Repositório GitHub**: https://github.com/canalbibliaemimagens-byte/oracle_trader_v2
- **Branch principal**: `main`
- **Commits**: 2
- **Fase**: Refatoração da v1 (monolítica) para v2 (modular)
- **Stack**: Python 100%

### Links Importantes
- **Código fonte (GitHub)**: https://github.com/canalbibliaemimagens-byte/oracle_trader_v2
- **Versão anterior**: https://github.com/canalbibliaemimagens-byte/oracle_trader_v2/blob/oracle_trader
- **Diretório do Projeto Claude**: Contém v1 original + instruções de refatoração

### 📖 Como Acessar Arquivos do GitHub

**URLs Raw** são links diretos para o conteúdo puro dos arquivos (sem interface web):

```
Formato:
https://raw.githubusercontent.com/[USUARIO]/[REPO]/[BRANCH]/[CAMINHO]

Exemplo real:
https://raw.githubusercontent.com/canalbibliaemimagens-byte/oracle_trader_v2/main/trading/executor.py
```

**Por que usar raw?**
- O Claude usa `web_fetch` para ler o código Python diretamente
- URLs normais retornam HTML (interface web), URLs raw retornam código puro

**Como montar:**
1. Pegue a URL normal: `github.com/.../blob/main/arquivo.py`
2. Substitua: `github.com` → `raw.githubusercontent.com`
3. Remova: `/blob/`
4. Resultado: `raw.githubusercontent.com/.../main/arquivo.py`

---

## 📂 ARQUITETURA v2 (OBJETIVO FINAL)

### Estrutura de Diretórios
```
oracle_trader_v2/
├── core/                  ← Fase 3 (⏳ Pendente)
│   ├── __init__.py       ✅ Criado (17 linhas)
│   ├── engine.py         ⏳ Loop principal orquestrador
│   ├── state_machine.py  ✅ Completo (343 linhas)
│   └── config.py         ✅ Completo (311 linhas)
│
├── trading/               ← Fase 2 (✅ Completa)
│   ├── __init__.py       ✅ Criado (28 linhas)
│   ├── executor.py       ✅ Completo (337 linhas)
│   ├── risk_manager.py   ✅ Completo (264 linhas)
│   ├── position_manager.py ✅ Completo (227 linhas)
│   ├── paper_trade.py    ✅ Completo (245 linhas)
│   └── lot_calculator.py ✅ Completo (339 linhas)
│
├── ml/                    ← Fase 4 (⏳ Pendente)
│   ├── __init__.py       ✅ Criado (12 linhas)
│   ├── model_loader.py   ⏳ Carregamento HMM+PPO
│   ├── features.py       ⏳ Migrar de v1
│   └── predictor.py      ⏳ Interface de predição
│
├── infra/                 ← Fase 2 (✅ Completa)
│   ├── __init__.py       ✅ Criado (29 linhas)
│   ├── broker_base.py    ✅ Completo (343 linhas)
│   └── mt5_client.py     ✅ Completo (526 linhas)
│
├── models/                ← Fase 1 (✅ Completa)
│   ├── __init__.py       ✅ Criado (67 linhas)
│   ├── position.py       ✅ Completo (228 linhas)
│   ├── trade.py          ✅ Completo (120 linhas)
│   ├── state.py          ✅ Completo (261 linhas)
│   └── enums.py          ✅ Completo (127 linhas)
│
├── config/                ← Configurações
│   ├── oracle_config.json
│   └── symbols_config.json
│
├── docs/                  ← Documentação
│   └── [arquivos diversos]
│
├── main.py               ⏳ Ponto de entrada (Fase 3)
├── requirements.txt      ✅ Dependências
└── .gitignore           ✅ Configurado
```

**Total v2 atual**: 3824 linhas em 18 arquivos  
**Total v1 original**: 5543 linhas em 12 arquivos  
**Redução**: -31% de código (ainda sem Engine e ML)

---

## 🔄 ESTADO DA REFATORAÇÃO

### Diretório do Projeto Claude
**Contém**: 
- ✅ **v1 Original** (oracle_trader.py - 2406 linhas monolíticas)
- ✅ **Documentação de refatoração** (métricas, decisões, instruções)
- ✅ **Arquivos auxiliares v1** (trading.py, features.py, etc.)
- ✅ **Histórico de decisões arquiteturais**

**Importante**: O diretório do projeto = **referência original** sendo refatorada.

### Versão GitHub (Código Vivo)
- **Branch**: `main`
- **Último commit**: [Verificar atual]
- **Estado**: Fases 1-2 completas, Fase 3 em andamento
- **Acessar via**: `web_fetch` usando URLs raw do GitHub

---

## 📊 PROGRESSO POR FASE

### ✅ Fase 1 - Estrutura + Models + Infra (100%)
**Objetivo**: Criar estrutura base e modelos de dados

**Realizações**:
- ✅ Estrutura de diretórios criada
- ✅ `models/` completo (5 arquivos, 803 linhas)
  - `position.py`: Position, VirtualPosition
  - `trade.py`: Trade, TradeResult
  - `state.py`: SymbolState, SystemState
  - `enums.py`: SymbolStatus, TradeAction, etc.
- ✅ `infra/broker_base.py`: Interface abstrata para brokers
- ✅ `infra/mt5_client.py`: Implementação MetaTrader5

**Decisões importantes**:
- Dataclasses para immutability
- Interface abstrata permite múltiplos brokers (MT5, CCXT futuro)
- Separação clara: models (dados) vs infra (conectividade)

---

### ✅ Fase 2 - Core + Trading + LotCalculator (100%)
**Objetivo**: Modularizar lógica de trading e gestão de risco

**Realizações**:
- ✅ `core/state_machine.py` (343 linhas)
  - Gerencia transições de estado dos símbolos
  - Estados: NO_MODEL, PAPER_TRADE, NORMAL, BLOCKED
  - Tracking de SL hits, warmup, quarantine
- ✅ `core/config.py` (311 linhas)
  - Gerenciamento de configurações runtime
  - Validação de config files
- ✅ `trading/executor.py` (337 linhas)
  - Execução unificada real/virtual
  - Abstrai diferenças entre brokers
- ✅ `trading/risk_manager.py` (264 linhas)
  - DD protection, SL protection, TP global
  - Cálculo de stop loss dinâmico
- ✅ `trading/position_manager.py` (227 linhas)
  - Sincronização de posições (reais + virtuais)
  - Cache e tracking
- ✅ `trading/paper_trade.py` (245 linhas)
  - Substitui WARMUP e QUARANTINE da v1
  - Conceito unificado de Paper Trade
- ✅ `trading/lot_calculator.py` (339 linhas)
  - Cálculo de lotes baseado em risco
  - Suporta fixed lot, risk-based, kelly criterion

**Métricas**:
- **Componentes refatorados**: 9/14 (64%)
- **Hooks extraídos**: 10 funções (~685 linhas)
- **Redução de complexidade**: arquivo maior de 2406 → 526 linhas (-78%)

**Decisões importantes**:
- Paper Trade unificado (4 motivos de entrada: STARTUP, SL_PROTECTION, TP_GLOBAL, MANUAL)
- Single Responsibility Principle (SRP) aplicado
- Eliminação de duplicação de código

---

### ⏳ Fase 3 - Engine Principal (0%)
**Objetivo**: Criar loop orquestrador e ponto de entrada

**Tarefas**:
- [ ] `core/engine.py` - Loop principal simplificado
  - Orquestração de módulos
  - Ciclo: Dados → Predição → Execução → Update
  - Signal handlers (graceful shutdown)
- [ ] `main.py` - Ponto de entrada
  - Inicialização de componentes
  - CLI arguments
  - Logging setup
- [ ] Adaptar `websocket_server.py` da v1
  - Integrar com novo Engine
  - Manter comandos existentes
  - Adicionar comandos v2

**Arquivos de referência v1**:
- `oracle_trader.py` (loop principal, linhas 1500-1800)
- `websocket_server.py` (229 linhas)
- `ws_commands.py` (372 linhas)

---

### ⏳ Fase 4 - ML (Model Loader, Features) (0%)
**Objetivo**: Integrar modelos de ML e features

**Tarefas**:
- [ ] `ml/model_loader.py`
  - Carregamento de modelos HMM + PPO
  - Validação de metadados
  - Configuração automática de LotCalculator
- [ ] `ml/features.py`
  - Migrar de `features.py` v1 (133 linhas)
  - Adicionar validação
  - Cache de cálculos
- [ ] `ml/predictor.py`
  - Interface unificada para predições
  - Suporte a múltiplos modelos
  - Fallback strategies

**Arquivos de referência v1**:
- `features.py` (133 linhas)
- `oracle_trader.py` (carregamento de modelos, linhas 200-400)
- `models.py` (359 linhas - estruturas de dados)

---

### ⏳ Fase 5 - Testes e Validação (0%)
**Objetivo**: Garantir qualidade e paridade com v1

**Tarefas**:
- [ ] Testes unitários
  - `trading/` (80%+ cobertura)
  - `core/` (80%+ cobertura)
  - Mocks para broker
- [ ] Testes de integração
  - Fluxo completo: Startup → Paper → Normal → SL → Paper → Normal
  - Simulação de cenários de risco
  - Multi-símbolo stress test
- [ ] Validação final
  - Comparar comportamento v1 vs v2
  - Performance benchmarks
  - Documentação de migração

**Estimativa**: ~50 testes

---

## 📐 DECISÕES DE ARQUITETURA

### Padrões Adotados

#### 1. **Responsabilidade Única (SRP)**
| Classe v1 | Classe v2 | Responsabilidade |
|-----------|-----------|------------------|
| OracleTrader (tudo) | Engine | Apenas orquestração |
| OracleTrader (risco) | RiskManager | Gestão de risco isolada |
| OracleTrader (estado) | StateMachine | Transições de estado |
| OracleTrader (execução) | Executor | Execução de ordens |
| - | PaperTradeManager | Simulação virtual |

#### 2. **Abstração de Broker**
- Interface `BrokerBase` permite múltiplos brokers
- MT5 implementado, CCXT (crypto) planejado
- Executor não conhece detalhes do broker

#### 3. **Estados do Símbolo (Máquina de Estados)**
```
NO_MODEL → PAPER_TRADE → NORMAL
    ↓           ↓           ↓
    └─────── BLOCKED ───────┘
```

#### 4. **Paper Trade Unificado**
Motivos de entrada:
- `STARTUP`: Inicialização do sistema
- `SL_PROTECTION`: Múltiplos SL hits
- `TP_GLOBAL`: Take Profit global atingido
- `MANUAL`: Comando do usuário

Critério de saída: N wins virtuais consecutivos

---

### Convenções de Código

#### Nomenclatura
- **Classes**: PascalCase (e.g., `RiskManager`, `StateMachine`)
- **Funções/métodos**: snake_case (e.g., `calculate_sl`, `sync_positions`)
- **Constantes**: UPPER_SNAKE_CASE (e.g., `MAX_DD_PERCENT`)
- **Privados**: prefixo `_` (e.g., `_validate_config`)

#### Imports
- Absolutos sempre que possível
- Agrupados: stdlib → third-party → local
- Type hints em todas as assinaturas

#### Documentação
- Docstrings em Google Style
- Type hints obrigatórios
- Comentários apenas para lógica complexa

---

### Anti-patterns Evitados

#### ❌ v1 (Monolítico)
```python
class OracleTrader:
    def run(self):
        # 2406 linhas em 1 método
        # Estado + Risco + Execução + WS + DB
```

#### ✅ v2 (Modular)
```python
class Engine:
    def __init__(self):
        self.state_machine = StateMachine()
        self.risk_manager = RiskManager()
        self.executor = Executor()
    
    def run(self):
        # <300 linhas
        # Apenas orquestração
```

---

## 🔍 COMPARAÇÃO v1 vs v2

### Métricas de Qualidade

| Métrica | v1 | v2 | Mudança |
|---------|-----|-----|---------|
| **Arquivo maior** | 2406 linhas | 526 linhas | **-78%** |
| **Média por arquivo** | 462 linhas | 212 linhas | **-54%** |
| **Classes** | 1 (monolítica) | 33 (especializadas) | **+3200%** |
| **Funções** | 62 (em 1 classe) | 123 (distribuídas) | **+98%** |
| **Funções/classe** | 62 | 3.7 média | **-94%** |

### Duplicação Eliminada

| Código | v1 | v2 |
|--------|-----|-----|
| Cálculo de lotes | Hardcoded + multiplicador | `LotCalculator` reutilizável |
| Transições de estado | 5+ lugares | `StateMachine` único |
| Verificação de risco | 3+ lugares | `RiskManager` único |
| Abertura/fechamento | Real vs virtual separados | `Executor` unificado |

---

## 💡 INSTRUÇÕES PARA O CLAUDE

### Como trabalhar com este projeto:

#### 1. **Consultar versão original (v1)**
```
Arquivos no diretório do projeto Claude:
- oracle_trader.py (2406 linhas) - referência original monolítica
- trading.py, features.py, etc. - módulos auxiliares v1
- Usar como baseline para entender lógica original
```

#### 2. **Acessar código atual (v2)**
```
GitHub é a fonte da verdade para código refatorado.
Use web_fetch para arquivos específicos:

https://raw.githubusercontent.com/canalbibliaemimagens-byte/oracle_trader_v2/main/core/config.py
https://raw.githubusercontent.com/canalbibliaemimagens-byte/oracle_trader_v2/main/trading/executor.py
```

#### 3. **Processo de refatoração**
```
1. Identificar funcionalidade na v1 (diretório do projeto)
2. Buscar módulo correspondente na v2 (GitHub)
3. Se ainda não existe na v2:
   a. Criar novo arquivo seguindo estrutura
   b. Extrair e modularizar código da v1
   c. Aplicar padrões v2 (SRP, type hints, docstrings)
4. Documentar decisões importantes
5. Atualizar métricas neste documento
```

#### 4. **Prioridades de qualidade**
- ✅ **Manter funcionalidade**: Comportamento idêntico à v1
- ✅ **Melhorar legibilidade**: Código autoexplicativo
- ✅ **Reduzir complexidade**: Métodos <50 linhas
- ✅ **Eliminar duplicação**: DRY principle
- ✅ **Type safety**: Type hints + validação
- ✅ **Documentação**: Docstrings completos

#### 5. **Ao final da sessão**
- [ ] Atualizar seção "Histórico de Refatoração"
- [ ] Atualizar "Progresso por Fase"
- [ ] Atualizar "Próximos Passos"
- [ ] Listar decisões arquiteturais importantes
- [ ] Documentar bugs/issues encontrados

---

## 📝 HISTÓRICO DE REFATORAÇÃO

### Sessão 1 - [DATA - Preencher]
**Fase**: 1 (Estrutura + Models)

**Objetivos**:
- Criar estrutura base de diretórios
- Implementar models/ completo
- Criar interface abstrata de broker

**Realizações**:
- ✅ Estrutura de diretórios oracle_trader_v2/
- ✅ `models/position.py` (228 linhas)
- ✅ `models/trade.py` (120 linhas)
- ✅ `models/state.py` (261 linhas)
- ✅ `models/enums.py` (127 linhas)
- ✅ `infra/broker_base.py` (343 linhas)
- ✅ `infra/mt5_client.py` (526 linhas)

**Decisões**:
- Usar dataclasses para immutability
- Criar interface abstrata BrokerBase para futura extensibilidade
- Separar concerns: dados (models) vs conectividade (infra)

**Pendências**:
- Testes unitários (Fase 5)

---

### Sessão 2 - [DATA - Preencher]
**Fase**: 2 (Core + Trading)

**Objetivos**:
- Implementar StateMachine e ConfigManager
- Criar módulos de trading (executor, risk, positions, paper)
- Extrair lógica de cálculo de lotes

**Realizações**:
- ✅ `core/state_machine.py` (343 linhas)
- ✅ `core/config.py` (311 linhas)
- ✅ `trading/executor.py` (337 linhas)
- ✅ `trading/risk_manager.py` (264 linhas)
- ✅ `trading/position_manager.py` (227 linhas)
- ✅ `trading/paper_trade.py` (245 linhas)
- ✅ `trading/lot_calculator.py` (339 linhas)

**Decisões**:
- Paper Trade unificado (4 motivos de entrada)
- Executor abstrai broker e unifica real/virtual
- LotCalculator suporta 3 estratégias (fixed, risk-based, kelly)

**Métricas alcançadas**:
- Componentes refatorados: 9/14 (64%)
- Redução de ~1719 linhas (de 5543 para 3824, -31%)

**Pendências**:
- Engine principal (Fase 3)
- ML modules (Fase 4)

---

### Sessão 3 - [DATA - Preencher quando iniciar Fase 3]
**Fase**: 3 (Engine Principal)

**Objetivos**:
- [Preencher no início da sessão]

**Realizações**:
- [Atualizar durante/após sessão]

**Decisões**:
- [Documentar decisões importantes]

---

## 🚀 PRÓXIMOS PASSOS

### 🎯 Imediatos (Fase 3 - Dividida em 2 Sessões)

#### **Sessão 3.1 - Engine e Entry Point**

**Objetivo**: Criar loop principal e ponto de entrada do sistema

**Tarefas**:
- [ ] `core/engine.py` (~300 linhas estimadas)
  - Loop principal simplificado
  - Orquestração: StateMachine + RiskManager + Executor + Predictor
  - Ciclo: `get_data()` → `predict()` → `execute()` → `update_state()`
  - Signal handlers (SIGINT, SIGTERM) para graceful shutdown
  - Logging estruturado
  
- [ ] `main.py` (~100 linhas estimadas)
  - Ponto de entrada do sistema
  - Parse de argumentos CLI (`--config`, `--symbols`, `--paper-only`)
  - Inicialização de componentes
  - Setup de logging (console + file)
  - Exception handling top-level

**Arquivos de referência v1 necessários**:
- `oracle_trader.py` (loop principal, linhas 1500-1800)

**Critérios de conclusão**:
- ✅ Sistema inicia sem erros
- ✅ Loop executa pelo menos 1 ciclo completo
- ✅ Graceful shutdown funciona (Ctrl+C)
- ✅ Logs são gerados corretamente

---

#### **Sessão 3.2 - WebSocket Integration**

**Objetivo**: Integrar controle remoto via WebSocket

**Tarefas**:
- [ ] Adaptar/criar `infra/websocket_server.py` (~300 linhas estimadas)
  - Migrar de `websocket_server.py` v1
  - Integrar com Engine v2
  - Comandos existentes: START, STOP, STATUS, BLOCK, UNBLOCK
  - Novos comandos v2: GET_METRICS, SET_PAPER_MODE
  - Thread-safe communication com Engine

**Arquivos de referência v1 necessários**:
- `websocket_server.py` (229 linhas)
- `ws_commands.py` (372 linhas)

**Critérios de conclusão**:
- ✅ WebSocket server inicia junto com Engine
- ✅ Comandos básicos funcionam (START/STOP/STATUS)
- ✅ Comandos de bloqueio funcionam (BLOCK/UNBLOCK)
- ✅ Respostas são retornadas corretamente ao cliente

---

### 📅 Curto Prazo (Fase 4 - Próximas 2-3 Sessões)

1. **Criar `ml/model_loader.py`** (~250 linhas estimadas)
   - Carregamento de pickle files (HMM + PPO)
   - Validação de metadados (symbols, timeframe, version)
   - Configuração automática de LotCalculator baseado em metadados
   - Cache de modelos em memória

2. **Criar `ml/features.py`** (~200 linhas estimadas)
   - Migrar de `features.py` v1 (133 linhas)
   - Adicionar validação de inputs
   - Cache de cálculos intermediários
   - Testes com dados históricos

3. **Criar `ml/predictor.py`** (~200 linhas estimadas)
   - Interface unificada: `predict(symbol, bars) -> TradeAction`
   - Suporte a múltiplos modelos (HMM, PPO, ensemble futuro)
   - Confidence scores
   - Fallback strategies (se modelo falhar)

**Arquivos de referência v1 necessários**:
- `features.py` (133 linhas)
- `oracle_trader.py` (predição, linhas 1200-1400)
- `models.py` (359 linhas)

---

### 📆 Médio Prazo (Fase 5 - Próximas 4-6 Sessões)

#### Testes Unitários (~30 testes)
- `tests/test_risk_manager.py`: DD, SL, TP validations
- `tests/test_executor.py`: Mocks de broker, real vs virtual
- `tests/test_state_machine.py`: Transições de estado
- `tests/test_lot_calculator.py`: Estratégias de lotes
- `tests/test_paper_trade.py`: Critérios de entrada/saída

#### Testes de Integração (~10 testes)
- `tests/integration/test_full_flow.py`:
  - Startup → Paper → Normal
  - SL hit → Paper → Recovery
  - TP global → Paper → Recovery
- `tests/integration/test_multi_symbol.py`:
  - 5 símbolos simultâneos
  - Independência de estados

#### Validação vs v1
- Comparar outputs v1 vs v2 com mesmo input
- Performance benchmarks (CPU, memória)
- Stress tests (100+ símbolos)

**Meta de cobertura**: 80%+ em módulos core e trading

---

## 📋 BACKLOG DE MELHORIAS (Pós v2.0)

### Prioridade Alta
- [ ] **Multi-broker**: Implementar CCXT para crypto exchanges
- [ ] **Dashboard Web**: Substituir WS local por interface cloud (Streamlit ou React)
- [ ] **Logs estruturados**: Migrar para structured logging (structlog)

### Prioridade Média
- [ ] **Trailing Stop**: SL dinâmico baseado em ATR
- [ ] **Multi-timeframe**: Combinar sinais M15 + H1 + H4
- [ ] **Portfolio Risk**: Gestão de risco por portfólio, não só por símbolo
- [ ] **Backtesting**: Modo replay com dados históricos

### Prioridade Baixa
- [ ] **ML Ensemble**: Combinar HMM + PPO + LSTM
- [ ] **Auto-retrain**: Retreinar modelos periodicamente
- [ ] **Telegram Bot**: Notificações e comandos via Telegram
- [ ] **Docker**: Containerização completa

---

## 📎 REFERÊNCIAS E RECURSOS

### Documentação Técnica
- **MetaTrader5 Python API**: https://www.mql5.com/en/docs/integration/python_metatrader5
- **Stable-Baselines3 (PPO)**: https://stable-baselines3.readthedocs.io/
- **HMMLearn**: https://hmmlearn.readthedocs.io/

### Padrões de Design
- **State Pattern**: StateMachine implementation
- **Strategy Pattern**: LotCalculator strategies
- **Adapter Pattern**: BrokerBase abstractions
- **Template Method**: Executor real vs virtual

### Artigos/Papers de Referência
- [Adicionar papers de RL trading quando relevante]

---

## 🔄 TEMPLATE DE PROMPT INICIAL PARA NOVA SESSÃO

```
Olá! Continuando o trabalho de refatoração do Oracle Trader v2.

═══════════════════════════════════════════════════════════
CONTEXTO DO PROJETO
═══════════════════════════════════════════════════════════

📍 Projeto: Oracle Trader v2.0 - Sistema autônomo de trading com RL
📊 Progresso: 40% (Fase 2 de 5 completa)
🔗 Repositório: https://github.com/canalbibliaemimagens-byte/oracle_trader_v2

REFERÊNCIAS:
✅ Versão original (v1): Diretório do projeto Claude
   - oracle_trader.py (2406 linhas monolíticas)
   - Usar como baseline de funcionalidade

✅ Código atual (v2): GitHub branch main
   - Fases 1-2 completas (models, infra, core, trading)
   - Acessar via web_fetch com URLs raw:
     https://raw.githubusercontent.com/canalbibliaemimagens-byte/oracle_trader_v2/main/[CAMINHO]

═══════════════════════════════════════════════════════════
ÚLTIMA SESSÃO (Resumo)
═══════════════════════════════════════════════════════════

Fase: [NÚMERO/PARTE - ex: "Fase 3.1" ou "Fase 2"]
Data: [DATA]

Concluído:
✅ [Item 1]
✅ [Item 2]
✅ [Item 3]

Pendente:
⏳ [Item 1]
⏳ [Item 2]

Decisões importantes:
• [Decisão arquitetural 1]
• [Decisão arquitetural 2]

═══════════════════════════════════════════════════════════
OBJETIVO HOJE
═══════════════════════════════════════════════════════════

[DESCREVER OBJETIVO ESPECÍFICO - USE ABORDAGEM GRANULAR]

Exemplo (Sessão 3.1):
"Fase 3 Parte 1 - Engine e Entry Point
 
 Tarefas:
 1. Criar core/engine.py com loop principal orquestrador
    - Ciclo: get_data → predict → execute → update
    - Signal handlers para graceful shutdown
 
 2. Criar main.py com CLI e inicialização
    - Argumentos: --config, --symbols, --paper-only
    - Setup de logging
 
 Critérios de conclusão:
 ✅ Sistema inicia sem erros
 ✅ Loop executa pelo menos 1 ciclo
 ✅ Graceful shutdown (Ctrl+C) funciona"

═══════════════════════════════════════════════════════════
ARQUIVOS RELEVANTES PARA HOJE
═══════════════════════════════════════════════════════════

v1 (referência no diretório do projeto):
- oracle_trader.py (linhas [RANGE - ex: 1500-1800 para loop])
- [outros arquivos v1 se necessário]

v2 (já existentes no GitHub para consulta):
- core/state_machine.py
- core/config.py
- trading/executor.py
- trading/risk_manager.py
- [outros módulos necessários]

v2 (criar hoje):
- core/engine.py (novo)
- main.py (novo)

═══════════════════════════════════════════════════════════
SOLICITAÇÃO
═══════════════════════════════════════════════════════════

Por favor:

1. Consulte oracle_trader.py v1 no diretório do projeto para entender:
   - Como o loop principal funciona (linhas ~1500-1800)
   - Ciclo de execução: dados → predição → ação → update
   - Como são tratados signals (SIGINT, SIGTERM)

2. Acesse módulos v2 necessários no GitHub via web_fetch:
   https://raw.githubusercontent.com/canalbibliaemimagens-byte/oracle_trader_v2/main/core/config.py
   https://raw.githubusercontent.com/canalbibliaemimagens-byte/oracle_trader_v2/main/trading/executor.py
   [etc.]

3. Crie os novos arquivos seguindo padrões v2:
   - Type hints completos
   - Docstrings em Google Style
   - Métodos <50 linhas
   - SRP (Single Responsibility Principle)

Lembre-se:
• Manter funcionalidade idêntica à v1
• Código limpo e bem documentado
• Orquestração simples no Engine (<300 linhas)
• Graceful shutdown obrigatório
```

---

## 📌 NOTAS IMPORTANTES

### ⚠️ Regras de Ouro
1. **NUNCA** fazer push direto para main sem revisão
2. **SEMPRE** manter backup antes de grandes refatorações
3. **SEMPRE** testar funcionalidade após mudanças (quando chegar Fase 5)
4. **SEMPRE** atualizar este documento ao final da sessão

### 🔍 Checklist de Qualidade (Cada Novo Arquivo)
- [ ] Type hints em todas as funções
- [ ] Docstrings completos (Google Style)
- [ ] Métodos <50 linhas
- [ ] Imports organizados (stdlib → third-party → local)
- [ ] Sem lógica duplicada
- [ ] Testes planejados (marcar em Fase 5)

### 📊 Sincronização
- **GitHub** = versão atual (código vivo)
- **Projeto Claude** = referência original v1
- **Este documento** = mapa de progresso e decisões

---

## ⚠️ AVISOS E CUIDADOS

### Riscos Conhecidos
- ⚠️ **Mudança de comportamento**: Sempre comparar output v1 vs v2
- ⚠️ **Performance**: Monitorar se refatoração não degradou performance
- ⚠️ **State transitions**: StateMachine deve replicar exatamente lógica v1
- ⚠️ **Paper Trade**: Critérios de entrada/saída devem ser idênticos

### Debugging
- Se algo não funcionar como v1:
  1. Comparar log v1 vs v2 linha a linha
  2. Verificar se todos os estados/flags foram migrados
  3. Validar configurações (config/*.json)

---

**Última atualização**: 02/02/2026  
**Próxima revisão agendada**: [Após cada sessão]  
**Responsável**: [Seu nome]
