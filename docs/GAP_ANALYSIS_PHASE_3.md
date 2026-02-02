# 📊 Análise de Gap: Planejamento vs Implementação (Fase 3.1)

Este documento diagnostica as diferenças entre o estado atual do projeto e o plano definido em `CONTEXTO_ORACLE_TRADER_V2.md`.

## 1. Estrutura de Arquivos

### ✅ Alinhado
- `main.py`: Implementado e funcional como ponto de entrada.
- `core/engine.py`: Implementado.
- `core/state_machine.py`: Implementado.
- `trading/executor.py`, `risk_manager.py`, `paper_trade.py`: Implementados na estrutura prevista.

### ⚠️ Divergências (Atenção para Próxima Fase)

| Componente | Planejado (`CONTEXTO`) | Implementado (Atual) | Ação Recomendada |
|------------|------------------------|----------------------|------------------|
| **WebSocket** | `infra/websocket/`<br>├── `server.py`<br>├── `client.py`<br>└── `commands.py` | `infra/websocket_server.py` (Arquivo único) | **Refatorar**: Dividir o arquivo único em pacote `infra/websocket/` na próxima fase. |
| **Config Loader** | `core/config_loader.py` | `core/config.py` (Nome diferente) | **Renomear ou Manter**: `config.py` é aceitável, mas documentar a decisão. |
| **Supabase** | `infra/supabase/`<br>├── `logger.py`<br>└── `metrics.py` | Ainda não migrado (pendente) | **Implementar**: Criar estrutura na Fase 3.2. |

---

## 2. Implementação Lógica

### WebSocket Server (Status: Funcional mas Monolítico)
O arquivo `infra/websocket_server.py` (564 linhas) contém:
1. Lógica do Servidor (`start`, `stop`, `broadcast`).
2. Handlers de Cliente (`_handle_client`).
3. Definição e Processamento de Comandos (`AVAILABLE_COMMANDS`, `handle_command`).

**Risco:** O arquivo cresceu rápido. Mistura infraestrutura (websockets) com lógica de negócio (comandos).
**Correção Planejada:** Separar `commands.py` é crucial para manter a facilidade de manutenção quando novos comandos v2 forem adicionados.

### Integração Main → Engine → WebSocket
A implementação atual no `main.py` está **correta e elegante**:
```python
ws_server.set_engine(engine)  # Injeção de dependência
engine.on_trade = ...          # Callbacks
```
Isso desacopla o Engine do WebSocket, seguindo o princípio de arquitetura hexagonal/ports-and-adapters.

---

## 3. Próximos Passos (Correção de Rumo)

Paraalinhar com o `CONTEXTO_ORACLE_TRADER_V2.md`, a próxima sessão de trabalho deve focar em:

1.  **Refatoração Infra Estrutural (Prioridade Alta)**
    -   Criar pasta `infra/websocket/`.
    -   Mover `WebSocketServer` para `infra/websocket/server.py`.
    -   Extrair lógica de comandos para `infra/websocket/commands.py`.
    -   Atualizar `main.py` e `infra/__init__.py` para os novos imports.

2.  **Supabase Logger (Prioridade Média)**
    -   Implementar `infra/supabase/` conforme plano.
    -   Migrar lógica do antigo `supabase_logger.py`.

3.  **ML Integration (Prioridade Média/Alta)**
    -   A pasta `ml/` está vazia (`__init__.py` apenas).
    -   Necessário portar `feature_calculator.py` e `model_loader.py`.

---

**Conclusão:** O projeto está saudável e funcional, mas a camada de Infraestrutura (WebSocket) desviou levemente do design modular planejado, tornando-se um ponto de atenção imediato antes que cresça demais.
