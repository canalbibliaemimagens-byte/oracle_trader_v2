# ⚙️ Módulo EXECUTOR: Especificação Técnica

**Versão:** 1.1  
**Nível:** Execução e Risco  
**Responsabilidade:** Receber sinais do Preditor, aplicar a "Lógica de Sincronização", mapear intensidade para lotes reais, validar riscos e enviar ordens ao Connector.

---

## 1. Estrutura de Arquivos

```
oracle_v2/executor/
├── __init__.py
├── executor.py             # Classe Principal
├── sync_logic.py           # A Regra de Ouro (State Machine)
├── lot_mapper.py           # Mapeamento Intensidade -> Lote
├── risk_guard.py           # Validações de Pré-Trade
└── comment_builder.py      # Monta comentários estruturados
```

---

## 2. Componentes

### 2.1 SyncLogic (`sync_logic.py`)

A função mais crítica do sistema. Determina se uma ordem deve ser aberta, mantida, fechada ou ignorada.

```python
from enum import Enum
from typing import Optional
from ..core.models import Signal, Position
from ..core.constants import Direction

class Decision(str, Enum):
    """Decisões possíveis da lógica de sincronização."""
    NOOP = "NOOP"           # Não fazer nada (já alinhado)
    OPEN = "OPEN"           # Abrir nova posição
    CLOSE = "CLOSE"         # Fechar posição atual
    WAIT_SYNC = "WAIT_SYNC" # Aguardar sincronização (entrada perdida)


def decide(signal: Signal, real_position: Optional[Position]) -> Decision:
    """
    Decide ação baseado no sinal do Preditor vs posição real.
    
    REGRAS DE SINCRONIZAÇÃO:
    
    | Real Pos  | Signal      | Decisão      | Motivo                              |
    |-----------|-------------|--------------|-------------------------------------|
    | FLAT      | WAIT        | NOOP         | Tudo calmo                          |
    | FLAT      | LONG/SHORT  | WAIT_SYNC    | Entrada perdida ("bonde passou")    |
    | LONG      | LONG        | NOOP         | Alinhado, mantém                    |
    | SHORT     | SHORT       | NOOP         | Alinhado, mantém                    |
    | LONG      | WAIT        | CLOSE        | Sinal de saída                      |
    | SHORT     | WAIT        | CLOSE        | Sinal de saída                      |
    | LONG      | SHORT       | CLOSE        | Inversão - fecha primeiro           |
    | SHORT     | LONG        | CLOSE        | Inversão - fecha primeiro           |
    
    REGRA DE BORDA (ENTRADA):
    A única chance de entrar é na transição:
    - De WAIT_SYNC para sinal diferente (inversão ou volta)
    - Implementado via estado interno do Executor
    
    Args:
        signal: Sinal do Preditor
        real_position: Posição real atual (None se FLAT)
        
    Returns:
        Decision indicando ação a tomar
    """
    signal_dir = signal.direction
    real_dir = real_position.direction if real_position else 0
    
    # Ambos FLAT
    if real_dir == 0 and signal_dir == 0:
        return Decision.NOOP
    
    # Real FLAT, Sinal posicionado -> Entrada perdida
    if real_dir == 0 and signal_dir != 0:
        return Decision.WAIT_SYNC
    
    # Mesma direção -> Alinhado
    if real_dir == signal_dir:
        return Decision.NOOP
    
    # Qualquer outra diferença -> Fecha
    # (real posicionado e sinal diferente: WAIT, ou direção oposta)
    return Decision.CLOSE


class SyncState:
    """
    Mantém estado de sincronização por símbolo.
    Necessário para implementar a "Regra de Borda".
    """
    
    def __init__(self):
        self.last_signal_dir: int = 0
        self.waiting_sync: bool = False
    
    def update(self, signal: Signal, decision: Decision) -> bool:
        """
        Atualiza estado e retorna se deve abrir posição.
        
        A abertura só ocorre na BORDA (transição de sinal).
        
        Returns:
            True se deve abrir posição agora
        """
        current_dir = signal.direction
        
        # Se estava em WAIT_SYNC e sinal mudou -> pode abrir
        if self.waiting_sync and current_dir != self.last_signal_dir:
            self.waiting_sync = False
            self.last_signal_dir = current_dir
            return current_dir != 0  # Abre se não for WAIT
        
        # Se decisão é WAIT_SYNC -> entra em espera
        if decision == Decision.WAIT_SYNC:
            self.waiting_sync = True
            self.last_signal_dir = current_dir
            return False
        
        # Atualiza último sinal
        self.last_signal_dir = current_dir
        return False
```

### 2.2 LotMapper (`lot_mapper.py`)

Converte a `intensity` (1, 2, 3) abstrata do modelo em lotes reais.

```python
from typing import Dict

class LotMapper:
    """
    Mapeia intensidade do sinal para lotes reais.
    
    Configuração por símbolo permite ajustar para diferentes instrumentos:
    - Forex: 0.01, 0.03, 0.05
    - Índices: 0.10, 0.30, 0.50
    - Ações: 1, 3, 5
    """
    
    def __init__(self, config: Dict[str, 'SymbolConfig']):
        self.config = config
    
    def map_lot(self, symbol: str, intensity: int) -> float:
        """
        Converte intensidade para lote real.
        
        Args:
            symbol: Nome do símbolo
            intensity: 1 (weak), 2 (moderate), 3 (strong)
            
        Returns:
            Volume em lotes
        """
        if symbol not in self.config:
            return 0.0
        
        cfg = self.config[symbol]
        
        if intensity == 1:
            return cfg.lot_weak
        elif intensity == 2:
            return cfg.lot_moderate
        elif intensity == 3:
            return cfg.lot_strong
        
        return 0.0
    
    def get_config(self, symbol: str) -> 'SymbolConfig':
        """Retorna configuração do símbolo."""
        return self.config.get(symbol)
```

### 2.3 RiskGuard (`risk_guard.py`)

Última linha de defesa antes de enviar a ordem.

```python
from dataclasses import dataclass
from typing import Optional
from ..core.models import AccountInfo

@dataclass
class RiskCheck:
    """Resultado de verificação de risco."""
    passed: bool
    reason: str = ""


class RiskGuard:
    """
    Validações de pré-trade.
    Bloqueia ordens que violam regras de risco.
    """
    
    def __init__(self, config: dict):
        self.dd_limit_pct = config.get('dd_limit_pct', 5.0)
        self.dd_emergency_pct = config.get('dd_emergency_pct', 10.0)
        self.initial_balance = config.get('initial_balance', 0)
        
        # Circuit breaker
        self.consecutive_losses = 0
        self.max_consecutive_losses = config.get('max_consecutive_losses', 5)
    
    def check_all(
        self, 
        symbol: str, 
        volume: float, 
        account: AccountInfo,
        symbol_config: 'SymbolConfig'
    ) -> RiskCheck:
        """
        Executa todas as verificações de risco.
        
        Returns:
            RiskCheck com resultado
        """
        # 1. Drawdown Check
        dd_check = self._check_drawdown(account)
        if not dd_check.passed:
            return dd_check
        
        # 2. Margin Check
        margin_check = self._check_margin(account, volume, symbol_config)
        if not margin_check.passed:
            return margin_check
        
        # 3. Spread Check
        spread_check = self._check_spread(symbol, symbol_config)
        if not spread_check.passed:
            return spread_check
        
        # 4. Circuit Breaker Check
        cb_check = self._check_circuit_breaker()
        if not cb_check.passed:
            return cb_check
        
        return RiskCheck(passed=True)
    
    def _check_drawdown(self, account: AccountInfo) -> RiskCheck:
        """Verifica se DD está dentro dos limites."""
        if self.initial_balance <= 0:
            return RiskCheck(passed=True)
        
        current_dd = ((self.initial_balance - account.equity) / self.initial_balance) * 100
        
        if current_dd >= self.dd_emergency_pct:
            return RiskCheck(
                passed=False, 
                reason=f"EMERGENCY: DD {current_dd:.1f}% >= {self.dd_emergency_pct}%"
            )
        
        if current_dd >= self.dd_limit_pct:
            return RiskCheck(
                passed=False,
                reason=f"DD_LIMIT: DD {current_dd:.1f}% >= {self.dd_limit_pct}%"
            )
        
        return RiskCheck(passed=True)
    
    def _check_margin(self, account: AccountInfo, volume: float, 
                      config: 'SymbolConfig') -> RiskCheck:
        """Verifica se há margem suficiente."""
        # Estimativa simplificada de margem necessária
        estimated_margin = volume * 1000  # Placeholder
        
        if account.free_margin < estimated_margin:
            return RiskCheck(
                passed=False,
                reason=f"MARGIN: Free {account.free_margin:.2f} < Required {estimated_margin:.2f}"
            )
        
        return RiskCheck(passed=True)
    
    def _check_spread(self, symbol: str, config: 'SymbolConfig') -> RiskCheck:
        """Verifica se spread está aceitável."""
        # TODO: Obter spread atual do Connector
        # Por enquanto, sempre passa
        return RiskCheck(passed=True)
    
    def _check_circuit_breaker(self) -> RiskCheck:
        """Verifica circuit breaker (perdas consecutivas)."""
        if self.consecutive_losses >= self.max_consecutive_losses:
            return RiskCheck(
                passed=False,
                reason=f"CIRCUIT_BREAKER: {self.consecutive_losses} losses consecutivas"
            )
        return RiskCheck(passed=True)
    
    def record_trade_result(self, pnl: float):
        """Registra resultado de trade para circuit breaker."""
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
```

### 2.4 CommentBuilder (`comment_builder.py`)

Monta comentário estruturado para rastreabilidade.

```python
class CommentBuilder:
    """
    Monta comentário estruturado para ordens.
    
    Formato: O|{V}|{H}|{A}|{I}|{B}|{D}|{VP}
    
    Campos:
    - V: Versão do sistema
    - H: HMM State (0-4)
    - A: Action Index (0-6)
    - I: Intensity (0-3)
    - B: Balance (USD, inteiro)
    - D: Drawdown % (1 decimal)
    - VP: Virtual PnL (2 decimais)
    
    Limite cTrader: 100 caracteres
    """
    
    VERSION = "2.0"
    MAX_LENGTH = 100
    
    @staticmethod
    def build(
        hmm_state: int,
        action_index: int,
        intensity: int,
        balance: float,
        drawdown_pct: float,
        virtual_pnl: float
    ) -> str:
        """
        Constrói comentário estruturado.
        
        Args:
            hmm_state: Estado HMM atual (0-4)
            action_index: Índice da ação PPO (0-6)
            intensity: Intensidade do sinal (0-3)
            balance: Balance atual em USD
            drawdown_pct: Drawdown atual em %
            virtual_pnl: PnL virtual do Preditor
            
        Returns:
            String formatada (max 100 chars)
        """
        comment = (
            f"O|{CommentBuilder.VERSION}|"
            f"{hmm_state}|{action_index}|{intensity}|"
            f"{int(balance)}|{drawdown_pct:.1f}|{virtual_pnl:.2f}"
        )
        
        # Trunca se necessário
        if len(comment) > CommentBuilder.MAX_LENGTH:
            comment = comment[:CommentBuilder.MAX_LENGTH]
        
        return comment
    
    @staticmethod
    def parse(comment: str) -> dict:
        """
        Parseia comentário estruturado.
        
        Args:
            comment: String do comentário
            
        Returns:
            Dict com campos parseados
        """
        if not comment or not comment.startswith("O|"):
            return {}
        
        parts = comment.split("|")
        if len(parts) < 8:
            return {}
        
        try:
            return {
                "version": parts[1],
                "hmm_state": int(parts[2]),
                "action_index": int(parts[3]),
                "intensity": int(parts[4]),
                "balance": int(parts[5]),
                "drawdown_pct": float(parts[6]),
                "virtual_pnl": float(parts[7])
            }
        except (ValueError, IndexError):
            return {}
```

### 2.5 Executor (`executor.py`)

Orquestra todos os componentes.

```python
from typing import Dict, Optional
from dataclasses import dataclass
from ..core.models import Signal, Position, OrderResult
from ..connector.base import BaseConnector
from .sync_logic import decide, Decision, SyncState
from .lot_mapper import LotMapper
from .risk_guard import RiskGuard
from .comment_builder import CommentBuilder

@dataclass
class SymbolConfig:
    """Configuração de execução por símbolo."""
    enabled: bool = True
    lot_weak: float = 0.01
    lot_moderate: float = 0.03
    lot_strong: float = 0.05
    sl_usd: float = 10.0
    tp_usd: float = 0.0
    max_spread_pips: float = 2.0

@dataclass
class ACK:
    """Acknowledgement de processamento de sinal."""
    symbol: str
    action: str
    status: str      # OK, SKIP, ERROR
    reason: str = ""
    ticket: Optional[int] = None


class Executor:
    """
    Processa sinais do Preditor e executa ordens.
    
    Responsabilidades:
    1. Aplicar lógica de sincronização
    2. Mapear intensidade para lotes
    3. Validar riscos
    4. Enviar ordens ao Connector
    5. Gerar ACKs
    """
    
    def __init__(self, connector: BaseConnector, config_path: str):
        self.connector = connector
        self.symbol_configs: Dict[str, SymbolConfig] = {}
        self.sync_states: Dict[str, SyncState] = {}
        self.lot_mapper: LotMapper = None
        self.risk_guard: RiskGuard = None
        self.paused = False
        
        self.load_config(config_path)
    
    def load_config(self, path: str):
        """Carrega configuração de símbolos do JSON."""
        import json
        with open(path) as f:
            data = json.load(f)
        
        for symbol, cfg in data.items():
            if symbol.startswith("_"):  # Ignora comentários
                continue
            self.symbol_configs[symbol] = SymbolConfig(**cfg)
            self.sync_states[symbol] = SyncState()
        
        self.lot_mapper = LotMapper(self.symbol_configs)
        self.risk_guard = RiskGuard(data.get("_risk", {}))
    
    async def process_signal(self, signal: Signal) -> ACK:
        """
        Processa sinal do Preditor.
        
        Flow:
        1. Verifica se símbolo está enabled
        2. Obtém posição real do Connector
        3. Aplica lógica de sincronização
        4. Se OPEN: mapeia lote, valida risco, executa
        5. Se CLOSE: fecha posição
        6. Retorna ACK
        """
        symbol = signal.symbol
        
        # 1. Verifica enabled
        if symbol not in self.symbol_configs:
            return ACK(symbol, signal.action, "SKIP", "NO_CONFIG")
        
        config = self.symbol_configs[symbol]
        if not config.enabled:
            return ACK(symbol, signal.action, "SKIP", "DISABLED")
        
        # 2. Verifica pause
        if self.paused:
            return ACK(symbol, signal.action, "SKIP", "PAUSED")
        
        # 3. Obtém posição real
        real_pos = await self.connector.get_position(symbol)
        
        # 4. Decisão de sincronização
        decision = decide(signal, real_pos)
        
        # 5. Atualiza estado de sync (para regra de borda)
        sync_state = self.sync_states[symbol]
        should_open = sync_state.update(signal, decision)
        
        # 6. Executa decisão
        if decision == Decision.NOOP:
            return ACK(symbol, signal.action, "OK", "SYNCED")
        
        if decision == Decision.WAIT_SYNC:
            if should_open:
                return await self._open_position(signal, config)
            return ACK(symbol, signal.action, "OK", "WAITING_SYNC")
        
        if decision == Decision.CLOSE:
            return await self._close_position(symbol, real_pos)
        
        return ACK(symbol, signal.action, "ERROR", "UNKNOWN_DECISION")
    
    async def _open_position(self, signal: Signal, config: SymbolConfig) -> ACK:
        """Abre nova posição."""
        symbol = signal.symbol
        
        # Mapeia lote
        volume = self.lot_mapper.map_lot(symbol, signal.intensity)
        if volume <= 0:
            return ACK(symbol, signal.action, "SKIP", "ZERO_LOT")
        
        # Valida risco
        account = await self.connector.get_account()
        risk_check = self.risk_guard.check_all(symbol, volume, account, config)
        if not risk_check.passed:
            return ACK(symbol, signal.action, "SKIP", risk_check.reason)
        
        # Calcula DD atual
        initial = self.risk_guard.initial_balance
        dd_pct = ((initial - account.equity) / initial * 100) if initial > 0 else 0
        
        # Monta comentário
        comment = CommentBuilder.build(
            hmm_state=signal.hmm_state,
            action_index=self._action_to_index(signal.action),
            intensity=signal.intensity,
            balance=account.balance,
            drawdown_pct=dd_pct,
            virtual_pnl=signal.virtual_pnl
        )
        
        # Executa ordem
        result = await self.connector.open_order(
            symbol=symbol,
            direction=signal.direction,
            volume=volume,
            sl=config.sl_usd,
            tp=config.tp_usd,
            comment=comment
        )
        
        if result.success:
            return ACK(symbol, signal.action, "OK", "OPENED", result.ticket)
        else:
            return ACK(symbol, signal.action, "ERROR", result.error)
    
    async def _close_position(self, symbol: str, position: Position) -> ACK:
        """Fecha posição existente."""
        result = await self.connector.close_order(position.ticket)
        
        if result.success:
            # Registra resultado para circuit breaker
            self.risk_guard.record_trade_result(position.pnl)
            return ACK(symbol, "CLOSE", "OK", "CLOSED", position.ticket)
        else:
            return ACK(symbol, "CLOSE", "ERROR", result.error)
    
    def _action_to_index(self, action_name: str) -> int:
        """Converte nome da ação para índice."""
        mapping = {
            "WAIT": 0,
            "LONG_WEAK": 1,
            "LONG_MODERATE": 2,
            "LONG_STRONG": 3,
            "SHORT_WEAK": 4,
            "SHORT_MODERATE": 5,
            "SHORT_STRONG": 6,
        }
        return mapping.get(action_name, 0)
    
    # =========================================================================
    # CONTROLES
    # =========================================================================
    
    def pause(self):
        """Pausa execução (não processa novos sinais)."""
        self.paused = True
    
    def resume(self):
        """Retoma execução."""
        self.paused = False
    
    async def close_position(self, symbol: str) -> bool:
        """Fecha posição de um símbolo específico."""
        pos = await self.connector.get_position(symbol)
        if pos:
            result = await self.connector.close_order(pos.ticket)
            return result.success
        return False
    
    async def close_all(self) -> int:
        """Fecha todas as posições. Retorna número de posições fechadas."""
        positions = await self.connector.get_positions()
        closed = 0
        for pos in positions:
            result = await self.connector.close_order(pos.ticket)
            if result.success:
                closed += 1
        return closed
    
    def get_state(self) -> dict:
        """Retorna estado para debug/dashboard."""
        return {
            "paused": self.paused,
            "symbols": {
                s: {
                    "enabled": cfg.enabled,
                    "lots": [cfg.lot_weak, cfg.lot_moderate, cfg.lot_strong],
                    "sl_usd": cfg.sl_usd,
                    "sync_waiting": self.sync_states.get(s, SyncState()).waiting_sync
                }
                for s, cfg in self.symbol_configs.items()
            }
        }
```

---

## 3. Configuração de Execução

**Arquivo:** `config/executor_symbols.json`

```json
{
  "_comment": "Configuração de execução por símbolo - Oracle v2.0",
  "_risk": {
    "dd_limit_pct": 5.0,
    "dd_emergency_pct": 10.0,
    "initial_balance": 10000,
    "max_consecutive_losses": 5
  },
  
  "EURUSD": {
    "enabled": true,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 10.0,
    "tp_usd": 0,
    "max_spread_pips": 2.0
  },
  
  "GBPUSD": {
    "enabled": true,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 15.0,
    "tp_usd": 0,
    "max_spread_pips": 2.5
  },
  
  "US500": {
    "enabled": true,
    "lot_weak": 0.10,
    "lot_moderate": 0.30,
    "lot_strong": 0.50,
    "sl_usd": 50.0,
    "tp_usd": 0,
    "max_spread_pips": 5.0
  },
  
  "XAUUSD": {
    "enabled": false,
    "lot_weak": 0.01,
    "lot_moderate": 0.03,
    "lot_strong": 0.05,
    "sl_usd": 20.0,
    "tp_usd": 0,
    "max_spread_pips": 3.0,
    "_notes": "Desabilitado - spread muito alto no momento"
  }
}
```

---

## 4. Formato do Comentário

### 4.1 Estrutura

```
O|{V}|{H}|{A}|{I}|{B}|{D}|{VP}
```

| Campo | Significado | Exemplo | Uso |
|-------|-------------|---------|-----|
| O | Prefixo Oracle | O | Identificação |
| V | Versão | 2.0 | Rastrear bugs por versão |
| H | HMM State | 3 | Análise por regime |
| A | Action Index | 1 | Debug (0-6) |
| I | Intensity | 2 | Análise de confiança (0-3) |
| B | Balance | 10234 | Curva de equity |
| D | Drawdown % | 0.5 | Análise de risco |
| VP | Virtual PnL | 12.50 | Medir drift |

### 4.2 Exemplos

```
O|2.0|3|1|1|10234|0.5|0.00     # Entrada LONG_WEAK
O|2.0|0|4|2|10150|1.2|-15.30   # Entrada SHORT_MODERATE
O|2.0|2|0|0|10300|0.0|25.00    # Posição fechada (WAIT)
```

### 4.3 Limite

- cTrader Label: 100 caracteres
- cTrader Comment: 512 caracteres

Usamos o Label (100 chars) por ser mais visível na plataforma.

---

*Versão 1.1 - Atualizado em 2026-02-04*
