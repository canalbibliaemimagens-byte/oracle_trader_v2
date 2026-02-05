# 🏗️ Oracle Trader v2.0 - Especificação de Contratos e Fluxos

**Versão:** 1.1  
**Data:** 2026-02-03  
**Status:** Documento de Planejamento (Revisado)

---

## 📋 Changelog v1.1

| Item | Antes | Depois | Motivo |
|------|-------|--------|--------|
| Ação 0 | `FLAT` | `WAIT` | FLAT é estado de posição, WAIT é sinal de "ficar fora" |
| Nome das ações | `SMALL/MEDIUM/LARGE` | `WEAK/MODERATE/STRONG` | Mais semântico - representa intensidade do sinal |
| Campo `size` nas actions | Lote fixo (0.01, etc) | `intensity` (1, 2, 3) | Executor mapeia intensidade → lote real |
| Config Executor | `lot_small/medium/large` | `lot_weak/moderate/strong` | Consistência com nomenclatura |

---

## 📋 Índice

1. [Visão Geral e Princípios](#1-visão-geral-e-princípios)
2. [Arquitetura de Módulos](#2-arquitetura-de-módulos)
3. [Contratos de Dados](#3-contratos-de-dados)
4. [Contratos de Comunicação](#4-contratos-de-comunicação)
5. [Fluxos de Operação](#5-fluxos-de-operação)
6. [Critérios de Sincronização](#6-critérios-de-sincronização)
7. [Métricas e Comentário de Ordem](#7-métricas-e-comentário-de-ordem)
8. [Definições Técnicas (cTrader)](#8-definições-técnicas-ctrader)

---

## 1. Visão Geral e Princípios

### 1.1 Objetivo

Sistema de trading autônomo baseado em modelos HMM+PPO, independente de sistema operacional, com separação total entre predição e execução.

### 1.2 Princípios Fundamentais

| Princípio | Descrição |
|-----------|-----------|
| **Isolamento Total** | Preditor não conhece conta real. Executor não conhece modelos. |
| **Identidade Treino-Execução** | Features e lógica do Preditor são idênticas ao notebook de treino. |
| **Mapeamento de Intensidade** | Modelo emite intensidade (fraco/moderado/forte). Executor mapeia para lotes reais. |
| **Simplicidade sobre Flexibilidade** | Menos código = menos bugs silenciosos. |
| **Posição Virtual** | Preditor mantém estado interno independente da realidade. |
| **Métricas na Plataforma** | cTrader como fonte primária. Comentário estruturado para dados extras. |

### 1.3 Glossário de Termos

| Termo | Significado | Contexto |
|-------|-------------|----------|
| **FLAT** | Estado de posição = sem posição aberta | Feature de posição no modelo (direction=0) |
| **WAIT** | Sinal/Ação = "não faça nada, fique de fora" | Ação índice 0 emitida pelo modelo |
| **Intensidade** | Força do sinal (1=fraco, 2=moderado, 3=forte) | Mapeado para lotes pelo Executor |

### 1.4 Decisões Arquiteturais Fixas

- **Broker:** cTrader Open API (independente de SO)
- **Ações do Modelo:** 7 ações (0=WAIT, 1-3=LONG, 4-6=SHORT) com 3 níveis de intensidade
- **Lotes no Treino:** `[0, 0.01, 0.03, 0.05]` (referência, não usados diretamente na execução)
- **Lotes no Executor:** Configuráveis por símbolo (mapeiam intensidade → lote real)
- **SL/TP:** Sempre em valor monetário (USD). Zero = desativado.
- **Defaults Executor:** SL=$10, TP=$0, Lotes=[0.01, 0.03, 0.05]
- **Comunicação:** WebSocket local entre módulos
- **Paper Trading:** Processo separado, paralelo ao real

---

## 2. Arquitetura de Módulos

### 2.1 Diagrama de Módulos

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORQUESTRADOR                             │
│                    (Inicialização/Shutdown)                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   CONNECTOR   │  │   PREDITOR    │  │   EXECUTOR    │
│   (cTrader)   │  │   (Cérebro)   │  │    (Mãos)     │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        │                  │                  ▼
        │                  │          ┌───────────────┐
        │                  │          │    PAPER      │
        │                  │          │  (Paralelo)   │
        │                  │          └───────────────┘
        │                  │
        └────────WS────────┴────────WS────────┘
```

### 2.2 Módulo CONNECTOR (Interface cTrader)

**Responsabilidade:** Única interface com cTrader API. Fornece dados e executa ações.

**Entradas:**
- Configuração de conexão (credenciais, servidor)
- Comandos de ação (comprar, vender, fechar)
- Requisições de dados (OHLCV, posições, conta)

**Saídas:**
- Stream de dados OHLCV
- Dados de conta (balance, equity, margin)
- Dados de posições abertas
- Confirmação de ordens (ticket, preço, status)
- Histórico de ordens (para métricas)

**NÃO faz:**
- Decisões de trading
- Cálculo de features
- Gestão de risco

### 2.3 Módulo PREDITOR (Cérebro)

**Responsabilidade:** Carregar modelos, calcular features, gerar sinais. Manter posição virtual.

**Entradas:**
- DataFrame OHLCV (recebido do Connector)
- Modelos carregados (ZIP com metadata)

**Saídas:**
- Sinais com intensidade (WAIT, LONG_WEAK, LONG_MODERATE, etc.)
- Estado interno para debug/log

**Características:**
- Usa mesmos LOT_SIZES do treino internamente: `[0, 0.01, 0.03, 0.05]`
- Mantém posição virtual por símbolo
- Calcula features idênticas ao treino
- Janela deslizante FIFO interna (mínimo 350 barras)
- Não conhece conta real, spread real, margem

**Lógica de Posição Virtual:**
- Segue EXATAMENTE a lógica do `TradingEnv`
- Não faz fechamento parcial
- Mudança de tamanho = fecha tudo + abre novo

**NÃO faz:**
- Comunicação com broker
- Validação de margem/risco
- Conversão de lotes

### 2.4 Módulo EXECUTOR (Mãos)

**Responsabilidade:** Receber sinais, mapear intensidade para lotes, validar, enviar ordens ao Connector.

**Entradas:**
- Sinais do Preditor (com intensidade)
- Configuração por símbolo (lotes, SL, TP)
- Dados de conta (do Connector)

**Saídas:**
- Ordens para o Connector
- ACK para o Preditor (log)
- Comentário estruturado na ordem

**Mapeamento de Intensidade → Lotes:**

| Intensidade | Nome | Config Key | Default |
|-------------|------|------------|---------|
| 1 | WEAK | `lot_weak` | 0.01 |
| 2 | MODERATE | `lot_moderate` | 0.03 |
| 3 | STRONG | `lot_strong` | 0.05 |

**Características:**
- Configuração JSON por símbolo
- Valida margem antes de enviar
- Não calcula features
- Não conhece HMM/PPO

**NÃO faz:**
- Predição
- Cálculo de features
- Decisão de direção

### 2.5 Módulo PAPER (Trading Simulado)

**Responsabilidade:** Simular execução idêntica ao TradingEnv do treino. Benchmark para medir drift.

**Entradas:**
- Mesmos sinais que o Executor recebe
- DataFrame OHLCV (do Connector)

**Saídas:**
- Trades simulados
- Métricas comparativas (vs conta real)

**Características:**
- Lógica idêntica ao `TradingEnv` do notebook
- Mesmos spreads, slippage, comissão do treino
- Salva no DB com flag `is_paper=true`
- Processo separado do Executor

---

## 3. Contratos de Dados

### 3.1 Modelo ZIP (Saída do Notebook)

**Estrutura do arquivo:**
```
{symbol}_{timeframe}.zip
├── {symbol}_{timeframe}_hmm.pkl
└── {symbol}_{timeframe}_ppo.zip
```

**Header do ZIP (`zip.comment`):**

```json
{
  "format_version": "2.0",
  "generated_at": "ISO8601",
  
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
    "total_pnl": 1234.56,
    "total_pips": 456.7,
    "max_drawdown_pct": 12.3,
    "sharpe_ratio": 1.23,
    "sortino_ratio": 1.56,
    "calmar_ratio": 2.1,
    "long_trades": 120,
    "short_trades": 114,
    "long_win_rate": 0.55,
    "short_win_rate": 0.52
  },
  
  "hmm_state_analysis": {
    "bull_states": [0, 2],
    "bear_states": [1, 4],
    "range_states": [3],
    "state_distribution": {
      "0": {"pct": 18.5, "label": "BULL", "avg_pnl": 12.3},
      "1": {"pct": 22.1, "label": "BEAR", "avg_pnl": -5.2},
      "2": {"pct": 15.3, "label": "BULL", "avg_pnl": 8.7},
      "3": {"pct": 28.9, "label": "RANGE", "avg_pnl": 2.1},
      "4": {"pct": 15.2, "label": "BEAR", "avg_pnl": -3.4}
    }
  },
  
  "data_info": {
    "total_bars": 50000,
    "train_bars": 35000,
    "val_bars": 7500,
    "test_bars": 7500,
    "date_start": "2024-01-01",
    "date_end": "2026-01-31"
  }
}
```

**Regra:** Nenhum campo de configuração de execução real (SL, TP, lotes reais) entra aqui. Este header é 100% sobre o treino.

### 3.2 Configuração do Executor (por símbolo)

**Arquivo:** `executor_config.json`

```json
{
  "_comment": "Mapeamento de intensidade do sinal para lotes reais",
  
  "EURUSD": {
    "enabled": true,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 10.0,
    "tp_usd": 0,
    "notes": "Forex padrão - lotes iguais ao treino"
  },
  
  "US500.cash": {
    "enabled": true,
    "lot_weak": 0.10,
    "lot_moderate": 0.30,
    "lot_strong": 0.50,
    "sl_usd": 50.0,
    "tp_usd": 0,
    "notes": "Índice - lotes 10x para manter risco proporcional"
  },
  
  "AAPL": {
    "enabled": true,
    "lot_weak": 1,
    "lot_moderate": 3,
    "lot_strong": 5,
    "sl_usd": 20.0,
    "tp_usd": 0,
    "notes": "Ação - lote mínimo é 1"
  },
  
  "XAUUSD": {
    "enabled": false,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 10.0,
    "tp_usd": 10.0,
    "notes": "Desabilitado - aguardando ajuste"
  }
}
```

**Regra de criação:** Quando um modelo é carregado e não existe config, criar entrada com defaults:
- `enabled`: false (usuário deve habilitar explicitamente)
- `lot_weak`: 0.01
- `lot_moderate`: 0.03
- `lot_strong`: 0.05
- `sl_usd`: 10.0
- `tp_usd`: 0 (desativado)

### 3.3 DataFrame OHLCV (Interno)

**Colunas obrigatórias:**
```
time     : int64 (Unix timestamp)
open     : float64
high     : float64
low      : float64
close    : float64
volume   : float64 (0 se não disponível)
```

**Regra:** Connector fornece neste formato. Preditor e Paper consomem diretamente.

### 3.4 Posição Virtual (Preditor)

**Estrutura interna por símbolo:**
```
symbol          : str
direction       : int (-1, 0, 1)  # -1=SHORT, 0=FLAT, 1=LONG
intensity       : int (0, 1, 2, 3)  # 0=sem posição
size            : float (do treino: 0.01, 0.03, 0.05)
entry_price     : float
entry_time      : int (Unix timestamp)
entry_hmm_state : int
pnl_current     : float (calculado a cada barra)
```

**Regra:** PnL calculado usando mesma fórmula do TradingEnv (spread, slippage, comissão do treino).

### 3.5 Posição Real (Executor)

**Estrutura recebida do Connector:**
```
ticket          : int
symbol          : str
direction       : int (-1, 0, 1)
size            : float
entry_price     : float
current_price   : float
pnl             : float
sl              : float
tp              : float
comment         : str
```

---

## 4. Contratos de Comunicação

### 4.1 Protocolo WebSocket

**Formato geral:** Texto plano com delimitador `|`

**Razão:** Simplicidade, legibilidade em logs, baixo overhead de parsing.

### 4.2 Mensagens: Connector → Preditor

#### OHLCV (Barra completa ou tick)
```
OHLCV|{symbol}|{time}|{open}|{high}|{low}|{close}|{volume}
```
Exemplo:
```
OHLCV|EURUSD|1706961600|1.08542|1.08567|1.08521|1.08553|1234
```

#### Dados de Conta
```
ACCOUNT|{balance}|{equity}|{margin}|{free_margin}
```
Exemplo:
```
ACCOUNT|10234.56|10312.45|125.00|10187.45
```

#### Posições Abertas
```
POSITIONS|{json_array}
```
Exemplo:
```
POSITIONS|[{"ticket":123,"symbol":"EURUSD","dir":1,"size":0.03,"pnl":12.50}]
```

### 4.3 Mensagens: Preditor → Executor

#### Sinal de Trade
```
SIGNAL|{symbol}|{action}|{hmm_state}|{virtual_pnl}
```

Onde `action` é o nome da ação (nomenclatura semântica):
- `WAIT` (ficar de fora)
- `LONG_WEAK`, `LONG_MODERATE`, `LONG_STRONG`
- `SHORT_WEAK`, `SHORT_MODERATE`, `SHORT_STRONG`

Exemplo:
```
SIGNAL|EURUSD|LONG_WEAK|3|0.00
SIGNAL|EURUSD|WAIT|2|-15.30
SIGNAL|GBPUSD|SHORT_STRONG|1|25.40
```

### 4.4 Mensagens: Executor → Preditor

#### ACK (Confirmação)
```
ACK|{symbol}|{action}|{status}|{details}
```

Status possíveis:
- `OK` - Ordem executada
- `FAIL` - Ordem rejeitada
- `SKIP` - Símbolo desabilitado ou já sincronizado
- `WAIT_SYNC` - Aguardando sincronização (entrada perdida)

Exemplos:
```
ACK|EURUSD|LONG_WEAK|OK|T:12345|P:1.08542|SLIP:0.00003
ACK|EURUSD|LONG_MODERATE|FAIL|MARGIN
ACK|EURUSD|WAIT|OK|T:12345|PNL:23.45
ACK|GBPUSD|LONG_MODERATE|SKIP|DISABLED
ACK|USDJPY|LONG_STRONG|WAIT_SYNC|MISSED_ENTRY
```

**Uso do ACK:** Apenas para log. Preditor não altera posição virtual baseado no ACK.

### 4.5 Mensagens: Comandos Manuais

#### Fechar posição específica
```
CMD|CLOSE|{symbol}
```

#### Fechar todas
```
CMD|CLOSE_ALL
```

#### Pausar/Retomar
```
CMD|PAUSE
CMD|RESUME
```

#### Status
```
CMD|STATUS
```

Resposta:
```
STATUS|{json_com_estado_completo}
```

---

## 5. Fluxos de Operação

### 5.1 Fluxo: Inicialização (e Recuperação de Crash)

**Comportamento único:** Inicialização e recuperação de crash seguem o mesmo fluxo.

```
1. ORQUESTRADOR inicia
   │
2. CONNECTOR conecta ao cTrader
   │ Se falhar: retry com backoff exponencial
   │
3. CONNECTOR baixa histórico (1 semana M15 ≈ 670 barras por símbolo)
   │
4. PREDITOR para cada modelo carregado:
   │ a. Carrega ZIP e extrai metadata do header
   │ b. Cria DataFrame com histórico recebido
   │ c. Executa fase de aquecimento (Total: 1000 barras):
   │    - Histórico carregado: Últimas 1000 barras.
   │    - Estabilização: Primeiras 350 barras (apenas cálculo, sem sinais).
   │    - Fast Forward: Próximas 650 barras (simulação de trading para alinhar estado).
   │    - Janela de Predição: Preditor mantém sempre as últimas 350 barras na memória.
   │ d. Estado final: posição virtual e indicadores prontos.
   │
5. EXECUTOR carrega config por símbolo
   │ a. Se símbolo não existe na config: criar com defaults (enabled=false)
   │ b. Consulta posições abertas no cTrader
   │
6. SINCRONIZAÇÃO inicial:
   │ - Executor NÃO fecha ordens automaticamente
   │ - Sincronização ocorre quando Preditor enviar sinal divergente
   │   (ver seção 6 - Critérios de Sincronização)
   │
7. PAPER inicia com mesmo histórico do Preditor
   │
8. Sistema entra em modo RUNNING
```

### 5.2 Fluxo: Ciclo Normal (Nova Barra)

```
1. CONNECTOR detecta nova barra
   │ (método: polling ou broadcast - ver seção 8)
   │
2. CONNECTOR envia OHLCV para PREDITOR
   │
3. PREDITOR para cada símbolo com modelo:
   │ a. Atualiza FIFO com nova barra
   │ b. Calcula features HMM
   │ c. Prediz estado HMM
   │ d. Calcula features RL (inclui posição virtual)
   │ e. Prediz ação PPO
   │ f. Atualiza posição virtual conforme ação
   │    - Mesmo tamanho e direção → mantém
   │    - Qualquer mudança → fecha tudo + abre novo (se aplicável)
   │ g. Envia SIGNAL para EXECUTOR
   │
4. EXECUTOR para cada SIGNAL recebido:
   │ a. Verifica se símbolo está enabled
   │ b. Aplica critérios de sincronização (seção 6)
   │ c. Se deve executar:
   │    - Mapeia intensidade → lote da config
   │    - Valida margem
   │    - Envia ordem ao CONNECTOR
   │    - Monta comentário estruturado
   │ d. Envia ACK ao PREDITOR
   │
5. PAPER recebe mesmo SIGNAL
   │ a. Aplica MESMA lógica de sincronização do Executor (seção 6).
   │ b. Executa em ambiente simulado (TradingEnv).
   │ c. Registra trade com is_paper=true.
   │
6. CONNECTOR confirma execução
   │
7. Ciclo aguarda próxima barra
```

### 5.3 Fluxo: Fechamento de Ordem (Externo)

Quando ordem é fechada fora do sistema (SL, TP, manual no cTrader):

```
1. CONNECTOR detecta ordem fechada (via polling ou evento)
   │
2. CONNECTOR notifica EXECUTOR
   │ CLOSED|{symbol}|{ticket}|{pnl}|{reason}
   │
3. EXECUTOR registra em log
   │
4. PREDITOR não é notificado diretamente
   │ (sincronização ocorre no próximo sinal - seção 6)
```

---

## 6. Critérios de Sincronização (A Regra de Ouro)

O mecanismo de sincronização garante que o Executor nunca opere de forma errática após restarts ou conexões perdidas. A lógica baseia-se na comparação simples entre o **SINAL DO PREDITOR** e a **POSIÇÃO REAL**.

### 6.1 Lógica de Decisão

O Executor avalia a cada sinal recebido:

| Posição Real | Sinal Preditor | Estado | Ação |
|--------------|----------------|--------|------|
| **Igual** | **Igual** | Sincronizado | **NADA** (Mantém posição) |
| **Aberta** | **Diferente** | Desalinhado / Reversão | **FECHAR IMEDIATAMENTE** |
| **FLAT** | **Posicionado** | Perdeu Entrada | **AGUARDAR** (Modo Espera) |

### 6.2 Detalhamento dos Cenários

#### Cenário 1: Sincronizado (Igual)
- Se `Real == Sinal`, o sistema está no estado correto. Nenhuma ação é necessária.

#### Cenário 2: Desalinhamento (Real Aberta != Sinal)
- **Situação:** O sistema tem uma ordem aberta, mas o Preditor mudou de ideia (foi para WAIT ou inverteu a mão).
- **Significado:** A posição atual não é mais válida segundo o modelo.
- **Ação:** O Executor fecha a posição imediatamente.
  - Se o novo sinal for WAIT, termina aí.
  - Se o novo sinal for uma inversão, a ordem de abertura será processada no próximo ciclo (ver Cenário 3/Regra de Borda).

#### Cenário 3: Entrada Perdida (Real FLAT != Sinal Posicionado)
- **Situação:** O Executor está zerado (ex: acabou de ligar, ou foi estopado externamente), mas o Preditor indica estar comprado/vendido (meio de um movimento).
- **Significado:** "O bonde já passou". Entrar agora seria arriscado (Risco/Retorno ruim).
- **Ação:** O Executor entra em modo de **ESPERA**.
  - Ignora todos os sinais repetidos daquela direção.
  - Aguarda até receber **qualquer sinal diferente do anterior** (início de um novo movimento ou retorno para WAIT).
  - Somente na **borda** da mudança de sinal (transição) uma nova entrada é permitida.

### 6.3 Ordens Fechadas Externamente (Stop Loss / Manual)
- O comportamento é idêntico ao Cenário 3.
- Ao detectar que a ordem fechou (Real = FLAT) enquanto o Preditor continua mandando manter (Sinal = Posicionado), o sistema cai na regra de "Entrada Perdida".
- Ele **não** reabre a ordem imediatamente. Ele espera o Preditor sinalizar o fim daquele movimento ou uma inversão.

### 6.4 Ordens Órfãs
Se o Executor encontrar uma ordem aberta para um símbolo que **não** tem modelo carregado (Preditor inativo para ele):
- Mantém a ordem aberta (não mexe no que não conhece).
- Emite alerta de "Ordem Órfã".
- Requer intervenção manual (`CMD|CLOSE`).

---

## 7. Métricas e Comentário de Ordem

### 7.1 Fonte Primária de Métricas

**cTrader histórico de ordens.** Persistido pela corretora, sem custo de infraestrutura.

### 7.2 Dados Extras (Comentário Estruturado)

Campos que cTrader não persiste mas são úteis para análise:

| Campo | Sigla | Descrição | Uso |
|-------|-------|-----------|-----|
| Versão | V | Versão do sistema | Rastrear bugs por versão |
| HMM State | H | Estado HMM na entrada | Análise por regime |
| Action Index | A | Índice da ação (0-6) | Debug |
| Intensity | I | Intensidade do sinal (1-3) | Análise de confiança |
| Balance | B | Balance no momento | Curva de equity |
| Drawdown | D | DD% no momento | Análise de risco |
| Virtual PnL | VP | PnL virtual do Preditor | Medir drift |
| Spread Real | SR | Spread no momento | Ajuste fino |
| Slippage | SL | Slippage sofrido | Ajuste fino |

### 7.3 Formato do Comentário

```
ORC|V:{version}|H:{hmm}|A:{action}|I:{intensity}|B:{balance}|D:{dd}|VP:{vpnl}
```

**Limite:** cTrader permite 100 caracteres. Formato compacto se necessário.

**Formato compacto:**
```
O|{V}|{H}|{A}|{I}|{B}|{D}|{VP}
```

Exemplo:
```
O|2.0|3|1|1|10234|0.5|0.00
```

Significado: Oracle 2.0, HMM state 3, action LONG_WEAK, intensity 1, balance $10234, DD 0.5%, virtual PnL $0.00

### 7.4 Métricas Derivadas (Pós-Processamento)

Extraídas do histórico cTrader + comentário:

| Métrica | Fonte | Uso |
|---------|-------|-----|
| Win Rate por HMM State | Comentário (H) | Identificar estados lucrativos |
| Win Rate por Intensidade | Comentário (I) | Validar força do sinal |
| PnL por Hora/Dia | cTrader timestamp | Identificar horários ruins |
| Drift (Real vs Virtual) | Comentário (VP) vs PnL real | Qualidade da execução |
| Slippage Médio | Comentário (SL) | Ajuste de spread no treino |
| Performance por Modelo | Comentário (MH) | Comparar versões |
| Drawdown Máximo | Comentário (D) sequencial | Risco real vs treino |

---

## 8. Definições Técnicas (cTrader Open API)

Especificações validadas para a implementação do Connector.

| # | Item | Especificação |
|---|------|---------------|
| 1 | **Método OHLCV** | Broadcast (Stream). Usar `SubscribeSpot` ou detectar virada de tempo localmente. |
| 2 | **Latência Histórico** | < 200ms (Protobuf). |
| 3 | **Limite Comentário** | 100 caracteres (Label) e 512 (Comment). |
| 4 | **Rate Limits** | 50 req/s (Live) e 5 req/s (Histórico). |
| 5 | **Autenticação** | OAuth 2.0. Refresh Token a cada 30 dias. |
| 6 | **Eventos** | Não há "New Bar" explícito. Monitorar `ProtoOATrendbar` ou detectar localmente. |
| 7 | **Timestamp** | Precisão em milissegundos (Unix Timestamp). |

---

## 9. Assinaturas de Módulos

### 9.1 Connector

```python
class Connector:
    # Conexão
    async def connect(credentials: dict) -> bool
    async def disconnect() -> None
    def is_connected() -> bool
    
    # Dados de Mercado
    async def get_ohlcv(symbol: str, timeframe: str, bars: int) -> DataFrame
    async def subscribe_bars(symbol: str, timeframe: str, callback: Callable) -> None
    
    # Dados de Conta
    async def get_account() -> AccountInfo
    async def get_positions() -> List[Position]
    async def get_order_history(since: datetime) -> List[Order]
    
    # Execução
    async def open_order(symbol: str, direction: int, size: float, 
                         sl: float, tp: float, comment: str) -> OrderResult
    async def close_order(ticket: int) -> OrderResult
    async def modify_order(ticket: int, sl: float, tp: float) -> OrderResult
```

### 9.2 Preditor

```python
class Preditor:
    # Inicialização
    def load_model(zip_path: str) -> bool
    def unload_model(symbol: str) -> bool
    def list_models() -> List[str]
    
    # Warmup
    def warmup(symbol: str, df: DataFrame) -> None
    
    # Ciclo
    def process_bar(symbol: str, bar: dict) -> Signal
    def get_virtual_position(symbol: str) -> VirtualPosition
    
    # Estado
    def get_state() -> dict

@dataclass
class Signal:
    symbol: str
    action: str  # WAIT, LONG_WEAK, LONG_MODERATE, LONG_STRONG, SHORT_*
    direction: int  # -1, 0, 1
    intensity: int  # 0, 1, 2, 3
    hmm_state: int
    virtual_pnl: float
```

### 9.3 Executor

```python
class Executor:
    # Configuração
    def load_config(path: str) -> None
    def get_symbol_config(symbol: str) -> SymbolConfig
    def set_symbol_config(symbol: str, config: SymbolConfig) -> None
    
    # Processamento
    async def process_signal(signal: Signal) -> ACK
    
    # Controle
    def pause() -> None
    def resume() -> None
    async def close_position(symbol: str) -> bool
    async def close_all() -> int
    
    # Estado
    def get_state() -> dict

@dataclass
class SymbolConfig:
    enabled: bool
    lot_weak: float
    lot_moderate: float
    lot_strong: float
    sl_usd: float
    tp_usd: float
```

### 9.4 Paper

```python
class Paper:
    # Inicialização
    def load_config(training_config: dict) -> None
    
    # Ciclo
    def process_signal(signal: Signal, current_bar: dict) -> PaperTrade
    
    # Métricas
    def get_metrics() -> dict
    def get_trades() -> List[PaperTrade]
    def compare_with_real(real_trades: List[Trade]) -> DriftReport
```

---

## 10. Checklist de Validação

Antes de considerar a especificação completa:

- [x] Nomenclatura semântica (WAIT, WEAK/MODERATE/STRONG)
- [x] Todos os campos do ZIP header definidos
- [x] Todos os tipos de mensagem WS documentados
- [x] Matriz de sincronização completa
- [x] Mapeamento de intensidade → lotes documentado
- [ ] Formato do comentário validado (limite de caracteres)
- [ ] Scripts de descoberta cTrader executados
- [ ] Assinaturas de módulos revisadas

---

## Histórico de Revisões

| Data | Versão | Alterações |
|------|--------|------------|
| 2026-02-03 | 1.0 | Versão inicial |
| 2026-02-03 | 1.1 | Nomenclatura semântica (WAIT, WEAK/MODERATE/STRONG), mapeamento de intensidade |

---

*Documento gerado como especificação de planejamento. Implementação deve seguir contratos e assinaturas definidos.*
