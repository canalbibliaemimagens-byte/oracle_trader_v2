# 📋 Oracle v8 - Lista de Inconsistências e Pendências

**Objetivo:** Mapear todas as mudanças necessárias antes de refatorar o notebook de treinamento.

---

## 🔴 DECISÕES PENDENTES (Bloqueiam Implementação)

### P1. Fonte dos Dados de Treinamento (CSV)

**Situação Atual:**
- CSV é exportado manualmente do MT5 Terminal
- Upload manual para Supabase Storage (`oracle_csv`)
- Notebook baixa do Supabase durante execução

**Opções para v2:**

| Opção | Fonte | Prós | Contras |
|-------|-------|------|---------|
| **A** | cTrader Terminal (manual) | Dados garantidos, sem custo API | Trabalho manual, depende do terminal |
| **B** | cTrader Open API (automático) | Automatizado, pode rodar em cron | Custo de tempo GPU se download demorar |
| **C** | Supabase (atual) | Já funciona, notebook não muda | Mantém dependência do MT5/manual |

**Perguntas para decidir:**
1. Quanto tempo leva para baixar 50k barras M15 via cTrader API? (segundos ou minutos?)
2. cTrader API tem rate limit que impacta download de histórico?
3. Dados do cTrader têm mesma qualidade/formato do MT5?

**Recomendação:** Se API demorar < 2 minutos para 50k barras, opção B é ideal (automação total). Se demorar muito, manter opção C (Supabase) e criar script separado para popular o bucket.

---

### P2. Parâmetros do Símbolo (symbol_params.json)

**Situação Atual:**
- Gerado pelo script `generate_symbol_params.py` no MT5
- Contém: `point`, `pip_value`, `spread_points`, `digits`, `min_lot`, `max_lot`
- Upload manual para Supabase

**Para v2 (cTrader):**
- Precisa de script equivalente para cTrader
- Ou: buscar via API no momento do treino (se rápido)

**Decisão necessária:** Manter JSON pré-gerado ou buscar via API?

---

## 🟡 INCONSISTÊNCIAS IDENTIFICADAS (Notebook vs Spec v2)

### I1. Nomenclatura das Ações

| Local | Atual | Spec v2 |
|-------|-------|---------|
| `ACTIONS[0]` | `FLAT` | `WAIT` |
| `ACTIONS[1]` | `LONG_SMALL` | `LONG_WEAK` |
| `ACTIONS[2]` | `LONG_MEDIUM` | `LONG_MODERATE` |
| `ACTIONS[3]` | `LONG_LARGE` | `LONG_STRONG` |
| `ACTIONS[4]` | `SHORT_SMALL` | `SHORT_WEAK` |
| `ACTIONS[5]` | `SHORT_MEDIUM` | `SHORT_MODERATE` |
| `ACTIONS[6]` | `SHORT_LARGE` | `SHORT_STRONG` |

**Impacto:** Apenas cosmético no treino, mas importante para consistência com Preditor/Executor.

---

### I2. Campo `size` vs `intensity` nas Actions

| Atual | Spec v2 |
|-------|---------|
| `"size": 0.01` | `"intensity": 1` |
| `"size": 0.03` | `"intensity": 2` |
| `"size": 0.05` | `"intensity": 3` |

**Motivo:** O lote real é decidido pelo Executor. O modelo emite intensidade do sinal.

**Impacto:** Mudança no JSON de saída. Treino interno continua usando lotes para cálculo de PnL.

---

### I3. Formato de Saída (4 arquivos separados → ZIP com metadata)

**Atual (v7):**
```
{symbol}_{tf}_hmm.pkl
{symbol}_{tf}_ppo.zip
{symbol}_{tf}_exec_config.json  ← JSON separado
{symbol}_{tf}_metrics.csv       ← Será removido
```

**Spec v2:**
```
{symbol}_{tf}.zip
├── {symbol}_{tf}_hmm.pkl
└── {symbol}_{tf}_ppo.zip
    (metadata no zip.comment)   ← JSON embutido no ZIP
```

**Mudanças necessárias:**
1. Remover `_exec_config.json` como arquivo separado
2. Remover `_metrics.csv` (métricas vão no metadata)
3. Adicionar `zip.comment` com JSON completo
4. Adicionar `format_version: "2.0"` no metadata

---

### I4. Estrutura do Metadata

**Atual (exec_config.json):**
```json
{
  "symbol": "EURUSD",
  "symbol_clean": "EURUSD",
  "timeframe": "M15",
  "generated_at": "...",
  "model_files": {...},
  "symbol_config": {...},
  "hmm_params": {...},
  "hmm_state_mapping": {...},
  "rl_params": {...},
  "training_info": {...},
  "actions": {...},
  "backtest_metrics": {...}
}
```

**Spec v2 (zip.comment):**
```json
{
  "format_version": "2.0",
  "generated_at": "...",
  
  "symbol": {
    "name": "EURUSD",
    "clean": "EURUSD",
    "timeframe": "M15"
  },
  
  "training_config": {...},
  "hmm_config": {...},
  "rl_config": {...},
  "actions": {...},
  "backtest_oos": {...},
  "hmm_state_analysis": {...},
  "data_info": {...}
}
```

**Mudanças:**
1. Adicionar `format_version`
2. Reorganizar `symbol` como objeto
3. Renomear `symbol_config` → `training_config`
4. Renomear `hmm_params` → `hmm_config`
5. Renomear `rl_params` → `rl_config`
6. Renomear `backtest_metrics` → `backtest_oos`
7. Adicionar `hmm_state_analysis` com distribuição
8. Adicionar `data_info` com datas e splits
9. Remover `model_files` (implícito pelo ZIP)

---

### I5. Campos Faltantes no Metadata

| Campo | Atual | Spec v2 | Fonte |
|-------|-------|---------|-------|
| `format_version` | ❌ | `"2.0"` | Hardcoded |
| `data_info.date_start` | ❌ | `"2024-01-01"` | Extrair do DataFrame |
| `data_info.date_end` | ❌ | `"2026-01-31"` | Extrair do DataFrame |
| `data_info.total_bars` | ❌ | `50000` | `len(df)` |
| `data_info.train_bars` | ❌ | `35000` | `len(df_train)` |
| `data_info.val_bars` | ❌ | `7500` | `len(df_val)` |
| `data_info.test_bars` | ❌ | `7500` | `len(df_test)` |
| `hmm_state_analysis.state_distribution` | Parcial | Completo | Calcular no treino |
| `backtest_oos.calmar_ratio` | ❌ | Presente | Calcular |

---

### I6. Campos no training_config

**Faltantes:**
- `slippage_points` (existe como `slippage_points_used`)
- `commission_per_lot` (existe como `commission_per_lot_used`)

**Renomear:**
- `spread_points_used` → `spread_points`
- `slippage_points_used` → `slippage_points`
- `commission_per_lot_used` → `commission_per_lot`

---

## 🟢 VALIDAÇÕES CONFIRMADAS (Não Precisa Mudar)

### V1. Features Idênticas ao Treino ✅
- `features.py` está correto e alinhado com `TradingEnv`
- PnL feature: `tanh(PnL / 100)` ✅
- Position size: `position_size * 10` ✅
- Position direction: `-1, 0, 1` ✅

### V2. Lógica de Posição Virtual ✅
- Não faz fechamento parcial
- Mudança de tamanho = fecha + abre
- Idêntico ao `TradingEnv._execute_action()`

### V3. LOT_SIZES Internos ✅
- `[0, 0.01, 0.03, 0.05]` hardcoded
- Usado para cálculo de PnL no treino
- Preditor usa internamente

### V4. Janela de Barras ✅
- 350 barras mínimo para features
- FIFO com `maxlen=350`

---

## 📝 CHECKLIST DE REFATORAÇÃO

### Fase 1: Decisões Pendentes
- [ ] **P1:** Definir fonte de dados (API vs Supabase)
- [ ] **P2:** Definir fonte de symbol_params (JSON vs API)

### Fase 2: Mudanças no Notebook

#### Nomenclatura
- [ ] **I1:** Renomear `FLAT` → `WAIT`
- [ ] **I1:** Renomear `SMALL/MEDIUM/LARGE` → `WEAK/MODERATE/STRONG`
- [ ] **I2:** Trocar `size` por `intensity` nas actions

#### Estrutura de Saída
- [ ] **I3:** Remover geração de `_exec_config.json`
- [ ] **I3:** Remover geração de `_metrics.csv`
- [ ] **I3:** Implementar `zip.comment` com metadata
- [ ] **I4:** Reorganizar estrutura do JSON
- [ ] **I5:** Adicionar campos faltantes
- [ ] **I6:** Renomear campos do training_config

#### Novos Cálculos
- [ ] Extrair `date_start` e `date_end` do DataFrame
- [ ] Calcular `state_distribution` completo
- [ ] Calcular `calmar_ratio`

### Fase 3: Validação
- [ ] ZIP carrega corretamente no Preditor v2
- [ ] Metadata é extraído do `zip.comment`
- [ ] Todos os campos necessários presentes

---

## 🔧 ESTIMATIVA DE ESFORÇO

| Tarefa | Complexidade | Tempo Estimado |
|--------|--------------|----------------|
| Decisões P1/P2 | Análise | 1 sessão de discussão |
| Nomenclatura (I1, I2) | Baixa | 15 min |
| Estrutura JSON (I4, I5, I6) | Média | 30 min |
| ZIP com comment (I3) | Média | 20 min |
| Testes e validação | Média | 30 min |
| **Total** | - | **~2 horas** (após decisões) |

---

## 📌 NOTAS ADICIONAIS

### Sobre Custo de GPU

O treinamento em Kaggle/Colab tem tempo limitado:
- **Kaggle:** 30h/semana GPU
- **Colab Free:** ~12h/sessão (com interrupções)
- **Colab Pro:** Mais estável

**Impacto das decisões:**
- Se download de dados via API demorar 5+ minutos, consome tempo de GPU desnecessariamente
- Melhor baixar dados ANTES de iniciar sessão GPU
- Opção: Célula de download em CPU, depois habilitar GPU para treino

### Sobre Compatibilidade

O formato v2 (ZIP com metadata no comment) é **breaking change**:
- Preditor v1 não lê o novo formato
- Precisa atualizar Preditor junto com notebook
- Sugestão: manter flag `format_version` para futuras migrações

---

*Documento criado em: 2026-02-04*
*Última atualização: 2026-02-04*
