# Oracle v2 Notebook 1.0 - Proposta de Reorganização

**Versão:** 1.0  
**Data:** 2026-02-04  
**Objetivo:** Notebook de treinamento HMM + PPO com download direto da API cTrader

---

## Visão Geral

### Mudanças Principais vs v7

| Aspecto | v7 | v2 Notebook 1.0 |
|---------|----|-----------------| 
| Fonte de dados | CSV no Supabase | **API cTrader** |
| Inputs interativos | 3 (ambiente, CSV, HMM) | **0** |
| Parâmetros do símbolo | symbol_params.json | **Direto da API** |
| Período dos dados | Fixo no CSV | **Configurável** |
| Spread/Commission | Fixo no JSON | **Real-time da API** |
| Documentação de params | Mínima | **Completa inline** |
| Suporta "Run All" | ❌ | ✅ |

### Estrutura do Notebook

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SEÇÃO 0: CONFIGURAÇÃO PRINCIPAL (usuário DEVE editar)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 1: PARÂMETROS AVANÇADOS (NÃO recomendado alterar)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 2: SETUP (auto)                                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 3: CONEXÃO cTRADER (auto)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 4: CONFIGURAÇÃO AUTOMÁTICA (auto)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 5: VISUALIZAÇÃO DOS DADOS (auto)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 6: TREINO HMM  🔒 INTOCÁVEL                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 7: TREINO PPO  🔒 INTOCÁVEL                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 8: BACKTEST (auto)                                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 9: EXPORT & UPLOAD (auto)                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  SEÇÃO 10: FINALIZAÇÃO (auto)                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## SEÇÃO 0: Configuração Principal

**Objetivo:** Parâmetros que o usuário DEVE configurar para cada treino.

```python
# =============================================================================
# ⚙️ SEÇÃO 0: CONFIGURAÇÃO PRINCIPAL
# =============================================================================
# Configure os parâmetros abaixo para seu modelo.
# Após configurar, execute: Runtime → Run All (Ctrl+F9)
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# 📊 SÍMBOLO E TIMEFRAME
# ─────────────────────────────────────────────────────────────────────────────
SYMBOL = "EURUSD"              # Nome do símbolo no cTrader (ex: EURUSD, GBPUSD, US500)
TIMEFRAME = "M15"              # Timeframe: M1, M5, M15, M30, H1, H4, D1

# ─────────────────────────────────────────────────────────────────────────────
# 📅 PERÍODO DO HISTÓRICO
# ─────────────────────────────────────────────────────────────────────────────
HISTORY_AMOUNT = 2             # Quantidade de períodos para trás
HISTORY_UNIT = "years"         # Unidade: "years", "months", "days"
HISTORY_END_DATE = "2026-02-04"  # Data final (YYYY-MM-DD), None = data atual

# Exemplo: AMOUNT=2, UNIT="years", END_DATE="2026-02-04"
#          → Baixa dados de 04/02/2024 até 04/02/2026

# ─────────────────────────────────────────────────────────────────────────────
# 🔮 PARÂMETROS HMM (Detecção de Regime de Mercado)
# ─────────────────────────────────────────────────────────────────────────────
HMM_STATES = 5                 # Número de estados/regimes (default: 5)
HMM_MOMENTUM_PERIOD = 12       # Período para cálculo de momentum (default: 12)
HMM_CONSISTENCY_PERIOD = 12    # Período para cálculo de consistência (default: 12)
HMM_RANGE_PERIOD = 20          # Período para posição no range (default: 20)

# ─────────────────────────────────────────────────────────────────────────────
# 💰 CUSTOS DE EXECUÇÃO
# ─────────────────────────────────────────────────────────────────────────────
SLIPPAGE_POINTS = 2            # Slippage simulado em pontos (default: 2)

# =============================================================================
```

---

## SEÇÃO 1: Parâmetros Avançados

**Objetivo:** Parâmetros com valores validados que NÃO são recomendados alterar, mas estão disponíveis para experimentação avançada.

```python
# =============================================================================
# 🔬 SEÇÃO 1: PARÂMETROS AVANÇADOS (NÃO RECOMENDADO ALTERAR)
# =============================================================================
# ⚠️ ATENÇÃO: Os valores abaixo foram calibrados e validados em extensivos
# backtests. Alterações podem degradar significativamente a performance do
# modelo ou causar comportamentos inesperados.
#
# Se você é iniciante, PULE ESTA SEÇÃO e use os valores padrão.
# Se você é experiente e quer explorar, leia a documentação de cada parâmetro.
# =============================================================================

# ─────────────────────────────────────────────────────────────────────────────
# 📈 PARÂMETROS RL (Features do Modelo PPO)
# ─────────────────────────────────────────────────────────────────────────────
# Estes parâmetros definem como o modelo "enxerga" o mercado.
# Alterar pode fazer o modelo interpretar padrões de forma diferente.
# ─────────────────────────────────────────────────────────────────────────────

RL_ROC_PERIOD = 10
# │ O QUE É: Período do Rate of Change (momentum de curto prazo)
# │ AFETA: Sensibilidade a movimentos rápidos de preço
# │ MENOR (5-8): Mais sensível a ruído, reage rápido a reversões
# │ MAIOR (12-20): Mais suave, ignora movimentos pequenos, captura tendências
# │ RELAÇÃO: Mercados voláteis (crypto, índices) podem se beneficiar de valores menores
# │ DEFAULT: 10 - Bom equilíbrio para forex e maioria dos ativos

RL_ATR_PERIOD = 14
# │ O QUE É: Período do Average True Range (medida de volatilidade)
# │ AFETA: Como o modelo percebe a volatilidade atual vs histórica
# │ MENOR (7-10): Volatilidade mais "nervosa", reage rápido a mudanças
# │ MAIOR (20-30): Volatilidade mais "estável", suaviza picos
# │ RELAÇÃO: Usado internamente para normalizar features e pode afetar sizing
# │ DEFAULT: 14 - Padrão da indústria, funciona bem na maioria dos casos

RL_EMA_PERIOD = 200
# │ O QUE É: Período da Média Móvel Exponencial (tendência de longo prazo)
# │ AFETA: Definição de "tendência" - preço acima/abaixo da EMA
# │ MENOR (50-100): Tendência de médio prazo, mais sinais de mudança
# │ MAIOR (200-300): Tendência de longo prazo, menos ruído
# │ RELAÇÃO: EMA200 é referência institucional, muito usada por traders
# │ DEFAULT: 200 - Padrão institucional, define tendência macro

RL_RANGE_PERIOD = 20
# │ O QUE É: Período para calcular posição no range (high/low)
# │ AFETA: Identificação de suporte/resistência de curto prazo
# │ MENOR (10-15): Range mais apertado, mais sinais de breakout
# │ MAIOR (30-50): Range mais amplo, menos falsos breakouts
# │ RELAÇÃO: Combinado com HMM_RANGE_PERIOD para detectar consolidação
# │ DEFAULT: 20 - ~1 mês de trading em M15, bom para swing

RL_VOLUME_MA_PERIOD = 20
# │ O QUE É: Período da média móvel de volume
# │ AFETA: Detecção de volume anormal (confirmação de movimentos)
# │ MENOR (10): Volume anormal detectado mais facilmente
# │ MAIOR (30-50): Precisa de mais confirmação para sinalizar
# │ RELAÇÃO: Volume relativo > 1 sugere interesse institucional
# │ DEFAULT: 20 - Consistente com outros períodos de curto prazo
# │ NOTA: Em forex, volume é tick volume (proxy, não volume real)

# ─────────────────────────────────────────────────────────────────────────────
# 🧠 PARÂMETROS DE TREINO PPO
# ─────────────────────────────────────────────────────────────────────────────
# Estes parâmetros controlam o algoritmo de aprendizado.
# Alterar requer conhecimento de Reinforcement Learning.
# ─────────────────────────────────────────────────────────────────────────────

RL_TOTAL_TIMESTEPS = 2_000_000
# │ O QUE É: Número total de passos de treino
# │ AFETA: Quanto o modelo "pratica" antes de ser avaliado
# │ MENOR (500k-1M): Treino mais rápido, pode não convergir
# │ MAIOR (3M-5M): Treino mais longo, risco de overfitting
# │ RELAÇÃO: Depende da complexidade do símbolo e quantidade de dados
# │ DEFAULT: 2M - Bom equilíbrio tempo/qualidade para maioria dos casos
# │ TEMPO: ~30-60min em GPU T4 (Kaggle/Colab)

RL_LEARNING_RATE = 3e-4
# │ O QUE É: Taxa de aprendizado do otimizador
# │ AFETA: Velocidade e estabilidade do aprendizado
# │ MENOR (1e-4): Aprendizado mais lento, mais estável
# │ MAIOR (1e-3): Aprendizado mais rápido, pode oscilar
# │ RELAÇÃO: LR alto + muitos timesteps = risco de divergir
# │ DEFAULT: 3e-4 - Recomendado pelo paper do PPO

RL_BATCH_SIZE = 512
# │ O QUE É: Quantidade de amostras por atualização de gradiente
# │ AFETA: Estabilidade do treino e uso de memória
# │ MENOR (64-256): Mais ruído, pode ajudar generalização
# │ MAIOR (1024-2048): Mais estável, requer mais memória GPU
# │ RELAÇÃO: Batch maior geralmente precisa de LR maior
# │ DEFAULT: 512 - Bom para GPUs com 8-16GB

RL_N_STEPS = 4096
# │ O QUE É: Passos coletados antes de cada atualização
# │ AFETA: Variância das estimativas de vantagem (advantage)
# │ MENOR (1024-2048): Atualizações mais frequentes, mais variância
# │ MAIOR (8192): Estimativas mais precisas, mais memória
# │ RELAÇÃO: N_STEPS deve ser divisível por BATCH_SIZE
# │ DEFAULT: 4096 - 8 batches por atualização

RL_GAMMA = 0.99
# │ O QUE É: Fator de desconto (discount factor)
# │ AFETA: Quanto o modelo valoriza recompensas futuras vs imediatas
# │ MENOR (0.9-0.95): Foco em curto prazo, mais trades
# │ MAIOR (0.99-0.999): Foco em longo prazo, menos trades
# │ RELAÇÃO: Trading de curto prazo pode usar gamma menor
# │ DEFAULT: 0.99 - Padrão para a maioria dos problemas RL

# ─────────────────────────────────────────────────────────────────────────────
# 💵 PARÂMETROS DE TRADING
# ─────────────────────────────────────────────────────────────────────────────
# Estes parâmetros definem o ambiente de simulação.
# ─────────────────────────────────────────────────────────────────────────────

INITIAL_BALANCE = 10000
# │ O QUE É: Balance inicial da conta simulada
# │ AFETA: Escala das recompensas e lot sizing
# │ RELAÇÃO: LOT_SIZES são calibrados para ~$10k
# │ DEFAULT: 10000 - Padrão para backtests comparáveis

COMMISSION_PER_LOT = 7.0
# │ O QUE É: Comissão por lote (round-trip)
# │ AFETA: Custo de cada trade, penaliza overtrading
# │ MENOR: Mais trades lucrativos, pode incentivar overtrading
# │ MAIOR: Menos trades, só entra em setups de alta probabilidade
# │ RELAÇÃO: Valor real depende da corretora (None = usa cTrader)
# │ DEFAULT: 7.0 - Típico para ECN forex

# ─────────────────────────────────────────────────────────────────────────────
# 📊 SPLIT DE DADOS
# ─────────────────────────────────────────────────────────────────────────────
# Como os dados são divididos para treino/validação/teste.
# ─────────────────────────────────────────────────────────────────────────────

TRAIN_RATIO = 0.70
VAL_RATIO = 0.15
TEST_RATIO = 0.15
# │ O QUE É: Proporção de dados para cada fase
# │ TRAIN: Usado para treinar o modelo
# │ VAL: Usado para early stopping e seleção de melhor modelo
# │ TEST: Usado apenas para backtest final (nunca visto no treino)
# │ RELAÇÃO: Mais treino = melhor fit, mas risco de overfit
# │ DEFAULT: 70/15/15 - Padrão da indústria de ML

# ─────────────────────────────────────────────────────────────────────────────
# 🔧 OVERRIDE DE CUSTOS (usa valor do cTrader se None)
# ─────────────────────────────────────────────────────────────────────────────

SPREAD_OVERRIDE = None
# │ O QUE É: Spread fixo em pontos (sobrescreve valor do cTrader)
# │ QUANDO USAR: Testar cenários pessimistas ou específicos
# │ EXEMPLO: SPREAD_OVERRIDE = 20 para simular spread alto
# │ DEFAULT: None - Usa spread real do cTrader

COMMISSION_OVERRIDE = None
# │ O QUE É: Comissão fixa por lote (sobrescreve valor do cTrader)
# │ QUANDO USAR: Comparar com outras corretoras
# │ DEFAULT: None - Usa comissão real do cTrader

# =============================================================================
# ▶️ CONFIGURAÇÃO COMPLETA - Execute Runtime → Run All (Ctrl+F9)
# =============================================================================
```

---

## Referência Rápida: Parâmetros e Mercado

### Relação Parâmetros ↔ Características do Mercado

| Característica do Mercado | Parâmetros Relacionados | Ajuste Sugerido |
|---------------------------|------------------------|-----------------|
| **Alta Volatilidade** (crypto, índices) | RL_ATR_PERIOD, RL_ROC_PERIOD | Períodos menores (7-10) |
| **Baixa Volatilidade** (forex major) | RL_ATR_PERIOD, RL_ROC_PERIOD | Valores default (10-14) |
| **Mercado em Tendência** | RL_EMA_PERIOD, RL_GAMMA | EMA menor (100), Gamma maior (0.995) |
| **Mercado em Range** | RL_RANGE_PERIOD, HMM_RANGE_PERIOD | Períodos menores para detectar breakouts |
| **Timeframe Curto** (M1, M5) | Todos os períodos | Reduzir proporcionalmente |
| **Timeframe Longo** (H4, D1) | Todos os períodos | Aumentar proporcionalmente |

### Guia para Experimentação

```
1. PRIMEIRO: Treine com valores default
   → Anote as métricas (Sharpe, WinRate, MaxDD)

2. DEPOIS: Altere UM parâmetro por vez
   → Compare com baseline

3. DOCUMENTE: O que funcionou e o que não funcionou

4. CUIDADO com:
   - Overfitting (métricas boas no treino, ruins no teste)
   - Correlações (alterar ROC_PERIOD pode precisar ajustar EMA_PERIOD)
```

---

## Secrets Necessários

Para o notebook funcionar, configure no Kaggle/Colab:

### Kaggle Secrets
```
CTRADER_CLIENT_ID      = "seu_client_id"
CTRADER_CLIENT_SECRET  = "seu_client_secret"
CTRADER_ACCESS_TOKEN   = "seu_access_token"
CTRADER_ACCOUNT_ID     = "seu_account_id"
SUPABASE_URL           = "https://xxx.supabase.co"
SUPABASE_KEY           = "sua_chave"
```

### Colab Secrets
Mesmas variáveis, configuradas em Runtime → Secrets.

---

## Fluxo de Execução

```
1. Usuário configura SEÇÃO 0:
   - SYMBOL = "EURUSD"
   - TIMEFRAME = "M15"
   - HISTORY_AMOUNT = 2
   - HISTORY_UNIT = "years"
   - HISTORY_END_DATE = "2026-02-04"

2. (Opcional) Usuário ajusta SEÇÃO 1 se quiser experimentar

3. Runtime → Run All (Ctrl+F9)

4. Notebook executa automaticamente:
   - Conecta cTrader
   - Baixa histórico (2 anos até 04/02/2026)
   - Obtém info do símbolo (point, spread, etc)
   - Treina HMM + PPO
   - Roda backtest OOS
   - Cria ZIP formato v2.0 (metadata no zip.comment)
   - Upload para Supabase oracle_models

5. Resultado:
   - EURUSD_M15.zip no oracle_models
   - Metadata completo no zip.comment
   - Hash verificado
```

---

## Resumo da Estrutura de Seções

| Seção | Nome | Editar? | Descrição |
|-------|------|---------|-----------|
| 0 | Configuração Principal | ✅ **SIM** | Símbolo, timeframe, período, HMM |
| 1 | Parâmetros Avançados | ⚠️ Não recomendado | RL features, PPO training, trading |
| 2 | Setup | ❌ Não | Imports, GPU, ambiente |
| 3 | Conexão cTrader | ❌ Não | Auth, download histórico |
| 4 | Config Automática | ❌ Não | Deriva parâmetros do símbolo |
| 5 | Visualização | ❌ Não | Plot preço, estatísticas |
| 6 | Treino HMM | 🔒 **INTOCÁVEL** | Features HMM, fit, análise estados |
| 7 | Treino PPO | 🔒 **INTOCÁVEL** | Features RL, TradingEnv, PPO.learn |
| 8 | Backtest | ❌ Não | Métricas, análise por regime |
| 9 | Export & Upload | ❌ Não | ZIP v2.0, Supabase |
| 10 | Finalização | ❌ Não | Resumo, shutdown |

---

## Changelog

### v2 Notebook 1.0 (2026-02-04)
- **NOVO:** Download direto da API cTrader (substitui CSV do Supabase)
- **NOVO:** Período configurável (years/months/days + data final)
- **NOVO:** Parâmetros avançados documentados inline
- **NOVO:** Auto-detecção de ambiente Kaggle/Colab
- **NOVO:** Zero inputs interativos (suporta Run All)
- **NOVO:** Formato de saída v2.0 (metadata no zip.comment)
- **REMOVIDO:** Dependência de symbol_params.json
- **REMOVIDO:** Dependência de CSVs pré-carregados
