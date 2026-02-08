# 🏗️ Oracle Trader v2.0 - Arquitetura de Alta Disponibilidade

**Status:** Especificação Técnica Final (Revisada v1.1)

**Ambiente:** Oracle Cloud E2.1.Micro (1GB RAM) | cTrader Open API | Python 3.10+

---

## 🔍 1. Diagnóstico e Resolução Central

### Problema: O "Drift" de Estado (Cérebro vs. Realidade)

O modelo PPO é treinado em um **"Ambiente Perfeito"** onde a ação decidida é a ação executada. Na v1, o filtro de risco causava um paradoxo:

* **Modelo:** Decidi comprar → "Acho que estou comprado".
* **Código v1:** Bloqueei a compra (Risco/Spread) → "Não comprei".
* **Resultado:** No próximo candle, o modelo recebe a feature de posição `0` (FLAT), entra em estado de confusão (out-of-distribution) e gera sinais inválidos.

### Solução v2.0: O Preditor como "Digital Twin"

O **Preditor** passa a ser um emulador puro do ambiente de treino (`TradingEnv`). Ele ignora a realidade do broker e mantém uma **Posição Virtual**. O **Executor** atua como um filtro passivo que decide se a vontade do "Cérebro" pode ser realizada no mundo real.

### Glossário de Termos Críticos

| Termo | Significado | Onde é usado |
|-------|-------------|--------------|
| **FLAT** | Estado da feature de posição = 0 (sem posição) | Feature `position_direction` no modelo |
| **WAIT** | Sinal/Ação = "ficar de fora" (ação índice 0) | Saída do modelo PPO |
| **Intensidade** | Força do sinal (1=WEAK, 2=MODERATE, 3=STRONG) | Mapeado para lotes pelo Executor |

---

## 🏛️ 2. Arquitetura Multi-Processo (Isolamento de RAM)

Para rodar 20 modelos em 1GB, dividimos o monólito em processos leves que se comunicam via **WebSocket Local**.

### A. PREDITOR (O Cérebro)

* **Função:** Mantém 20 instâncias de `(HMM + PPO + VirtualEnv)`.
* **Estado:** Mantém `virtual_position` e `fifo_buffer` (350 barras).
* **Gatilho:** Recebe evento de `New Bar` via WebSocket.
* **Memória:** ~250MB (Carrega PyTorch CPU e Pesos).
* **Resiliência:** Em caso de crash, realiza **Fast-Forward Warmup** (reprocessa as 350 barras para reconstruir o estado virtual antes do próximo sinal).

**Lógica de Posição Virtual (idêntica ao TradingEnv):**
```python
def execute_action(self, target_dir, target_intensity):
    # Mesmo tamanho e direção → mantém
    if target_dir == self.position_direction and target_intensity == self.position_intensity:
        return
    
    # QUALQUER mudança → fecha tudo primeiro
    if self.position_direction != 0:
        self._close_position()
    
    # Abre nova se não for WAIT
    if target_dir != 0:
        self._open_position(target_dir, target_intensity)
```

**Importante:** Não existe fechamento parcial. Mudança de intensidade = fecha + abre.

### B. EXECUTOR (As Mãos)

* **Função:** Interface assíncrona com **cTrader Open API**.
* **Lógica:** Recebe o `SIGNAL`, mapeia intensidade → lote, checa `Equity`, `Drawdown` e `Slippage`.
* **Modo Paper:** Pode rodar em paralelo ao Live para comparar o *Drift* entre a Posição Virtual e a Real.
* **Memória:** ~80MB (Sem PyTorch, apenas WebSockets e Protobuf).

**Mapeamento de Intensidade → Lotes (configurável por símbolo):**

| Intensidade | Nome do Sinal | Default | US500 | AAPL |
|-------------|---------------|---------|-------|------|
| 1 | WEAK | 0.01 | 0.10 | 1 |
| 2 | MODERATE | 0.03 | 0.30 | 3 |
| 3 | STRONG | 0.05 | 0.50 | 5 |

---

## 📦 3. O "Modelo Atômico" (ZIP + Metadata)

O arquivo `.zip` agora é a **única fonte de verdade**. Nenhuma configuração fica no servidor; tudo viaja com o modelo.

### Estrutura do Arquivo

```
EURUSD_M15.zip
├── EURUSD_M15_hmm.pkl
└── EURUSD_M15_ppo.zip
```

**Header do ZIP (`zip.comment`):** JSON com metadados completos.

### Metadados Críticos (Inclusos no JSON)

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
    "lot_sizes": [0, 0.01, 0.03, 0.05]
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
  }
}
```

---

## 📡 4. Protocolo de Sincronia e Tempo

### Sincronização NTP (Essencial para Abertura)

Para garantir que a execução de **Abertura** seja precisa:

1. **Chrony/NTP:** Ativo na Oracle Cloud para garantir erro de relógio < 10ms.
2. **Gatilho de Execução:** O Preditor processa o sinal no segundo `01` do candle para garantir que o cTrader já processou o fechamento da barra anterior.

### Comunicação IPC (Inter-Process Communication)

* **Transporte:** `websockets` (Python lib).
* **Formato:** Texto plano com delimitador `|`.
* **Latência:** < 5ms (via localhost).

### Formato das Mensagens

```
# Preditor → Executor
SIGNAL|EURUSD|LONG_WEAK|3|0.00
SIGNAL|EURUSD|WAIT|2|-15.30
SIGNAL|GBPUSD|SHORT_STRONG|1|25.40

# Executor → Preditor (ACK)
ACK|EURUSD|LONG_WEAK|OK|T:12345|P:1.08542
ACK|EURUSD|LONG_MODERATE|FAIL|MARGIN
ACK|USDJPY|LONG_STRONG|WAIT_SYNC|MISSED_ENTRY
```

---

## ⚙️ 5. Gestão de Recursos (Oracle 1GB RAM)

| Técnica | Implementação |
| --- | --- |
| **Swap** | Arquivo de 2GB em SSD (Prevenção de OOM Killer). |
| **Inference Mode** | `torch.no_grad()` e `policy.eval()` ativos. |
| **Garbage Collection** | `gc.collect()` após o loop de 20 modelos a cada 15 min. |
| **cTrader API** | Substitui o peso do MT5/Wine por uma conexão WebSocket pura. |

---

## 📅 6. Plano de Migração e Implementação

### Fase 1: Refatoração do Notebook (Salvamento)

* Implementar salvamento com `zip.comment` contendo JSON de metadados.
* Usar nomenclatura semântica: WAIT, WEAK/MODERATE/STRONG.
* Incluir `intensity` ao invés de `size` nas actions.

### Fase 2: O Preditor "Digital Twin"

* Desenvolver o loop que mantém a posição virtual independente do que o executor faça.
* Implementar a lógica de **Warmup FIFO (350 barras)** na inicialização.
* Garantir que a lógica de posição seja idêntica ao `TradingEnv`:
  - Sem fechamento parcial
  - Mudança de intensidade = fecha + abre

### Fase 3: O Executor cTrader (Async)

* Criar o cliente assíncrono para a Open API da FTMO/Spotware.
* Implementar mapeamento de intensidade → lotes por símbolo.
* Implementar a "Cerca de Proteção" (Risk Guard) que apenas lê os sinais e valida o capital.

### Fase 4: Config por Símbolo

* Implementar `executor_config.json` com mapeamento de lotes.
* Defaults para novos modelos: `enabled=false`, lotes padrão.
* Exemplos:
  ```json
  {
    "EURUSD": { "lot_weak": 0.01, "lot_moderate": 0.03, "lot_strong": 0.05 },
    "US500":  { "lot_weak": 0.10, "lot_moderate": 0.30, "lot_strong": 0.50 },
    "AAPL":   { "lot_weak": 1, "lot_moderate": 3, "lot_strong": 5 }
  }
  ```

---

## ✅ Critérios de Sucesso (KPIs)

1. **Sincronia de Posição:** A `virtual_position` do Preditor deve ser idêntica à posição do Backtest em 100% do tempo.
2. **Uso de RAM:** O sistema completo (Preditor + Executor) deve manter-se abaixo de **600MB** estáveis.
3. **Latência de Execução:** Tempo entre `New Bar` e `Order Sent` < 100ms para todos os 20 ativos.
4. **Mapeamento Correto:** Intensidade do sinal deve ser mapeada corretamente para lotes por símbolo.

---

## Histórico de Revisões

| Data | Versão | Alterações |
|------|--------|------------|
| 2026-02-03 | 1.0 | Versão inicial |
| 2026-02-03 | 1.1 | Nomenclatura semântica (WAIT, WEAK/MODERATE/STRONG), mapeamento de intensidade, config por símbolo |
