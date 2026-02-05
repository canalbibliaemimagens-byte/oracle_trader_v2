# 🏗️ Oracle Trader v2.0 - Arquitetura de Alta Disponibilidade

**Status:** Especificação Técnica Final (Revisada)

**Ambiente:** Oracle Cloud E2.1.Micro (1GB RAM) | cTrader Open API | Python 3.10+

---

## 🔍 1. Diagnóstico e Resolução Central

### Problema: O "Drift" de Estado (Cérebro vs. Realidade)

O modelo PPO é treinado em um **"Ambiente Perfeito"** onde a ação decidida é a ação executada. Na v1, o filtro de risco (v2.407 linhas) causava um paradoxo:

* **Modelo:** Decidi comprar → "Acho que estou comprado".
* **Código v1:** Bloqueei a compra (Risco/Spread) → "Não comprei".
* **Resultado:** No próximo candle, o modelo recebe a feature de posição `0` (Flat), entra em estado de confusão (out-of-distribution) e gera sinais inválidos.

### Solução v2.0: O Preditor como "Digital Twin"

O **Preditor** passa a ser um emulador puro do ambiente de treino (`TradingEnv`). Ele ignora a realidade do broker e mantém uma **Posição Virtual**. O **Executor** atua como um filtro passivo que decide se a vontade do "Cérebro" pode ser realizada no mundo real.

---

## 🏛️ 2. Arquitetura Multi-Processo (Isolamento de RAM)

Para rodar 20 modelos em 1GB, dividimos o monólito em processos leves que se comunicam via **WebSocket Local**.

### A. PREDITOR (O Cérebro)

* **Função:** Mantém 20 instâncias de `(HMM + PPO + VirtualEnv)`.
* **Estado:** Mantém `virtual_position` e `fifo_buffer` (350 barras).
* **Gatilho:** Recebe evento de `New Bar` via WebSocket.
* **Memória:** ~250MB (Carrega PyTorch CPU e Pesos).
* **Resiliência:** Em caso de crash, realiza **Fast-Forward Warmup** (reprocessa as 350 barras para reconstruir o estado virtual antes do próximo sinal).

### B. EXECUTOR (As Mãos)

* **Função:** Interface assíncrona com **cTrader Open API**.
* **Lógica:** Recebe o `SIGNAL`, checa `Equity`, `Drawdown` e `Slippage`.
* **Modo Paper:** Pode rodar em paralelo ao Live para comparar o *Drift* entre a Posição Virtual e a Real.
* **Memória:** ~80MB (Sem PyTorch, apenas WebSockets e Protobuf).

---

## 📦 3. O "Modelo Atômico" (ZIP + Metadata)

O arquivo `.zip` agora é a **única fonte de verdade**. Nenhuma configuração fica no servidor; tudo viaja com o modelo.

### Estrutura do Arquivo

* `model.zip`
* `ppo_weights.zip` (SB3)
* `hmm_matrices.pkl` (hmmlearn)
* **Comment (Header):** JSON com metadados (Periods, Scalers, Actions).

### Metadados Críticos (Inclusos no JSON)

```json
{
  "hmm_config": { "n_states": 5, "features": "log_returns" },
  "normalization": {
    "position_map": { "long": 1.0, "flat": 0.0, "short": -1.0 },
    "feature_scaling": "standard_params_here"
  },
  "execution_delay_ms": 500
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
* **Formato:** JSON estruturado.
* **Latência:** < 5ms (via localhost).

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

* Implementar a função `save_production_model(model, params)` que injeta o JSON no `zip.comment`.

### Fase 2: O Preditor "Digital Twin"

* Desenvolver o loop que mantém a posição virtual independente do que o executor faça.
* Implementar a lógica de **Warmup FIFO (350 barras)** na inicialização.

### Fase 3: O Executor cTrader (Async)

* Criar o cliente assíncrono para a Open API da FTMO/Spotware.
* Implementar a "Cerca de Proteção" (Risk Guard) que apenas lê os sinais e valida o capital.

---

## ✅ Critérios de Sucesso (KPIs)

1. **Sincronia de Posição:** A `virtual_position` do Preditor deve ser idêntica à posição do Backtest em 100% do tempo.
2. **Uso de RAM:** O sistema completo (Preditor + Executor) deve manter-se abaixo de **600MB** estáveis.
3. **Latência de Execução:** Tempo entre `New Bar` e `Order Sent` < 100ms para todos os 20 ativos.
