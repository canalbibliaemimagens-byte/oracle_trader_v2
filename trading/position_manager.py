"""
Oracle Trader v2 - Position Manager

Gerencia posições reais no broker.

Responsabilidades:
- Sincronizar estado local com broker
- Detectar fechamentos externos (SL/TP hit)
- Atualizar PnL das posições
"""

import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone

from models import (
    Position,
    Trade,
    SymbolState,
    SymbolConfig,
    Direction,
)
from infra import BrokerBase

logger = logging.getLogger("OracleTrader.Position")


class PositionManager:
    """
    Gerencia posições reais.
    
    Mantém cache local e sincroniza com broker.
    Detecta fechamentos externos e notifica o sistema.
    """
    
    def __init__(self, broker: BrokerBase, magic_base: int = 777000):
        self.broker = broker
        self.magic_base = magic_base
        
        # Cache de posições conhecidas (ticket -> info)
        self._position_cache: Dict[int, dict] = {}
    
    # =========================================================================
    # Sincronização
    # =========================================================================
    
    def sync_positions(self, symbols: Dict[str, SymbolState]) -> List[dict]:
        """
        Sincroniza posições do broker com estado local.
        
        Args:
            symbols: Dicionário de estados dos símbolos
            
        Returns:
            Lista de fechamentos detectados
        """
        # Obtém posições atuais do broker
        broker_positions = self.broker.get_positions(self.magic_base)
        current_tickets = {p['ticket']: p for p in broker_positions}
        
        # Atualiza posições existentes
        for pos in broker_positions:
            symbol = pos['symbol']
            if symbol not in symbols:
                continue
            
            state = symbols[symbol]
            self._update_position_from_broker(state, pos)
            
            # Atualiza cache
            self._position_cache[pos['ticket']] = {
                'symbol': symbol,
                'direction': 1 if pos['type'] == 0 else -1,
                'size': pos['volume'],
                'open_price': pos['price_open'],
                'last_pnl': pos['profit'],
            }
        
        # Detecta posições fechadas externamente
        closed_positions = self._detect_closed_positions(current_tickets, symbols)
        
        return closed_positions
    
    def _update_position_from_broker(self, state: SymbolState, pos: dict) -> None:
        """
        Atualiza estado da posição a partir dos dados do broker.
        """
        config = state.config
        direction = 1 if pos['type'] == 0 else -1
        
        # Calcula PnL em pips
        if config and config.point > 0:
            pnl_pips = (pos['price_current'] - pos['price_open']) / config.point / 10 * direction
        else:
            pnl_pips = 0
        
        state.position = Position(
            ticket=pos['ticket'],
            symbol=pos['symbol'],
            direction=direction,
            size=pos['volume'],
            open_price=pos['price_open'],
            current_price=pos['price_current'],
            pnl=pos['profit'],
            pnl_pips=pnl_pips,
            sl=pos['sl'],
            tp=pos['tp'],
            magic=pos['magic'],
        )
    
    def _detect_closed_positions(
        self, 
        current_tickets: Dict[int, dict],
        symbols: Dict[str, SymbolState]
    ) -> List[dict]:
        """
        Detecta posições que foram fechadas externamente.
        
        Returns:
            Lista de dicts com informações dos fechamentos
        """
        closed = []
        
        # Tickets que sumiram
        closed_tickets = set(self._position_cache.keys()) - set(current_tickets.keys())
        
        for ticket in closed_tickets:
            cached = self._position_cache.pop(ticket, None)
            if not cached:
                continue
            
            symbol = cached['symbol']
            if symbol not in symbols:
                continue
            
            state = symbols[symbol]
            
            # Consulta histórico do broker para detalhes
            close_info = self.broker.get_closed_position_info(ticket)
            
            if close_info:
                pnl = close_info['pnl']
                close_reason = close_info['close_reason']
                close_price = close_info['close_price']
            else:
                pnl = cached['last_pnl']
                close_reason = "UNKNOWN"
                close_price = 0
            
            closed.append({
                'ticket': ticket,
                'symbol': symbol,
                'direction': cached['direction'],
                'size': cached['size'],
                'open_price': cached['open_price'],
                'close_price': close_price,
                'pnl': pnl,
                'close_reason': close_reason,
            })
            
            logger.warning(
                f"[{symbol}] Posição #{ticket} fechada externamente | "
                f"Motivo: {close_reason} | PnL: ${pnl:.2f}"
            )
            
            # Limpa posição no estado
            state.position = Position()
        
        return closed
    
    # =========================================================================
    # Operações
    # =========================================================================
    
    def get_open_positions(self, symbols: Dict[str, SymbolState]) -> List[dict]:
        """
        Retorna lista de posições abertas.
        """
        positions = []
        for symbol, state in symbols.items():
            if state.position.is_open:
                positions.append({
                    'symbol': symbol,
                    'direction': state.position.direction_str,
                    'size': state.position.size,
                    'open_price': state.position.open_price,
                    'current_price': state.position.current_price,
                    'pnl': state.position.pnl,
                    'pnl_pips': state.position.pnl_pips,
                })
        return positions
    
    def get_total_exposure(self, symbols: Dict[str, SymbolState]) -> dict:
        """
        Calcula exposição total.
        """
        total_long = 0.0
        total_short = 0.0
        total_pnl = 0.0
        count = 0
        
        for state in symbols.values():
            if state.position.is_open:
                count += 1
                total_pnl += state.position.pnl
                
                if state.position.direction == Direction.LONG.value:
                    total_long += state.position.size
                else:
                    total_short += state.position.size
        
        return {
            'count': count,
            'total_long_lots': total_long,
            'total_short_lots': total_short,
            'total_pnl': round(total_pnl, 2),
            'net_exposure': total_long - total_short,
        }
    
    def clear_cache(self) -> None:
        """
        Limpa cache de posições.
        
        Usar após reconexão com broker.
        """
        self._position_cache.clear()
        logger.info("Cache de posições limpo")
