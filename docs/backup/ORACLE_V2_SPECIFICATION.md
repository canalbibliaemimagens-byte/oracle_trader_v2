# 🏗️ Oracle Trader v2.0 - Especificação de Contratos e Fluxos

**Versão:** 1.0  
**Data:** 2026-02-03  
**Status:** Documento de Planejamento  

---

## 📋 Índice

1. [Visão Geral e Princípios](#1-visão-geral-e-princípios)
2. [Arquitetura de Módulos](#2-arquitetura-de-módulos)
3. [Contratos de Dados](#3-contratos-de-dados)
4. [Contratos de Comunicação](#4-contratos-de-comunicação)
5. [Fluxos de Operação](#5-fluxos-de-operação)
6. [Critérios de Sincronização](#6-critérios-de-sincronização)
7. [Métricas e Comentário de Ordem](#7-métricas-e-comentário-de-ordem)
8. [Pontos a Definir (cTrader)](#8-pontos-a-definir-ctrader)

---

## 1. Visão Geral e Princípios

### 1.1 Objetivo

Sistema de trading autônomo baseado em modelos HMM+PPO, independente de sistema operacional, com separação total entre predição e execução.

### 1.2 Princípios Fundamentais

| Princípio | Descrição |
|-----------|-----------|
| **Isolamento Total** | Preditor não conhece conta real. Executor não conhece modelos. |
| **Identidade Treino-Execução** | Features e LOT_SIZES do Preditor são idênticos ao notebook de treino. |
| **Configuração Explícita** | Sem tabelas de conversão. Usuário configura cada símbolo. Defaults fixos. |
| **Simplicidade sobre Flexibilidade** | Menos código = menos bugs silenciosos. |
| **Posição Virtual** | Preditor mantém estado interno independente da realidade. |
| **Métricas na Plataforma** | cTrader como fonte primária. Comentário estruturado para dados extras. |

### 1.3 Decisões Arquiteturais Fixas

- **Broker:** cTrader Open API (independente de SO)
- **LOT_SIZES Preditor:** `[0, 0.01, 0.03, 0.05]` (hardcoded, igual treino)
- **SL/TP:** Sempre em valor monetário (USD). Zero = desativado.
- **Defaults Executor:** SL=$10, TP=$10, Lotes=[0.01, 0.03, 0.05]
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
- Stream de dados OHLCV (a cada segundo ou broadcast - **A DEFINIR**)
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
- Comandos de sinal via WebSocket
- Estado interno para debug/log

**Características:**
- LOT_SIZES hardcoded: `[0, 0.01, 0.03, 0.05]`
- Mantém posição virtual por símbolo
- Calcula features idênticas ao treino
- Janela deslizante FIFO interna (mínimo 1 semana M15 = ~670 barras)
- Não conhece conta real, spread real, margem

**NÃO faz:**
- Comunicação com broker
- Validação de margem/risco
- Conversão de lotes

### 2.4 Módulo EXECUTOR (Mãos)

**Responsabilidade:** Receber sinais, validar, enviar ordens ao Connector.

**Entradas:**
- Comandos de sinal do Preditor
- Configuração por símbolo (lotes, SL, TP)
- Dados de conta (do Connector)

**Saídas:**
- Ordens para o Connector
- ACK para o Preditor (log)
- Comentário estruturado na ordem

**Características:**
- Configuração JSON por símbolo
- Defaults fixos: SL=$10, TP=$10, Lotes=[0.01, 0.03, 0.05]
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
- Mesmos comandos que o Executor recebe
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
    "0": {"name": "FLAT", "direction": 0, "size": 0},
    "1": {"name": "LONG_SMALL", "direction": 1, "size": 0.01},
    "2": {"name": "LONG_MEDIUM", "direction": 1, "size": 0.03},
    "3": {"name": "LONG_LARGE", "direction": 1, "size": 0.05},
    "4": {"name": "SHORT_SMALL", "direction": -1, "size": 0.01},
    "5": {"name": "SHORT_MEDIUM", "direction": -1, "size": 0.03},
    "6": {"name": "SHORT_LARGE", "direction": -1, "size": 0.05}
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
  "EURUSD": {
    "enabled": true,
    "lot_small": 0.01,
    "lot_medium": 0.03,
    "lot_large": 0.05,
    "sl_usd": 10.0,
    "tp_usd": 0,
    "notes": "Configurado em 2026-02-03"
  },
  "US500.cash": {
    "enabled": true,
    "lot_small": 0.10,
    "lot_medium": 0.30,
    "lot_large": 0.50,
    "sl_usd": 15.0,
    "tp_usd": 0,
    "notes": "Índice - lotes maiores"
  }
}
```

**Regra de criação:** Quando um modelo é carregado e não existe config, criar entrada com defaults:
- `enabled`: false (usuário deve habilitar explicitamente)
- `lot_small`: 0.01
- `lot_medium`: 0.03
- `lot_large`: 0.05
- `sl_usd`: 10.0
- `tp_usd`: 10.0

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
direction       : int (-1, 0, 1)
size            : float (0.01, 0.03, 0.05)
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

Onde `action` é o nome da ação:
- `FLAT`
- `LONG_SMALL`, `LONG_MEDIUM`, `LONG_LARGE`
- `SHORT_SMALL`, `SHORT_MEDIUM`, `SHORT_LARGE`

Exemplo:
```
SIGNAL|EURUSD|LONG_SMALL|3|0.00
SIGNAL|EURUSD|FLAT|2|-15.30
SIGNAL|GBPUSD|SHORT_LARGE|1|25.40
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

Exemplos:
```
ACK|EURUSD|LONG_SMALL|OK|T:12345|P:1.08542|SLIP:0.00003
ACK|EURUSD|LONG_SMALL|FAIL|MARGIN
ACK|EURUSD|FLAT|OK|T:12345|PNL:23.45
ACK|GBPUSD|LONG_MEDIUM|SKIP|DISABLED
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
   │ (método de detecção: A DEFINIR - polling ou broadcast)
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
   │ g. Envia SIGNAL para EXECUTOR
   │
4. EXECUTOR para cada SIGNAL recebido:
   │ a. Verifica se símbolo está enabled
   │ b. Aplica critérios de sincronização (seção 6)
   │ c. Se deve executar:
   │    - Converte tamanho (SMALL→lot_small da config)
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

### 6. Fluxo de Sincronização (A Regra de Ouro)

O mecanismo de sincronização garante que o Executor nunca opere de forma errática após restarts ou conexões perdidas. A lógica baseia-se na comparação simples entre o **SINAL DO PREDITOR** e a **POSIÇÃO REAL**.

### 6.1 Lógica de Decisão

O Executor avalia a cada sinal recebido:

| Posição Real | Sinal Preditor | Estado | Ação |
|--------------|----------------|--------|------|
| **Igual**    | **Igual**      | Sincronizado | **NADA** (Mantém posição) |
| **Aberta**   | **Diferente**  | Desalinhado / Reversão | **FECHAR IMEDIATAMENTE** |
| **FLAT**     | **Diferente** (Posicionado) | Perdeu Entrada | **AGUARDAR** (Modo Espera) |

### 6.2 Detalhamento dos Cenários

#### Cenário 1: Sincronizado (Igual)
*   Se `Real == Sinal`, o sistema está no estado correto. Nenhuma ação é necessária.

#### Cenário 2: Desalinhamento (Real Aberta != Sinal)
*   **Situação:** O sistema tem uma ordem aberta, mas o Preditor mudou de ideia (foi para FLAT ou inverteu a mão).
*   **Significado:** A posição atual não é mais válida segundo o modelo.
*   **Ação:** O Executor fecha a posição imediatamente.
    *   Se o novo sinal for FLAT, termina aí.
    *   Se o novo sinal for uma inversão, a ordem de abertura será processada no próximo ciclo (ver Cenário 3/Regra de Borda).

#### Cenário 3: Entrada Perdida (Real FLAT != Sinal Posicionado)
*   **Situação:** O Executor está zerado (ex: acabou de ligar, ou foi estopado externamente), mas o Preditor indica estar comprado/vendido (meio de um movimento).
*   **Significado:** "O bonde já passou". Entrar agora seria arriscado (Risco/Retorno ruim).
*   **Ação:** O Executor entra em modo de **ESPERA**.
    *   Ignora todos os sinais repetidos daquela direção.
    *   Aguarda até receber **qualquer sinal diferente do anterior** (início de um novo movimento ou retorno para FLAT).
    *   Somente na **borda** da mudança de sinal (transição) uma nova entrada é permitida.

#### 6.3 Ordens Fechadas Externamente (Stop Loss / Manual)
*   O comportamento é idêntico ao Cenário 3.
*   Ao detectar que a ordem fechou (Real = FLAT) enquanto o Preditor continua mandando manter (Sinal = Posicionado), o sistema cai na regra de "Entrada Perdida".
*   Ele **não** reabre a ordem imediatamente. Ele espera o Preditor sinalizar o fim daquele movimento ou uma inversão.

#### 6.4 Ordens Órfãs
Se o Executor encontrar uma ordem aberta para um símbolo que **não** tem modelo carregado (Preditor inativo para ele):
*   Mantém a ordem aberta (não mexe no que não conhece).
*   Emite alerta de "Ordem Órfã".
*   Requer intervenção manual (`CMD|CLOSE`).

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
| Balance | B | Balance no momento | Curva de equity |
| Drawdown | D | DD% no momento | Análise de risco |
| Virtual PnL | VP | PnL virtual do Preditor | Medir drift |
| Spread Real | SR | Spread no momento | Ajuste fino |
| Slippage | SL | Slippage sofrido | Ajuste fino |
| Cycle | C | Número do ciclo | Debug |
| Model Hash | MH | Hash curto do modelo | Identificar versão do modelo |

### 7.3 Formato do Comentário

```
ORC|V:{version}|H:{hmm}|A:{action}|B:{balance}|D:{dd}|VP:{vpnl}|SR:{spread}|SL:{slip}|C:{cycle}|MH:{hash}
```

**Limite:** cTrader permite ~31 caracteres. Ajustar conforme necessário.

**Formato compacto (se necessário):**
```
O|{V}|{H}|{A}|{B}|{D}|{VP}
```

Exemplo:
```
O|2.0|3|1|10234|0.5|0.00
```

Significado: Oracle 2.0, HMM state 3, action LONG_SMALL, balance $10234, DD 0.5%, virtual PnL $0.00

### 7.4 Métricas Derivadas (Pós-Processamento)

Extraídas do histórico cTrader + comentário:

| Métrica | Fonte | Uso |
|---------|-------|-----|
| Win Rate por HMM State | Comentário (H) | Identificar estados lucrativos |
| PnL por Hora/Dia | cTrader timestamp | Identificar horários ruins |
| Drift (Real vs Virtual) | Comentário (VP) vs PnL real | Qualidade da execução |
| Slippage Médio | Comentário (SL) | Ajuste de spread no treino |
| Performance por Modelo | Comentário (MH) | Comparar versões |
| Drawdown Máximo | Comentário (D) sequencial | Risco real vs treino |
| Profit Factor por Regime | H + PnL real | Ajuste fino do HMM |

### 7.5 Script de Extração (Especificação)

**Entrada:** Histórico de ordens do cTrader (CSV ou API)

**Saída:** DataFrame com colunas expandidas do comentário

**Assinatura:**
```
parse_order_history(orders: List[Order]) -> DataFrame
```

---

## 8. Definições Técnicas (cTrader Open API)

Especificações validadas para a implementação do Connector.

| # | Item | Especificação Oficial / Decisão |
|---|---|---|
| 1 | **Método OHLCV** | **Broadcast (Stream).** Usar `SubscribeSpot` para dados tick-a-tick ou eventos de barra quando disponíveis. Polling é desencorajado. |
| 2 | **Latência Histórico** | **< 200ms** (Protobuf). Extremamente rápido. Não afeta significativamente o tempo de boot. |
| 3 | **Limite Comentário** | **100 caracteres** (Label) e 512 (Comment). Usaremos limite de segurança de **100 chars**. |
| 4 | **Rate Limits** | 50 req/s (Live) e 5 req/s (Histórico). Suficiente. |
| 5 | **Autenticação** | **OAuth 2.0**. Requer gestão de *Refresh Token* a cada 30 dias. |
| 6 | **Eventos** | Não há "New Bar" explícito. Monitorar `ProtoOATrendbar` no stream ou detectar virada de tempo localmente. Ordem fechada gera `ORDER_FILLED`. |
| 7 | **Timestamp** | Precisão em **milissegundos** (Unix Timestamp). |

### 8.2 Scripts de Descoberta (a criar)

Após receber token cTrader:

1. **test_connection.py** - Testar autenticação
2. **test_history_download.py** - Medir tempo de download de 1 semana M15
3. **test_order_execution.py** - Testar envio de ordem (conta demo)
4. **test_comment_length.py** - Verificar limite de caracteres
5. **test_events.py** - Verificar quais eventos estão disponíveis

---

## 9. Assinaturas de Módulos

### 9.1 Connector

```
class Connector:
    # Conexão
    connect(credentials: dict) -> bool
    disconnect() -> None
    is_connected() -> bool
    
    # Dados de Mercado
    get_ohlcv(symbol: str, timeframe: str, bars: int) -> DataFrame
    subscribe_bars(symbol: str, timeframe: str, callback: Callable) -> None
    
    # Dados de Conta
    get_account() -> AccountInfo
    get_positions() -> List[Position]
    get_order_history(since: datetime) -> List[Order]
    
    # Execução
    open_order(symbol: str, direction: int, size: float, sl: float, tp: float, comment: str) -> OrderResult
    close_order(ticket: int) -> OrderResult
    modify_order(ticket: int, sl: float, tp: float) -> OrderResult
```

### 9.2 Preditor

```
class Preditor:
    # Inicialização
    load_model(zip_path: str) -> bool
    unload_model(symbol: str) -> bool
    list_models() -> List[str]
    
    # Warmup
    warmup(symbol: str, df: DataFrame) -> None
    
    # Ciclo
    process_bar(symbol: str, bar: dict) -> Signal
    get_virtual_position(symbol: str) -> VirtualPosition
    
    # Estado
    get_state() -> dict
```

### 9.3 Executor

```
class Executor:
    # Configuração
    load_config(path: str) -> None
    get_symbol_config(symbol: str) -> SymbolConfig
    set_symbol_config(symbol: str, config: SymbolConfig) -> None
    
    # Processamento
    process_signal(signal: Signal) -> ACK
    
    # Controle
    pause() -> None
    resume() -> None
    close_position(symbol: str) -> bool
    close_all() -> int
    
    # Estado
    get_state() -> dict
```

### 9.4 Paper

```
class Paper:
    # Inicialização
    load_config(training_config: dict) -> None
    
    # Ciclo
    process_signal(signal: Signal, current_bar: dict) -> PaperTrade
    
    # Métricas
    get_metrics() -> dict
    get_trades() -> List[PaperTrade]
    compare_with_real(real_trades: List[Trade]) -> DriftReport
```

---

## 10. Checklist de Validação

Antes de considerar a especificação completa:

- [ ] Todos os campos do ZIP header definidos
- [ ] Todos os tipos de mensagem WS documentados
- [ ] Matriz de sincronização completa
- [ ] Formato do comentário validado (limite de caracteres)
- [ ] Scripts de descoberta cTrader executados
- [ ] Assinaturas de módulos revisadas

---

## Histórico de Revisões

| Data | Versão | Alterações |
|------|--------|------------|
| 2026-02-03 | 1.0 | Versão inicial |

---

*Documento gerado como especificação de planejamento. Implementação deve seguir contratos e assinaturas definidos.*
