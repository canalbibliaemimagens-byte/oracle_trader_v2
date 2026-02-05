# 📝 Módulo PAPER: Especificação Técnica

**Versão:** 1.1  
**Nível:** Simulação e Benchmark  
**Responsabilidade:** Executar os sinais do Preditor em um ambiente simulado que replica **exatamente** as condições do `TradingEnv` usado no notebook. O objetivo é medir o "Drift" (desvio) entre a performance teórica e a real.

---

## 1. Estrutura de Arquivos

```
oracle_v2/paper/
├── __init__.py
├── paper_trader.py       # Engine de simulação
├── account.py            # Conta simulada
└── stats.py              # Cálculo de métricas
```

---

## 2. Princípio de Funcionamento

O `PaperTrader` roda **em paralelo** ao `Executor` real. Ambos recebem o mesmo `Signal` do `Preditor`.

```
                    ┌─────────────┐
                    │   PREDITOR  │
                    │   (Signal)  │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
       ┌──────────────┐         ┌──────────────┐
       │   EXECUTOR   │         │    PAPER     │
       │    (Real)    │         │  (Simulado)  │
       └──────────────┘         └──────────────┘
              │                         │
              ▼                         ▼
       [ Conta Real ]           [ Conta Virtual ]
```

### 2.1 Comparação

| Aspecto | Executor Real | Paper Trader |
|---------|---------------|--------------|
| Slippage | Real (variável) | Fixo (do treino) |
| Spread | Real (variável) | Fixo (do treino) |
| Comissão | Real | Fixa (do treino) |
| Rejeições | Pode ocorrer | Nunca ocorre |
| Latência | Real | Zero |

### 2.2 Diagnóstico de Drift

| Real Ganhando | Paper Ganhando | Diagnóstico |
|---------------|----------------|-------------|
| ✅ | ✅ | Sistema funcionando bem |
| ❌ | ✅ | **Drift de Execução** - problema no Connector/Executor |
| ❌ | ❌ | **Drift de Mercado** - modelo desatualizado |
| ✅ | ❌ | Improvável (sorte no real?) - investigar |

---

## 3. Componentes

### 3.1 PaperAccount (`account.py`)

Mantém o estado financeiro da simulação.

```python
from dataclasses import dataclass, field
from typing import Dict, List
from ..core.models import Signal

@dataclass
class PaperPosition:
    """Posição virtual no Paper."""
    symbol: str
    direction: int
    intensity: int
    volume: float
    entry_price: float
    entry_time: float
    current_pnl: float = 0.0


@dataclass
class PaperTrade:
    """Trade fechado no Paper."""
    symbol: str
    direction: int
    intensity: int
    volume: float
    entry_price: float
    exit_price: float
    entry_time: float
    exit_time: float
    pnl: float
    pnl_pips: float
    commission: float
    hmm_state: int


class PaperAccount:
    """
    Conta simulada para Paper Trading.
    Replica a lógica do TradingEnv.
    """
    
    def __init__(self, initial_balance: float, training_config: dict):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.equity = initial_balance
        
        # Parâmetros do treino
        self.spread_points = training_config.get('spread_points', 7)
        self.slippage_points = training_config.get('slippage_points', 2)
        self.commission_per_lot = training_config.get('commission_per_lot', 7.0)
        self.point = training_config.get('point', 0.00001)
        self.pip_value = training_config.get('pip_value', 10.0)
        self.lot_sizes = training_config.get('lot_sizes', [0, 0.01, 0.03, 0.05])
        
        # Estado
        self.positions: Dict[str, PaperPosition] = {}
        self.closed_trades: List[PaperTrade] = []
        self.total_commission = 0.0
    
    def open_position(self, symbol: str, direction: int, intensity: int, 
                      price: float, timestamp: float) -> bool:
        """
        Abre posição virtual.
        Aplica spread e slippage do treino.
        """
        if symbol in self.positions:
            return False  # Já tem posição
        
        volume = self.lot_sizes[intensity]
        if volume <= 0:
            return False
        
        # Aplica custos de entrada
        spread_cost = self.spread_points * self.point
        slippage = self.slippage_points * self.point
        
        if direction == 1:  # LONG
            entry_price = price + spread_cost + slippage
        else:  # SHORT
            entry_price = price - spread_cost - slippage
        
        # Deduz comissão de entrada (metade)
        commission = (self.commission_per_lot * volume) / 2
        self.balance -= commission
        self.total_commission += commission
        
        self.positions[symbol] = PaperPosition(
            symbol=symbol,
            direction=direction,
            intensity=intensity,
            volume=volume,
            entry_price=entry_price,
            entry_time=timestamp
        )
        
        return True
    
    def close_position(self, symbol: str, price: float, timestamp: float,
                       hmm_state: int) -> PaperTrade:
        """
        Fecha posição virtual.
        Retorna o trade fechado.
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        
        # Aplica slippage de saída
        slippage = self.slippage_points * self.point
        if pos.direction == 1:  # LONG
            exit_price = price - slippage
        else:  # SHORT
            exit_price = price + slippage
        
        # Calcula PnL
        price_diff = (exit_price - pos.entry_price) * pos.direction
        pips = price_diff / self.point / 10
        pnl = pips * self.pip_value * pos.volume
        
        # Deduz comissão de saída (metade)
        commission = (self.commission_per_lot * pos.volume) / 2
        pnl -= commission
        self.total_commission += commission
        
        # Atualiza balance
        self.balance += pnl
        self.equity = self.balance
        
        # Cria trade
        trade = PaperTrade(
            symbol=symbol,
            direction=pos.direction,
            intensity=pos.intensity,
            volume=pos.volume,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=timestamp,
            pnl=pnl,
            pnl_pips=pips,
            commission=commission * 2,  # Total (entrada + saída)
            hmm_state=hmm_state
        )
        
        self.closed_trades.append(trade)
        del self.positions[symbol]
        
        return trade
    
    def update_equity(self, prices: Dict[str, float]):
        """Atualiza equity com PnL flutuante."""
        floating_pnl = 0.0
        
        for symbol, pos in self.positions.items():
            if symbol in prices:
                price = prices[symbol]
                price_diff = (price - pos.entry_price) * pos.direction
                pips = price_diff / self.point / 10
                pos.current_pnl = pips * self.pip_value * pos.volume
                floating_pnl += pos.current_pnl
        
        self.equity = self.balance + floating_pnl
```

### 3.2 PaperTrader (`paper_trader.py`)

Engine principal de simulação.

```python
from typing import Dict, Optional
from ..core.models import Signal, Bar
from ..core.actions import get_direction, get_intensity, action_from_index
from .account import PaperAccount, PaperTrade

class PaperTrader:
    """
    Simula execução de sinais em paralelo ao real.
    Usa exatamente os mesmos parâmetros do treino.
    """
    
    def __init__(self, initial_balance: float = 10000):
        self.initial_balance = initial_balance
        self.accounts: Dict[str, PaperAccount] = {}
        self.training_configs: Dict[str, dict] = {}
    
    def load_config(self, symbol: str, training_config: dict):
        """
        Carrega configuração de treino para um símbolo.
        Deve ser chamado após carregar modelo no Preditor.
        """
        self.training_configs[symbol] = training_config
        self.accounts[symbol] = PaperAccount(self.initial_balance, training_config)
    
    def process_signal(self, signal: Signal, current_bar: Bar) -> Optional[PaperTrade]:
        """
        Processa sinal do Preditor.
        Retorna trade se fechou posição, None caso contrário.
        
        Args:
            signal: Sinal do Preditor
            current_bar: Barra atual (para preço)
            
        Returns:
            PaperTrade se fechou posição, None se abriu ou manteve
        """
        symbol = signal.symbol
        
        if symbol not in self.accounts:
            return None
        
        account = self.accounts[symbol]
        price = current_bar.close
        timestamp = current_bar.time
        
        target_dir = signal.direction
        target_intensity = signal.intensity
        
        current_pos = account.positions.get(symbol)
        current_dir = current_pos.direction if current_pos else 0
        
        # Mesma posição -> NOOP
        if current_dir == target_dir:
            return None
        
        trade = None
        
        # Fecha posição existente
        if current_dir != 0:
            trade = account.close_position(symbol, price, timestamp, signal.hmm_state)
        
        # Abre nova posição
        if target_dir != 0:
            account.open_position(symbol, target_dir, target_intensity, price, timestamp)
        
        return trade
    
    def get_metrics(self) -> dict:
        """Retorna métricas consolidadas de todos os símbolos."""
        all_trades = []
        total_balance = 0
        
        for symbol, account in self.accounts.items():
            all_trades.extend(account.closed_trades)
            total_balance += account.balance
        
        if not all_trades:
            return {
                'total_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'avg_balance': self.initial_balance
            }
        
        wins = [t for t in all_trades if t.pnl > 0]
        total_pnl = sum(t.pnl for t in all_trades)
        
        return {
            'total_trades': len(all_trades),
            'total_pnl': round(total_pnl, 2),
            'win_rate': round(len(wins) / len(all_trades) * 100, 1),
            'avg_balance': round(total_balance / len(self.accounts), 2),
            'total_commission': sum(a.total_commission for a in self.accounts.values())
        }
    
    def get_trades(self, symbol: str = None) -> list:
        """Retorna trades fechados."""
        if symbol:
            return self.accounts.get(symbol, PaperAccount(0, {})).closed_trades
        
        all_trades = []
        for account in self.accounts.values():
            all_trades.extend(account.closed_trades)
        return sorted(all_trades, key=lambda t: t.exit_time)
    
    def compare_with_real(self, real_trades: list) -> dict:
        """
        Compara trades do Paper com trades reais.
        Retorna relatório de drift.
        """
        paper_trades = self.get_trades()
        
        paper_pnl = sum(t.pnl for t in paper_trades)
        real_pnl = sum(t.get('pnl', 0) for t in real_trades)
        
        paper_wins = len([t for t in paper_trades if t.pnl > 0])
        real_wins = len([t for t in real_trades if t.get('pnl', 0) > 0])
        
        return {
            'paper_trades': len(paper_trades),
            'real_trades': len(real_trades),
            'paper_pnl': round(paper_pnl, 2),
            'real_pnl': round(real_pnl, 2),
            'pnl_drift': round(paper_pnl - real_pnl, 2),
            'pnl_drift_pct': round((paper_pnl - real_pnl) / abs(paper_pnl) * 100, 1) if paper_pnl != 0 else 0,
            'paper_win_rate': round(paper_wins / len(paper_trades) * 100, 1) if paper_trades else 0,
            'real_win_rate': round(real_wins / len(real_trades) * 100, 1) if real_trades else 0,
        }
```

### 3.3 Stats (`stats.py`)

Cálculo de métricas avançadas.

```python
from typing import List
from .account import PaperTrade
import numpy as np

def calculate_sharpe(trades: List[PaperTrade], bars_per_year: int = 20160) -> float:
    """Calcula Sharpe Ratio anualizado."""
    if len(trades) < 2:
        return 0
    
    returns = [t.pnl for t in trades]
    if np.std(returns) == 0:
        return 0
    
    return np.mean(returns) / np.std(returns) * np.sqrt(bars_per_year)


def calculate_max_drawdown(trades: List[PaperTrade], initial_balance: float) -> float:
    """Calcula drawdown máximo em %."""
    if not trades:
        return 0
    
    equity = initial_balance
    peak = initial_balance
    max_dd = 0
    
    for t in trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)
    
    return round(max_dd * 100, 2)


def calculate_profit_factor(trades: List[PaperTrade]) -> float:
    """Calcula Profit Factor."""
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = abs(sum(t.pnl for t in trades if t.pnl < 0))
    
    if losses == 0:
        return float('inf') if wins > 0 else 0
    
    return round(wins / losses, 2)
```

---

## 4. Persistência

Os trades do Paper devem ser salvos na mesma tabela de trades do Real, diferenciados por flag.

```sql
-- Tabela trades (Supabase)
CREATE TABLE trades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id TEXT,
    timestamp TIMESTAMPTZ,
    symbol TEXT,
    direction INT,
    intensity INT,
    volume FLOAT,
    entry_price FLOAT,
    exit_price FLOAT,
    pnl FLOAT,
    pnl_pips FLOAT,
    commission FLOAT,
    hmm_state INT,
    is_paper BOOLEAN DEFAULT FALSE,  -- Flag para diferenciar
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX idx_trades_session ON trades(session_id);
CREATE INDEX idx_trades_is_paper ON trades(is_paper);
CREATE INDEX idx_trades_symbol ON trades(symbol);
```

---

## 5. Integração

```python
# orchestrator.py

async def on_signal(signal: Signal, current_bar: Bar):
    # Executa em paralelo
    executor_task = asyncio.create_task(executor.process_signal(signal))
    paper_trade = paper_trader.process_signal(signal, current_bar)
    
    # Aguarda executor
    ack = await executor_task
    
    # Loga trade do paper se houver
    if paper_trade:
        await persistence.log_trade(paper_trade, is_paper=True)
```

---

*Versão 1.1 - Atualizado em 2026-02-04*
