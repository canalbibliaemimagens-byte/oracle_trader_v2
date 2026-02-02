"""
Oracle Trader v2 - Risk Manager

Gerenciamento centralizado de risco.

Responsabilidades:
- Calcular e monitorar Drawdown
- Verificar limites (DD Limit, DD Emergency)
- Verificar Take Profit Global
- Calcular Stop Loss (fixo ou ATR)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from models import (
    SystemState,
    SymbolState,
    SymbolConfig,
    Direction,
)

logger = logging.getLogger("OracleTrader.Risk")


@dataclass
class RiskConfig:
    """Configuração de risco"""
    # Drawdown limits (porcentagem)
    dd_limit_pct: float = 5.0       # Bloqueia novas posições
    dd_emergency_pct: float = 10.0  # Fecha tudo
    dd_tp_pct: float = 0.0          # Take Profit global (0 = desativado)
    
    # Stop Loss
    use_atr_sl: bool = True
    atr_period: int = 14
    atr_multiplier: float = 4.0
    sl_min_pips: float = 20.0
    sl_max_pips: float = 100.0


class RiskManager:
    """
    Gerencia risco do sistema.
    
    Monitora drawdown, verifica limites e calcula stop loss.
    """
    
    def __init__(self, config: RiskConfig = None):
        self.config = config or RiskConfig()
    
    # =========================================================================
    # Drawdown
    # =========================================================================
    
    def update_drawdown(self, system: SystemState) -> None:
        """
        Atualiza cálculo de drawdown.
        
        DD = (Equity - Balance) / Balance * 100
        - POSITIVO = lucro flutuante
        - NEGATIVO = perda flutuante
        """
        if system.balance <= 0:
            return
        
        system.current_dd = ((system.equity - system.balance) / system.balance) * 100
        
        # Atualiza máximo DD (mais negativo)
        if system.current_dd < system.max_dd:
            system.max_dd = system.current_dd
            system.max_dd_pct = abs(system.current_dd)
    
    def check_risk_limits(self, system: SystemState) -> Tuple[bool, bool, bool]:
        """
        Verifica todos os limites de risco.
        
        Returns:
            Tuple (dd_limit_hit, dd_emergency_hit, tp_global_hit)
        """
        # DD para verificação é o valor absoluto quando negativo
        dd_abs = abs(system.current_dd) if system.current_dd < 0 else 0
        
        dd_limit_hit = dd_abs >= self.config.dd_limit_pct
        dd_emergency_hit = dd_abs >= self.config.dd_emergency_pct
        
        # TP Global: DD positivo (lucro flutuante)
        tp_global_hit = (
            self.config.dd_tp_pct > 0 and 
            system.current_dd >= self.config.dd_tp_pct
        )
        
        return dd_limit_hit, dd_emergency_hit, tp_global_hit
    
    def should_block_new_positions(self, system: SystemState) -> bool:
        """
        Verifica se deve bloquear novas posições.
        
        Retorna True se DD limit foi atingido.
        """
        dd_abs = abs(system.current_dd) if system.current_dd < 0 else 0
        return dd_abs >= self.config.dd_limit_pct
    
    def should_emergency_close(self, system: SystemState) -> bool:
        """
        Verifica se deve fazer fechamento de emergência.
        
        Retorna True se DD emergency foi atingido.
        """
        dd_abs = abs(system.current_dd) if system.current_dd < 0 else 0
        return dd_abs >= self.config.dd_emergency_pct
    
    def should_take_profit_global(self, system: SystemState) -> bool:
        """
        Verifica se deve realizar Take Profit global.
        
        Retorna True se lucro flutuante atingiu o target.
        """
        if self.config.dd_tp_pct <= 0:
            return False
        return system.current_dd >= self.config.dd_tp_pct
    
    def update_risk_limit_status(self, system: SystemState) -> None:
        """
        Atualiza flag de risk_limit_active no sistema.
        
        - Ativa quando DD atinge limite
        - Desativa quando DD volta para 80% do limite
        """
        dd_abs = abs(system.current_dd) if system.current_dd < 0 else 0
        
        if dd_abs >= self.config.dd_limit_pct:
            if not system.risk_limit_active:
                system.risk_limit_active = True
                logger.warning(f"[RISK] LIMIT ON: DD {system.current_dd:+.2f}%")
        elif dd_abs < self.config.dd_limit_pct * 0.8:
            if system.risk_limit_active:
                system.risk_limit_active = False
                logger.info(f"[RISK] LIMIT OFF: DD {system.current_dd:+.2f}%")
    
    # =========================================================================
    # Stop Loss
    # =========================================================================
    
    def calculate_sl(
        self,
        symbol: str,
        direction: int,
        entry_price: float,
        config: SymbolConfig,
        df: pd.DataFrame = None,
        symbol_sl_max_pips: float = None,
    ) -> float:
        """
        Calcula Stop Loss para uma posição.
        
        Args:
            symbol: Nome do símbolo
            direction: Direção (1=LONG, -1=SHORT)
            entry_price: Preço de entrada
            config: Configuração do símbolo
            df: DataFrame com OHLCV (para ATR)
            symbol_sl_max_pips: SL máximo específico do símbolo
            
        Returns:
            Preço do Stop Loss
        """
        # SL máximo efetivo
        sl_max = symbol_sl_max_pips if symbol_sl_max_pips else self.config.sl_max_pips
        
        # Determina pip_multiplier baseado nos dígitos
        if config.digits >= 3:  # Forex (3-5 digits)
            pip_multiplier = 10
        else:  # Índices, metais
            pip_multiplier = 1
        
        # Valor padrão em pontos
        sl_points = sl_max * pip_multiplier
        atr_used = False
        
        # Tenta usar ATR
        if self.config.use_atr_sl and df is not None and len(df) > self.config.atr_period:
            atr_points = self._calculate_atr_points(df, config)
            
            if atr_points > 0:
                sl_points = atr_points * self.config.atr_multiplier
                atr_used = True
        
        # Aplica limites (convertendo pips para pontos)
        sl_min_points = self.config.sl_min_pips * pip_multiplier
        sl_max_points = sl_max * pip_multiplier
        
        sl_points = max(sl_min_points, min(sl_points, sl_max_points))
        
        # Converte pontos para distância de preço
        sl_distance = sl_points * config.point
        
        # Calcula preço do SL
        if direction == Direction.LONG.value:
            sl = entry_price - sl_distance
        else:
            sl = entry_price + sl_distance
        
        sl = round(sl, config.digits)
        
        # Log
        method = "ATR" if atr_used else "FIXO"
        logger.debug(f"[{symbol}] SL {method}: {sl_points:.0f}pts | Entry={entry_price} SL={sl}")
        
        return sl
    
    def _calculate_atr_points(self, df: pd.DataFrame, config: SymbolConfig) -> float:
        """
        Calcula ATR em pontos.
        """
        try:
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            close = df['close'].astype(float)
            
            # True Range
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            # ATR
            atr_value = tr.rolling(self.config.atr_period).mean().iloc[-1]
            
            if pd.isna(atr_value) or atr_value <= 0:
                return 0
            
            # Converte para pontos
            return atr_value / config.point
            
        except Exception as e:
            logger.error(f"Erro no cálculo ATR: {e}")
            return 0
    
    # =========================================================================
    # Utilitários
    # =========================================================================
    
    def get_risk_summary(self, system: SystemState) -> dict:
        """
        Retorna resumo de risco para dashboard.
        """
        dd_abs = abs(system.current_dd) if system.current_dd < 0 else 0
        
        return {
            'current_dd': round(system.current_dd, 2),
            'max_dd': round(system.max_dd, 2),
            'max_dd_pct': round(system.max_dd_pct, 2),
            'risk_limit_active': system.risk_limit_active,
            'dd_limit_pct': self.config.dd_limit_pct,
            'dd_emergency_pct': self.config.dd_emergency_pct,
            'dd_tp_pct': self.config.dd_tp_pct,
            'pct_to_limit': round(self.config.dd_limit_pct - dd_abs, 2),
            'pct_to_emergency': round(self.config.dd_emergency_pct - dd_abs, 2),
        }
