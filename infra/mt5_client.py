"""
Oracle Trader v2 - Cliente MetaTrader 5

Implementação do BrokerBase para MetaTrader 5.
Requer Windows e a biblioteca MetaTrader5 instalada.

Uso:
    broker = MT5Client()
    await broker.connect()
    account = broker.get_account_info()
"""

import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
import uuid

import pandas as pd

from .broker_base import (
    BrokerBase, 
    AccountInfo, 
    SymbolInfo, 
    Tick,
)

# Importa models do pacote pai
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from models import Trade, TradeResult, Direction

logger = logging.getLogger("OracleTrader.MT5")

# Tenta importar MT5
try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False
    mt5 = None


# Mapeamento de timeframes
TIMEFRAME_MAP = {}
if HAS_MT5:
    TIMEFRAME_MAP = {
        'M1': mt5.TIMEFRAME_M1,
        'M5': mt5.TIMEFRAME_M5,
        'M15': mt5.TIMEFRAME_M15,
        'M30': mt5.TIMEFRAME_M30,
        'H1': mt5.TIMEFRAME_H1,
        'H4': mt5.TIMEFRAME_H4,
        'D1': mt5.TIMEFRAME_D1,
    }


class MT5Client(BrokerBase):
    """
    Cliente para MetaTrader 5.
    
    Implementa BrokerBase usando a biblioteca oficial mt5.
    """
    
    def __init__(self, config: dict = None):
        super().__init__(config)
        self._lock = asyncio.Lock()
        
        if not HAS_MT5:
            logger.error("MetaTrader5 não instalado. Execute: pip install MetaTrader5")
    
    # =========================================================================
    # Conexão
    # =========================================================================
    
    async def connect(self) -> bool:
        """Conecta ao terminal MT5"""
        if not HAS_MT5:
            logger.error("MT5 não disponível")
            return False
        
        try:
            if not mt5.initialize():
                error = mt5.last_error()
                logger.error(f"MT5 initialize falhou: {error}")
                return False
            
            self.connected = True
            
            # Log info
            terminal = self.get_terminal_info()
            account = self.get_account_info()
            
            logger.info(f"MT5 conectado: {terminal.get('name', '?')} (build {terminal.get('build', '?')})")
            if account:
                logger.info(f"Conta: {account.login} | {account.server}")
                logger.info(f"Balance: ${account.balance:.2f} | Equity: ${account.equity:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao conectar MT5: {e}")
            return False
    
    def disconnect(self) -> None:
        """Desconecta do MT5"""
        if HAS_MT5 and self.connected:
            mt5.shutdown()
        self.connected = False
        logger.info("MT5 desconectado")
    
    @property
    def is_connected(self) -> bool:
        return self.connected and HAS_MT5
    
    # =========================================================================
    # Informações da Conta
    # =========================================================================
    
    def get_account_info(self) -> Optional[AccountInfo]:
        if not self.is_connected:
            return None
        
        account = mt5.account_info()
        if not account:
            return None
        
        return AccountInfo(
            login=account.login,
            server=account.server,
            balance=account.balance,
            equity=account.equity,
            margin=account.margin,
            free_margin=account.margin_free,
            margin_level=account.margin_level,
            currency=account.currency,
            leverage=account.leverage,
        )
    
    def get_terminal_info(self) -> Dict:
        if not self.is_connected:
            return {}
        
        info = mt5.terminal_info()
        if not info:
            return {}
        
        return {
            'name': info.name,
            'build': info.build,
            'connected': info.connected,
            'trade_allowed': info.trade_allowed,
        }
    
    # =========================================================================
    # Informações de Símbolos
    # =========================================================================
    
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        if not self.is_connected:
            return None
        
        info = mt5.symbol_info(symbol)
        if not info:
            # Tenta habilitar o símbolo
            mt5.symbol_select(symbol, True)
            info = mt5.symbol_info(symbol)
            if not info:
                return None
        
        return SymbolInfo(
            symbol=symbol,
            point=info.point,
            digits=info.digits,
            volume_min=info.volume_min,
            volume_max=info.volume_max,
            volume_step=info.volume_step,
            spread=info.spread,
            trade_allowed=info.trade_mode > 0,
        )
    
    def get_tick(self, symbol: str) -> Optional[Tick]:
        if not self.is_connected:
            return None
        
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return None
        
        return Tick(
            symbol=symbol,
            bid=tick.bid,
            ask=tick.ask,
            last=tick.last,
            time=tick.time,
        )
    
    # =========================================================================
    # Dados Históricos
    # =========================================================================
    
    def get_bars(
        self, 
        symbol: str, 
        timeframe: str, 
        count: int = 300
    ) -> Optional[pd.DataFrame]:
        if not self.is_connected:
            return None
        
        tf = TIMEFRAME_MAP.get(timeframe, mt5.TIMEFRAME_M15)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        
        if rates is None or len(rates) == 0:
            return None
        
        df = pd.DataFrame(rates)
        df.rename(columns={'tick_volume': 'volume'}, inplace=True)
        
        return df[['time', 'open', 'high', 'low', 'close', 'volume']]
    
    # =========================================================================
    # Posições
    # =========================================================================
    
    def get_positions(self, magic: int = None) -> List[Dict]:
        if not self.is_connected:
            return []
        
        positions = mt5.positions_get()
        if not positions:
            return []
        
        result = []
        for pos in positions:
            # Filtra por magic se especificado
            if magic and pos.magic < magic:
                continue
            
            result.append({
                'ticket': pos.ticket,
                'symbol': pos.symbol,
                'type': pos.type,  # 0=BUY, 1=SELL
                'volume': pos.volume,
                'price_open': pos.price_open,
                'price_current': pos.price_current,
                'sl': pos.sl,
                'tp': pos.tp,
                'profit': pos.profit,
                'swap': pos.swap,
                'magic': pos.magic,
                'comment': pos.comment,
                'time': pos.time,
            })
        
        return result
    
    async def open_position(
        self,
        symbol: str,
        direction: int,
        lots: float,
        sl: float = 0,
        tp: float = 0,
        magic: int = 0,
        comment: str = "",
    ) -> TradeResult:
        async with self._lock:
            if not self.is_connected:
                return TradeResult(success=False, message="MT5 não conectado")
            
            # Obtém informações do símbolo
            sym_info = self.get_symbol_info(symbol)
            if not sym_info:
                return TradeResult(success=False, message=f"Símbolo {symbol} não encontrado")
            
            # Normaliza lotes
            lots = self.normalize_lots(lots, sym_info)
            
            # Obtém tick atual
            tick = self.get_tick(symbol)
            if not tick:
                return TradeResult(success=False, message=f"Tick não disponível para {symbol}")
            
            # Define preço e tipo
            if direction == Direction.LONG.value:
                price = tick.ask
                order_type = mt5.ORDER_TYPE_BUY
            else:
                price = tick.bid
                order_type = mt5.ORDER_TYPE_SELL
            
            # Monta requisição
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lots,
                "type": order_type,
                "price": price,
                "deviation": 10,
                "magic": magic,
                "comment": comment,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            if sl > 0:
                request["sl"] = sl
            if tp > 0:
                request["tp"] = tp
            
            # Envia ordem
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return TradeResult(
                    success=False,
                    message=f"Erro {result.retcode}: {result.comment}",
                    error_code=result.retcode,
                    requested_price=price,
                )
            
            # Cria registro do trade
            trade = Trade(
                id=str(uuid.uuid4())[:8],
                symbol=symbol,
                direction=direction,
                action="OPEN",
                size=lots,
                price=result.price,
                sl=sl,
                timestamp=datetime.now(timezone.utc),
                comment=comment,
                magic=magic,
            )
            
            # Calcula slippage
            slippage = abs(result.price - price) / sym_info.point
            
            logger.info(f"[{symbol}] OPEN {'BUY' if direction == 1 else 'SELL'} {lots} @ {result.price} | SL: {sl}")
            
            return TradeResult(
                success=True,
                trade=trade,
                message="OK",
                requested_price=price,
                executed_price=result.price,
                slippage_points=slippage,
            )
    
    async def close_position(
        self,
        symbol: str,
        ticket: int,
        volume: float,
        direction: int,
        magic: int = 0,
    ) -> TradeResult:
        async with self._lock:
            if not self.is_connected:
                return TradeResult(success=False, message="MT5 não conectado")
            
            # Obtém informações do símbolo
            sym_info = self.get_symbol_info(symbol)
            if not sym_info:
                return TradeResult(success=False, message=f"Símbolo {symbol} não encontrado")
            
            # Normaliza lotes
            volume = self.normalize_lots(volume, sym_info)
            
            # Obtém tick atual
            tick = self.get_tick(symbol)
            if not tick:
                return TradeResult(success=False, message=f"Tick não disponível para {symbol}")
            
            # Define preço e tipo (inverso da direção original)
            if direction == Direction.LONG.value:
                price = tick.bid
                order_type = mt5.ORDER_TYPE_SELL
            else:
                price = tick.ask
                order_type = mt5.ORDER_TYPE_BUY
            
            # Monta requisição
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "deviation": 10,
                "magic": magic,
                "position": ticket,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Envia ordem
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return TradeResult(
                    success=False,
                    message=f"Erro {result.retcode}: {result.comment}",
                    error_code=result.retcode,
                )
            
            # Cria registro do trade
            trade = Trade(
                id=str(uuid.uuid4())[:8],
                symbol=symbol,
                direction=direction,
                action="CLOSE",
                size=volume,
                price=result.price,
                timestamp=datetime.now(timezone.utc),
                magic=magic,
            )
            
            logger.info(f"[{symbol}] CLOSE {volume} @ {result.price}")
            
            return TradeResult(
                success=True,
                trade=trade,
                message="OK",
                executed_price=result.price,
            )
    
    async def modify_position(
        self,
        ticket: int,
        sl: float = None,
        tp: float = None,
    ) -> TradeResult:
        async with self._lock:
            if not self.is_connected:
                return TradeResult(success=False, message="MT5 não conectado")
            
            # Obtém posição atual
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return TradeResult(success=False, message=f"Posição {ticket} não encontrada")
            
            pos = positions[0]
            
            # Monta requisição
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": ticket,
                "sl": sl if sl is not None else pos.sl,
                "tp": tp if tp is not None else pos.tp,
            }
            
            result = mt5.order_send(request)
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return TradeResult(
                    success=False,
                    message=f"Erro {result.retcode}: {result.comment}",
                    error_code=result.retcode,
                )
            
            logger.info(f"[{pos.symbol}] MODIFY #{ticket} SL={sl} TP={tp}")
            
            return TradeResult(success=True, message="OK")
    
    # =========================================================================
    # Histórico
    # =========================================================================
    
    def get_closed_position_info(self, ticket: int) -> Optional[Dict]:
        if not self.is_connected:
            return None
        
        try:
            # Busca deals da posição
            deals = mt5.history_deals_get(position=ticket)
            if not deals or len(deals) == 0:
                return None
            
            # Procura deal de fechamento (entry == 1 = OUT)
            close_deal = None
            for d in deals:
                if d.entry == 1:  # DEAL_ENTRY_OUT
                    close_deal = d
                    break
            
            if not close_deal:
                close_deal = deals[-1]
            
            # Determina motivo do fechamento
            close_reason = "UNKNOWN"
            comment = close_deal.comment.lower() if close_deal.comment else ""
            
            if "sl" in comment or "stop loss" in comment or "[sl]" in comment:
                close_reason = "SL"
            elif "tp" in comment or "take profit" in comment or "[tp]" in comment:
                close_reason = "TP"
            elif hasattr(close_deal, 'reason'):
                if close_deal.reason == 4:
                    close_reason = "SL"
                elif close_deal.reason == 5:
                    close_reason = "TP"
                elif close_deal.reason in [0, 3]:
                    close_reason = "MANUAL"
            
            # Soma totais
            total_pnl = sum(d.profit for d in deals)
            total_commission = sum(d.commission for d in deals)
            total_swap = sum(d.swap for d in deals)
            
            return {
                'ticket': ticket,
                'pnl': total_pnl,
                'commission': total_commission,
                'swap': total_swap,
                'close_price': close_deal.price,
                'close_time': close_deal.time,
                'close_reason': close_reason,
                'volume': close_deal.volume,
                'deals_count': len(deals),
            }
            
        except Exception as e:
            logger.error(f"Erro ao consultar histórico #{ticket}: {e}")
            return None
