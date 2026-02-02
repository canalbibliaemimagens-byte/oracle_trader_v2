# 📓 Requisitos para Notebook de Treinamento v2

Este documento especifica os requisitos para atualizar o notebook de treinamento
para ser compatível com o Oracle Trader v2.

## 🎯 Objetivo

O notebook deve gerar modelos que incluam metadados sobre a classe do ativo,
permitindo que o Executor calcule lotes apropriados dinamicamente.

---

## 📋 Metadados Obrigatórios

O arquivo `*_exec_config.json` deve incluir:

```json
{
  "symbol": "EURUSD",
  "timeframe": "M15",
  
  "training_info": {
    "asset_class": "FOREX",
    "base_balance": 10000,
    "scale_step": 10000,
    "lot_sizes": [0, 0.01, 0.03, 0.05],
    "min_lot": 0.01,
    "lot_step": 0.01
  }
}
```

### Campos Obrigatórios

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `asset_class` | string | Classe do ativo (ver tabela abaixo) |
| `base_balance` | float | Saldo base usado no treinamento (tipicamente 10000) |
| `scale_step` | float | Degrau de escalonamento (tipicamente 10000) |
| `lot_sizes` | array | [FLAT, small, medium, large] usados no treinamento |
| `min_lot` | float | Lote mínimo do símbolo no broker |
| `lot_step` | float | Step de lote do símbolo no broker |

---

## 🏷️ Classes de Ativos

| Classe | Exemplos | lot_sizes Base | min_lot |
|--------|----------|----------------|---------|
| `FOREX` | EURUSD, GBPUSD, USDJPY | [0, 0.01, 0.03, 0.05] | 0.01 |
| `INDEX` | US500, US30, GER40, UK100 | [0, 0.1, 0.3, 0.5] | 0.1 |
| `COMMODITY` | XTIUSD (Oil), XNGUSD (Gas) | [0, 0.01, 0.03, 0.05] | 0.01 |
| `METAL` | XAUUSD (Gold), XAGUSD (Silver) | [0, 0.01, 0.03, 0.05] | 0.01 |
| `CRYPTO` | BTCUSD, ETHUSD | [0, 0.001, 0.003, 0.005] | 0.01 |
| `STOCK` | AAPL, GOOGL, MSFT | [0, 1, 3, 5] | 1 |

---

## 📋 Notas:

### Lista de excessões:
- GER40.cash: Manter lot_sizes Base = Forex.

### ⚠️ Alerta de Risco:
- Para CRYPTO avaliar com cuidado, pois o recomendado é 0.001, mas o broker aceita até 0.01.

---

## 🔄 Escalonamento Dinâmico

O Oracle Trader v2 escala os lotes automaticamente baseado no saldo:

```
Saldo        | Scale | Forex Lots        | Index Lots
-------------|-------|-------------------|-------------
10k - 19.9k  | 1x    | 0.01/0.03/0.05    | 0.1/0.3/0.5
20k - 29.9k  | 2x    | 0.02/0.06/0.10    | 0.2/0.6/1.0
30k - 39.9k  | 3x    | 0.03/0.09/0.15    | 0.3/0.9/1.5
...          | ...   | ...               | ...
100k+        | 10x+  | 0.10/0.30/0.50    | 1.0/3.0/5.0
```

**O notebook NÃO precisa implementar este escalonamento** - ele é feito
automaticamente pelo Executor em runtime.

---

## ⚠️ Importante: Gestão de Risco

### O que o NOTEBOOK faz:
- Treina o modelo para prever direção e intensidade (small/medium/large)
- Usa ambiente com custos realistas (spread, slippage, commission)
- Salva metadados da classe do ativo

### O que o NOTEBOOK NÃO faz:
- **NÃO** implementa `risk_per_trade_pct` ou similar
- **NÃO** limita drawdown durante treinamento
- **NÃO** considera o saldo para decidir tamanho de posição

### Por quê?
O modelo performa melhor quando opera com "risco infinito" - ele foca apenas
em prever a direção correta. A gestão de risco é responsabilidade do Executor:
- DD Limit → Paper Trade
- DD Emergency → Fecha tudo
- SL Protection → Paper Trade após N SL hits
- TP Global → Fecha tudo com lucro

---

## 📝 Exemplo de Implementação no Notebook

```python
# No início do notebook
ASSET_CLASS = "FOREX"  # Configurar manualmente ou detectar do símbolo

ASSET_CONFIGS = {
    "FOREX": {
        "lot_sizes": [0, 0.01, 0.03, 0.05],
        "min_lot": 0.01,
        "lot_step": 0.01,
        "spread_typical": 10,
    },
    "INDEX": {
        "lot_sizes": [0, 0.1, 0.3, 0.5],
        "min_lot": 0.1,
        "lot_step": 0.1,
        "spread_typical": 50,
    },
    # ... outras classes
}

# Ao salvar exec_config.json
config = ASSET_CONFIGS[ASSET_CLASS]

execution_config = {
    "symbol": SYMBOL,
    "timeframe": TIMEFRAME,
    "training_info": {
        "asset_class": ASSET_CLASS,
        "base_balance": INITIAL_BALANCE,
        "scale_step": 10000,
        "lot_sizes": config["lot_sizes"],
        "min_lot": config["min_lot"],
        "lot_step": config["lot_step"],
    },
    # ... resto do config
}
```

---

## 🔍 Detecção Automática de Classe (Opcional)

O notebook pode detectar a classe automaticamente:

```python
def detect_asset_class(symbol: str) -> str:
    """Detecta classe do ativo pelo nome do símbolo"""
    symbol_upper = symbol.upper()
    
    # Índices
    if any(idx in symbol_upper for idx in ['US500', 'US30', 'US100', 'GER40', 'UK100', 'JPN225']):
        return "INDEX"
    
    # Metais
    if any(metal in symbol_upper for metal in ['XAU', 'XAG', 'GOLD', 'SILVER']):
        return "METAL"
    
    # Commodities
    if any(cmd in symbol_upper for cmd in ['XTI', 'XNG', 'OIL', 'BRENT', 'WTI']):
        return "COMMODITY"
    
    # Crypto
    if any(crypto in symbol_upper for crypto in ['BTC', 'ETH', 'XRP', 'LTC']):
        return "CRYPTO"
    
    # Ações (geralmente 1-5 letras sem números)
    if len(symbol) <= 5 and symbol.isalpha():
        return "STOCK"
    
    # Default: Forex
    return "FOREX"
```

---

## ✅ Checklist de Atualização

- [ ] Adicionar variável `ASSET_CLASS` no início do notebook
- [ ] Criar dicionário `ASSET_CONFIGS` com configurações por classe
- [ ] Atualizar `LOT_SIZES` para usar `ASSET_CONFIGS[ASSET_CLASS]["lot_sizes"]`
- [ ] Atualizar `MIN_LOT` para usar config da classe
- [ ] Atualizar `execution_config` para incluir `training_info` completo
- [ ] (Opcional) Implementar `detect_asset_class()` para detecção automática
- [ ] Testar com pelo menos um símbolo de cada classe principal (FOREX, INDEX)

---

## 📦 Arquivos Gerados

O notebook deve gerar os seguintes arquivos:

```
{SYMBOL}_{TIMEFRAME}/
├── {SYMBOL}_{TIMEFRAME}_hmm.pkl         # Modelo HMM
├── {SYMBOL}_{TIMEFRAME}_ppo.zip         # Modelo PPO
├── {SYMBOL}_{TIMEFRAME}_exec_config.json # Config + Metadados
└── {SYMBOL}_{TIMEFRAME}_metrics.csv      # Métricas do backtest
```

---

*Documento criado para Oracle Trader v2.0*
