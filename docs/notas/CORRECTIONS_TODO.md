# 📝 Correções Necessárias - Oracle Trader v2.0

**Data:** 2026-02-06
**Status:** Pendente de Correção
**Objetivo:** Alinhar codebase com especificação e boas práticas.

---

## 1. Imports Absolutos vs Relativos
**Problema:** O código utiliza imports absolutos baseados na raiz do projeto (ex: `from connector.base import ...`) dentro de subpacotes.
- **Arquivo:** `connector/__init__.py`, `connector/ctrader/client.py`, etc.
- **Risco:** Falha de importação se o projeto for instalado como pacote (`pip install .`) ou se o diretório raiz não estiver no `PYTHONPATH`.
- **Correção Sugerida:** Converter para imports relativos ou absolutos com namespace completo.
  - De: `from connector.base import BaseConnector`
  - Para: `from ..base import BaseConnector` (relativo) OU `from oracle_trader_v2.connector.base import ...` (se namespace existir).

## 2. Inconsistência de Localização: `bar_detector.py`
**Problema:** A especificação define que `bar_detector.py` deve residir dentro do módulo específico cTrader, mas foi implementado na raiz do conector.
- **Spec:** `connector/ctrader/bar_detector.py` (SPEC_CONNECTOR.md)
- **Atual:** `connector/bar_detector.py`
- **Impacto:** Violação da organização modular. O detector de barras baseado em ticks é uma necessidade específica da cTrader (que não envia eventos de barra), não necessariamente de todos os conectores.
- **Correção Sugerida:** Mover arquivo para `connector/ctrader/`.

## 3. Duplicação de Código no Preditor
**Problema:** Métodos com lógica idêntica duplicada.
- **Arquivo:** `preditor/preditor.py`
- **Métodos:** `_predict_internal` e `_predict_and_signal`.
- **Detalhe:** Ambos calculam features, rodam HMM, rodam PPO e atualizam posição virtual.
- **Correção Sugerida:** `_predict_and_signal` deve chamar `_predict_internal` e apenas envelopar o resultado no objeto `Signal`.

## 4. Estrutura de Arquivos: `warmup.py`
**Problema:** Lógica de warmup implementada dentro da classe principal `Preditor` em vez de arquivo separado conforme spec.
- **Spec:** `preditor/warmup.py` (SPEC_PREDITOR.md)
- **Atual:** Método `Preditor.warmup()` em `preditor/preditor.py`.
- **Correção Sugerida:** Extrair lógica para `preditor/warmup.py` para manter classe `Preditor` mais limpa e coerente com a spec.

## 5. Erro Crítico de Conversão de Volume (cTrader)
**Problema:** Inconsistência matemática na conversão de unidades para lotes ao parsear posições.
- **Arquivo:** `connector/ctrader/messages.py`
- **Função:** `parse_positions`
- **Código Atual:** `volume = pos.tradeData.volume / 100`
- **Análise:**
  - `volume_to_units` converte `0.01 lot` -> `1000 units` (Fator 100.000).
  - `units_to_volume` converte `1000 units` -> `0.01 lot` (Divisão por 100.000).
  - `parse_positions` divide por 100.
    - Se receber `1000 units` (0.01 lot), retorna `10.0`. Isso seria interpretado como 10 lotes padrão.
- **Correção Sugerida:** Alterar divisão para `100000.0` (ou usar a função helper `units_to_volume` existente).

---

## Ação Recomendada
Não modificar o código agora. Criar uma tarefa específica de "Refactoring & Bugfix" para aplicar essas correções em lote antes de iniciar a Fase 4 (Executor).
