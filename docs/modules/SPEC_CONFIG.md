# ⚙️ Módulo CONFIG: Especificação Técnica

**Versão:** 1.1  
**Nível:** Configuração  
**Responsabilidade:** Definir estrutura e validação de arquivos de configuração do sistema, separando config global (runtime) de config por símbolo (execução).

---

## 1. Estrutura de Arquivos

```
config/
├── default.yaml              # Config principal (runtime)
├── executor_symbols.json     # Config por símbolo (lot mapping, SL)
└── dev.yaml                  # Sobrescrita para desenvolvimento
```

---

## 2. Config Principal (`default.yaml`)

Configurações globais do sistema.

```yaml
# Oracle Trader v2.0 - Configuração Principal
version: "2.0"

# ═══════════════════════════════════════════════════════════════
# BROKER
# ═══════════════════════════════════════════════════════════════
broker:
  type: "ctrader"                    # ctrader | mock
  client_id: "${CT_CLIENT_ID}"       # OAuth Client ID
  client_secret: "${CT_CLIENT_SECRET}"
  access_token: "${CT_ACCESS_TOKEN}"
  account_id: "${CT_ACCOUNT_ID}"
  environment: "demo"                # demo | live

# ═══════════════════════════════════════════════════════════════
# PATHS
# ═══════════════════════════════════════════════════════════════
paths:
  models_dir: "./models"                    # Diretório dos ZIPs de modelos
  executor_config: "./config/executor_symbols.json"
  log_dir: "./logs"
  cache_dir: "./cache"

# ═══════════════════════════════════════════════════════════════
# TRADING
# ═══════════════════════════════════════════════════════════════
trading:
  timeframe: "M15"                   # Timeframe padrão
  initial_balance: 10000             # Balance inicial (para Paper)
  close_on_exit: false               # Fecha posições ao encerrar
  close_on_day_change: false         # Fecha posições na virada do dia

# ═══════════════════════════════════════════════════════════════
# RISK MANAGEMENT
# ═══════════════════════════════════════════════════════════════
risk:
  dd_limit_pct: 5.0                  # DD% que bloqueia novas posições
  dd_emergency_pct: 10.0             # DD% que fecha tudo (emergency stop)
  max_positions: 10                  # Máximo de posições simultâneas
  max_position_per_symbol: 1         # Máximo de posições por símbolo
  
  # Circuit Breaker
  circuit_breaker:
    enabled: true
    consecutive_losses: 3            # Losses consecutivos para ativar
    cooldown_minutes: 60             # Tempo de pausa após ativação

# ═══════════════════════════════════════════════════════════════
# PERSISTENCE (SUPABASE)
# ═══════════════════════════════════════════════════════════════
persistence:
  enabled: true
  supabase_url: "${SUPABASE_URL}"
  supabase_key: "${SUPABASE_KEY}"
  retry_interval_seconds: 300        # Intervalo de retry para pendentes

# ═══════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════
logging:
  level: "INFO"                      # DEBUG | INFO | WARNING | ERROR
  format: "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
  file_enabled: true
  file_path: "./logs/oracle.log"
  max_size_mb: 10
  backup_count: 5

# ═══════════════════════════════════════════════════════════════
# HEALTH MONITORING
# ═══════════════════════════════════════════════════════════════
health:
  heartbeat_interval_seconds: 60     # Intervalo de heartbeat
  symbol_timeout_seconds: 300        # Timeout sem atividade do símbolo
  memory_limit_mb: 1000              # Alerta se memória exceder
```

---

## 3. Config de Símbolos (`executor_symbols.json`)

Configuração específica por símbolo para o Executor.

```json
{
  "_comment": "Configuração de execução por símbolo - Oracle v2.0",
  "_version": "2.0",
  
  "EURUSD": {
    "enabled": true,
    "lot_mapping": {
      "1": 0.01,
      "2": 0.03,
      "3": 0.05
    },
    "sl_pips": 50,
    "use_atr_sl": true,
    "atr_multiplier": 2.0,
    "max_spread_points": 20,
    "notes": "Par principal - baixo spread"
  },
  
  "GBPUSD": {
    "enabled": true,
    "lot_mapping": {
      "1": 0.01,
      "2": 0.03,
      "3": 0.05
    },
    "sl_pips": 60,
    "use_atr_sl": true,
    "atr_multiplier": 2.5,
    "max_spread_points": 25,
    "notes": "Mais volátil que EURUSD"
  },
  
  "US30": {
    "enabled": true,
    "lot_mapping": {
      "1": 0.1,
      "2": 0.3,
      "3": 0.5
    },
    "sl_pips": 100,
    "use_atr_sl": true,
    "atr_multiplier": 2.0,
    "max_spread_points": 50,
    "notes": "Dow Jones - lotes maiores"
  },
  
  "XAUUSD": {
    "enabled": false,
    "lot_mapping": {
      "1": 0.01,
      "2": 0.03,
      "3": 0.05
    },
    "sl_pips": 200,
    "use_atr_sl": true,
    "atr_multiplier": 3.0,
    "max_spread_points": 50,
    "notes": "Ouro - desabilitado por enquanto"
  }
}
```

### Campos do Symbol Config

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `enabled` | bool | Se false, símbolo é ignorado mesmo com modelo |
| `lot_mapping` | dict | Mapeamento intensidade → volume real |
| `sl_pips` | float | Stop Loss fixo em pips |
| `use_atr_sl` | bool | Se true, usa ATR para SL |
| `atr_multiplier` | float | Multiplicador do ATR para SL |
| `max_spread_points` | int | Spread máximo para abrir posição |
| `notes` | string | Comentários (ignorado pelo sistema) |

---

## 4. Validação de Config

```python
# config/validator.py

from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class ValidationError:
    """Erro de validação."""
    field: str
    message: str
    severity: str  # "error" | "warning"


class ConfigValidator:
    """
    Valida arquivos de configuração.
    """
    
    def validate_main_config(self, config: dict) -> List[ValidationError]:
        """Valida config principal (YAML)."""
        errors = []
        
        # Campos obrigatórios
        required = ['version', 'broker', 'paths', 'trading']
        for field in required:
            if field not in config:
                errors.append(ValidationError(
                    field=field,
                    message=f"Campo obrigatório ausente: {field}",
                    severity="error"
                ))
        
        # Broker
        if 'broker' in config:
            broker = config['broker']
            if broker.get('type') not in ['ctrader', 'mock']:
                errors.append(ValidationError(
                    field="broker.type",
                    message="Tipo de broker inválido (use 'ctrader' ou 'mock')",
                    severity="error"
                ))
            
            if broker.get('environment') not in ['demo', 'live']:
                errors.append(ValidationError(
                    field="broker.environment",
                    message="Environment inválido (use 'demo' ou 'live')",
                    severity="error"
                ))
        
        # Risk
        if 'risk' in config:
            risk = config['risk']
            if risk.get('dd_limit_pct', 0) >= risk.get('dd_emergency_pct', 100):
                errors.append(ValidationError(
                    field="risk",
                    message="dd_limit_pct deve ser menor que dd_emergency_pct",
                    severity="error"
                ))
        
        return errors
    
    def validate_symbols_config(self, config: dict) -> List[ValidationError]:
        """Valida config de símbolos (JSON)."""
        errors = []
        
        for symbol, settings in config.items():
            if symbol.startswith('_'):
                continue  # Ignora campos de metadados
            
            # Lot mapping
            if 'lot_mapping' not in settings:
                errors.append(ValidationError(
                    field=f"{symbol}.lot_mapping",
                    message="lot_mapping é obrigatório",
                    severity="error"
                ))
            else:
                mapping = settings['lot_mapping']
                for intensity in ['1', '2', '3']:
                    if intensity not in mapping:
                        errors.append(ValidationError(
                            field=f"{symbol}.lot_mapping.{intensity}",
                            message=f"Intensidade {intensity} não definida",
                            severity="warning"
                        ))
            
            # SL
            if not settings.get('sl_pips') and not settings.get('use_atr_sl'):
                errors.append(ValidationError(
                    field=f"{symbol}",
                    message="Defina sl_pips ou use_atr_sl=true",
                    severity="warning"
                ))
        
        return errors
```

---

## 5. Loader de Config

```python
# config/loader.py

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any

def expand_env_vars(config: dict) -> dict:
    """
    Expande variáveis de ambiente no formato ${VAR}.
    
    Args:
        config: Dicionário de configuração
        
    Returns:
        Config com variáveis expandidas
    """
    def _expand(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            var_name = value[2:-1]
            return os.environ.get(var_name, value)
        elif isinstance(value, dict):
            return {k: _expand(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [_expand(item) for item in value]
        return value
    
    return _expand(config)


def load_yaml_config(path: str) -> dict:
    """Carrega configuração YAML."""
    with open(path) as f:
        config = yaml.safe_load(f)
    return expand_env_vars(config)


def load_json_config(path: str) -> dict:
    """Carrega configuração JSON."""
    with open(path) as f:
        return json.load(f)


def merge_configs(base: dict, override: dict) -> dict:
    """
    Mescla duas configs (override sobrescreve base).
    
    Args:
        base: Config base
        override: Config que sobrescreve
        
    Returns:
        Config mesclada
    """
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


class ConfigLoader:
    """
    Carrega e gerencia configurações do sistema.
    """
    
    def __init__(self, config_dir: str = "./config"):
        self.config_dir = Path(config_dir)
        self._main_config = None
        self._symbols_config = None
    
    def load(self, config_name: str = "default", env: str = None) -> dict:
        """
        Carrega configuração principal.
        
        Args:
            config_name: Nome do arquivo (sem extensão)
            env: Ambiente opcional para sobrescrita (dev, prod)
            
        Returns:
            Config carregada
        """
        # Carrega config base
        base_path = self.config_dir / f"{config_name}.yaml"
        config = load_yaml_config(str(base_path))
        
        # Aplica sobrescrita de ambiente se existir
        if env:
            env_path = self.config_dir / f"{env}.yaml"
            if env_path.exists():
                env_config = load_yaml_config(str(env_path))
                config = merge_configs(config, env_config)
        
        self._main_config = config
        return config
    
    def load_symbols(self, path: str = None) -> dict:
        """
        Carrega configuração de símbolos.
        
        Args:
            path: Caminho opcional (default: do main config)
            
        Returns:
            Config de símbolos
        """
        if path is None:
            path = self._main_config.get('paths', {}).get(
                'executor_config', 
                './config/executor_symbols.json'
            )
        
        self._symbols_config = load_json_config(path)
        return self._symbols_config
    
    def get_symbol_config(self, symbol: str) -> dict:
        """Retorna config de um símbolo específico."""
        if self._symbols_config is None:
            self.load_symbols()
        
        return self._symbols_config.get(symbol, {})
    
    def is_symbol_enabled(self, symbol: str) -> bool:
        """Verifica se símbolo está habilitado."""
        config = self.get_symbol_config(symbol)
        return config.get('enabled', False)
```

---

## 6. Schema de Validação (Pydantic)

Opcionalmente, usar Pydantic para validação tipada:

```python
# config/schema.py

from pydantic import BaseModel, Field, validator
from typing import Dict, Optional, List

class BrokerConfig(BaseModel):
    type: str = Field(..., pattern="^(ctrader|mock)$")
    client_id: str
    client_secret: str
    access_token: str
    account_id: str
    environment: str = Field("demo", pattern="^(demo|live)$")


class RiskConfig(BaseModel):
    dd_limit_pct: float = Field(5.0, ge=0, le=100)
    dd_emergency_pct: float = Field(10.0, ge=0, le=100)
    max_positions: int = Field(10, ge=1)
    max_position_per_symbol: int = Field(1, ge=1)
    
    @validator('dd_emergency_pct')
    def validate_emergency(cls, v, values):
        if 'dd_limit_pct' in values and v <= values['dd_limit_pct']:
            raise ValueError('dd_emergency_pct deve ser maior que dd_limit_pct')
        return v


class TradingConfig(BaseModel):
    timeframe: str = Field("M15", pattern="^(M1|M5|M15|M30|H1|H4|D1)$")
    initial_balance: float = Field(10000, gt=0)
    close_on_exit: bool = False
    close_on_day_change: bool = False


class MainConfig(BaseModel):
    version: str
    broker: BrokerConfig
    trading: TradingConfig
    risk: Optional[RiskConfig] = None


class SymbolConfig(BaseModel):
    enabled: bool = True
    lot_mapping: Dict[str, float]
    sl_pips: float = Field(50, gt=0)
    use_atr_sl: bool = False
    atr_multiplier: float = Field(2.0, gt=0)
    max_spread_points: int = Field(20, gt=0)
    notes: Optional[str] = None
    
    @validator('lot_mapping')
    def validate_lot_mapping(cls, v):
        required_keys = {'1', '2', '3'}
        if not required_keys.issubset(v.keys()):
            raise ValueError('lot_mapping deve ter chaves 1, 2, 3')
        return v
```

---

## 7. Uso

```python
# No Orchestrator

from config.loader import ConfigLoader
from config.validator import ConfigValidator

# Carrega
loader = ConfigLoader("./config")
config = loader.load("default", env="dev")  # Mescla default + dev
symbols = loader.load_symbols()

# Valida
validator = ConfigValidator()
errors = validator.validate_main_config(config)
errors += validator.validate_symbols_config(symbols)

if any(e.severity == "error" for e in errors):
    for e in errors:
        print(f"[{e.severity.upper()}] {e.field}: {e.message}")
    raise ValueError("Configuração inválida")

# Usa
print(f"DD Limit: {config['risk']['dd_limit_pct']}%")
print(f"EURUSD lot_mapping: {symbols['EURUSD']['lot_mapping']}")
```

---

*Versão 1.1 - Atualizado em 2026-02-04*
