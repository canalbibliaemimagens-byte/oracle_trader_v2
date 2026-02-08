# 📝 Correções Necessárias - Fases 4, 5 e 6

**Data:** 2026-02-06
**Status:** 🛑 BLOQUEANTE
**Prioridade:** CRÍTICA

---

## 1. 🛑 Falha Crítica no Warmup (Orchestrator + Connector)

**O Problema:**
O `Orchestrator` (Fase 6) tenta realizar warmup chamando `await self.connector.get_history(...)`.
No entanto, o `CTraderConnector` (Fase 3/Twisted) implementa explicitamente os métodos `async` levantando `NotImplementedError`, forçando o uso do sufixo `_deferred`.

**Cenário de Erro:**
Ao iniciar o sistema (`orchestrator.start()`), o passo 8 (`_warmup_models`) chamará `get_history`, o que causará um crash imediato da aplicação.

**Arquivos Afetados:**
- `orchestrator/orchestrator.py`: Linha 360 (`await self.connector.get_history(...)`)
- `connector/ctrader/client.py`: Linha 296 (`raise NotImplementedError("Use get_history_deferred()")`)

**Solução Recomendada:**
Criar um **Adapter** ou **Bridge Helper** no `CTraderConnector` que permita chamadas `async` compatíveis com o padrão do sistema.
*Exemplo:* Implementar `get_history` convertendo o deferred interno para `asyncio.Future` usando `asyncioreactor`.

---

## 2. ⚠️ Lógica Incompleta no Risk Guard (Executor)

**O Problema:**
O método `_check_spread` em `executor/risk_guard.py` é um placeholder (retorna sempre True com "TODO").
Em operações reais, spreads altos (ex: horário de notícias ou rollover) podem destruir a estratégia.

**Arquivos Afetados:**
- `executor/risk_guard.py`

**Solução Recomendada:**
Implementar checagem de spread usando o último tick recebido pelo `Connector`.
*Nota:* Isso exige que o `Executor` tenha acesso ao último tick ("hot path") ou que o `Connector` exponha essa informação de forma síncrona/cacheada.

---

## 3. ℹ️ Chaves Hardcoded no Persistence (Menor)

**O Problema:**
O método `log_trade` em `persistence/supabase_client.py` constrói o dicionário na mão. Se a estrutura do modelo `OrderResult` ou `Trade` mudar, o log quebrará silenciosamente ou enviará dados incompletos.

**Solução Recomendada:**
Usar `trade_data.model_dump()` (Pydantic) ou similar para garantir consistência com o schema do banco.

---

## Plano de Ação

1.  **Imediato:** Corrigir o **Item 1 (Warmup Crash)**. Sem isso, o sistema não roda.
2.  **Curto Prazo:** Implementar **Item 2 (Check Spread)** antes de operar em conta Real.
3.  **Médio Prazo:** Refatorar **Item 3 (Persistence)**.
