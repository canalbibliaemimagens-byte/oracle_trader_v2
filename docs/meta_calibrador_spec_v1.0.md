# Meta-Calibrador Inteligente - Especificação Técnica

**Versão:** 1.0 (Arquivo para Implementação Futura)  
**Data:** 2026-02-04  
**Status:** 📁 Arquivado - Aguardando Oracle v2 estável + 50+ modelos treinados  
**Prioridade:** Roadmap v3+

---

## 1. Contexto e Motivação

### 1.1 Problema Observado

Com base em ~300 trades em 3 dias de operação real:

| Categoria | Exemplos | Desempenho c/ Default | Observação |
|-----------|----------|----------------------|-------------|
| **Forex Major** | EURUSD, AUDUSD, USDJPY | ✅ Excelente | Setup default funciona |
| **Forex Cross** | EURJPY, USDCAD | ✅ Bom | Setup default funciona |
| **Índices** | JP225, US500, GER40 | ⚠️ Variável | Alguns precisam ajuste |
| **Forex Minor** | NZDUSD, CADCHF, AUDCHF, GBPUSD | ❌ Negativo | Precisam fine-tuning |

**Gargalo identificado:** Fine-tuning manual é demorado (~30-60min por modelo).

### 1.2 Lições Aprendidas

```
📌 LIÇÃO 1: PPO é superior
   - Testados: Bayesian, Grid Search, Random Search, outros RL
   - Resultado: Nenhum chegou perto do PPO
   - Conclusão: Manter PPO, não buscar alternativas

📌 LIÇÃO 2: Menos é mais
   - Features complexas (50+) → Overfitting
   - Features simples (6 base + HMM) → Generalização
   - Conclusão: Não adicionar complexidade na engenharia de features

📌 LIÇÃO 3: Categorias importam
   - Forex Major/Cross: Comportamento similar
   - Índices: Comportamento distinto
   - Conclusão: Treinar calibrador por categoria, não misturado
```

---

## 2. Conceito: Consultoria Offline

O Meta-Calibrador é um modelo de **Meta-Reinforcement Learning** que atua como "Consultor de Setup".

### 2.1 O Que Ele Faz

```
NÃO opera no mercado
NÃO toma decisões de trade
NÃO roda em tempo real

✅ Analisa histórico do ativo
✅ Identifica "personalidade" estatística (DNA)
✅ Sugere parâmetros ideais para HMM + PPO
✅ Executa em milissegundos (pós-treinamento)
```

### 2.2 Filosofia

> "Aprender a preparar, para o robô poder executar."

O calibrador **aprende a regra geral**:
- "Para ativos com DNA tipo X, o setup ideal é Y"

---

## 3. Arquitetura por Categoria

### 3.1 Por Que Separar?

Misturar Crypto + Forex + Índices força o modelo a aprender padrões muito distintos:

```
Crypto (BTC):   Hurst ~0.45, Kurtosis ~8,  Volatilidade ~80%
Forex (EUR):   Hurst ~0.52, Kurtosis ~4,  Volatilidade ~8%
Índice (SP500): Hurst ~0.48, Kurtosis ~5,  Volatilidade ~15%
```

**Resultado:** Modelo medíocre em tudo, excelente em nada.

### 3.2 Estrutura Proposta

```
META-CALIBRADORES (3 modelos independentes)
│
├── 🔵 Calibrador FOREX
│   ├── Treino: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, EURGBP, etc.
│   ├── Mínimo: 10 pares forex
│   └── Especialidade: Baixa volatilidade, alta liquidez
│
├── 🟢 Calibrador ÍNDICES
│   ├── Treino: US500, US30, GER40, JP225, UK100, etc.
│   ├── Mínimo: 5 índices
│   └── Especialidade: Gaps, sessões, volatilidade média
│
└── 🟡 Calibrador COMMODITIES (futuro)
    ├── Treino: XAUUSD, XAGUSD, USOIL, etc.
    ├── Mínimo: 5 commodities
    └── Especialidade: Tendências longas, eventos macro
```

### 3.3 Requisitos Mínimos

| Calibrador | Ativos para Treino | Ativos para Validação |
|------------|-------------------|----------------------|
| Forex | 10+ pares | 3+ pares nunca vistos |
| Índices | 5+ índices | 2+ índices nunca vistos |
| Commodities | 5+ commodities | 2+ nunca vistos |

---

## 4. DNA do Ativo (Espaço de Observação)

O calibrador toma decisões baseadas na "personalidade" estatística do símbolo.

### 4.1 Métricas Calculadas (nos 70% de treino)

```python
def calculate_dna(df: pd.DataFrame) -> np.ndarray:
    """
    Calcula o DNA (assinatura estatística) de um ativo.
    
    Returns:
        Array com 4 features normalizadas [-1, 1]
    """
    close = df['close'].values
    returns = np.diff(np.log(close))
    
    # 1. Expoente de Hurst (tendência vs reversão)
    #    H > 0.5: Tendencioso (momentum)
    #    H < 0.5: Reversivo (mean-reversion)
    #    H = 0.5: Random walk
    hurst = compute_hurst_exponent(close)
    hurst_norm = (hurst - 0.5) * 4  # Normaliza para ~[-1, 1]
    
    # 2. Volatilidade Agregada (explosividade)
    #    Desvio padrão anualizado dos retornos
    volatility = np.std(returns) * np.sqrt(252 * bars_per_day)
    vol_norm = np.tanh(volatility / 0.3)  # 30% vol → ~0.9
    
    # 3. Kurtosis (caudas longas, eventos extremos)
    #    Normal = 3, Fat tails > 3
    kurt = scipy.stats.kurtosis(returns, fisher=True)  # Excess kurtosis
    kurt_norm = np.tanh(kurt / 5)  # Kurt 5 → ~0.76
    
    # 4. Eficiência Fractal (ruído/zigue-zague)
    #    1.0 = Tendência perfeita
    #    0.0 = Ruído puro
    fractal_eff = compute_fractal_efficiency(close, period=20)
    frac_norm = fractal_eff * 2 - 1  # [0,1] → [-1,1]
    
    return np.array([hurst_norm, vol_norm, kurt_norm, frac_norm])
```

### 4.2 Funções Auxiliares

```python
def compute_hurst_exponent(series: np.ndarray, max_lag: int = 100) -> float:
    """
    Calcula o expoente de Hurst via R/S Analysis.
    """
    lags = range(2, min(max_lag, len(series) // 4))
    rs_values = []
    
    for lag in lags:
        chunks = np.array_split(series, len(series) // lag)
        rs_chunk = []
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            mean = np.mean(chunk)
            std = np.std(chunk)
            if std == 0:
                continue
            cumdev = np.cumsum(chunk - mean)
            r = np.max(cumdev) - np.min(cumdev)
            rs_chunk.append(r / std)
        if rs_chunk:
            rs_values.append((lag, np.mean(rs_chunk)))
    
    if len(rs_values) < 2:
        return 0.5
    
    lags, rs = zip(*rs_values)
    log_lags = np.log(lags)
    log_rs = np.log(rs)
    
    slope, _ = np.polyfit(log_lags, log_rs, 1)
    return slope


def compute_fractal_efficiency(close: np.ndarray, period: int = 20) -> float:
    """
    Calcula a eficiência fractal média.
    Efficiency = |Move direto| / |Soma dos movimentos|
    """
    efficiencies = []
    for i in range(period, len(close)):
        window = close[i-period:i+1]
        direct_move = abs(window[-1] - window[0])
        total_move = np.sum(np.abs(np.diff(window)))
        if total_move > 0:
            efficiencies.append(direct_move / total_move)
    
    return np.mean(efficiencies) if efficiencies else 0.5
```

### 4.3 Interpretação do DNA

| Métrica | Valor Alto | Valor Baixo | Impacto no Setup |
|---------|------------|-------------|------------------|
| **Hurst** | Tendencioso | Reversivo | EMA maior, Range menor |
| **Volatilidade** | Explosivo | Calmo | ATR menor (mais sensível) |
| **Kurtosis** | Eventos extremos | Normal | Gamma maior (horizonte longo) |
| **Fractal** | Tendência limpa | Muito ruído | ROC maior (filtrar ruído) |

---

## 5. Espaço de Ação (Parâmetros a Calibrar)

### 5.1 Abordagem: Ação Discreta (Recomendada)

```python
# Presets curados incluindo HMM_STATES
# HMM_STATES afeta a granularidade da detecção de regime:
#   - 3 estados: Bull/Bear/Range (simples, menos overfitting)
#   - 5 estados: Default (bom equilíbrio)
#   - 7 estados: Mais nuances (mercados complexos, risco de overfitting)

ACTION_PRESETS = {
    # ─────────────────────────────────────────────────────────
    # Presets para BAIXA VOLATILIDADE (Forex Major)
    # ─────────────────────────────────────────────────────────
    0: {
        "name": "FOREX_DEFAULT",
        "HMM_STATES": 5,
        "HMM_MOMENTUM_PERIOD": 12,
        "HMM_CONSISTENCY_PERIOD": 12,
        "HMM_RANGE_PERIOD": 20,
        "RL_ROC_PERIOD": 10,
        "RL_ATR_PERIOD": 14,
        "RL_EMA_PERIOD": 200,
        "RL_RANGE_PERIOD": 20,
        "RL_GAMMA": 0.99,
    },
    1: {
        "name": "FOREX_TRENDING",
        "HMM_STATES": 5,
        "HMM_MOMENTUM_PERIOD": 15,
        "HMM_CONSISTENCY_PERIOD": 15,
        "HMM_RANGE_PERIOD": 25,
        "RL_ROC_PERIOD": 12,
        "RL_ATR_PERIOD": 14,
        "RL_EMA_PERIOD": 150,
        "RL_RANGE_PERIOD": 25,
        "RL_GAMMA": 0.995,
    },
    2: {
        "name": "FOREX_RANGING",
        "HMM_STATES": 7,  # Mais estados para capturar micro-regimes em range
        "HMM_MOMENTUM_PERIOD": 10,
        "HMM_CONSISTENCY_PERIOD": 10,
        "HMM_RANGE_PERIOD": 15,
        "RL_ROC_PERIOD": 8,
        "RL_ATR_PERIOD": 10,
        "RL_EMA_PERIOD": 200,
        "RL_RANGE_PERIOD": 15,
        "RL_GAMMA": 0.98,
    },
    
    # ─────────────────────────────────────────────────────────
    # Presets para MÉDIA VOLATILIDADE (Índices)
    # ─────────────────────────────────────────────────────────
    3: {
        "name": "INDEX_DEFAULT",
        "HMM_STATES": 5,
        "HMM_MOMENTUM_PERIOD": 10,
        "HMM_CONSISTENCY_PERIOD": 10,
        "HMM_RANGE_PERIOD": 15,
        "RL_ROC_PERIOD": 8,
        "RL_ATR_PERIOD": 10,
        "RL_EMA_PERIOD": 200,
        "RL_RANGE_PERIOD": 15,
        "RL_GAMMA": 0.99,
    },
    4: {
        "name": "INDEX_VOLATILE",
        "HMM_STATES": 5,
        "HMM_MOMENTUM_PERIOD": 8,
        "HMM_CONSISTENCY_PERIOD": 8,
        "HMM_RANGE_PERIOD": 12,
        "RL_ROC_PERIOD": 6,
        "RL_ATR_PERIOD": 7,
        "RL_EMA_PERIOD": 150,
        "RL_RANGE_PERIOD": 12,
        "RL_GAMMA": 0.985,
    },
    5: {
        "name": "INDEX_SIMPLE",
        "HMM_STATES": 3,  # Menos estados para índices com comportamento claro
        "HMM_MOMENTUM_PERIOD": 12,
        "HMM_CONSISTENCY_PERIOD": 12,
        "HMM_RANGE_PERIOD": 20,
        "RL_ROC_PERIOD": 10,
        "RL_ATR_PERIOD": 14,
        "RL_EMA_PERIOD": 200,
        "RL_RANGE_PERIOD": 20,
        "RL_GAMMA": 0.99,
    },
    
    # ─────────────────────────────────────────────────────────
    # Presets para ALTA VOLATILIDADE (Commodities, Crypto)
    # ─────────────────────────────────────────────────────────
    6: {
        "name": "VOLATILE_DEFAULT",
        "HMM_STATES": 5,
        "HMM_MOMENTUM_PERIOD": 8,
        "HMM_CONSISTENCY_PERIOD": 8,
        "HMM_RANGE_PERIOD": 10,
        "RL_ROC_PERIOD": 6,
        "RL_ATR_PERIOD": 7,
        "RL_EMA_PERIOD": 100,
        "RL_RANGE_PERIOD": 10,
        "RL_GAMMA": 0.98,
    },
    7: {
        "name": "VOLATILE_TRENDING",
        "HMM_STATES": 3,  # Simples: só Bull/Bear/Range para tendências fortes
        "HMM_MOMENTUM_PERIOD": 10,
        "HMM_CONSISTENCY_PERIOD": 10,
        "HMM_RANGE_PERIOD": 15,
        "RL_ROC_PERIOD": 8,
        "RL_ATR_PERIOD": 10,
        "RL_EMA_PERIOD": 100,
        "RL_RANGE_PERIOD": 12,
        "RL_GAMMA": 0.99,
    },
    8: {
        "name": "VOLATILE_COMPLEX",
        "HMM_STATES": 7,  # Mais estados para capturar regimes complexos
        "HMM_MOMENTUM_PERIOD": 6,
        "HMM_CONSISTENCY_PERIOD": 6,
        "HMM_RANGE_PERIOD": 8,
        "RL_ROC_PERIOD": 5,
        "RL_ATR_PERIOD": 7,
        "RL_EMA_PERIOD": 100,
        "RL_RANGE_PERIOD": 10,
        "RL_GAMMA": 0.97,
    },
}

N_ACTIONS = len(ACTION_PRESETS)  # 9 presets
```

### 5.2 HMM_STATES: Impacto na Detecção de Regime

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  HMM_STATES = 3 (Simples)                                                   │
│  ───────────────────────────────────────────────────────────────────────────│
│  Estados: BULL | BEAR | RANGE                                               │
│  Vantagens: Menos overfitting, sinais mais claros                           │
│  Ideal para: Ativos com tendências fortes e definidas                       │
│  Exemplos: BTC em bull run, índices em rally                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  HMM_STATES = 5 (Default)                                                   │
│  ───────────────────────────────────────────────────────────────────────────│
│  Estados: STRONG_BULL | WEAK_BULL | RANGE | WEAK_BEAR | STRONG_BEAR         │
│  Vantagens: Bom equilíbrio entre nuance e generalização                     │
│  Ideal para: Maioria dos ativos (forex major, índices estáveis)             │
│  Exemplos: EURUSD, USDJPY, SP500                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│  HMM_STATES = 7 (Complexo)                                                  │
│  ───────────────────────────────────────────────────────────────────────────│
│  Estados: Múltiplos níveis de bull/bear + consolidações                     │
│  Vantagens: Captura micro-regimes e transições                              │
│  Risco: Overfitting em dados limitados                                      │
│  Ideal para: Ativos laterais complexos, forex minor em range                │
│  Exemplos: AUDCHF em consolidação, pares exóticos                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5.3 Por Que Discreto e Não Contínuo?

```
✅ Discreto (Presets):
   - Converge mais rápido
   - Presets são combinações já validadas
   - Menos risco de parâmetros "estranhos"
   - Interpretável ("usou preset FOREX_TRENDING")

❌ Contínuo (Multiplicadores):
   - Mais flexível teoricamente
   - Converge lentamente
   - Pode gerar combinações inválidas (EMA=37, ATR=11.4)
   - Difícil de interpretar e debugar
```

---

## 6. Função de Recompensa

### 6.1 Abordagem Simplificada (Recomendada)

> **Princípio "Menos é Mais":** Usar Sharpe Ratio de mini-backtest ao invés de Informação Mútua complexa.

```python
def calculate_reward(
    params: dict,
    df_train: pd.DataFrame,
    df_val: pd.DataFrame,
) -> float:
    """
    Calcula a recompensa para um conjunto de parâmetros.
    
    Usa os dados de VALIDAÇÃO (15%) para evitar overfitting.
    
    Returns:
        Sharpe Ratio do mini-backtest (normalizado)
    """
    # 1. Treina HMM + PPO com os parâmetros sugeridos (RÁPIDO)
    #    Usa apenas 200k steps (10% do treino normal)
    model = train_quick_model(df_train, params, timesteps=200_000)
    
    # 2. Roda backtest nos dados de VALIDAÇÃO
    results = run_backtest(model, df_val)
    
    # 3. Calcula Sharpe Ratio
    returns = results['daily_returns']
    if len(returns) < 10 or np.std(returns) == 0:
        return -1.0  # Penaliza modelos que não operam
    
    sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
    
    # 4. Normaliza para [-1, 1] (facilita o aprendizado)
    #    Sharpe 2.0 → ~0.9, Sharpe -1.0 → ~-0.5
    reward = np.tanh(sharpe / 2.0)
    
    return reward
```

### 6.2 Por Que Sharpe e Não Informação Mútua?

| Métrica | Prós | Contras |
|---------|------|---------|
| **Informação Mútua** | Teoricamente elegante | Computacionalmente caro, sensível à discretização |
| **Sharpe Ratio** | Direto, interpretável, rápido | Requer mini-backtest |

**Decisão:** Sharpe é mais prático e alinhado com o objetivo final (performance de trading).

---

## 7. Arquitetura do Modelo

### 7.0 Lição Aprendida: Correlação Arquitetura ↔ Parâmetros

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  PONTO DE VIRADA: Rede 256x256x256                                          │
│  ───────────────────────────────────────────────────────────────────────────│
│  Antes (32x32 ou 64x64):                                                    │
│    - Modelos não convergiam bem                                             │
│    - Performance inconsistente                                              │
│    - Parâmetros de treino não faziam diferença                              │
│                                                                             │
│  Depois (256x256x256):                                                      │
│    - Convergência estável                                                   │
│    - Performance consistente                                                │
│    - Parâmetros de treino passaram a importar                               │
└─────────────────────────────────────────────────────────────────────────────┘

CORRELAÇÃO VALIDADA (Oracle):
┌──────────────────────┬─────────────────────────────────────────────────────┐
│  Parâmetro           │  Valor calibrado para rede 256x256x256              │
├──────────────────────┼─────────────────────────────────────────────────────┤
│  net_arch            │  pi=[256,256,256], vf=[256,256,256]                 │
│  learning_rate       │  3e-4 (funciona bem com rede profunda)              │
│  n_steps             │  4096 (coleta suficiente para gradientes estáveis)  │
│  batch_size          │  512 (bom para GPU T4 16GB)                         │
│  total_timesteps     │  2_000_000 (tempo: ~1.5h em GPU T4)                 │
│  gamma               │  0.99 (horizonte longo para trading)                │
└──────────────────────┴─────────────────────────────────────────────────────┘

APLICAÇÃO AO CALIBRADOR:
- Mesma arquitetura 256x256x256
- Mesmos hiperparâmetros de treino
- Tempo similar (~1.5h por categoria)
- GPU obrigatória (Kaggle/Colab T4)
```

### 7.1 Rede Neural (256x256x256)

```python
import torch
import torch.nn as nn

class MetaCalibratorNet(nn.Module):
    """
    Rede 256x256x256: DNA (4) → Hidden → Action (N_ACTIONS)
    
    LIÇÃO APRENDIDA:
    - Redes rasas (32x32) não capturaram padrões suficientes
    - 256x256x256 foi o ponto de virada no Oracle
    - Mesma arquitetura aplicada ao Calibrador
    
    Filosofia "Menos é Mais" aplica-se às FEATURES, não à capacidade da rede.
    """
    
    def __init__(self, n_actions: int = 9):
        super().__init__()
        
        self.net = nn.Sequential(
            nn.Linear(4, 256),      # DNA input
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, n_actions),  # Action output (logits)
        )
    
    def forward(self, dna: torch.Tensor) -> torch.Tensor:
        return self.net(dna)


# Para o PPO, a policy_kwargs segue o mesmo padrão
policy_kwargs = dict(
    net_arch=dict(
        pi=[256, 256, 256],  # Policy network
        vf=[256, 256, 256],  # Value network
    )
)
```

### 7.2 Treinamento com PPO

```python
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

class MetaCalibratorEnv(gym.Env):
    """
    Ambiente onde cada episódio é:
    1. Receber DNA de um ativo aleatório
    2. Escolher um preset de parâmetros
    3. Receber reward baseado no mini-backtest
    """
    
    def __init__(self, asset_pool: List[str], category: str = "forex"):
        super().__init__()
        
        self.asset_pool = asset_pool  # Lista de ativos para treino
        self.category = category
        
        # Spaces
        self.observation_space = spaces.Box(
            low=-1, high=1, shape=(4,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(N_ACTIONS)  # 9 presets
        
        # Cache de dados (pré-carregados)
        self.data_cache = self._load_all_data()
    
    def reset(self, seed=None):
        # Escolhe ativo aleatório
        self.current_asset = np.random.choice(self.asset_pool)
        
        # Carrega dados e calcula DNA
        df = self.data_cache[self.current_asset]
        train_end = int(len(df) * 0.70)
        df_train = df.iloc[:train_end]
        
        self.df_train = df_train
        self.df_val = df.iloc[train_end:int(len(df) * 0.85)]
        
        dna = calculate_dna(df_train)
        return dna.astype(np.float32), {}
    
    def step(self, action: int):
        # Obtém preset escolhido
        params = ACTION_PRESETS[action]
        
        # Calcula reward (mini-backtest)
        reward = calculate_reward(params, self.df_train, self.df_val)
        
        # Episódio termina após 1 decisão
        done = True
        
        return np.zeros(4), reward, done, False, {
            "asset": self.current_asset,
            "preset": params["name"],
            "reward": reward,
        }


# ─────────────────────────────────────────────────────────────────────────────
# TREINAMENTO
# ─────────────────────────────────────────────────────────────────────────────
# LIÇÃO APRENDIDA: Rede 256x256x256 foi o ponto de virada no Oracle.
# Aplicamos a mesma arquitetura ao Calibrador para consistência.
# ─────────────────────────────────────────────────────────────────────────────

env = DummyVecEnv([lambda: MetaCalibratorEnv(
    asset_pool=["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", 
                "NZDUSD", "USDCHF", "EURGBP", "EURJPY", "GBPJPY"],
    category="forex"
)])

model = PPO(
    "MlpPolicy",
    env,
    learning_rate=3e-4,
    n_steps=4096,      # Consistente com Oracle
    batch_size=512,    # Consistente com Oracle
    n_epochs=10,
    gamma=0.99,        # Consistente com Oracle
    policy_kwargs=dict(
        net_arch=dict(
            pi=[256, 256, 256],  # Policy: 256x256x256
            vf=[256, 256, 256],  # Value: 256x256x256
        )
    ),
    verbose=1,
    device='cuda',     # GPU obrigatória para 256x256x256
)

# ~1.5h de treino em GPU T4 (Kaggle/Colab)
model.learn(total_timesteps=200_000)
model.save("meta_calibrator_forex")
```

---

## 8. Pipeline de Uso

### 8.1 Fluxo Completo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FASE 1: META-TREINAMENTO (Uma vez por categoria, ~2h)                      │
│  ───────────────────────────────────────────────────────────────────────────│
│  1. Carregar 10+ ativos da categoria (ex: Forex)                            │
│  2. Treinar MetaCalibratorEnv com PPO                                       │
│  3. Salvar modelo: meta_calibrator_forex.zip                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  FASE 2: SUGESTÃO DE PARÂMETROS (Por ativo, ~1 segundo)                     │
│  ───────────────────────────────────────────────────────────────────────────│
│  1. Carregar histórico do novo ativo                                        │
│  2. Calcular DNA                                                            │
│  3. Passar DNA pelo calibrador → Preset sugerido                            │
│  4. Retornar parâmetros                                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  FASE 3: TREINAMENTO DO PREDITOR (Por ativo, ~30-60min)                     │
│  ───────────────────────────────────────────────────────────────────────────│
│  1. Usar parâmetros sugeridos pelo calibrador                               │
│  2. Treinar HMM + PPO normalmente                                           │
│  3. Backtest OOS                                                            │
│  4. Deploy se aprovado                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Código de Uso (Inferência)

```python
def suggest_parameters(symbol: str, df: pd.DataFrame, category: str = "forex") -> dict:
    """
    Sugere parâmetros ideais para um ativo.
    
    Args:
        symbol: Nome do símbolo
        df: DataFrame com histórico OHLCV
        category: "forex", "indices", ou "commodities"
    
    Returns:
        Dict com parâmetros sugeridos
    """
    # 1. Carrega calibrador da categoria
    calibrator = PPO.load(f"meta_calibrator_{category}")
    
    # 2. Calcula DNA (usando 70% dos dados)
    train_end = int(len(df) * 0.70)
    dna = calculate_dna(df.iloc[:train_end])
    
    # 3. Obtém ação (preset) sugerida
    action, _ = calibrator.predict(dna, deterministic=True)
    
    # 4. Retorna parâmetros
    params = ACTION_PRESETS[int(action)]
    
    print(f"[{symbol}] DNA: {dna.round(2)}")
    print(f"[{symbol}] Preset sugerido: {params['name']}")
    
    return params


# Exemplo de uso
params = suggest_parameters("AUDCHF", df_audchf, category="forex")
# Output:
# [AUDCHF] DNA: [-0.12, 0.34, 0.21, -0.45]
# [AUDCHF] Preset sugerido: FOREX_RANGING
```

---

## 9. Estratégia de Dados

### 9.1 Janelas Temporais

```
CALIBRADOR (Meta-Treino):
├── Período: 3 anos de histórico
├── Fonte: Cesta de 10+ ativos da categoria
└── Split: 70% treino DNA, 15% reward calc, 15% bloqueado

PREDITOR (Trading RL):
├── Período: 2 anos de histórico
├── Fonte: Ativo específico
└── Split: 70% treino, 15% validação, 15% teste OOS
```

### 9.2 Proteção Contra Data Leakage

```
                    CALIBRADOR                    PREDITOR
                    (3 anos)                      (2 anos)
    
    ├─────────────────┼─────────────────┤         ├───────────┼───────────┤
    │     TREINO      │   VAL  │ TESTE │         │  TREINO   │VAL│ TESTE │
    │      70%        │  15%   │  15%  │         │   70%     │15%│  15%  │
    └─────────────────┴────────┴───────┘         └───────────┴───┴───────┘
    
    │◄─────── DNA calculado ──────►│              │◄── Modelo treina ──►│
                                   │                                     │
                          Reward calculado ──────────────────────────────│
                          (validação do calibrador = treino do preditor)
```

---

## 10. Estimativas de Recursos

### 10.1 Tempo de Desenvolvimento

| Componente | Estimativa | Dependências |
|------------|------------|--------------|
| DNA Calculator | 4h | numpy, scipy |
| Action Presets | 2h | Análise empírica |
| MetaCalibratorEnv | 8h | gym, SB3 |
| Mini-backtest rápido | 8h | Simplificar TradingEnv |
| Integração com Notebook | 4h | Oracle v2 estável |
| Testes e validação | 8h | 10+ ativos por categoria |
| **Total** | **~35h** | |

### 10.2 Tempo de Treino (por categoria)

| Fase | Tempo | Hardware |
|------|-------|----------|
| Meta-treino (200k steps) | ~1.5h | **GPU T4** (Kaggle/Colab) |
| Inferência (por ativo) | ~1s | CPU |

**Nota:** A rede 256x256x256 requer GPU. O tempo de ~1.5h é consistente com o treino do Oracle.

### 10.3 Requisitos de Dados

| Categoria | Ativos Mínimos | Dados por Ativo |
|-----------|---------------|-----------------|
| Forex | 10 pares | 3 anos M15 |
| Índices | 5 índices | 3 anos M15 |
| Commodities | 5 commodities | 3 anos M15 |

---

## 11. Critérios de Sucesso

### 11.1 Métricas de Validação

O Meta-Calibrador será considerado bem-sucedido se:

```
1. GENERALIZAÇÃO
   - Desempenho em ativos NUNCA VISTOS >= 80% do desempenho em ativos de treino
   
2. MELHORIA vs DEFAULT
   - Sharpe médio com parâmetros sugeridos > Sharpe com default
   - Em pelo menos 70% dos ativos testados

3. CONSISTÊNCIA
   - Para o mesmo DNA, sempre sugere o mesmo preset (determinístico)
   
4. VELOCIDADE
   - Inferência < 1 segundo por ativo
```

### 11.2 Checklist de Validação

```
□ Treinar calibrador FOREX com 10+ pares
□ Validar em 3+ pares nunca vistos
□ Comparar Sharpe: Sugerido vs Default
□ Documentar casos de sucesso e falha
□ Repetir para ÍNDICES e COMMODITIES
```

---

## 12. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Overfitting nos ativos de treino | Média | Alto | Validar em ativos nunca vistos |
| Mini-backtest muito lento | Alta | Médio | Simplificar TradingEnv, menos timesteps |
| DNA não captura diferenças | Baixa | Alto | Adicionar métricas se necessário |
| Presets insuficientes | Média | Médio | Expandir para 10-15 presets |

---

## 13. Roadmap de Implementação

### Pré-requisitos

```
□ Oracle v2 estável e funcionando
□ 10+ modelos Forex treinados com default
□ 5+ modelos Índices treinados com default
□ Dados de performance real (como a imagem dos 300 trades)
```

### Fases

```
FASE 0: Coleta de Evidência (ATUAL)
├── Treinar modelos com default
├── Documentar quais funcionam e quais não
└── Identificar padrões (DNA → Performance)

FASE 1: MVP Forex (~20h)
├── Implementar DNA Calculator
├── Criar 6 presets baseados em evidência
├── Treinar calibrador com 10 pares
└── Validar em 3 pares novos

FASE 2: Expansão (~15h)
├── Calibrador Índices
├── Calibrador Commodities
└── Integração com Oracle v2 Notebook

FASE 3: Otimização (futuro)
├── Expandir presets se necessário
├── Ajuste fino baseado em feedback real
└── Automação completa
```

---

## 14. Conclusão

O Meta-Calibrador é uma evolução natural do Oracle, mas deve ser implementado **após** termos:

1. ✅ Oracle v2 estável
2. ⏳ 50+ modelos treinados
3. ⏳ Dados de performance real por categoria

**Princípio guia:** Menos é mais. Começar simples (6 presets discretos) e expandir conforme necessário.

---

## Apêndice: Código Completo de Referência

```python
# meta_calibrator.py
# Implementação completa do Meta-Calibrador

import numpy as np
import pandas as pd
import scipy.stats
import gymnasium as gym
from gymnasium import spaces
from stable_baselines3 import PPO
from typing import List, Dict

# [Todo o código das seções anteriores consolidado aqui]
# Ver seções 4, 5, 6, 7 e 8 para implementação detalhada
```

---

**Documento arquivado para implementação futura.**
