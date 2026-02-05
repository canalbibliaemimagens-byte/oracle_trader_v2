# Oracle Trader v2.0 - Plano de Implementação

**Objetivo:** Construir um sistema de trading modular e de alta disponibilidade para cTrader, garantindo paridade exata de features com o ambiente de treinamento.

---

## Fase 1: Core & Fundação (A "Verdade")
**Meta:** Implementar o núcleo matemático e verificá-lo contra a referência da V1.
**Dependências:** Nenhuma.

- [ ] **Configuração de Infraestrutura**
  - [ ] Inicializar ambiente Python (`poetry` ou `venv`).
  - [ ] Instalar dependências: `numpy`, `pandas`, `pydantic`, `hmmlearn`, `stable-baselines3`.
  - [ ] Criar estrutura de diretórios (`core`, `connector`, `preditor`, `executor`, `config`, `tests`).

- [ ] **Módulo: Core**
  - [ ] Implementar `core/constants.py` (Enums, Timeframes).
  - [ ] Implementar `core/models.py` (Bar, Signal, Position - dataclasses imutáveis).
  - [ ] Implementar `core/actions.py` (Mapeamento de ações, conversões).
  - [ ] **CRÍTICO:** Implementar `core/features.py` (FeatureCalculator).

- [ ] **Verificação: Paridade de Features**
  - [ ] Criar `tests/test_features_parity.py`.
  - [ ] Rodar comparação contra `tests/features_v1_reference.py`.
  - [ ] **Critério de Sucesso:** Desvio 0.000000 em precisão float.

---

## Fase 2: Connector & Dados (Os "Olhos")
**Meta:** Abstrair a interação com o broker e lidar com fluxos de dados.
**Dependências:** Core.

- [ ] **Módulo: Connector (Base & Mock)**
  - [ ] Implementar `connector/base.py` (Interface Abstrata).
  - [ ] Implementar `connector/mock/` (MockClient para testes sem broker).
  
- [ ] **Módulo: Connector (cTrader)**
  - [ ] Implementar `connector/ctrader/auth.py` (Loop OAuth2).
  - [ ] Implementar `connector/ctrader/client.py` (Lógica de conexão).
  - [ ] Implementar `connector/ctrader/bar_detector.py` (Lógica Tick -> Bar).
  - [ ] Implementar `connector/ctrader/rate_limiter.py`.

- [ ] **Verificação**
  - [ ] Testar Mock Connector gerando barras.
  - [ ] Testar autenticação cTrader Connector (conta demo).

---

## Fase 3: Motor Preditor (O "Cérebro")
**Meta:** Carregar modelos e gerar sinais no vácuo ("Digital Twin").
**Dependências:** Core.

- [ ] **Módulo: Preditor**
  - [ ] Implementar `preditor/model_loader.py` (Unzip, ler metadados do comentário).
  - [ ] Implementar `preditor/virtual_position.py` (Lógica idêntica ao Gym Env).
  - [ ] Implementar `preditor/buffer.py` (Janela FIFO).
  - [ ] Implementar `preditor/preditor.py` (Motor Principal, lógica de Warmup).

- [ ] **Verificação**
  - [ ] Carregar um modelo `.zip` de exemplo.
  - [ ] Alimentar barras históricas e verificar geração de "Signal".
  - [ ] Verificar transições de "Virtual Position".

---

## Fase 4: Execução & Risco (As "Mãos")
**Meta:** Traduzir sinais em ordens seguras.
**Dependências:** Core, Connector.

- [ ] **Módulo: Config**
  - [ ] Implementar `config/loader.py` e `default.yaml`.
  - [ ] Implementar `config/schema.py` (Validação Pydantic).
  
- [ ] **Módulo: Executor**
  - [ ] Implementar `executor/sync_logic.py` (A "Regra de Ouro").
  - [ ] Implementar `executor/risk_guard.py` (Checagens de DD, Margem).
  - [ ] Implementar `executor/lot_mapper.py` (Intensidade -> Lotes).
  - [ ] Implementar `executor/comment_builder.py` (Trilha de auditoria).
  - [ ] Implementar `executor/executor.py` (Loop Principal: Signal -> Order).

- [ ] **Verificação**
  - [ ] Teste unitário das transições de estado do SyncLogic.
  - [ ] Dry-run do Executor com Mock Connector.

---

## Fase 5: Persistência & Paper (Memória & Benchmark)
**Meta:** Salvar dados e comparar performance.
**Dependências:** Core, Supabase.

- [ ] **Módulo: Persistência**
  - [ ] Implementar `persistence/supabase_client.py` (Async com retry).
  - [ ] Implementar `persistence/local_storage.py` (Backup offline).
  - [ ] Implementar `persistence/session_manager.py` (Heartbeat).

- [ ] **Módulo: Paper**
  - [ ] Implementar `paper/account.py` (Balanço simulado).
  - [ ] Implementar `paper/paper_trader.py` (Simulação de execução).

---

## Fase 6: Orquestração & Lançamento
**Meta:** Unir tudo em um ciclo de vida robusto.

- [ ] **Módulo: Orquestrador**
  - [ ] Implementar `orchestrator/lifecycle.py` (Sequência de Startup/Shutdown).
  - [ ] Implementar `orchestrator/health.py` (Watchdog).
  - [ ] Implementar `orchestrator/orchestrator.py` (Fiação principal).
  - [ ] Implementar `orchestrator/cli.py` (Ponto de entrada via linha de comando).

- [ ] **Teste de Integração Final**
  - [ ] Rodar sistema completo no broker "Mock".
  - [ ] Rodar sistema completo na conta cTrader "Demo".
  - [ ] Validar logs e registros no DB.

---

## Ordem de Prioridade
1. **Core** (Bloqueante para tudo)
2. **Preditor** (Lógica complexa)
3. **Connector** (Dependência externa)
4. **Executor** (Lógica de negócio)
5. **Orquestrador** (Cola)
