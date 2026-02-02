"""
Oracle Trader v2 - Paper Trade Manager

Gerencia operações virtuais quando o símbolo está em modo PAPER_TRADE.
Mantém a "memória" do modelo sem executar ordens reais.

Características:
- NÃO persiste em banco de dados (apenas memória)
- Simula abertura/fechamento de posições
- Rastreia estatísticas virtuais (wins, losses, streak)
- Usado para decidir quando voltar ao trading real
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from models import (
    SymbolState,
    SymbolConfig,
    VirtualPosition,
    TradeAction,
    Direction,
)

logger = logging.getLogger("OracleTrader.PaperTrade")


class PaperTradeManager:
    """
    Gerencia operações virtuais em modo Paper Trade.
    
    Quando um símbolo está em PAPER_TRADE, este manager:
    1. Abre posições virtuais (sem executar no broker)
    2. Atualiza PnL virtual baseado no preço de mercado
    3. Fecha posições virtuais e registra resultado
    4. Mantém estatísticas para critérios de saída
    """
    
    def __init__(self):
        # Configuração de simulação
        self.simulate_spread: bool = True
        self.simulate_slippage: bool = False
        self.default_spread_points: int = 10
    
    # =========================================================================
    # Execução Virtual
    # =========================================================================
    
    def execute_virtual_action(
        self,
        state: SymbolState,
        action: TradeAction,
        lot_size: float,
        current_price: float,
        config: SymbolConfig,
    ) -> Tuple[bool, str]:
        """
        Executa ação do modelo de forma virtual.
        
        Args:
            state: Estado do símbolo
            action: Ação do modelo (WAIT, BUY, SELL)
            lot_size: Tamanho do lote
            current_price: Preço atual do ativo
            config: Configuração do símbolo
            
        Returns:
            Tuple (executou_algo, mensagem)
        """
        current_dir = state.virtual_position.direction if state.virtual_position.is_open else 0
        target_dir = self._get_direction(action)
        
        # WAIT = fechar posição virtual se aberta
        if action == TradeAction.WAIT:
            if state.virtual_position.is_open:
                return self._close_virtual_position(state, current_price, config, "WAIT")
            return False, "Sem posição virtual"
        
        # Mesma direção = manter
        if current_dir == target_dir:
            # Atualiza PnL
            state.virtual_position.update_pnl(
                current_price, 
                config.point, 
                config.pip_value
            )
            return False, f"Mantendo {state.virtual_position.direction_str}"
        
        # Direção diferente = fechar e abrir nova
        if current_dir != 0:
            self._close_virtual_position(state, current_price, config, "REVERSE")
        
        # Abre nova posição virtual
        return self._open_virtual_position(
            state, 
            target_dir, 
            lot_size, 
            current_price, 
            config
        )
    
    def _open_virtual_position(
        self,
        state: SymbolState,
        direction: int,
        lot_size: float,
        price: float,
        config: SymbolConfig,
    ) -> Tuple[bool, str]:
        """
        Abre posição virtual.
        """
        # Simula spread
        if self.simulate_spread:
            spread_value = config.spread_points * config.point
            if direction == Direction.LONG.value:
                price = price + spread_value / 2  # Compra no ask
            else:
                price = price - spread_value / 2  # Vende no bid
        
        state.virtual_position = VirtualPosition(
            symbol=state.symbol,
            direction=direction,
            size=lot_size,
            open_price=price,
            open_time=datetime.now(timezone.utc),
            current_price=price,
            virtual_pnl=0.0,
            virtual_pnl_pips=0.0,
        )
        
        dir_str = "LONG" if direction == 1 else "SHORT"
        logger.debug(f"[{state.symbol}] 📝 Virtual OPEN {dir_str} {lot_size} @ {price:.5f}")
        
        return True, f"Virtual {dir_str} aberto"
    
    def _close_virtual_position(
        self,
        state: SymbolState,
        price: float,
        config: SymbolConfig,
        reason: str = "",
    ) -> Tuple[bool, str]:
        """
        Fecha posição virtual e registra resultado.
        """
        if not state.virtual_position.is_open:
            return False, "Sem posição virtual"
        
        pos = state.virtual_position
        
        # Simula spread no fechamento
        if self.simulate_spread:
            spread_value = config.spread_points * config.point
            if pos.direction == Direction.LONG.value:
                price = price - spread_value / 2  # Vende no bid
            else:
                price = price + spread_value / 2  # Compra no ask
        
        # Calcula PnL final
        pos.update_pnl(price, config.point, config.pip_value)
        
        pnl = pos.virtual_pnl
        pips = pos.virtual_pnl_pips
        
        # Registra nas estatísticas virtuais
        state.virtual_stats.record_trade(pnl, pips)
        
        # Log
        result = "WIN" if pnl > 0 else "LOSS"
        logger.debug(
            f"[{state.symbol}] 📝 Virtual CLOSE {pos.direction_str} | "
            f"PnL: ${pnl:.2f} ({pips:.1f} pips) | {result} | "
            f"Streak: {state.virtual_stats.current_streak}"
        )
        
        # Limpa posição virtual
        state.virtual_position = VirtualPosition()
        
        return True, f"Virtual fechado: ${pnl:.2f}"
    
    # =========================================================================
    # Atualização de PnL
    # =========================================================================
    
    def update_virtual_pnl(
        self,
        state: SymbolState,
        current_price: float,
        config: SymbolConfig,
    ) -> None:
        """
        Atualiza PnL da posição virtual com preço atual.
        
        Deve ser chamado periodicamente no loop principal.
        """
        if not state.virtual_position.is_open:
            return
        
        state.virtual_position.update_pnl(
            current_price,
            config.point,
            config.pip_value
        )
    
    # =========================================================================
    # Utilitários
    # =========================================================================
    
    def _get_direction(self, action: TradeAction) -> int:
        """Converte ação para direção numérica"""
        if action == TradeAction.BUY:
            return Direction.LONG.value
        elif action == TradeAction.SELL:
            return Direction.SHORT.value
        return Direction.FLAT.value
    
    def get_virtual_status(self, state: SymbolState) -> dict:
        """
        Retorna status da posição virtual para dashboard.
        """
        status = {
            'has_position': state.virtual_position.is_open,
            'stats': state.virtual_stats.to_dict(),
        }
        
        if state.virtual_position.is_open:
            status['position'] = state.virtual_position.to_dict()
        
        return status
    
    def force_close_virtual(
        self,
        state: SymbolState,
        current_price: float,
        config: SymbolConfig,
    ) -> None:
        """
        Força fechamento da posição virtual.
        
        Usado quando o símbolo sai do Paper Trade.
        """
        if state.virtual_position.is_open:
            self._close_virtual_position(state, current_price, config, "FORCE_CLOSE")
