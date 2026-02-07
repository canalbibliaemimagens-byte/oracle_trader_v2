# Auditoria de Fallbacks, Mocks e Estimativas

**Data:** 07/02/2026
**Status:** ⚠️ Crítico para Produção

Este documento lista todos os mecanismos de defesa (fallbacks), simulações (mocks) e estimativas encontrados na base de código do Oracle Trader v2.

> **ALERTA DE PRODUÇÃO:**
> Todos os itens listados abaixo representam **riscos de integridade financeira**.
> Em um ambiente de produção (Dinheiro Real), o sistema deve **FALHAR (Fail Fast)** ao invés de **ADIVINHAR (Guess/Fallback)**.
> Um fallback silencioso pode levar a ordens com tamanho errado, preços de stop inválidos ou execução em momentos de mercado sem dados.

---

## 1. Conectores e Dados de Conta

### 1.1 `connector/ctrader/client.py`
- **`get_account()`** (Linha 414)
    - **O que faz:** Retorna um objeto `AccountInfo` com valores zerados (Balance=0, Equity=0) porque a API cTrader não tem um endpoint direto único de "Account Info" compatível com a interface síncrona esperada.
    - **Risco:** O sistema opera "cego" em relação ao saldo real se depender desse método. O `SessionManager` pode iniciar com saldo 0 ou incorreto.
    - **Ação:** Implementar monitoramento real via `ProtoOAExecutionEvent` para atualizar saldo localmente.

- **`_handle_spot()`** (Linha 143)
    - **O que faz:** Usa `int(time.time())` se o tick vier sem timestamp.
    - **Risco:** Dados com timestamp do servidor local (latência incluida) vs servidor da bolsa.

### 1.2 `connector/base.py`
- **Mock Connector**
    - **O que faz:** O sistema suporta `type: mock` na config.
    - **Risco:** Risco operacional de rodar em produção esquecendo a config em `mock`.

## 2. Execução e Risco (Crítico)

### 2.1 `executor/risk_guard.py`
- **`_check_spread()`** (Linha 111)
    - **O que faz:** `if current_spread is None: return RiskCheck(passed=True)` (Fail-Open).
    - **Justificativa Dev:** Permitir testar sem ter fluxo de dados de spread ativo.
    - **Risco Prod:** Operar durante notícias/alta volatilidade com spreads gigantescos sem saber.
    - **Ação:** Mudar para **Fail-Close** (bloquear trade se spread for desconhecido).

- **`_check_margin()`** (Linha 94)
    - **O que faz:** `estimated_margin = volume * 1000`. Assume alavancagem fixa/padrão.
    - **Risco Prod:** Se a alavancagem da conta mudar ou o ativo tiver margem diferente (ex: Ouro, Crypto), o cálculo estará errado, podendo causar Margin Call real.
    - **Ação:** Obter requisitos de margem exatos via API (`ProtoOASymbolByIdRes`).

### 2.2 `executor/price_converter.py`
- **`DEFAULT_PIP_VALUES`** (Tabela Estática)
    - **O que faz:** Usa valores fixos ($10/lot) se a API falhar.
    - **Risco Prod:** Valores de pip mudam com taxas de câmbio (para pares XXX/JPY, etc). Stop Loss financeiro será calculado errado.
- **`_estimate_pip_value()`** (Estimativa)
    - **O que faz:** Tenta adivinhar o valor do pip pela string do símbolo (ex: "termina com USD").
    - **Risco Prod:** Se o broker usar sufixos não padrão (`EURUSD.pro`), a lógica pode quebrar ou assumir errado.

## 3. Orquestração

### 3.1 `orchestrator/orchestrator.py`
- **`_spread_update_loop()`** (Linha 277)
    - **O que faz:** Hardcoded `point = 0.00001` ou `0.001` (JPY) se a API não informar.
    - **Risco:** Símbolos exóticos ou índices (DAX, BTC) podem ter `point` totalmente diferente (1.0, 0.01).
    - **Ação:** Exigir `point` e `digits` corretos da API; falhar se não disponível.

---

## Plano de Remediação (Roadmap v2.1 Production)

1.  **Refatoração do RiskGuard:** Converter `_check_spread` para lançar erro se dados faltarem.
2.  **Conector Robusto:** Implementar cache local de `AccountInfo` atualizado por eventos de execução, removendo o mock de `get_account`.
3.  **PriceConverter Estrito:** Remover `_estimate_pip_value` e `DEFAULT_PIP_VALUES`. Se `get_symbol_info` falhar, o bot deve parar/alertar, não tentar operar.
4.  **Validação de Config:** No startup, verificar se `broker.type != mock` se a flag `--production` estiver ativa.
