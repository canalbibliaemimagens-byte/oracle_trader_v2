# 📚 Oracle Trader v2.0 - Guia de Desenvolvimento

> **Sistema Autônomo de Trading com Reinforcement Learning (HMM + PPO)**

![Status](https://img.shields.io/badge/Status-Em%20Desenvolvimento-yellow)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![License](https://img.shields.io/badge/License-Privado-red)

---

## 🔗 Links Rápidos

| Recurso | Link |
| :--- | :--- |
| 📂 **Repositório GitHub** | [oracle_trader_v2](https://github.com/canalbibliaemimagens-byte/oracle_trader_v2) |
| 📊 **Dashboard** | [oracle-rl.vercel.app](https://oracle-rl.vercel.app/) |
| 🗄️ **Supabase** | [Projeto Supabase](https://supabase.com/dashboard/project/erinxuykijsydorlgjgy) |
| ☁️ **Oracle Cloud** | [cloud.oracle.com](https://cloud.oracle.com) |

---

## 📖 Sobre Este Diretório

Este diretório (`/docs`) contém toda a documentação técnica para:
- **Entender** a arquitetura do sistema
- **Implementar** os módulos de código
- **Implantar** em produção (Oracle Cloud VM)
- **Treinar** novos modelos (Kaggle/Colab)

---

## 🗺️ Roteiro de Leitura

### 🏗️ Fase 1: Entendimento (Arquitetura)
*Antes de escrever código, entenda o "que" e o "porquê".*

| # | Documento | Descrição | Tempo |
| :--- | :--- | :--- | :--- |
| 1 | [Estrutura do Projeto](ORACLE_V2_PROJECT_STRUCTURE.md) | Visão geral dos módulos, diretórios e como as peças se encaixam. **Comece aqui.** | 15min |
| 2 | [Arquitetura de Alta Disponibilidade](ARCH_V2_HIGH_AVAILABILITY_v1.1.md) | Conceito de "Digital Twin", uso de RAM (1GB), processos isolados. | 20min |

### 🛠️ Fase 2: Construção (Implementação)
*Regras de negócio e roteiro de codificação.*

| # | Documento | Descrição | Tempo |
| :--- | :--- | :--- | :--- |
| 3 | [Especificação Técnica](ORACLE_V2_SPECIFICATION_v1.1.md) | **A Bíblia.** Contratos de dados, protocolos, lógica de sincronização. Consulte sempre. | 60min |
| 4 | [Plano de Implementação](implementation_plan_v2.md) | Checklist passo-a-passo. Ordem de criação: Core → Preditor → Connector → ... | 30min |
| 5 | [Notebook v2 Spec](oracle_v2_notebook_1.0_reorganization.md) | Especificação do ambiente de treino. Garante `.zip` compatíveis com v2. | 20min |

### 🧩 Fase 2.5: Specs Detalhadas por Módulo
*Consulte conforme for implementar cada módulo.*

| Módulo | Spec | Descrição |
| :--- | :--- | :--- |
| `core/` | [SPEC_CORE.md](modules/SPEC_CORE.md) | Tipos base, enums, dataclasses |
| `config/` | [SPEC_CONFIG.md](modules/SPEC_CONFIG.md) | Carregamento e validação de configs |
| `predictor/` | [SPEC_PREDITOR.md](modules/SPEC_PREDITOR.md) | HMM + PPO, cálculo de features |
| `connector/` | [SPEC_CONNECTOR.md](modules/SPEC_CONNECTOR.md) | Interface com cTrader API |
| `executor/` | [SPEC_EXECUTOR.md](modules/SPEC_EXECUTOR.md) | Gestão de ordens e posições |
| `orchestrator/` | [SPEC_ORCHESTRATOR.md](modules/SPEC_ORCHESTRATOR.md) | Loop principal, state machine |
| `paper/` | [SPEC_PAPER.md](modules/SPEC_PAPER.md) | Modo paper trading |
| `persistence/` | [SPEC_PERSISTENCE.md](modules/SPEC_PERSISTENCE.md) | Supabase logger |

### 🚀 Fase 3: Implantação (Deployment)
*Colocando em produção.*

| # | Documento | Descrição | Tempo |
| :--- | :--- | :--- | :--- |
| 6 | [Guia Oracle Cloud VM](guia_oracle_cloud_vm_arm.md) | Configuração do servidor ARM gratuito, Python, Docker, ZRAM. 24/7. | 45min |

### 🔮 Fase 4: Roadmap (Futuro)
*Funcionalidades planejadas.*

| # | Documento | Descrição | Status |
| :--- | :--- | :--- | :--- |
| 7 | [Meta-Calibrador](meta_calibrador_spec_v1.0.md) | Sistema de auto-calibração de parâmetros via Meta-RL. | 📁 Arquivado |

---

## 📂 Estrutura do Diretório `/docs`

```text
docs/
├── README.md                              # ← Você está aqui
│
├── 📐 Arquitetura
│   ├── ORACLE_V2_PROJECT_STRUCTURE.md     # Estrutura de pastas e módulos
│   └── ARCH_V2_HIGH_AVAILABILITY_v1.1.md  # Digital Twin, RAM, processos
│
├── 📋 Especificações
│   ├── ORACLE_V2_SPECIFICATION_v1.1.md    # Especificação técnica completa
│   ├── oracle_v2_notebook_1.0_reorganization.md  # Spec do notebook
│   └── meta_calibrador_spec_v1.0.md       # (Futuro) Meta-Calibrador
│
├── 🧩 modules/                            # Specs detalhadas por módulo
│   ├── SPEC_CORE.md                       # Tipos base, config, utils
│   ├── SPEC_CONFIG.md                     # Configurações e validação
│   ├── SPEC_PREDITOR.md                   # HMM + PPO, features
│   ├── SPEC_CONNECTOR.md                  # Interface cTrader
│   ├── SPEC_EXECUTOR.md                   # Gestão de ordens
│   ├── SPEC_ORCHESTRATOR.md               # Loop principal, state machine
│   ├── SPEC_PAPER.md                      # Paper trading mode
│   └── SPEC_PERSISTENCE.md                # Supabase logger
│
├── 🛠️ Implementação
│   └── implementation_plan_v2.md          # Checklist de desenvolvimento
│
├── 🚀 Deployment
│   └── guia_oracle_cloud_vm_arm.md        # Setup Oracle Cloud
│
├── 🔍 Análise
│   └── ORACLE_V8_INCONSISTENCIAS.md       # Issues identificadas na v1
│
└── 📦 backup/                             # Versões antigas (histórico)
    ├── ARCH_V2_HIGH_AVAILABILITY.md
    ├── implementation_plan.md
    └── ORACLE_V2_SPECIFICATION.md
```

---

## 🏃 Quick Start para Desenvolvedores

### 1. Clone o Repositório

```bash
git clone https://github.com/canalbibliaemimagens-byte/oracle_trader_v2.git
cd oracle_trader_v2
```

### 2. Configure o Ambiente

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate   # Windows

# Instalar dependências
pip install -r requirements.txt
```

### 3. Configure as Variáveis de Ambiente

```bash
cp .env.example .env
# Edite .env com suas credenciais
```

### 4. Leia os Documentos na Ordem

1. [ORACLE_V2_PROJECT_STRUCTURE.md](ORACLE_V2_PROJECT_STRUCTURE.md)    → Entenda a estrutura
2. [ORACLE_V2_SPECIFICATION_v1.1.md](ORACLE_V2_SPECIFICATION_v1.1.md)   → Entenda as regras
3. [implementation_plan_v2.md](implementation_plan_v2.md)         → Comece a codar

---

## 📊 Status do Projeto

### Módulos v2.0

| Módulo | Status | Spec | Descrição |
| :--- | :--- | :--- | :--- |
| `core/` | 🟡 Spec Pronta | [SPEC_CORE](modules/SPEC_CORE.md) | Tipos base, configurações, utilitários |
| `config/` | 🟡 Spec Pronta | [SPEC_CONFIG](modules/SPEC_CONFIG.md) | Carregamento e validação |
| `predictor/` | 🟡 Spec Pronta | [SPEC_PREDITOR](modules/SPEC_PREDITOR.md) | HMM + PPO, cálculo de features |
| `connector/` | 🟡 Spec Pronta | [SPEC_CONNECTOR](modules/SPEC_CONNECTOR.md) | Interface com cTrader |
| `executor/` | 🟡 Spec Pronta | [SPEC_EXECUTOR](modules/SPEC_EXECUTOR.md) | Gestão de ordens e posições |
| `orchestrator/` | 🟡 Spec Pronta | [SPEC_ORCHESTRATOR](modules/SPEC_ORCHESTRATOR.md) | Loop principal, state machine |
| `paper/` | 🟡 Spec Pronta | [SPEC_PAPER](modules/SPEC_PAPER.md) | Paper trading mode |
| `persistence/` | 🟡 Spec Pronta | [SPEC_PERSISTENCE](modules/SPEC_PERSISTENCE.md) | Supabase logger |

**Legenda:** 🟢 Completo | 🟡 Em Progresso | 🔴 Não Iniciado

### Componentes Auxiliares

| Componente | Status | Descrição |
| :--- | :--- | :--- |
| Notebook v2 | 🟡 Spec Pronta | Treino HMM + PPO (Kaggle/Colab) |
| Dashboard | 🟢 Funcional | React + Supabase Realtime |
| Oracle Cloud VM | 🟡 Guia Pronto | Deploy ARM 24/7 |

---

## 🔧 Stack Tecnológica

### Backend (Trading Engine)
- **Python 3.11+**
- **stable-baselines3** (PPO)
- **hmmlearn** (Hidden Markov Model)
- **asyncio** (Concorrência)
- **websockets** (API)

### Infraestrutura
- **Oracle Cloud** (VM ARM gratuita)
- **Supabase** (PostgreSQL + Realtime)
- **Docker** (Containerização)

### Treino de Modelos
- **Kaggle/Colab** (GPU T4)
- **PyTorch** (via SB3)

### Dashboard
- **React** + **TypeScript**
- **Tailwind CSS**
- **Vercel** (Hosting)

---

## 📝 Convenções de Código

### Commits

```text
feat: nova funcionalidade
fix: correção de bug
docs: documentação
refactor: refatoração sem mudança de comportamento
test: testes
chore: manutenção
```

### Branches

```text
main        → Produção (protegido)
develop     → Desenvolvimento
feature/*   → Novas funcionalidades
fix/*       → Correções
```

### Nomenclatura de Arquivos

```text
snake_case.py         → Módulos Python
UPPER_SNAKE.md        → Documentos principais
lowercase-with-dash/  → Diretórios
```

---

## 🤝 Contribuição

1. Leia a [Especificação Técnica](ORACLE_V2_SPECIFICATION_v1.1.md) antes de contribuir
2. Siga o [Plano de Implementação](implementation_plan_v2.md) para saber o que fazer
3. Crie uma branch `feature/sua-feature`
4. Faça commits seguindo as convenções
5. Abra um Pull Request para `develop`

---

## ❓ FAQ

<details>
<summary><b>Como treinar um novo modelo?</b></summary>

1. Acesse o [Notebook v2](oracle_v2_notebook_1.0_reorganization.md)
2. Configure SYMBOL, TIMEFRAME e HISTORY_*
3. Execute "Run All" no Kaggle/Colab
4. O modelo será salvo no Supabase automaticamente
</details>

<details>
<summary><b>Como adicionar um novo símbolo?</b></summary>

1. Treine o modelo no Notebook
2. O modelo aparecerá no Dashboard
3. Configure `lot_multiplier` no `symbols_config.json`
4. Use `UNBLOCK_SYMBOL` para ativar
</details>

<details>
<summary><b>Como debugar problemas?</b></summary>

1. Verifique logs: `tail -f logs/oracle.log`
2. Verifique Supabase: tabela `events`
3. Verifique Dashboard: aba "Logs"
</details>

---

## 📞 Suporte

- **Documentação:** Este diretório `/docs`
- **Issues:** GitHub Issues
- **Logs:** Supabase `events` table

---

## 📄 Licença

Projeto privado. Todos os direitos reservados.

---

*Última atualização: 2026-02-04*
