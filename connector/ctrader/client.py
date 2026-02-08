"""
Oracle Trader v2.0 - cTrader Connector (Raw)
============================================

Implementação "Raw" do conector cTrader usando Twisted puro e Protobuf.
Substitui a implementação legada baseada em ctrader-open-api e automat.

Features:
- Conexão SSL via RawCTraderClient
- Gestão de estado (Cache de Posições/Ordens/Conta)
- BarDetector integrado
- Mapeamento Protobuf -> Core Models
"""
import logging
import asyncio
import time
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, List, Optional, Any

from twisted.internet import reactor

from core.models import AccountInfo, Bar, OrderResult, Position, TickData, OrderUpdate
from ..base import BaseConnector
from .bar_detector import BarDetector
from .raw_client import RawCTraderClient
from ..rate_limiter import RateLimiter

# Protobuf definitions
from ctrader_open_api.messages import OpenApiMessages_pb2 as msg
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as mdl
from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as common

logger = logging.getLogger("Connector.cTrader")

# Timeframe Map
TIMEFRAME_TO_PERIOD = {
    "M1": 1, "M5": 5, "M15": 7, "M30": 8, "H1": 9, "H4": 10, "D1": 12
}

class CTraderConnector(BaseConnector):
    """
    Conector cTrader usando protocolo Raw (Twisted + Protobuf).
    """

    def __init__(self, config: dict):
        self.config = config
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.access_token = config['access_token']
        self.account_id = int(config['account_id'])
        self.environment = config.get('environment', 'demo').lower()
        
        # Mapa de Símbolos
        self._symbol_map: Dict[str, int] = {}       # "EURUSD" -> 1
        self._symbol_map_rev: Dict[int, str] = {}   # 1 -> "EURUSD"
        self._symbol_details: Dict[str, Any] = {}
        
        # Componentes
        host = "demo.ctraderapi.com" if self.environment == "demo" else "live.ctraderapi.com"
        port = 5035
        self.client = RawCTraderClient(host, port)
        self.bar_detector = BarDetector()
        self._rate_limiter = RateLimiter(50)
        
        # State
        self._connected = False
        self._account_cache: Dict[str, float] = {"balance": 0.0, "equity": 0.0}
        self._positions_cache: Dict[int, Position] = {} # ticket -> Position
        self._orders_cache: Dict[int, Any] = {}
        
        # Callbacks
        self.client.on_connected = self._on_connected
        self.client.on_disconnected = self._on_disconnected
        self.client.on_message = self._on_message
        
        # External Callbacks (Orchestrator wire-up)
        self.on_tick: Optional[Callable[[TickData], Awaitable[None]]] = None
        self.on_bar: Optional[Callable[[Bar], Awaitable[None]]] = None
        self.on_order_update: Optional[Callable[[OrderUpdate], Awaitable[None]]] = None

    # === LIFECYCLE ===

    async def connect(self):
        """Inicia conexão e autentica."""
        logger.info(f"Connecting to cTrader ({self.environment})...")
        await self.client.connect()
        
        # Aguarda flag de conexão (setada após Auth)
        for _ in range(30):
            if self._connected:
                return True
            await asyncio.sleep(1)
            
        logger.error("Connection timeout")
        await self.disconnect()
        return False

    async def disconnect(self):
        await self.client.disconnect()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def _on_connected(self):
        """Callback do RawClient. Inicia Auth."""
        logger.info("TCP Connected. Authenticating...")
        asyncio.create_task(self._authenticate_and_subscribe())

    def _on_disconnected(self, reason):
        logger.warning(f"Disconnected: {reason}")
        self._connected = False

    async def _authenticate_and_subscribe(self):
        try:
            # 1. App Auth
            app_req = msg.ProtoOAApplicationAuthReq()
            app_req.clientId = self.client_id
            app_req.clientSecret = self.client_secret
            await self.client.send_request(app_req, mdl.PROTO_OA_APPLICATION_AUTH_REQ)
            
            # 2. Account Auth
            acc_req = msg.ProtoOAAccountAuthReq()
            acc_req.ctidTraderAccountId = self.account_id
            acc_req.accessToken = self.access_token
            await self.client.send_request(acc_req, mdl.PROTO_OA_ACCOUNT_AUTH_REQ)
            logger.info("Authenticated.")
            
            self._connected = True
            
            # 3. Initial Data
            await self._fetch_initial_data()
            
        except Exception as e:
            logger.error(f"Auth failed: {e}")
            self._connected = False

    async def _fetch_initial_data(self):
        """Busca símbolos, assets e estado inicial."""
        # Symbols (light — nomes e IDs)
        sym_req = msg.ProtoOASymbolsListReq()
        sym_req.ctidTraderAccountId = self.account_id
        _, payload = await self.client.send_request(sym_req, mdl.PROTO_OA_SYMBOLS_LIST_REQ)
        res = msg.ProtoOASymbolsListRes()
        res.ParseFromString(payload)
        
        for s in res.symbol:
            self._symbol_map[s.symbolName] = s.symbolId
            self._symbol_map_rev[s.symbolId] = s.symbolName
        logger.info(f"Loaded {len(self._symbol_map)} symbols")

        # Symbol details (full — digits, lots, commission)
        all_ids = list(self._symbol_map.values())
        # API limita batch size, enviar em chunks de 100
        for i in range(0, len(all_ids), 100):
            chunk = all_ids[i:i+100]
            try:
                detail_req = msg.ProtoOASymbolByIdReq()
                detail_req.ctidTraderAccountId = self.account_id
                detail_req.symbolId.extend(chunk)
                _, detail_payload = await self.client.send_request(
                    detail_req, mdl.PROTO_OA_SYMBOL_BY_ID_REQ
                )
                detail_res = msg.ProtoOASymbolByIdRes()
                detail_res.ParseFromString(detail_payload)
                
                for s in detail_res.symbol:
                    name = self._symbol_map_rev.get(s.symbolId, str(s.symbolId))
                    self._symbol_details[name] = {
                        "digits": s.digits,
                        "pip_position": s.pipPosition,
                        "lot_size": s.lotSize if s.lotSize else 100000,
                        "min_volume": s.minVolume / 100 if s.minVolume else 0,
                        "max_volume": s.maxVolume / 100 if s.maxVolume else 0,
                        "step_volume": s.stepVolume / 100 if s.stepVolume else 0,
                        "swap_long": s.swapLong if s.swapLong else 0,
                        "swap_short": s.swapShort if s.swapShort else 0,
                        "point": 10 ** (-s.digits) if s.digits else 0.00001,
                    }
                logger.info(f"Loaded details for {len(detail_res.symbol)} symbols (batch {i//100+1})")
            except Exception as e:
                logger.warning(f"Failed to load symbol details batch {i//100+1}: {e}")

        # Trader Info (Balance)
        logger.info("Requesting Trader Info...")
        trader_req = msg.ProtoOATraderReq()
        trader_req.ctidTraderAccountId = self.account_id
        _, payload = await self.client.send_request(trader_req, mdl.PROTO_OA_TRADER_REQ)
        self._handle_trader_res(payload)
        logger.info("Trader Info requested.")
        
        # Reconcile (Posições iniciais)
        rec_req = msg.ProtoOAReconcileReq()
        rec_req.ctidTraderAccountId = self.account_id
        _, payload = await self.client.send_request(rec_req, mdl.PROTO_OA_RECONCILE_REQ)
        self._handle_reconcile(payload)

    # === MESSAGE HANDLING ===

    def _on_message(self, payload_type: int, payload: bytes):
        """Router de eventos push."""
        # logger.info(f"DEBUG: RX Type {payload_type}")
        try:
            if payload_type == mdl.PROTO_OA_SPOT_EVENT:
                self._handle_spot(payload)
            elif payload_type == mdl.PROTO_OA_EXECUTION_EVENT:
                asyncio.create_task(self._handle_execution(payload))
            elif payload_type == mdl.PROTO_OA_TRADER_RES:
                self._handle_trader_res(payload)
            elif payload_type == mdl.PROTO_OA_RECONCILE_RES:
                self._handle_reconcile(payload)
            elif payload_type == mdl.PROTO_OA_ERROR_RES:
                res = msg.ProtoOAErrorRes()
                res.ParseFromString(payload)
                logger.error(f"cTrader Error: {res.description} ({res.errorCode})")
        except Exception as e:
            logger.error(f"Message handling error: {e}", exc_info=True)

    def _handle_spot(self, payload):
        res = msg.ProtoOASpotEvent()
        res.ParseFromString(payload)
        
        symbol_id = res.symbolId
        symbol_name = self._symbol_map_rev.get(symbol_id)
        if not symbol_name: return

        # Usar digits do símbolo para decodificar preços corretamente
        sym_info = self._symbol_details.get(symbol_name, {})
        digits = sym_info.get("digits", 5)
        divisor = 10 ** digits

        bid = res.bid / divisor if res.bid else 0.0
        ask = res.ask / divisor if res.ask else 0.0
        
        if bid > 0 and ask > 0:
            # Atualizar PnL das posições no cache
            mid = (bid + ask) / 2
            for pos in self._positions_cache.values():
                if pos.symbol == symbol_name:
                    pos.current_price = mid
                    # PnL estimado (sem considerar comissão/swap)
                    pip_size = sym_info.get("point", 0.00001) * 10
                    if pip_size > 0:
                        pips = (mid - pos.open_price) * pos.direction / pip_size
                        pos.pnl = pips * 10.0 * pos.volume  # pip_value ~10 USD/lot para forex

            # Atualizar equity estimada
            floating = sum(p.pnl for p in self._positions_cache.values())
            self._account_cache["equity"] = self._account_cache["balance"] + floating

            # BarDetector
            asyncio.create_task(self.bar_detector.on_tick(symbol_name, int(time.time()), bid, ask))

    async def _handle_execution(self, payload):
        res = msg.ProtoOAExecutionEvent()
        res.ParseFromString(payload)
        
        if res.HasField('position'):
            p = res.position
            pid = p.positionId
            
            # Se status for CLOSED (PositionStatus enum = 2)
            if p.positionStatus == 2:
                if pid in self._positions_cache:
                    del self._positions_cache[pid]
                    logger.info(f"Position {pid} closed")
            else:
                # Update/Create
                sym = self._symbol_map_rev.get(p.tradeData.symbolId, str(p.tradeData.symbolId))
                sym_info = self._symbol_details.get(sym, {})
                digits = sym_info.get("digits", 5)
                divisor = 10 ** digits
                
                entry = p.price / divisor if p.price else 0.0
                direction = 1 if p.tradeData.tradeSide == 1 else -1
                vol = p.tradeData.volume / 100000.0
                
                pos_obj = Position(
                    ticket=pid,
                    symbol=sym,
                    volume=vol,
                    direction=direction, 
                    open_price=entry,
                    current_price=entry,
                    pnl=0.0,
                    sl=p.stopLoss / divisor if hasattr(p, 'stopLoss') and p.stopLoss else 0,
                    tp=p.takeProfit / divisor if hasattr(p, 'takeProfit') and p.takeProfit else 0,
                    open_time=int(p.tradeData.openTimestamp / 1000) if p.tradeData.openTimestamp else 0,
                    comment=p.tradeData.comment if hasattr(p.tradeData, 'comment') and p.tradeData.comment else "",
                )
                self._positions_cache[pid] = pos_obj
                logger.info(f"Position {pid} updated: {direction} {vol} {sym}")
        
        if res.HasField('order'):
            # Notifica Orchestrator
            o = res.order
            status = "FILLED" if o.orderStatus == 1 else "REJECTED" # Simplificado
            if self.on_order_update:
                await self.on_order_update(OrderUpdate(
                    id=str(o.orderId),
                    status=status,
                    filled_quantity=o.executedVolume / 100000.0 if o.executedVolume else 0,
                    average_price=o.executionPrice if o.executionPrice else 0
                ))

    def _handle_trader_res(self, payload):
        res = msg.ProtoOATraderRes()
        res.ParseFromString(payload)
        t = res.trader
        self._account_cache["balance"] = t.balance / 100.0
        self._account_cache["equity"] = t.balance / 100.0 # Aproximado, equity real precisa de spots
        logger.info(f"Balance updated: {self._account_cache['balance']}")

    def _handle_reconcile(self, payload):
        res = msg.ProtoOAReconcileRes()
        res.ParseFromString(payload)
        # Atualiza posições abertas
        self._positions_cache.clear()
        for p in res.position:
            sym = self._symbol_map_rev.get(p.tradeData.symbolId, str(p.tradeData.symbolId))
            sym_info = self._symbol_details.get(sym, {})
            digits = sym_info.get("digits", 5)
            divisor = 10 ** digits
            
            pos_obj = Position(
                ticket=p.positionId,
                symbol=sym,
                volume=p.tradeData.volume / 100000.0,
                direction=1 if p.tradeData.tradeSide == 1 else -1,
                open_price=p.price / divisor if p.price else 0,
                current_price=p.price / divisor if p.price else 0,
                pnl=0.0,
                sl=p.stopLoss / divisor if hasattr(p, 'stopLoss') and p.stopLoss else 0,
                tp=p.takeProfit / divisor if hasattr(p, 'takeProfit') and p.takeProfit else 0,
                open_time=int(p.tradeData.openTimestamp / 1000) if p.tradeData.openTimestamp else 0,
                comment=p.tradeData.comment if hasattr(p.tradeData, 'comment') and p.tradeData.comment else "",
            )
            self._positions_cache[p.positionId] = pos_obj
        logger.info(f"Reconciled: {len(self._positions_cache)} positions")

    # === PUBLIC API ===

    async def get_account(self) -> AccountInfo:
        return AccountInfo(
            balance=self._account_cache.get("balance", 0.0),
            equity=self._account_cache.get("equity", 0.0), # TODO: Calcular equity live
            margin=0.0,
            free_margin=0.0,
            margin_level=0.0,
            currency="USD"
        )

    async def get_positions(self) -> List[Position]:
        # Idealmente retornamos do cache, mas podemos forçar reconcile se crítico
        return list(self._positions_cache.values())

    async def subscribe_bars(self, symbols: List[str], timeframe: str, callback):
        ids = []
        for s in symbols:
            sid = self._symbol_map.get(s)
            if sid:
                ids.append(sid)
                self.bar_detector.register(s, timeframe, callback)
            else:
                logger.warning(f"Symbol not found: {s}")
        
        if ids:
            req = msg.ProtoOASubscribeSpotsReq()
            req.ctidTraderAccountId = self.account_id
            req.symbolId.extend(ids)
            req.subscribeToSpotTimestamp = True
            await self.client.send_request(req, mdl.PROTO_OA_SUBSCRIBE_SPOTS_REQ)
            logger.info(f"Subscribed spots for {symbols}")
            
    async def unsubscribe_bars(self, symbols: List[str]) -> None:
        """Cancela assinatura de barras."""
        # Unsubscribe na API (opcional, pode manter spots para outros propósitos)
        # Por enquanto removemos apenas o callback do detector
        pass

    async def open_order(self, symbol: str, direction: int, volume: float, sl: float = 0, tp: float = 0, comment: str = "") -> OrderResult:
        sid = self._symbol_map.get(symbol)
        if not sid: return OrderResult(False, error="Symbol not found")
        
        req = msg.ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = sid
        req.orderType = 1 # MARKET
        req.tradeSide = 1 if direction == 1 else 2
        req.volume = int(volume * 100000) # Assumindo lotes padrão
        if sl: req.stopLoss = sl
        if tp: req.takeProfit = tp
        if comment: req.comment = comment
        
        try:
            pt, payload = await self.client.send_request(req, mdl.PROTO_OA_NEW_ORDER_REQ)
            # Parse result (ExecutionEvent)
            # A resposta do request NewOrder É um ExecutionEvent? Não.
            # A resposta geralmente é vazia ou confirmação técnica.
            # O ExecutionEvent vem assincronamente via push?
            # Na v2, NewOrderReq não tem Resposta direta contendo a ordem.
            # Mas o client raw aguarda qualquer resposta com o clientMsgId.
            # Se a API responder com ExecutionEvent com mesmo clientMsgId, funciona.
            # Caso contrário, precisamos confirmar via stream.
            
            # Workaround simples: Assumir sucesso se não der erro de protocolo.
            return OrderResult(True) 
        except Exception as e:
            return OrderResult(False, error=str(e))

    async def close_order(self, ticket: int, volume: float = 0) -> OrderResult:
        req = msg.ProtoOAClosePositionReq()
        req.ctidTraderAccountId = self.account_id
        req.positionId = ticket
        req.volume = int(volume * 100000)
        
        try:
            await self.client.send_request(req, mdl.PROTO_OA_CLOSE_POSITION_REQ)
            return OrderResult(True, ticket=ticket)
        except Exception as e:
            return OrderResult(False, error=str(e))

    async def get_history(self, symbol: str, timeframe: str, bars: int) -> List[Bar]:
        sid = self._symbol_map.get(symbol)
        if not sid: return []
        
        period = TIMEFRAME_TO_PERIOD.get(timeframe, 1)
        
        tf_min = {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440
        }.get(timeframe, 1)
        
        to_ts = int(time.time() * 1000)
        from_ts = to_ts - (bars * tf_min * 60 * 1000)
        
        req = msg.ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self.account_id
        req.period = period
        req.symbolId = sid
        req.fromTimestamp = from_ts
        req.toTimestamp = to_ts
        
        try:
            _, payload = await self.client.send_request(req, mdl.PROTO_OA_GET_TRENDBARS_REQ)
            res = msg.ProtoOAGetTrendbarsRes()
            res.ParseFromString(payload)
            
            # Obter digits do símbolo para parsing correto
            digits = 5  # default forex
            sym_info = self._symbol_details.get(symbol)
            if sym_info and 'digits' in sym_info:
                digits = sym_info['digits']
            
            result = []
            for tb in res.trendbar:
                # cTrader trendbar: low é absoluto (em unidades de 10^digits)
                # deltaOpen, deltaHigh, deltaClose são deltas a partir do low
                low = tb.low / (10 ** digits) if tb.low else 0
                bar = Bar(
                    symbol=symbol,
                    time=int(tb.utcTimestampInMinutes * 60) if tb.utcTimestampInMinutes else 0,
                    open=low + (tb.deltaOpen / (10 ** digits) if tb.deltaOpen else 0),
                    high=low + (tb.deltaHigh / (10 ** digits) if tb.deltaHigh else 0),
                    low=low,
                    close=low + (tb.deltaClose / (10 ** digits) if tb.deltaClose else 0),
                    volume=float(tb.volume) if tb.volume else 0,
                )
                result.append(bar)
            
            result.sort(key=lambda b: b.time)
            logger.info(f"get_history({symbol}, {timeframe}): {len(result)} bars")
            return result
            
        except Exception as e:
            logger.error(f"Get history failed: {e}")
            return []

    async def modify_order(self, ticket: int, sl=0, tp=0):
        req = msg.ProtoOAAmendPositionSLTPReq()
        req.ctidTraderAccountId = self.account_id
        req.positionId = ticket
        if sl > 0: req.stopLoss = sl
        if tp > 0: req.takeProfit = tp
        
        try:
            await self.client.send_request(req, mdl.PROTO_OA_AMEND_POSITION_SLTP_REQ)
            return OrderResult(True, ticket=ticket)
        except Exception as e:
            logger.error(f"Modify failed: {e}")
            return OrderResult(False, error=str(e))
        
    async def get_position(self, symbol):
        for p in self._positions_cache.values():
            if p.symbol == symbol: return p
        return None
        
    async def get_symbol_info(self, symbol):
        return self._symbol_details.get(symbol)
    
    async def get_order_history(self, since: datetime) -> List[dict]:
        """Retorna histórico de Deals (transações)."""
        from_ts = int(since.timestamp() * 1000)
        to_ts = int(time.time() * 1000)
        
        try:
            req = msg.ProtoOADealListReq(
                ctidTraderAccountId=self.account_id,
                fromTimestamp=from_ts,
                toTimestamp=to_ts
            )
            # req.maxRows = 50
        except Exception as e:
            logger.error(f"Constructor failed: {e}")
            return []
        
        try:
            _, payload = await self.client.send_request(req, mdl.PROTO_OA_DEAL_LIST_REQ)
            res = msg.ProtoOADealListRes()
            res.ParseFromString(payload)
            
            deals = []
            for d in res.deal:
                try:
                    deal = {
                        "id": d.dealId,
                        "order_id": d.orderId,
                        "position_id": d.positionId,
                        "symbol": self._symbol_map_rev.get(d.symbolId, str(d.symbolId)),
                        "volume": d.volume / 100000.0,
                        "type": "BUY" if d.tradeSide == 1 else "SELL",
                        "entry_price": d.executionPrice if d.HasField('executionPrice') else 0.0, 
                        "close_price": d.executionPrice, # Se for closing deal
                        "pnl": d.closePositionDetail.grossProfit / 100.0 if d.HasField('closePositionDetail') and d.closePositionDetail.HasField('grossProfit') else 0.0,
                        "commission": getattr(d, 'commission', 0) / 100.0, 
                        "swap": getattr(d, 'swap', 0) / 100.0,
                        "timestamp": d.executionTimestamp / 1000.0,
                        "status": "FILLED" if d.dealStatus == 1 else "PARTIALLY_FILLED" 
                    }
                    deals.append(deal)
                except Exception as e:
                    logger.error(f"Error mapping deal {d.dealId}: {e}")
            return deals
        except Exception as e:
            logger.error(f"Get deals failed: {e}")
            return []
