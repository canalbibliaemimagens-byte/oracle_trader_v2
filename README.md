# 🤖 Oracle Trader v2.0

Sistema autônomo de trading com Reinforcement Learning (HMM + PPO).

## 🏗️ Arquitetura

```
oracle_trader_v2/
├── core/               # Engine principal e máquina de estados
│   ├── engine.py       # Loop principal orquestrador
│   ├── state_machine.py# Transições de estado dos símbolos
│   └── config.py       # Configurações runtime
│
├── trading/            # Lógica de execução
│   ├── executor.py     # Execução de ordens (abstrato)
│   ├── risk_manager.py # DD, SL Protection, TP Global
│   ├── position_manager.py # Gestão de posições
│   └── paper_trade.py  # Simulação virtual (substitui Warmup/Quarentena)
│
├── ml/                 # Machine Learning
│   ├── model_loader.py # Carregamento de modelos HMM+PPO
│   ├── features.py     # Cálculo de features
│   └── predictor.py    # Interface de predição
│
├── infra/              # Infraestrutura e conectividade
│   ├── broker_base.py  # Interface abstrata para brokers
│   ├── mt5_client.py   # Implementação MetaTrader5
│   ├── websocket.py    # WebSocket server/client
│   └── supabase.py     # Persistência e analytics
│
├── models/             # Dataclasses e tipos
│   ├── position.py     # Position, VirtualPosition
│   ├── trade.py        # Trade, TradeResult
│   ├── state.py        # SymbolState, SystemState
│   └── enums.py        # SymbolStatus, TradeAction, etc.
│
├── config/             # Arquivos de configuração
│   ├── oracle_config.json
│   └── symbols_config.json
│
├── main.py             # Ponto de entrada
└── requirements.txt
```

## 🔌 Conectividade com Brokers

A v2 foi projetada para suportar múltiplos brokers através de uma interface abstrata.

### Implementações Disponíveis
| Broker | Módulo | Status |
|--------|--------|--------|
| MetaTrader 5 | `infra/mt5_client.py` | ✅ Implementado |
| CCXT (Crypto) | `infra/ccxt_client.py` | 🔮 Futuro |
| WebSocket | `infra/ws_client.py` | 🔮 Futuro |

### Como Adicionar Novo Broker
1. Crie uma classe que herde de `BrokerBase` (`infra/broker_base.py`)
2. Implemente os métodos abstratos:
   - `connect()` / `disconnect()`
   - `get_account_info()`
   - `get_positions()`
   - `open_position()` / `close_position()`
   - `get_bars()` / `get_tick()`
3. Registre no `config/oracle_config.json`

## 🎯 Conceito: Paper Trade

A v2 substitui os estados **WARMUP** e **QUARANTINE** por um único conceito: **PAPER_TRADE**.

### Motivos de Entrada em Paper Trade
| Motivo | Descrição | Critério de Saída |
|--------|-----------|-------------------|
| `STARTUP` | Inicialização do sistema | Primeira predição WAIT |
| `SL_PROTECTION` | Múltiplos SL hits | N wins virtuais consecutivos |
| `TP_GLOBAL` | Take Profit global atingido | N wins virtuais consecutivos |
| `MANUAL` | Comando do usuário | Comando UNBLOCK |

### Configuração
```json
{
  "paper_trade": {
    "exit_wins_required": 3,
    "exit_streak_required": 2,
    "track_virtual_pnl": true
  }
}
```

## 📊 Estados do Símbolo

```
                    ┌─────────────┐
                    │   BLOCKED   │◄──── Comando manual
                    └─────────────┘
                          │
                          │ UNBLOCK
                          ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  NO_MODEL   │───►│ PAPER_TRADE │◄───│   NORMAL    │
└─────────────┘    └─────────────┘    └─────────────┘
      │                   │                  ▲
      │ Load Model        │ Exit Criteria    │
      └───────────────────┴──────────────────┘
```

## 🚀 Início Rápido

```bash
# Ativar ambiente
conda activate metatraderML

# Instalar dependências
pip install -r requirements.txt

# Executar
python main.py --config config/oracle_config.json
```

## 📝 Changelog

### v2.0.0 (Em desenvolvimento)
- Arquitetura modular
- Paper Trade unificado (substitui Warmup/Quarentena)
- Suporte a múltiplos brokers (interface abstrata)
- Código limpo (<300 linhas no engine principal)

---

**Versão anterior:** [Oracle Trader v4.5](../oracle_trader/)
