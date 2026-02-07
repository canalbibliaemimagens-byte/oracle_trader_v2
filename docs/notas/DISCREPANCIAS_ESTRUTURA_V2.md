# Discrepâncias de Estrutura e Implementação (v2.0)

**Data:** 07/02/2026
**Status:** Aberto

Este documento registra as divergências identificadas entre a documentação oficial (`docs/ORACLE_V2_PROJECT_STRUCTURE.md`) e a base de código atual.

## 1. Módulos Ausentes

### 1.1 Módulo `api/`
- **Status:** ❌ Ausente no projeto.
- **Documentação:** Mencionado em `ORACLE_V2_PROJECT_STRUCTURE.md` como responsável pelo WebSocket Server (Dashboard) e Handlers de Comandos.
- **Impacto:** Funcionalidades de comunicação externa ou dashboard não estão implementadas.
- **Arquivos Faltantes:**
    - `api/__init__.py`
    - `api/websocket_server.py`
    - `api/commands.py`

### 1.2 Specs Ausentes
- **`docs/modules/SPEC_API.md`**: A especificação técnica deste módulo também não foi encontrada.

## 2. Componentes Não Documentados

Arquivos que existem no código mas não constam na documentação de estrutura:

### 2.1 Orchestrator
- **Arquivo:** `orchestrator/lifecycle.py`
- **Função:** Provavelmente gerencia o ciclo de vida da aplicação (startup/shutdown), mas não está mapeado no diagrama de estrutura.
- **Arquivo Faltante (Doc):** `orchestrator/ipc.py` (Mencionado na doc, mas não existe no código. Pode ter sido substituído ou renomeado).

### 2.2 Executor
- **Arquivo:** `executor/risk_guard.py`
- **Função:** Implementa lógica crítica de proteção de risco (Drawdown, Circuit Breaker).
- **Status da Doc:** Essencial para o sistema, mas ausente na visão geral da estrutura.

## 3. Ambiente e Dependências

### 3.1 `requirements.txt`
- **Problema:** Faltava a dependência `pytest-asyncio`.
- **Correção:** Adicionado manualmente para permitir a execução dos testes.
- **Observação:** As dependências de ML (`torch`, `stable-baselines3`, `hmmlearn`) estão comentadas, o que é esperado para o ambiente de execução leve, mas deve ser observado caso se tente rodar treinamento ou inferência pesada neste ambiente.

## 4. Ações Recomendadas

1.  **Decisão sobre API:** Confirmar se o módulo `api/` será implementado agora ou se foi postergado. Se postergado, atualizar a documentação para marcar como "Futuro".
2.  **Atualizar Estrutura:** Adicionar `lifecycle.py` e `risk_guard.py` ao `ORACLE_V2_PROJECT_STRUCTURE.md`.
3.  **Sincronizar Docs:** Criar ou remover referências a `SPEC_API.md`.
