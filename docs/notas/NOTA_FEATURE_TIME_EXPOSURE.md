# 📝 Nota Técnica: Feature de Tempo de Exposição

**Status:** 💡 Proposta para teste em versões futuras  
**Versão:** v2.1+  
**Impacto:** Mudança no observation space (requer retreino de modelos)

---

## 1. Motivação

Atualmente, as features de posição informam ao modelo:
- **Direção** (-1, 0, +1)
- **Tamanho** (lots normalizado)
- **PnL flutuante** (normalizado)

O modelo **não sabe** há quanto tempo está exposto. Essa informação pode ser útil para:
- Evitar "overstay" (ficar muito tempo em trades sem movimento)
- Capturar custo de oportunidade
- Aprender padrões de duração ótima por regime

---

## 2. Proposta

Adicionar uma 4ª feature de posição: **Tempo de Exposição**.

### 2.1 Lógica

```python
# Contador de barras em posição
bars_in_position: int = 0

# A cada barra:
if position.direction == 0:
    bars_in_position = 0  # Reset quando flat
else:
    bars_in_position += 1  # Incrementa enquanto exposto
```

### 2.2 Normalização (CRÍTICO)

O contador cresce indefinidamente, então **DEVE** ser normalizado para não dominar as outras features.

```python
# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  NORMALIZAÇÃO COM TANH                                                    ║
# ║  - Satura suavemente em ±1.0                                              ║
# ║  - Divisor 20 = saturação em ~50 barras (ajustável por timeframe)         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

time_exposure = np.tanh(bars_in_position / 20.0)
```

### 2.3 Tabela de Referência

| Barras | time_exposure | Interpretação |
|--------|---------------|---------------|
| 0 | 0.00 | Sem posição / acabou de abrir |
| 5 | 0.24 | Posição recente |
| 10 | 0.46 | Posição curta |
| 20 | 0.76 | Posição média |
| 30 | 0.89 | Posição longa |
| 50 | 0.97 | Posição muito longa |
| 100+ | ~1.00 | Saturado |

### 2.4 Ajuste por Timeframe

O divisor (20) deve ser ajustado conforme o timeframe:

| Timeframe | Divisor Sugerido | Saturação em |
|-----------|------------------|--------------|
| M1 | 60 | ~150 barras (~2.5h) |
| M5 | 30 | ~75 barras (~6h) |
| M15 | 20 | ~50 barras (~12h) |
| H1 | 10 | ~25 barras (~1 dia) |
| H4 | 5 | ~12 barras (~2 dias) |

---

## 3. Implementação

### 3.1 No TradingEnv (Notebook)

```python
class TradingEnv(gym.Env):
    def __init__(self, ..., use_time_exposure: bool = False, time_divisor: float = 20.0):
        # ...
        self.use_time_exposure = use_time_exposure
        self.time_divisor = time_divisor
        self.bars_in_position = 0
        
        # Ajusta observation space
        n_pos_features = 4 if use_time_exposure else 3
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, 
            shape=(len(feature_columns) + n_pos_features,), 
            dtype=np.float32
        )
    
    def reset(self, ...):
        # ...
        self.bars_in_position = 0
        return self._get_obs(), {}
    
    def step(self, action):
        # ...
        # Atualiza contador ANTES de processar ação
        if self.position_direction != 0:
            self.bars_in_position += 1
        
        # Processa ação (pode fechar posição)
        # ...
        
        # Se fechou, reset contador
        if self.position_direction == 0:
            self.bars_in_position = 0
        
        return self._get_obs(), reward, done, False, info
    
    def _get_obs(self):
        market = self.features[self.current_step]
        
        # Features de posição base
        pos_features = [
            float(self.position_direction),
            float(self.position_size) * 10,
            np.tanh(float(self.floating_pnl) / 100.0),
        ]
        
        # Feature de tempo (opcional)
        if self.use_time_exposure:
            time_exposure = np.tanh(self.bars_in_position / self.time_divisor)
            pos_features.append(time_exposure)
        
        return np.concatenate([market, pos_features]).astype(np.float32)
```

### 3.2 No Preditor (Execução)

```python
class Preditor:
    def __init__(self, ..., use_time_exposure: bool = False, time_divisor: float = 20.0):
        # ...
        self.use_time_exposure = use_time_exposure
        self.time_divisor = time_divisor
        self.bars_in_position = 0
    
    def on_new_bar(self, bar: Bar):
        # Incrementa contador se em posição
        if self.virtual_position.direction != 0:
            self.bars_in_position += 1
        
        # Calcula features e faz predição
        # ...
    
    def on_position_closed(self):
        self.bars_in_position = 0
    
    def calc_position_features(self) -> list:
        features = [
            float(self.virtual_position.direction),
            float(self.virtual_position.size) * 10,
            np.tanh(float(self.virtual_position.pnl) / 100.0),
        ]
        
        if self.use_time_exposure:
            time_exposure = np.tanh(self.bars_in_position / self.time_divisor)
            features.append(time_exposure)
        
        return features
```

---

## 4. Compatibilidade

### 4.1 Modelos Existentes (v2.0)

- **NÃO compatíveis** com a nova feature
- Observation space diferente (14 vs 15 features)
- Continuam funcionando com `use_time_exposure=False`

### 4.2 Modelos Novos (v2.1+)

- Treinados com `use_time_exposure=True`
- Requerem execução com a mesma flag

### 4.3 Detecção Automática

O `exec_config.json` deve indicar se o modelo usa a feature:

```json
{
    "training_info": {
        "use_time_exposure": true,
        "time_divisor": 20.0,
        "observation_size": 15
    }
}
```

---

## 5. Experimentos Sugeridos

### 5.1 Teste A/B

1. Treinar 2 modelos para o mesmo par:
   - Modelo A: `use_time_exposure=False` (baseline)
   - Modelo B: `use_time_exposure=True`

2. Comparar métricas:
   - Sharpe Ratio
   - Duração média de trades
   - Win rate por duração

### 5.2 Análise de Impacto

Verificar se o modelo aprende a:
- Sair mais cedo de trades sem momentum
- Segurar mais tempo trades em tendência
- Diferenciar comportamento por regime HMM

---

## 6. Riscos

| Risco | Mitigação |
|-------|-----------|
| Feature domina outras | Normalização com tanh (saturação) |
| Overfitting à duração | Validar em múltiplos ativos |
| Complexidade adicional | Flag opcional, default=False |
| Incompatibilidade | Versionar no exec_config.json |

---

## 7. Decisão

- **v2.0:** NÃO implementar (manter compatibilidade)
- **v2.1+:** Implementar como feature OPCIONAL para testes
- **v3.0:** Avaliar se deve ser DEFAULT baseado em resultados

---

## Resumo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FEATURE: Tempo de Exposição                                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  O QUE: Contador de barras desde abertura da posição                        │
│  NORMALIZAÇÃO: np.tanh(bars_in_position / divisor)                          │
│  DIVISOR: ~20 para M15 (ajustar por timeframe)                              │
│  RANGE: [0, 1] - satura suavemente                                          │
│  IMPACTO: +1 feature no observation space                                   │
│  STATUS: Proposta para v2.1+                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

*Nota técnica arquivada para implementação futura.*
