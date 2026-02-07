# Changelog — Correções Aplicadas (2026-02-07)

## Arquivos Modificados (8) + Criado (1)

---

### 🆕 NOVO: `executor/price_converter.py`

Módulo crítico que converte SL/TP financeiro (USD) para preço absoluto, conforme requerido pela cTrader Open API.

- `PriceConverter` com métodos `usd_to_sl_price()` e `usd_to_tp_price()`
- Tabela estática `DEFAULT_PIP_VALUES` para 20+ pares forex como fallback
- Tenta `symbol_info` do Connector primeiro, fallback para tabela, depois estimativa
- Fórmula: `pip_value_total = pip_value_per_lot × volume` → `distance = usd / pip_value_total`
- Suporte a pares JPY (3 dígitos) e pares normais (5 dígitos)
- Cache de symbol_info com `invalidate_cache()`

---

### ✏️ `executor/executor.py`

- **PriceConverter integrado** — `_open_position()` agora converte `config.sl_usd` e `config.tp_usd` para preço absoluto antes de enviar ao Connector
- **`_get_current_price()`** — novo helper que obtém preço atual via posição aberta ou Connector
- **Comentário explicativo** no bloco de conversão documentando o problema e a solução

---

### ✏️ `executor/__init__.py`

- Adicionado export de `PriceConverter`

---

### ✏️ `connector/ctrader/messages.py`

- **Import corrigido**: `from core.models import Bar` → `from ...core.models import Bar`
- **Import corrigido**: `from core.models import Position` → `from ...core.models import Position`
- Esses imports absolutos falhavam quando o projeto era importado como pacote

---

### ✏️ `connector/ctrader/client.py`

- **Docstring reescrita** com diagrama ASCII da bridge Twisted→AsyncIO
- **Seção "BaseConnector ABC"** renomeada para "Bridge Twisted→AsyncIO" com comentário bloco explicando:
  - Como a bridge funciona (asyncioreactor → Deferred.asFuture)
  - Requisitos (instalar reactor antes de imports)
  - Referências cruzadas para docs/notas/CONNECTOR_BRIDGE_PATTERN.md

---

### ✏️ `orchestrator/lifecycle.py`

- **Docstring expandida** de `install_twisted_reactor()` com diagrama ASCII explicando:
  - Por que a bridge é necessária (SDK Twisted vs sistema asyncio)
  - Como funciona (asyncioreactor substitui reactor padrão)
  - Ordem de chamada (ANTES de qualquer import Twisted)
  - Quem chama (cli.py)

---

### ✏️ `orchestrator/cli.py`

- **Comentário expandido** na chamada de `install_twisted_reactor()`
- Explicação de por que o import do Orchestrator vem DEPOIS da instalação do reactor

---

### ✏️ `orchestrator/orchestrator.py`

- **`_spread_update_loop()`** — nova task assíncrona (30s) que:
  - Consulta `get_symbol_info()` do Connector para cada símbolo ativo
  - Converte spread em points para pips
  - Alimenta `risk_guard.update_spread()` com dados atuais
  - Sem isso, `_check_spread` opera em modo fail-open (permite tudo)
- **`_start_tasks()`** — adicionada `_spread_update_loop` à lista de tasks

---

### ✏️ `docs/ORACLE_V2_PROJECT_STRUCTURE.md`

- **executor/** — adicionados `risk_guard.py` e `price_converter.py`
- **preditor/** — substituído `signal.py` (não existe) por `buffer.py`
- **orchestrator/** — adicionados `lifecycle.py` e `cli.py`, removido `ipc.py`
- **paper/** — substituído `drift_analyzer.py` por `account.py` e `stats.py`
- **persistence/** — adicionado `local_storage.py`
- **api/** — removido como módulo, adicionada nota apontando para API Gateway externo
- **Tabela de módulos** — removida entrada `api/`
- **Tabela de migração** — `websocket_server.py` e `ws_commands.py` marcados como postergados
- **Fase 4** — `ipc.py` → `lifecycle.py` + `cli.py`, nota sobre api/ removido
