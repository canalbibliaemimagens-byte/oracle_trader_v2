"""
Oracle Trader v2 - Config Manager

Carrega e gerencia configurações do sistema.
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional, Any

from .state_machine import PaperTradeConfig
from trading.risk_manager import RiskConfig

logger = logging.getLogger("OracleTrader.Config")


@dataclass
class BrokerConfig:
    """Configuração do broker"""
    type: str = "mt5"
    magic_base: int = 777000
    comment_prefix: str = "OracleV2"


@dataclass
class WebSocketConfig:
    """Configuração do WebSocket"""
    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class RuntimeConfig:
    """
    Configuração completa do sistema.
    
    Carregada do arquivo JSON e pode ser alterada em runtime.
    """
    # Sub-configurações
    broker: BrokerConfig = field(default_factory=BrokerConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    paper_trade: PaperTradeConfig = field(default_factory=PaperTradeConfig)
    websocket: WebSocketConfig = field(default_factory=WebSocketConfig)
    
    # Globais
    lot_multiplier_global: float = 1.0
    models_dir: str = "./models"
    log_level: str = "INFO"
    
    def to_dict(self) -> dict:
        """Converte para dicionário"""
        return {
            'broker': {
                'type': self.broker.type,
                'magic_base': self.broker.magic_base,
                'comment_prefix': self.broker.comment_prefix,
            },
            'risk': {
                'dd_limit_pct': self.risk.dd_limit_pct,
                'dd_emergency_pct': self.risk.dd_emergency_pct,
                'dd_tp_pct': self.risk.dd_tp_pct,
                'use_atr_sl': self.risk.use_atr_sl,
                'atr_period': self.risk.atr_period,
                'atr_multiplier': self.risk.atr_multiplier,
                'sl_min_pips': self.risk.sl_min_pips,
                'sl_max_pips': self.risk.sl_max_pips,
            },
            'paper_trade': {
                'exit_wins_required': self.paper_trade.exit_wins_required,
                'exit_streak_required': self.paper_trade.exit_streak_required,
                'sl_window_minutes': self.paper_trade.sl_window_minutes,
                'sl_max_hits': self.paper_trade.sl_max_hits,
            },
            'websocket': {
                'enabled': self.websocket.enabled,
                'host': self.websocket.host,
                'port': self.websocket.port,
            },
            'lot_multiplier_global': self.lot_multiplier_global,
            'models_dir': self.models_dir,
            'log_level': self.log_level,
        }


class ConfigManager:
    """
    Gerencia configurações do sistema.
    
    - Carrega do arquivo JSON
    - Permite alterações em runtime
    - Salva alterações de volta no arquivo
    """
    
    def __init__(self, config_path: str = "config/oracle_config.json"):
        self.config_path = Path(config_path)
        self.config = RuntimeConfig()
        self.symbols_config: Dict[str, dict] = {}
        self.symbols_config_path = self.config_path.parent / "symbols_config.json"
    
    def load(self) -> RuntimeConfig:
        """
        Carrega configuração do arquivo JSON.
        """
        if not self.config_path.exists():
            logger.warning(f"Config não encontrado: {self.config_path}. Usando defaults.")
            return self.config
        
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)
            
            self._apply_config(data)
            logger.info(f"Config carregada: {self.config_path}")
            
        except Exception as e:
            logger.error(f"Erro ao carregar config: {e}")
        
        return self.config
    
    def _apply_config(self, data: dict) -> None:
        """
        Aplica dados do JSON na configuração.
        """
        # Broker
        if 'broker' in data:
            b = data['broker']
            self.config.broker.type = b.get('type', 'mt5')
            self.config.broker.magic_base = b.get('magic_base', 777000)
            self.config.broker.comment_prefix = b.get('comment_prefix', 'OracleV2')
        
        # Risk
        if 'risk' in data:
            r = data['risk']
            self.config.risk.dd_limit_pct = r.get('dd_limit_pct', 5.0)
            self.config.risk.dd_emergency_pct = r.get('dd_emergency_pct', 10.0)
            self.config.risk.dd_tp_pct = r.get('dd_tp_pct', 0.0)
        
        # Stop Loss
        if 'stop_loss' in data:
            s = data['stop_loss']
            self.config.risk.use_atr_sl = s.get('use_atr', True)
            self.config.risk.atr_period = s.get('atr_period', 14)
            self.config.risk.atr_multiplier = s.get('atr_multiplier', 4.0)
            self.config.risk.sl_min_pips = s.get('min_pips', 20)
            self.config.risk.sl_max_pips = s.get('max_pips', 100)
        
        # SL Protection (para paper trade config)
        if 'sl_protection' in data:
            sp = data['sl_protection']
            self.config.paper_trade.sl_window_minutes = sp.get('window_minutes', 30)
            self.config.paper_trade.sl_max_hits = sp.get('max_hits', 2)
        
        # Paper Trade
        if 'paper_trade' in data:
            pt = data['paper_trade']
            self.config.paper_trade.exit_wins_required = pt.get('exit_wins_required', 3)
            self.config.paper_trade.exit_streak_required = pt.get('exit_streak_required', 2)
        
        # WebSocket
        if 'websocket' in data:
            ws = data['websocket']
            self.config.websocket.enabled = ws.get('enabled', True)
            self.config.websocket.host = ws.get('host', '127.0.0.1')
            self.config.websocket.port = ws.get('port', 8765)
        
        # Globais
        self.config.lot_multiplier_global = data.get('lot_multiplier_global', 1.0)
        self.config.models_dir = data.get('models_dir', './models')
        
        if 'logging' in data:
            self.config.log_level = data['logging'].get('level', 'INFO')
    
    def load_symbols_config(self) -> Dict[str, dict]:
        """
        Carrega configuração individual dos símbolos.
        """
        if not self.symbols_config_path.exists():
            logger.warning(f"Symbols config não encontrado: {self.symbols_config_path}")
            return {}
        
        try:
            with open(self.symbols_config_path, 'r') as f:
                data = json.load(f)
            
            # Remove comentários
            self.symbols_config = {
                k: v for k, v in data.items() 
                if not k.startswith('_')
            }
            
            logger.info(f"Symbols config: {len(self.symbols_config)} símbolos")
            return self.symbols_config
            
        except Exception as e:
            logger.error(f"Erro ao carregar symbols config: {e}")
            return {}
    
    def save(self) -> bool:
        """
        Salva configuração atual no arquivo.
        """
        try:
            # Reconstrói o formato do JSON
            data = {
                "_comment": "Oracle Trader v2.0 - Configuração",
                "broker": {
                    "type": self.config.broker.type,
                    "magic_base": self.config.broker.magic_base,
                    "comment_prefix": self.config.broker.comment_prefix,
                },
                "risk": {
                    "dd_limit_pct": self.config.risk.dd_limit_pct,
                    "dd_emergency_pct": self.config.risk.dd_emergency_pct,
                    "dd_tp_pct": self.config.risk.dd_tp_pct,
                },
                "stop_loss": {
                    "use_atr": self.config.risk.use_atr_sl,
                    "atr_period": self.config.risk.atr_period,
                    "atr_multiplier": self.config.risk.atr_multiplier,
                    "min_pips": self.config.risk.sl_min_pips,
                    "max_pips": self.config.risk.sl_max_pips,
                },
                "sl_protection": {
                    "window_minutes": self.config.paper_trade.sl_window_minutes,
                    "max_hits": self.config.paper_trade.sl_max_hits,
                },
                "paper_trade": {
                    "exit_wins_required": self.config.paper_trade.exit_wins_required,
                    "exit_streak_required": self.config.paper_trade.exit_streak_required,
                    "track_virtual_pnl": True,
                    "log_virtual_trades": True,
                },
                "lot_multiplier_global": self.config.lot_multiplier_global,
                "models_dir": self.config.models_dir,
                "websocket": {
                    "enabled": self.config.websocket.enabled,
                    "host": self.config.websocket.host,
                    "port": self.config.websocket.port,
                },
                "logging": {
                    "level": self.config.log_level,
                },
            }
            
            with open(self.config_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Config salva: {self.config_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")
            return False
    
    def update(self, updates: dict) -> None:
        """
        Atualiza configuração em runtime.
        
        Args:
            updates: Dict com atualizações (formato plano)
        """
        for key, value in updates.items():
            # Risk
            if key == 'dd_limit_pct':
                self.config.risk.dd_limit_pct = value
            elif key == 'dd_emergency_pct':
                self.config.risk.dd_emergency_pct = value
            elif key == 'dd_tp_pct':
                self.config.risk.dd_tp_pct = value
            elif key == 'use_atr_sl':
                self.config.risk.use_atr_sl = value
            elif key == 'atr_multiplier':
                self.config.risk.atr_multiplier = value
            elif key == 'sl_min_pips':
                self.config.risk.sl_min_pips = value
            elif key == 'sl_max_pips':
                self.config.risk.sl_max_pips = value
            
            # Paper Trade
            elif key == 'exit_wins_required':
                self.config.paper_trade.exit_wins_required = value
            elif key == 'exit_streak_required':
                self.config.paper_trade.exit_streak_required = value
            elif key == 'sl_window_minutes':
                self.config.paper_trade.sl_window_minutes = value
            elif key == 'sl_max_hits':
                self.config.paper_trade.sl_max_hits = value
            
            # Globais
            elif key == 'lot_multiplier_global':
                self.config.lot_multiplier_global = value
            elif key == 'models_dir':
                self.config.models_dir = value
        
        logger.info(f"Config atualizada: {updates}")
    
    def get_symbol_config(self, symbol: str) -> Optional[dict]:
        """
        Retorna configuração de um símbolo específico.
        """
        return self.symbols_config.get(symbol)
    
    def is_symbol_enabled(self, symbol: str) -> bool:
        """
        Verifica se símbolo está habilitado.
        """
        cfg = self.symbols_config.get(symbol, {})
        return cfg.get('enabled', False) and cfg.get('lot_multiplier') is not None
