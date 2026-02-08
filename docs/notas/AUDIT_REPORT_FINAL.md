# 🔍 Auditoria Completa — oracle_trader_v2 (Fases 1-6)

**Data:** 2026-02-07  
**Escopo:** Confronto de TODA a implementação contra as specs em `docs/modules/`  
**Resultado:** 12 issues encontradas (3 críticas, 5 sérias, 4 menores)

---

## 🛑 CRÍTICOS (sistema não funciona sem corrigir)

### C1. Twisted/AsyncIO Bridge ausente no CTraderConnector

**Severidade:** 🛑 CRASH na inicialização  
**Arquivos:** `orchestrator/orchestrator.py`, `executor/executor.py`, `connector/ctrader/client.py`

Todos os métodos `async` no `CTraderConnector` levantam `NotImplementedError`:

```
get_history → "Use get_history_deferred()"
subscribe_bars → "Use subscribe_spots_deferred()"
get_positions → "Use get_positions_deferred()"
open_order → "Use open_order_deferred()"
close_order → "Use close_position_deferred()"
get_account → NotImplementedError
get_position → NotImplementedError
```

Mas o Orchestrator e Executor chamam esses métodos via `await`:

- `orchestrator.py` L175: `await self.connector.subscribe_bars(...)`
- `orchestrator.py` L232: `await self.connector.get_account()`
- `orchestrator.py` L338: `await self.connector.get_positions()`
- `orchestrator.py` L360: `await self.connector.get_history(...)`
- `executor.py` L103: `await self.connector.get_position(symbol)`
- `executor.py` L165: `await self.connector.open_order(...)`

O doc `CONNECTOR_BRIDGE_PATTERN.md` descreve a solução (asyncioreactor ou Deferred→Future wrapper) mas NÃO está implementada.

**Fix:** Implementar bridge no `CTraderConnector` que converte cada `_deferred` para `asyncio.Future`. Sem isso, o sistema funciona APENAS com `MockConnector`.

---

### C2. `executor_symbols.json` não tem seção `_risk` — RiskGuard sempre com defaults

**Severidade:** 🛑 Proteção de risco nula  
**Arquivos:** `executor/executor.py` L76, `config/executor_symbols.json`

O executor faz:
```python
risk_config = data.get("_risk", {})
self.risk_guard = RiskGuard(risk_config)
```

Mas o JSON real NÃO contém `_risk`:
```json
{"_comment": "...", "_version": "2.0", "EURUSD": {...}, "_default": {...}}
```

**Consequência:** `RiskGuard` inicializa com `initial_balance=0`, o que faz `_check_drawdown` retornar sempre `True` (bypass completo). O circuit breaker funciona com defaults genéricos.

**Fix:** Adicionar `_risk` ao JSON OU ler de `default.yaml`.

---

### C3. `default.yaml` tem estrutura incompatível com Orchestrator

**Severidade:** 🛑 Config silenciosamente vazia  
**Arquivos:** `orchestrator/orchestrator.py`, `config/default.yaml`

O YAML atual:
```yaml
persistence:
  enabled: false
```

Mas o Orchestrator lê:
```python
self.config.get("supabase_url", "")        # ← root level (não existe)
self.config.get("supabase_key", "")        # ← root level (não existe)
self.config.get("initial_balance", 10000)  # ← root level (não existe)
self.config.get("timeframe", "M15")        # ← root level (não existe)
self.config.get("close_on_exit", False)    # ← root level (não existe)
self.config.get("broker", {})              # ← root level (não existe)
```

Nenhum desses campos existe no YAML. O Orchestrator vai sempre usar os defaults sem aviso.

**Fix:** Atualizar `default.yaml` para incluir todos os campos que o Orchestrator espera, OU ajustar o Orchestrator para ler dos sub-paths corretos (`self.config.get("persistence", {}).get("enabled")`).

---

## ⚠️ SÉRIOS (funciona mas com bugs/riscos)

### S1. `data.pop()` muta dicionário no Supabase update → retry perde filtros

**Severidade:** ⚠️ Perda silenciosa de dados em retry  
**Arquivo:** `persistence/supabase_client.py` L71-78

```python
elif operation == "update":
    filter_key = data.pop("_filter_key", None)   # ← MUTA o dict
    filter_val = data.pop("_filter_val", None)   # ← MUTA o dict
```

Se o `_execute` falha, o `data` (já sem `_filter_key/_filter_val`) vai para a `_retry_queue`. Na próxima tentativa de retry, o dicionário não terá mais os filtros, o que faz a operação update sem WHERE (se implementado) ou simplesmente falhar.

**Fix:** Usar `data.get()` em vez de `data.pop()`, e remover as chaves numa cópia:
```python
filter_key = data.get("_filter_key")
clean_data = {k: v for k, v in data.items() if not k.startswith("_filter")}
```

---

### S2. `_check_spread` é placeholder — zero proteção contra spread widening

**Severidade:** ⚠️ Risco financeiro em produção  
**Arquivo:** `executor/risk_guard.py` L93

```python
def _check_spread(self, symbol: str, config: SymbolConfig) -> RiskCheck:
    return RiskCheck(passed=True)  # TODO
```

Sem check de spread, o sistema abre ordens durante rollover (00:00 UTC), notícias de alto impacto (NFP, CPI), ou flash crashes quando o spread pode ser 10-50x o normal.

**Fix:** O `BaseConnector` expõe `get_symbol_info(symbol)` — usar para obter spread atual. Ou manter cache do último tick no Connector com `.current_spread(symbol)`.

---

### S3. `SymbolConfig` não tem `max_spread_pips` no JSON real

**Severidade:** ⚠️ Mesmo quando spread check for implementado, não terá threshold  
**Arquivo:** `config/executor_symbols.json`

O `lot_mapper.py` define `SymbolConfig` com `max_spread_pips: float = 2.0`, mas o JSON real não inclui esse campo. O default de 2.0 pips pode ser apertado demais para alguns pares.

**Fix:** Adicionar `max_spread_pips` ao JSON por símbolo.

---

### S4. Paper compara `direction + intensity` mas TradingEnv compara apenas `action`

**Severidade:** ⚠️ Drift measurement incorreto  
**Arquivo:** `paper/paper_trader.py` L67-69

```python
if current_dir == target_dir and current_intensity == target_intensity:
    return None
```

No `TradingEnv` do notebook, se a ação muda de `LONG_WEAK` para `LONG_MODERATE`, o env fecha e reabre. Mas no Paper, como `direction == direction` E `intensity != intensity`, ele fecha e reabre corretamente. Porém, se por algum motivo `direction` for igual mas `action` diferente com mesma `intensity`, haveria inconsistência. Risco baixo mas vale documentar.

---

### S5. `Decision.OPEN` é dead code — decide() nunca retorna OPEN

**Severidade:** ⚠️ Code smell / confusão  
**Arquivo:** `executor/executor.py` L121, `executor/sync_logic.py`

O enum `Decision` tem 4 valores: `NOOP, OPEN, CLOSE, WAIT_SYNC`. Mas a função `decide()` retorna apenas 3: `NOOP, CLOSE, WAIT_SYNC` — nunca `OPEN`.

No `executor.py` L121:
```python
if decision == Decision.OPEN:
    return await self._open_position(signal, config)
```

Este bloco NUNCA é alcançado. A abertura real acontece via `should_open` na `SyncState.update()`.

**Fix:** Remover `Decision.OPEN` do enum e o bloco correspondente no executor, ou documentar que é reservado para futuro.

---

## ℹ️ MENORES (melhorias e boas práticas)

### M1. `log_trade` hardcoda campos — inconsistência com schema futuro

**Severidade:** ℹ️ Manutenibilidade  
**Arquivo:** `persistence/supabase_client.py` L107-123

Cada campo é mapeado manualmente. Se `Signal` ou `Trade` ganhar campos novos, o log não os captura.

**Fix:** Usar `dataclasses.asdict()` ou Pydantic `.model_dump()`.

---

### M2. `psutil` não está no requirements.txt

**Severidade:** ℹ️ ImportError em produção  
**Arquivo:** `orchestrator/health.py` L68

`HealthMonitor._get_memory_mb()` tenta `import psutil` com fallback para `/proc`. O fallback funciona em Linux, mas `psutil` deveria estar no requirements.

---

### M3. `supabase` não está no requirements.txt

**Severidade:** ℹ️ ImportError  
**Arquivo:** `persistence/supabase_client.py` L35

`from supabase import create_client` — a lib `supabase-py` não está listada.

---

### M4. Orchestrator `_init_executor` é chamado ANTES de `_init_connector` no método start()

**Severidade:** ℹ️ Potencial bug  
**Arquivo:** `orchestrator/orchestrator.py`

Na implementação, a ordem é:
```
L113: Persistence
L117: Preditor
L122: Connector  ← passo 4
L126: Executor   ← passo 5, usa self.connector
```

O Executor recebe `self.connector` no construtor (L323: `Executor(connector=self.connector, ...)`). Isso funciona porque o Connector já foi inicializado no passo anterior. **OK nesta implementação**, mas a spec original (§4 Orchestrator) dizia que Executor vinha ANTES do Connector. A implementação atual está correta — a spec estava errada.

---

## Resumo de Ações

| # | Issue | Prioridade | Esforço |
|---|-------|-----------|---------|
| C1 | Bridge Twisted→AsyncIO | 🛑 Bloqueante | Alto |
| C2 | `_risk` ausente no JSON | 🛑 Bloqueante | Baixo |
| C3 | `default.yaml` incompatível | 🛑 Bloqueante | Baixo |
| S1 | `data.pop` muta dict no retry | ⚠️ Sério | Baixo |
| S2 | Spread check placeholder | ⚠️ Sério | Médio |
| S3 | `max_spread_pips` ausente | ⚠️ Sério | Baixo |
| S4 | Paper logic vs TradingEnv | ⚠️ Sério | Baixo |
| S5 | Dead code `Decision.OPEN` | ⚠️ Sério | Baixo |
| M1 | Hardcoded log_trade | ℹ️ Menor | Médio |
| M2 | psutil no requirements | ℹ️ Menor | Trivial |
| M3 | supabase no requirements | ℹ️ Menor | Trivial |
| M4 | Ordem init documentada | ℹ️ Menor | Trivial |

### Ordem recomendada de correção:
1. **C2 + C3** (5 min cada — config fixes)
2. **S1** (5 min — pop→get)
3. **S5** (5 min — remover dead code)
4. **M2 + M3** (2 min — requirements.txt)
5. **S2 + S3** (30 min — spread check)
6. **C1** (2-4h — Twisted bridge, mais complexo)

---

## ✅ Status das Correções (Atualizado 2026-02-07)

| # | Issue | Status | O que foi feito |
|---|-------|--------|-----------------|
| C1 | Bridge Twisted→AsyncIO | ✅ | `_deferred_to_future()` no client.py + `install_twisted_reactor()` no lifecycle.py + cli.py chama antes de tudo |
| C2 | `_risk` ausente no JSON | ✅ | Adicionado `_risk` com dd_limit=5%, emergency=10%, initial_balance=10000, max_losses=5 |
| C3 | `default.yaml` incompatível | ✅ | Adicionados broker, timeframe, initial_balance, supabase_url/key, close_on_exit/day_change, log_file |
| S1 | `data.pop` muta dict | ✅ | `data.pop()` → `data.get()` + cópia limpa sem `_filter` keys |
| S2 | Spread check placeholder | ✅ | Implementado com cache `_current_spreads` + `update_spread()` + check vs `max_spread_pips` |
| S3 | `max_spread_pips` ausente | ✅ | Adicionado ao JSON (EURUSD: 2.0, _default: 3.0) |
| S4 | Paper logic vs TradingEnv | ✅ | Agora fecha/reabre quando intensidade muda (mesmo direction), alinhado com TradingEnv |
| S5 | Dead code Decision.OPEN | ✅ | Removido do enum e do executor.py |
| M1 | Hardcoded log_trade | ✅ | Refatorado com merge de defaults — aceita dict direto, campos extras ignorados |
| M2 | psutil no requirements | ✅ | Adicionado `psutil>=5.9.0` |
| M3 | supabase no requirements | ✅ | Adicionado `supabase>=2.0.0` |
| M4 | Ordem init documentada | ✅ | Docstring do orchestrator atualizada com ordem correta + NOTA explicativa |
