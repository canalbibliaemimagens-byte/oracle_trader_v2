"""
Oracle Trader v2 - Executor

Executa ordens de trading (real ou virtual).

Responsabilidades:
- Receber ações do modelo
- Calcular lotes apropriados (via LotCalculator)
- Decidir se executa real ou virtual (baseado no status)
- Coordenar com broker e paper trade manager
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
import uuid

from models import (
    SymbolState,
    SymbolConfig,
    SystemState,
    Trade,
    TradeResult,
    TradeAction,
    SymbolStatus,
    Direction,
    action_to_trade,
    get_direction_from_action,
)
from infra import BrokerBase
from .paper_trade import PaperTradeManager
from .risk_manager import RiskManager
from .lot_calculator import LotCalculator, AssetClass

logger = logging.getLogger("OracleTrader.Executor")


class Executor:
    """
    Executa ações de trading.
    
    Decide automaticamente se executa real ou virtual
    baseado no status do símbolo.
    
    Usa LotCalculator para ajustar lotes baseado no saldo.
    """
    
    def __init__(
        self,
        broker: BrokerBase,
        risk_manager: RiskManager,
        paper_trade: PaperTradeManager,
        magic_base: int = 777000,
    ):
        self.broker = broker
        self.risk_manager = risk_manager
        self.paper_trade = paper_trade
        self.magic_base = magic_base
        
        # Contador de trades para comment
        self._trade_counter = 0
        
        # LotCalculators por símbolo (criados sob demanda)
        self._lot_calculators: Dict[str, LotCalculator] = {}
    
    def get_lot_calculator(self, symbol: str, config: SymbolConfig = None) -> LotCalculator:
        """
        Obtém ou cria LotCalculator para um símbolo.
        
        Args:
            symbol: Nome do símbolo
            config: SymbolConfig com metadados do modelo
        """
        if symbol not in self._lot_calculators:
            # Tenta criar a partir dos metadados do modelo
            if config and hasattr(config, 'asset_class'):
                try:
                    asset_class = AssetClass(config.asset_class)
                    self._lot_calculators[symbol] = LotCalculator.from_asset_class(asset_class)
                    logger.info(f"[{symbol}] LotCalculator criado: {asset_class.value}")
                except (ValueError, AttributeError):
                    pass
            
            # Fallback: usa FOREX como padrão
            if symbol not in self._lot_calculators:
                self._lot_calculators[symbol] = LotCalculator.from_asset_class(AssetClass.FOREX)
                logger.debug(f"[{symbol}] LotCalculator criado: FOREX (default)")
        
        return self._lot_calculators[symbol]
    
    def set_lot_calculator(self, symbol: str, calculator: LotCalculator) -> None:
        """
        Define LotCalculator específico para um símbolo.
        
        Útil quando carregando modelo com metadados.
        """
        self._lot_calculators[symbol] = calculator
        logger.info(f"[{symbol}] LotCalculator definido: {calculator.config.asset_class.value}")
    
    # =========================================================================
    # Execução Principal
    # =========================================================================
    
    async def execute_action(
        self,
        state: SymbolState,
        action: TradeAction,
        action_idx: int,
        current_price: float,
        system: SystemState,
        df=None,
    ) -> Tuple[bool, str]:
        """
        Executa ação do modelo.
        
        Automaticamente escolhe entre execução real ou virtual
        baseado no status do símbolo.
        
        Args:
            state: Estado do símbolo
            action: Ação do modelo (WAIT, BUY, SELL)
            action_idx: Índice da ação (0-6) para cálculo de lote
            current_price: Preço atual
            system: Estado do sistema
            df: DataFrame OHLCV (para cálculo de SL)
            
        Returns:
            Tuple (executou, mensagem)
        """
        config = state.config
        
        # Símbolo BLOCKED não executa nada
        if state.status == SymbolStatus.BLOCKED:
            return False, "Símbolo bloqueado"
        
        # Calcula lote usando LotCalculator (escalonamento dinâmico)
        lot_calc = self.get_lot_calculator(state.symbol, config)
        lot_size = lot_calc.get_lot_for_action(action_idx, system.balance)
        
        # Aplica multiplicador global se existir
        if hasattr(config, 'lot_multiplier') and config.lot_multiplier:
            lot_size = round(lot_size * config.lot_multiplier, 2)
        
        # PAPER_TRADE: executa virtualmente
        if state.status == SymbolStatus.PAPER_TRADE:
            return self.paper_trade.execute_virtual_action(
                state, action, lot_size, current_price, config
            )
        
        # NORMAL: executa no broker (com verificações de risco)
        return await self._execute_real(
            state, action, lot_size, current_price, system, df
        )
    
    # =========================================================================
    # Execução Real
    # =========================================================================
    
    async def _execute_real(
        self,
        state: SymbolState,
        action: TradeAction,
        lot_size: float,
        current_price: float,
        system: SystemState,
        df=None,
    ) -> Tuple[bool, str]:
        """
        Executa ação no broker real.
        """
        config = state.config
        current_dir = state.position.direction if state.position.is_open else 0
        target_dir = get_direction_from_action(action)
        
        # WAIT = fechar posição se aberta
        if action == TradeAction.WAIT:
            if state.position.is_open:
                return await self._close_position(state, "WAIT_SIGNAL", system)
            return False, "Sem posição"
        
        # Verifica risk limit para novas posições
        if system.risk_limit_active and current_dir == 0:
            logger.info(f"[{state.symbol}] Risk limit ativo - bloqueando nova posição")
            return False, "Risk limit ativo"
        
        # Reversão: fecha e abre na direção oposta
        if current_dir != 0 and current_dir != target_dir:
            await self._close_position(state, "REVERSE", system)
            
            if not system.risk_limit_active:
                return await self._open_position(
                    state, target_dir, lot_size, current_price, system, df
                )
            return True, "Fechou para reverso (risk limit)"
        
        # Nova posição
        if current_dir == 0:
            return await self._open_position(
                state, target_dir, lot_size, current_price, system, df
            )
        
        # Mesma direção - manter
        return False, f"Mantendo {state.position.direction_str}"
    
    async def _open_position(
        self,
        state: SymbolState,
        direction: int,
        lots: float,
        price: float,
        system: SystemState,
        df=None,
    ) -> Tuple[bool, str]:
        """
        Abre posição no broker.
        """
        config = state.config
        symbol = state.symbol
        
        # Calcula SL
        sl = self.risk_manager.calculate_sl(
            symbol, direction, price, config, df,
            config.sl_max_pips
        )
        
        # Magic e comment
        self._trade_counter += 1
        magic = self.magic_base
        comment = f"OracleV2_{self._trade_counter}"
        
        # Executa no broker
        result = await self.broker.open_position(
            symbol=symbol,
            direction=direction,
            lots=lots,
            sl=sl,
            tp=0,  # Sem TP (modelo decide quando fechar)
            magic=magic,
            comment=comment,
        )
        
        if not result.success:
            logger.error(f"[{symbol}] Falha ao abrir: {result.message}")
            return False, result.message
        
        # Atualiza estatísticas
        state.trades_count += 1
        system.total_trades += 1
        
        dir_str = "BUY" if direction == 1 else "SELL"
        logger.info(f"[{symbol}] OPEN {dir_str} {lots} @ {result.executed_price}")
        
        return True, f"Abriu {dir_str}"
    
    async def _close_position(
        self,
        state: SymbolState,
        reason: str,
        system: SystemState,
    ) -> Tuple[bool, str]:
        """
        Fecha posição no broker.
        """
        if not state.position.is_open:
            return False, "Sem posição"
        
        pos = state.position
        symbol = state.symbol
        
        result = await self.broker.close_position(
            symbol=symbol,
            ticket=pos.ticket,
            volume=pos.size,
            direction=pos.direction,
            magic=pos.magic,
        )
        
        if not result.success:
            logger.error(f"[{symbol}] Falha ao fechar: {result.message}")
            return False, result.message
        
        # Atualiza estatísticas
        pnl = pos.pnl
        state.total_pnl += pnl
        system.total_pnl += pnl
        
        if pnl > 0:
            state.wins += 1
            system.total_wins += 1
            state.max_win = max(state.max_win, pnl)
            state.current_streak = max(1, state.current_streak + 1) if state.current_streak >= 0 else 1
        else:
            state.losses += 1
            system.total_losses += 1
            state.max_loss = min(state.max_loss, pnl)
            state.current_streak = min(-1, state.current_streak - 1) if state.current_streak <= 0 else -1
        
        logger.info(f"[{symbol}] CLOSE {pos.size} | PnL: ${pnl:.2f} | Reason: {reason}")
        
        # Limpa posição
        state.position = Position()
        
        return True, f"Fechou ${pnl:.2f}"
    
    # =========================================================================
    # Operações em Lote
    # =========================================================================
    
    async def close_all_positions(
        self,
        symbols: Dict[str, SymbolState],
        system: SystemState,
        reason: str = "CLOSE_ALL",
    ) -> Dict[str, float]:
        """
        Fecha todas as posições abertas.
        
        Returns:
            Dict com PnL por símbolo
        """
        results = {}
        
        for symbol, state in symbols.items():
            if state.position.is_open:
                pnl = state.position.pnl
                await self._close_position(state, reason, system)
                results[symbol] = pnl
        
        if results:
            total_pnl = sum(results.values())
            logger.info(f"[CLOSE_ALL] {len(results)} posições fechadas | Total: ${total_pnl:.2f}")
        
        return results


# Import necessário no final para evitar circular
from models import Position
