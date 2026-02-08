# 🧠 Módulo PREDITOR: Especificação Técnica

**Versão:** 1.1  
**Nível:** Lógica Central (Core Business)  
**Responsabilidade:** Manter o "Digital Twin" (Gêmeo Digital) do ambiente de treinamento. Carregar modelos, processar dados de mercado e gerar sinais de trading baseados EXCLUSIVAMENTE em uma posição virtual, ignorando o estado real da conta.

---

## 1. Estrutura de Arquivos

```
oracle_v2/preditor/
├── __init__.py
├── preditor.py            # Classe Principal (Preditor)
├── model_loader.py        # Gestão de ZIP e Metadados
├── virtual_position.py    # Lógica de Posição Virtual
├── buffer.py              # Gestão de FIFO (Janela Deslizante)
└── warmup.py              # Lógica de Fast-Forward
```

---

## 2. Conceitos Chave

### 2.1 Posição Virtual (Digital Twin)

O `Preditor` acredita que suas ordens são sempre executadas instantaneamente, sem erro, sem rejeição. Isso garante que as features de entrada da rede neural (`position_direction`, `position_profit`) sejam matematicamente consistentes com o treinamento.

**Regra de Ouro:** O Preditor nunca olha para o `Executor`. Ele é cego para a realidade.

### 2.2 Estrutura do Modelo (.zip)

Cada arquivo de modelo segue o padrão:

```
{symbol}_{timeframe}.zip
├── {symbol}_{timeframe}_hmm.pkl    # Objeto hmmlearn
└── {symbol}_{timeframe}_ppo.zip    # Objeto stable-baselines3
```

**Exemplo:**
```
EURUSD_M15.zip
├── EURUSD_M15_hmm.pkl
└── EURUSD_M15_ppo.zip
```

### 2.3 Metadata no ZIP (zip.comment)

O metadata do modelo fica **no comentário do arquivo ZIP** (não como arquivo separado).

```python
import zipfile
import json

# Leitura do metadata
with zipfile.ZipFile("EURUSD_M15.zip", 'r') as zf:
    metadata = json.loads(zf.comment.decode('utf-8'))

# Escrita do metadata (no notebook de treino)
with zipfile.ZipFile("EURUSD_M15.zip", 'a') as zf:
    zf.comment = json.dumps(metadata).encode('utf-8')
```

**Estrutura do Metadata:**

```json
{
  "format_version": "2.0",
  "generated_at": "2026-02-03T10:30:00Z",
  
  "symbol": {
    "name": "EURUSD",
    "clean": "EURUSD",
    "timeframe": "M15"
  },
  
  "training_config": {
    "point": 0.00001,
    "pip_value": 10.0,
    "spread_points": 7,
    "slippage_points": 2,
    "commission_per_lot": 7.0,
    "digits": 5,
    "initial_balance": 10000,
    "lot_sizes": [0, 0.01, 0.03, 0.05],
    "total_timesteps": 2000000
  },
  
  "hmm_config": {
    "n_states": 5,
    "momentum_period": 12,
    "consistency_period": 12,
    "range_period": 20
  },
  
  "rl_config": {
    "roc_period": 10,
    "atr_period": 14,
    "ema_period": 200,
    "range_period": 20,
    "volume_ma_period": 20
  },
  
  "actions": {
    "0": {"name": "WAIT", "direction": 0, "intensity": 0},
    "1": {"name": "LONG_WEAK", "direction": 1, "intensity": 1},
    "2": {"name": "LONG_MODERATE", "direction": 1, "intensity": 2},
    "3": {"name": "LONG_STRONG", "direction": 1, "intensity": 3},
    "4": {"name": "SHORT_WEAK", "direction": -1, "intensity": 1},
    "5": {"name": "SHORT_MODERATE", "direction": -1, "intensity": 2},
    "6": {"name": "SHORT_STRONG", "direction": -1, "intensity": 3}
  },
  
  "hmm_state_analysis": {
    "bull_states": [0, 2],
    "bear_states": [1, 4],
    "range_states": [3]
  },
  
  "backtest_oos": {
    "total_trades": 234,
    "win_rate": 0.543,
    "profit_factor": 1.45,
    "sharpe_ratio": 1.23
  },
  
  "data_info": {
    "total_bars": 50000,
    "train_bars": 35000,
    "date_start": "2024-01-01",
    "date_end": "2026-01-31"
  }
}
```

---

## 3. Componentes

### 3.1 Preditor (`preditor.py`)

Gerencia múltiplos modelos simultaneamente.

```python
from typing import Dict, Optional, List
from dataclasses import dataclass
from ..core.models import Bar, Signal
from ..core.constants import Direction

@dataclass
class LoadedModel:
    symbol: str
    timeframe: str
    hmm_model: Any           # hmmlearn.GaussianHMM
    ppo_model: Any           # stable_baselines3.PPO
    metadata: dict
    training_config: dict
    hmm_config: dict
    rl_config: dict


class Preditor:
    """
    Digital Twin do TradingEnv.
    Mantém posição virtual e gera sinais baseados apenas em dados de mercado.
    """
    
    def __init__(self):
        self.models: Dict[str, LoadedModel] = {}
        self.buffers: Dict[str, BarBuffer] = {}
        self.virtual_positions: Dict[str, VirtualPosition] = {}

    def load_model(self, zip_path: str) -> bool:
        """
        Carrega modelo do ZIP.
        1. Extrai metadata do zip.comment
        2. Carrega HMM e PPO
        3. Inicializa buffer FIFO vazio
        4. Inicializa posição virtual FLAT
        
        Returns:
            True se carregou com sucesso
        """
        pass

    def unload_model(self, symbol: str) -> bool:
        """Remove modelo da memória."""
        pass
    
    def list_models(self) -> List[str]:
        """Retorna lista de símbolos com modelos carregados."""
        return list(self.models.keys())

    def warmup(self, symbol: str, bars: List[Bar]) -> None:
        """
        Fast-forward do modelo com histórico.
        Alimenta o buffer e executa predições sem emitir sinais.
        """
        pass

    def process_bar(self, symbol: str, bar: Bar) -> Optional[Signal]:
        """
        Processa uma nova barra fechada.
        
        Flow:
        1. Adiciona barra ao buffer FIFO
        2. Se buffer < 350 barras: return None (ainda em warmup)
        3. Calcula features HMM
        4. Prediz estado HMM
        5. Calcula features RL (inclui posição virtual)
        6. Prediz ação PPO
        7. Atualiza posição virtual
        8. Retorna Signal
        
        Args:
            symbol: Símbolo do ativo
            bar: Barra OHLCV fechada
            
        Returns:
            Signal se pronto, None se ainda em warmup
        """
        pass

    def get_virtual_position(self, symbol: str) -> Optional[VirtualPosition]:
        """Retorna posição virtual atual do símbolo."""
        return self.virtual_positions.get(symbol)

    def get_state(self) -> dict:
        """Retorna estado completo para debug/dashboard."""
        return {
            "models": list(self.models.keys()),
            "positions": {
                s: {
                    "direction": vp.direction,
                    "intensity": vp.intensity,
                    "entry_price": vp.entry_price,
                    "pnl": vp.current_pnl
                }
                for s, vp in self.virtual_positions.items()
            },
            "buffer_sizes": {s: len(b) for s, b in self.buffers.items()}
        }
```

### 3.2 VirtualPosition (`virtual_position.py`)

Implementa a lógica **exata** do `TradingEnv._execute_action()` usado no treino.

```python
from dataclasses import dataclass, field
from ..core.constants import Direction
from ..core.actions import Action, get_direction, get_intensity

@dataclass
class VirtualPosition:
    """
    Posição virtual mantida pelo Preditor.
    Replica EXATAMENTE a lógica do TradingEnv.
    """
    direction: int = 0          # -1, 0, 1
    intensity: int = 0          # 0, 1, 2, 3
    entry_price: float = 0.0
    current_pnl: float = 0.0
    
    # Parâmetros do treino (carregados do metadata)
    spread_points: float = 0.0
    slippage_points: float = 0.0
    commission_per_lot: float = 0.0
    point: float = 0.00001
    pip_value: float = 10.0
    lot_sizes: list = field(default_factory=lambda: [0, 0.01, 0.03, 0.05])
    
    def update(self, action: Action, current_price: float) -> float:
        """
        Atualiza posição virtual baseado na ação.
        
        Lógica (idêntica ao TradingEnv):
        - Se mesma direção e intensidade: NOOP (mantém)
        - Qualquer mudança: fecha posição atual + abre nova
        - WAIT: fecha posição se aberta
        
        Args:
            action: Ação do modelo (WAIT, LONG_WEAK, etc)
            current_price: Preço atual
            
        Returns:
            PnL realizado se fechou posição, 0 caso contrário
        """
        target_dir = get_direction(action).value
        target_intensity = get_intensity(action)
        
        # Mesma posição -> NOOP
        if target_dir == self.direction and target_intensity == self.intensity:
            self._update_floating_pnl(current_price)
            return 0.0
        
        # Qualquer mudança -> fecha + abre
        realized_pnl = 0.0
        if self.direction != 0:
            realized_pnl = self._close(current_price)
        
        if target_dir != 0:
            self._open(target_dir, target_intensity, current_price)
        
        return realized_pnl
    
    def _open(self, direction: int, intensity: int, price: float):
        """Abre posição virtual com custos do treino."""
        spread_cost = self.spread_points * self.point
        slippage = self.slippage_points * self.point  # Simplificado (sem random)
        
        if direction == 1:  # LONG
            self.entry_price = price + spread_cost + slippage
        else:  # SHORT
            self.entry_price = price - spread_cost - slippage
        
        self.direction = direction
        self.intensity = intensity
        self.current_pnl = 0.0
        
        # Deduz comissão (metade na entrada)
        lot_size = self.lot_sizes[intensity]
        self._apply_commission(lot_size, half=True)
    
    def _close(self, price: float) -> float:
        """Fecha posição virtual, retorna PnL realizado."""
        if self.direction == 0:
            return 0.0
        
        slippage = self.slippage_points * self.point
        
        if self.direction == 1:  # LONG
            exit_price = price - slippage
        else:  # SHORT
            exit_price = price + slippage
        
        # Calcula PnL
        price_diff = (exit_price - self.entry_price) * self.direction
        pips = price_diff / self.point / 10  # Converte para pips
        lot_size = self.lot_sizes[self.intensity]
        pnl = pips * self.pip_value * lot_size
        
        # Deduz comissão (metade na saída)
        pnl -= (self.commission_per_lot * lot_size) / 2
        
        # Reset
        realized = pnl
        self.direction = 0
        self.intensity = 0
        self.entry_price = 0.0
        self.current_pnl = 0.0
        
        return realized
    
    def _update_floating_pnl(self, current_price: float):
        """Atualiza PnL flutuante (para features)."""
        if self.direction == 0:
            self.current_pnl = 0.0
            return
        
        price_diff = (current_price - self.entry_price) * self.direction
        pips = price_diff / self.point / 10
        lot_size = self.lot_sizes[self.intensity]
        self.current_pnl = pips * self.pip_value * lot_size
    
    def _apply_commission(self, lot_size: float, half: bool = False):
        """Aplica comissão (metade na entrada, metade na saída)."""
        comm = self.commission_per_lot * lot_size
        if half:
            comm /= 2
        self.current_pnl -= comm
```

### 3.3 ModelLoader (`model_loader.py`)

Responsável por carregar o ZIP e extrair metadata do `zip.comment`.

```python
import zipfile
import json
import pickle
from pathlib import Path
from typing import Optional, Tuple, Any

class ModelLoader:
    """Carrega modelos do formato ZIP v2.0"""
    
    SUPPORTED_VERSIONS = ["2.0"]
    
    @staticmethod
    def load(zip_path: str) -> Tuple[Optional[dict], Optional[Any], Optional[Any]]:
        """
        Carrega modelo completo do ZIP.
        
        Args:
            zip_path: Caminho para o arquivo ZIP
            
        Returns:
            (metadata, hmm_model, ppo_model) ou (None, None, None) se falhar
        """
        path = Path(zip_path)
        if not path.exists():
            return None, None, None
        
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                # 1. Extrai metadata do zip.comment
                metadata = json.loads(zf.comment.decode('utf-8'))
                
                # 2. Valida versão
                version = metadata.get("format_version", "1.0")
                if version not in ModelLoader.SUPPORTED_VERSIONS:
                    raise ValueError(f"Versão não suportada: {version}")
                
                # 3. Identifica arquivos
                symbol_info = metadata.get("symbol", {})
                symbol = symbol_info.get("name", "")
                timeframe = symbol_info.get("timeframe", "")
                prefix = f"{symbol}_{timeframe}"
                
                hmm_file = f"{prefix}_hmm.pkl"
                ppo_file = f"{prefix}_ppo.zip"
                
                # 4. Extrai e carrega HMM
                with zf.open(hmm_file) as f:
                    hmm_data = pickle.load(f)
                    if isinstance(hmm_data, dict):
                        hmm_model = hmm_data.get('model', hmm_data)
                    else:
                        hmm_model = hmm_data
                
                # 5. Extrai PPO para temp e carrega
                import tempfile
                from stable_baselines3 import PPO
                
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
                    tmp.write(zf.read(ppo_file))
                    tmp_path = tmp.name
                
                ppo_model = PPO.load(tmp_path, device='cpu')
                Path(tmp_path).unlink()  # Limpa temp
                
                return metadata, hmm_model, ppo_model
                
        except Exception as e:
            print(f"Erro ao carregar modelo: {e}")
            return None, None, None
    
    @staticmethod
    def validate_metadata(metadata: dict) -> bool:
        """Valida se metadata tem todos os campos necessários."""
        required = [
            "format_version",
            "symbol",
            "training_config",
            "hmm_config",
            "rl_config",
            "actions"
        ]
        return all(key in metadata for key in required)
```

### 3.4 BarBuffer (`buffer.py`)

Gerencia janela deslizante FIFO.

```python
from collections import deque
from typing import List, Optional
import pandas as pd
from ..core.models import Bar

class BarBuffer:
    """Buffer FIFO para barras OHLCV."""
    
    def __init__(self, maxlen: int = 350):
        self.maxlen = maxlen
        self._buffer: deque = deque(maxlen=maxlen)
    
    def append(self, bar: Bar):
        """Adiciona barra ao buffer."""
        self._buffer.append(bar)
    
    def is_ready(self) -> bool:
        """Verifica se tem barras suficientes para predição."""
        return len(self._buffer) >= self.maxlen
    
    def to_dataframe(self) -> pd.DataFrame:
        """Converte buffer para DataFrame (para cálculo de features)."""
        if not self._buffer:
            return pd.DataFrame()
        
        return pd.DataFrame([
            {
                'time': b.time,
                'open': b.open,
                'high': b.high,
                'low': b.low,
                'close': b.close,
                'volume': b.volume
            }
            for b in self._buffer
        ])
    
    def __len__(self) -> int:
        return len(self._buffer)
    
    def clear(self):
        """Limpa o buffer."""
        self._buffer.clear()
```

### 3.5 Warmup (`warmup.py`)

Lógica de fast-forward para inicialização.

```python
from typing import List
from ..core.models import Bar

def warmup_preditor(preditor: 'Preditor', symbol: str, bars: List[Bar]) -> int:
    """
    Executa warmup do Preditor com histórico.
    
    O warmup:
    1. Alimenta o buffer com barras históricas
    2. Executa predições silenciosas (sem emitir sinais)
    3. Alinha a posição virtual com o que o modelo "teria feito"
    
    Args:
        preditor: Instância do Preditor
        symbol: Símbolo do ativo
        bars: Lista de barras históricas (mais antigas primeiro)
        
    Returns:
        Número de barras processadas
    """
    if symbol not in preditor.models:
        return 0
    
    processed = 0
    for bar in bars:
        # Adiciona ao buffer
        preditor.buffers[symbol].append(bar)
        
        # Se buffer pronto, executa predição silenciosa
        if preditor.buffers[symbol].is_ready():
            # Calcula features e prediz (sem emitir sinal externamente)
            _ = preditor._predict_internal(symbol, bar)
            processed += 1
    
    return processed
```

---

## 4. Requisitos de Performance

| Métrica | Limite | Motivo |
|---------|--------|--------|
| Latência de Inferência | < 10ms | Não atrasar ciclo de execução |
| Uso de Memória por Modelo | < 100MB | Suportar múltiplos símbolos |
| Tempo de Warmup | < 5s para 1000 barras | Inicialização rápida |

**Otimizações:**
- Carregar modelos com `device='cpu'` (GPU não necessária para inferência)
- Não carregar otimizadores ou buffers de replay do treino
- Usar `deterministic=True` na predição (sem sampling)

---

## 5. Logs e Debug

O Preditor deve emitir logs estruturados:

```python
import logging

logger = logging.getLogger("Preditor")

# A cada predição
logger.debug(f"[{symbol}] HMM:{hmm_state} -> {action.name} | "
             f"VPos: {vp.direction}@{vp.entry_price:.5f} | "
             f"VPnL: ${vp.current_pnl:.2f}")

# A cada mudança de posição virtual
logger.info(f"[{symbol}] Virtual: {old_dir} -> {new_dir} | "
            f"Realized: ${realized_pnl:.2f}")
```

Isso permite diagnosticar o "Drift" comparando com a execução real posteriormente.

---

## 6. Integração com Outros Módulos

### 6.1 Recebe do Connector
- `List[Bar]` via callback `on_bar`

### 6.2 Envia para Executor
- `Signal` via WebSocket interno ou chamada direta

### 6.3 Não Interage Com
- Conta real (balance, margin)
- Posições reais
- Ordens reais

---

*Versão 1.1 - Atualizado em 2026-02-04*
