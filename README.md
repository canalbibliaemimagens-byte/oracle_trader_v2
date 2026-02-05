# 🤖 Oracle Trader v2.0

> **Sistema Autônomo de Trading com Reinforcement Learning**

[![Status](https://img.shields.io/badge/Status-Em%20Desenvolvimento-yellow)]()
[![Python](https://img.shields.io/badge/Python-3.11+-blue)]()
[![cTrader](https://img.shields.io/badge/Broker-cTrader%20Open%20API-green)]()
[![License](https://img.shields.io/badge/License-Privado-red)]()

---

## 🔗 Links Rápidos

| Recurso | Link |
|---------|------|
| 📂 **Repositório** | [GitHub](https://github.com/canalbibliaemimagens-byte/oracle_trader_v2) |
| 📊 **Dashboard** | [oracle-rl.vercel.app](https://oracle-rl.vercel.app/) |
| 🗄️ **Supabase** | [Projeto](https://supabase.com/dashboard/project/erinxuykijsydorlgjgy) |
| 📚 **Documentação** | [docs/README.md](docs/README.md) |

---

## 📖 Sobre o Projeto

Oracle Trader v2.0 é um sistema autônomo de trading projetado para **alta disponibilidade** e **paridade exata** entre os ambientes de treinamento e execução.

### Arquitetura "Digital Twin"

O sistema utiliza uma arquitetura de "Gêmeo Digital" onde o motor de predição opera em um ambiente isolado, garantindo que o comportamento do modelo em produção seja idêntico ao seu desempenho durante o treinamento.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORACLE TRADER v2.0                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌───────────┐   │
│   │   cTrader   │───▶│  Connector  │───▶│  Preditor   │───▶│ Executor  │   │
│   │    (API)    │    │  (Broker)   │    │ (HMM + PPO) │    │ (Ordens)  │   │
│   └─────────────┘    └─────────────┘    └─────────────┘    └───────────┘   │
│         │                                      │                  │        │
│         │            ┌─────────────┐           │                  │        │
│         └───────────▶│ Orchestrator│◀──────────┴──────────────────┘        │
│                      │   (Core)    │                                       │
│                      └──────┬──────┘                                       │
│                             │                                              │
│                      ┌──────▼──────┐                                       │
│                      │  Supabase   │                                       │
│                      │  (Logs/DB)  │                                       │
│                      └─────────────┘                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🌟 Principais Características

### 🧠 Inteligência Artificial
- **HMM (Hidden Markov Model)** - Detecção de regime de mercado (Bull/Bear/Range)
- **PPO (Proximal Policy Optimization)** - Decisão de trade via Reinforcement Learning
- **Rede 256x256x256** - Arquitetura profunda otimizada para trading

### 🔄 Arquitetura Digital Twin
- **Posição Virtual** - O `Preditor` mantém estado que espelha o ambiente de treino
- **Zero Drift** - Elimina discrepâncias entre treino e produção
- **Ações Semânticas** - Modelo emite "intenção" (LONG_STRONG, WAIT), não ordens brutas

### 🛡️ Gestão de Risco
- **Drawdown Protection** - Limites de DD automáticos
- **SL Protection** - Warmup após múltiplos SL hits
- **Paper Trading** - Modo simulação para validação

### ⚡ Performance
- **20+ Modelos Simultâneos** - Otimizado para 1GB RAM
- **Oracle Cloud ARM** - Roda 24/7 em VM gratuita
- **Memória Compartilhada** - Estruturas de dados otimizadas

### 🔌 Broker Agnostic
- **Lógica Separada** - Core independente do broker
- **cTrader Open API** - Módulo `Connector` abstrai a comunicação
- **Extensível** - Fácil adicionar outros brokers

---

## 📊 Resultados

> Dados de ~300 trades em 3 dias de operação (v1)

| Categoria | Exemplos | Performance |
|-----------|----------|-------------|
| Forex Major | EURUSD, AUDUSD, USDJPY | ✅ Excelente |
| Forex Cross | EURJPY, USDCAD | ✅ Bom |
| Índices | JP225, US500 | ⚠️ Variável |

*A v2.0 visa melhorar a consistência em todas as categorias.*

---

## 📂 Estrutura do Projeto

```
oracle_trader_v2/
│
├── 📁 docs/                    # Documentação completa
│   ├── modules/                # Specs detalhadas por módulo
│   └── backup/                 # Versões anteriores
│
├── 📁 oracle_v2/               # Código fonte principal
│   ├── core/                   # Tipos base, constantes, utilitários
│   ├── config/                 # Configurações e validação
│   ├── connector/              # Interface cTrader Open API
│   ├── preditor/               # HMM + PPO + Posição Virtual
│   ├── executor/               # Gestão de ordens e risco
│   ├── orchestrator/           # Loop principal, state machine
│   ├── paper/                  # Simulação para benchmark
│   └── persistence/            # Supabase logger
│
├── 📁 models/                  # Modelos treinados (.zip)
│
├── 📁 tests/                   # Testes automatizados
│
├── 📄 .env.example             # Template de variáveis de ambiente
├── 📄 requirements.txt         # Dependências Python
└── 📄 README.md                # Este arquivo
```

---

## 🚀 Quick Start

### Pré-requisitos

- Python 3.11+
- Conta cTrader com Open API habilitada
- Conta Supabase (opcional, para logs)

### Instalação

```bash
# 1. Clone o repositório
git clone https://github.com/canalbibliaemimagens-byte/oracle_trader_v2.git
cd oracle_trader_v2

# 2. Crie o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate   # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure as variáveis de ambiente
cp .env.example .env
# Edite .env com suas credenciais
```

### Configuração

```bash
# .env
CTRADER_CLIENT_ID=seu_client_id
CTRADER_CLIENT_SECRET=seu_client_secret
CTRADER_ACCESS_TOKEN=seu_access_token
CTRADER_ACCOUNT_ID=seu_account_id

SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_KEY=sua_chave_anon
```

### Execução

```bash
# Modo produção
python -m oracle_v2.main

# Modo paper trading
python -m oracle_v2.main --paper

# Com logs verbosos
python -m oracle_v2.main --log-level DEBUG
```

---

## 📚 Documentação

A documentação completa está em [`docs/`](docs/README.md).

### Roteiro de Leitura

| Ordem | Documento | Descrição |
|-------|-----------|-----------|
| 1 | [Estrutura do Projeto](docs/ORACLE_V2_PROJECT_STRUCTURE.md) | **Comece aqui.** Visão geral da arquitetura |
| 2 | [Especificação Técnica](docs/ORACLE_V2_SPECIFICATION_v1.1.md) | Contratos, protocolos, regras de negócio |
| 3 | [Plano de Implementação](docs/implementation_plan_v2.md) | Checklist passo-a-passo |
| 4 | [Alta Disponibilidade](docs/ARCH_V2_HIGH_AVAILABILITY_v1.1.md) | Digital Twin, gestão de memória |
| 5 | [Notebook de Treino](docs/oracle_v2_notebook_1.0_reorganization.md) | Spec do ambiente Kaggle/Colab |
| 6 | [Guia Oracle Cloud](docs/guia_oracle_cloud_vm_arm.md) | Deploy em VM ARM gratuita |

### Specs dos Módulos

| Módulo | Spec | Descrição |
|--------|------|-----------|
| `core/` | [SPEC_CORE](docs/modules/SPEC_CORE.md) | Tipos base, enums, dataclasses |
| `config/` | [SPEC_CONFIG](docs/modules/SPEC_CONFIG.md) | Carregamento e validação |
| `preditor/` | [SPEC_PREDITOR](docs/modules/SPEC_PREDITOR.md) | HMM + PPO, features |
| `connector/` | [SPEC_CONNECTOR](docs/modules/SPEC_CONNECTOR.md) | Interface cTrader |
| `executor/` | [SPEC_EXECUTOR](docs/modules/SPEC_EXECUTOR.md) | Ordens e risco |
| `orchestrator/` | [SPEC_ORCHESTRATOR](docs/modules/SPEC_ORCHESTRATOR.md) | Loop principal |
| `paper/` | [SPEC_PAPER](docs/modules/SPEC_PAPER.md) | Simulação |
| `persistence/` | [SPEC_PERSISTENCE](docs/modules/SPEC_PERSISTENCE.md) | Supabase logger |

---

## 🧪 Treinamento de Modelos

Os modelos são treinados em **Kaggle** ou **Google Colab** usando GPU T4.

### Processo

1. Configure o notebook com SYMBOL e TIMEFRAME
2. Execute "Run All"
3. O modelo é salvo automaticamente no Supabase
4. Baixe e coloque na pasta `models/`

### Especificações do Modelo

| Parâmetro | Valor |
|-----------|-------|
| Arquitetura | PPO (256x256x256) |
| HMM States | 5 (default) |
| Timesteps | 2.000.000 |
| Tempo de Treino | ~1.5h (GPU T4) |

Ver [Notebook Spec](docs/oracle_v2_notebook_1.0_reorganization.md) para detalhes.

---

## 🔧 Stack Tecnológica

### Trading Engine
| Tecnologia | Uso |
|------------|-----|
| Python 3.11+ | Linguagem principal |
| stable-baselines3 | PPO (Reinforcement Learning) |
| hmmlearn | Hidden Markov Model |
| asyncio | Concorrência |
| websockets | API real-time |

### Infraestrutura
| Tecnologia | Uso |
|------------|-----|
| Oracle Cloud | VM ARM gratuita (24/7) |
| Supabase | PostgreSQL + Realtime |
| Docker | Containerização (opcional) |

### Treino
| Tecnologia | Uso |
|------------|-----|
| Kaggle/Colab | GPU T4 gratuita |
| PyTorch | Backend do SB3 |

### Dashboard
| Tecnologia | Uso |
|------------|-----|
| React + TypeScript | Frontend |
| Tailwind CSS | Estilização |
| Vercel | Hosting |

---

## 📈 Roadmap

### v2.0 (Atual)
- [x] Especificação técnica completa
- [x] Specs de todos os módulos
- [x] Arquitetura Digital Twin
- [ ] Implementação do Core
- [ ] Implementação do Preditor
- [ ] Implementação do Connector
- [ ] Integração e testes

### v2.1 (Futuro)
- [ ] Multi-timeframe analysis
- [ ] Notificações (Telegram/Discord)
- [ ] Métricas avançadas no Dashboard

### v3.0 (Roadmap)
- [ ] [Meta-Calibrador](docs/meta_calibrador_spec_v1.0.md) - Auto-calibração de parâmetros
- [ ] Suporte a múltiplos brokers
- [ ] Backtesting integrado

---

## 🤝 Contribuição

1. Leia a [Especificação Técnica](docs/ORACLE_V2_SPECIFICATION_v1.1.md)
2. Siga o [Plano de Implementação](docs/implementation_plan_v2.md)
3. Crie uma branch `feature/sua-feature`
4. Faça commits seguindo as convenções
5. Abra um Pull Request

### Convenções de Commit

```
feat: nova funcionalidade
fix: correção de bug
docs: documentação
refactor: refatoração
test: testes
chore: manutenção
```

---

## ❓ FAQ

<details>
<summary><b>Como treinar um novo modelo?</b></summary>

1. Acesse Kaggle ou Colab
2. Configure SYMBOL e TIMEFRAME no notebook
3. Execute "Run All"
4. O modelo será salvo no Supabase
5. Baixe e coloque em `models/`
</details>

<details>
<summary><b>Posso usar com outro broker além do cTrader?</b></summary>

A arquitetura é broker-agnostic. O módulo `Connector` abstrai a comunicação.
Para adicionar outro broker, implemente a interface definida em `SPEC_CONNECTOR.md`.
</details>

<details>
<summary><b>Quanto custa rodar o sistema?</b></summary>

- **VM Oracle Cloud**: Gratuita (Always Free Tier)
- **Supabase**: Gratuito (Free Tier)
- **Kaggle/Colab**: Gratuito (GPU T4)
- **Vercel**: Gratuito (Hobby Tier)

O sistema foi projetado para rodar 100% gratuito.
</details>

<details>
<summary><b>Qual a performance esperada?</b></summary>

Resultados variam por ativo. Em testes com ~300 trades:
- Forex Major: Win rate ~55-60%, Sharpe > 1.0
- Índices: Mais variável, requer ajuste de parâmetros

Ver [Meta-Calibrador](docs/meta_calibrador_spec_v1.0.md) para otimização futura.
</details>

---

## ⚠️ Aviso Legal

Este software é fornecido apenas para fins educacionais e de pesquisa. **Trading envolve risco de perda financeira.** O autor não se responsabiliza por perdas decorrentes do uso deste sistema.

- Não é conselho financeiro
- Performance passada não garante resultados futuros
- Use por sua conta e risco

---

## 📄 Licença

Projeto privado. Todos os direitos reservados.

---

## 📞 Contato

- **Issues**: [GitHub Issues](https://github.com/canalbibliaemimagens-byte/oracle_trader_v2/issues)
- **Documentação**: [docs/](docs/README.md)

---

*Última atualização: 2026-02-05*
