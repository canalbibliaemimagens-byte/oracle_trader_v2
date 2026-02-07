"""
Oracle Trader v2.0 - cTrader Open API Connector
=================================================

Usa ctrader-open-api (Twisted) para comunicação real com cTrader.

┌─────────────────────────────────────────────────────────────────────────┐
│  NOTA SOBRE TWISTED vs ASYNCIO (Bridge Pattern)                         │
│                                                                         │
│  O SDK oficial ctrader-open-api usa Twisted (Deferreds) para TCP/SSL.  │
│  O Oracle Trader v2 usa asyncio em todo o sistema.                     │
│                                                                         │
│  A bridge funciona assim:                                               │
│    1. lifecycle.py instala asyncioreactor ANTES de qualquer import     │
│       do Twisted reactor (chamado por cli.py no startup)               │
│    2. Isso faz o reactor Twisted rodar DENTRO do loop asyncio          │
│    3. _deferred_to_future() converte Deferred → asyncio.Future         │
│    4. Os métodos async (connect, get_history, open_order, etc.)        │
│       chamam os métodos _deferred internos e convertem o resultado     │
│                                                                         │
│  Resultado: Orchestrator e Executor usam await normalmente.            │
│  Eles NÃO sabem que Twisted existe por baixo.                          │
│                                                                         │
│  Docs: docs/notas/CONNECTOR_BRIDGE_PATTERN.md                          │
│  Refs: orchestrator/lifecycle.py, orchestrator/cli.py                  │
└─────────────────────────────────────────────────────────────────────────┘

Fluxo de uso (via bridge async):
  1. connector = CTraderConnector(credentials, "demo")
  2. await connector.connect()       # Bridge: cria client, autentica, carrega símbolos
  3. await connector.get_history(...) # Bridge: get_history_deferred → asyncio.Future
  4. await connector.subscribe_bars(...)  # Bridge: subscribe_spots_deferred → Future
  5. await connector.open_order(...)  # Bridge: open_order_deferred → Future

Fluxo de uso (Twisted nativo, para debugging):
  1. connector.create_client()
  2. connector._client.startService()
  3. d = connector.authenticate()     # Retorna Deferred
  4. d = connector.get_history_deferred(...)  # Retorna Deferred
"""

import logging
import time
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

from ...core.models import AccountInfo, Bar, OrderResult, Position
from ..base import BaseConnector
from .bar_detector import BarDetector
from ..rate_limiter import RateLimiter
from .auth import OAuth2Manager
from .messages import (
    build_account_auth_req,
    build_amend_position_sltp_req,
    build_app_auth_req,
    build_close_position_req,
    build_new_order_req,
    build_reconcile_req,
    build_subscribe_spots_req,
    build_symbols_list_req,
    build_trendbars_req,
    parse_trendbars,
    parse_positions,
    volume_to_units,
)

logger = logging.getLogger("Connector.cTrader")


class CTraderConnector(BaseConnector):
    """Implementação cTrader Open API (Twisted-based)."""

    def __init__(self, credentials: dict, environment: str = "demo"):
        self.credentials = credentials
        self.environment = environment
        self.auth_manager = OAuth2Manager(credentials)
        self.bar_detector = BarDetector()

        self.account_id: int = int(credentials.get('account_id', 0))
        self._symbol_map: Dict[str, int] = {}
        self._symbol_map_rev: Dict[int, str] = {}
        self._symbol_details: Dict[str, dict] = {}

        self._client = None
        self._connected = False
        self._subscriptions: Dict[str, Callable] = {}
        self._rate_limiter_trading = RateLimiter(50)
        self._rate_limiter_history = RateLimiter(5)
        
        # Cache de informações da conta (atualizado via trader req e execution events)
        self._cached_account: Dict[str, float] = {
            "balance": 0,
            "equity": 0,
            "margin": 0,
            "free_margin": 0,
        }

    # === CONEXÃO ===

    def create_client(self):
        """Cria Client Twisted. Chamar antes de startService()."""
        from ctrader_open_api import Client, TcpProtocol, EndPoints

        host = (EndPoints.PROTOBUF_DEMO_HOST if self.environment == "demo"
                else EndPoints.PROTOBUF_LIVE_HOST)

        self._client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self._client.setConnectedCallback(self._on_connected)
        self._client.setDisconnectedCallback(self._on_disconnected)
        self._client.setMessageReceivedCallback(self._on_message)
        logger.info(f"Cliente criado: {host}:{EndPoints.PROTOBUF_PORT} ({self.environment})")
        return self._client

    def _on_connected(self, client):
        self._connected = True
        logger.info("TCP/SSL conectado")

    def _on_disconnected(self, client, reason):
        self._connected = False
        logger.warning(f"Desconectado: {reason}")

    def _on_message(self, client, message):
        """Processa mensagens assíncronas (spots, executions, errors)."""
        from ctrader_open_api import Protobuf
        from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType as PT

        t = message.payloadType
        if t == PT.PROTO_OA_SPOT_EVENT:
            self._handle_spot(message)
        elif t == PT.PROTO_OA_EXECUTION_EVENT:
            self._handle_execution(message)
        elif t == PT.PROTO_OA_TRADER_RES:
            self._handle_trader_res(message)
        elif t == PT.PROTO_OA_ERROR_RES:
            try:
                err = Protobuf.extract(message)
                logger.error(f"cTrader: {err.errorCode} - {err.description}")
            except Exception:
                logger.error(f"cTrader error (raw): type={t}")

    def _handle_spot(self, message):
        """Alimenta BarDetector com ticks recebidos."""
        from ctrader_open_api import Protobuf
        from twisted.internet import defer

        spot = Protobuf.extract(message)
        name = self._symbol_map_rev.get(spot.symbolId)
        if not name:
            return

        bid = spot.bid / 100000.0 if spot.bid else 0
        ask = spot.ask / 100000.0 if spot.ask else 0
        tick_time = int(spot.timestamp / 1000) if spot.timestamp else int(time.time())

        d = defer.ensureDeferred(self.bar_detector.on_tick(name, tick_time, bid, ask))
        d.addErrback(lambda f: logger.error(f"BarDetector: {f}"))

    # === AUTENTICAÇÃO ===

    def authenticate(self):
        """App Auth + Account Auth. Retorna Deferred."""
        token = self.auth_manager.get_valid_token()
        if not token:
            from twisted.internet import defer
            return defer.fail(Exception("Sem token"))

        msg = build_app_auth_req(self.credentials['client_id'], self.credentials['client_secret'])
        d = self._client.send(msg)
        d.addCallback(self._after_app_auth, token)
        return d

    def _after_app_auth(self, response, token):
        logger.info("App Auth OK")
        msg = build_account_auth_req(token, self.account_id)
        d = self._client.send(msg)
        d.addCallback(self._after_account_auth)
        return d

    def _after_account_auth(self, response):
        """Após auth da conta, solicita informações do trader."""
        logger.info(f"Account Auth OK (id={self.account_id})")
        # Solicita informações da conta (balance, equity, etc.)
        from .messages import build_trader_req
        msg = build_trader_req(self.account_id)
        d = self._client.send(msg, responseTimeoutInSeconds=10)
        d.addCallback(lambda r: logger.debug("Trader info requested"))
        return d

    def _handle_execution(self, message):
        """Atualiza cache de conta após execution events."""
        from ctrader_open_api import Protobuf
        try:
            event = Protobuf.extract(message)
            # ExecutionEvent contém balance e equity após a operação
            if hasattr(event, 'position') and event.position:
                pos = event.position
                if hasattr(pos, 'moneyDigits'):
                    divisor = 10 ** pos.moneyDigits
                    if hasattr(pos, 'swap'):
                        # Atualiza com dados disponíveis
                        logger.debug(f"Execution: position {pos.positionId}")
            # Também pode ter deal com balance
            if hasattr(event, 'deal') and event.deal:
                deal = event.deal
                if hasattr(deal, 'closePositionDetail'):
                    detail = deal.closePositionDetail
                    if hasattr(detail, 'balance'):
                        self._cached_account["balance"] = detail.balance / 100.0
                        logger.debug(f"Balance updated: {self._cached_account['balance']}")
        except Exception as e:
            logger.debug(f"ExecutionEvent parse: {e}")

    def _handle_trader_res(self, message):
        """Processa resposta do ProtoOATraderReq com informações da conta."""
        from ctrader_open_api import Protobuf
        try:
            res = Protobuf.extract(message)
            if hasattr(res, 'trader'):
                trader = res.trader
                # Balance em centavos (dividir por 100)
                if hasattr(trader, 'balance'):
                    self._cached_account["balance"] = trader.balance / 100.0
                    self._cached_account["equity"] = trader.balance / 100.0  # Equity = balance quando sem posições
                    logger.info(f"Account info: balance={self._cached_account['balance']:.2f}")
        except Exception as e:
            logger.debug(f"TraderRes parse: {e}")

    # === SÍMBOLOS ===

    def load_symbols(self):
        """Carrega mapeamento name→symbolId. Retorna Deferred."""
        msg = build_symbols_list_req(self.account_id)
        d = self._client.send(msg, responseTimeoutInSeconds=15)
        d.addCallback(self._parse_symbols)
        return d

    def _parse_symbols(self, response):
        from ctrader_open_api import Protobuf
        res = Protobuf.extract(response)
        for sym in res.symbol:
            name = sym.symbolName if hasattr(sym, 'symbolName') else str(sym.symbolId)
            self._symbol_map[name] = sym.symbolId
            self._symbol_map_rev[sym.symbolId] = name
        logger.info(f"Carregados {len(self._symbol_map)} símbolos")

    def get_symbol_id(self, name: str) -> Optional[int]:
        return self._symbol_map.get(name)

    # === HISTÓRICO ===

    def get_history_deferred(self, symbol: str, timeframe: str, bars: int):
        """Baixa barras históricas. Retorna Deferred[List[Bar]]."""
        from twisted.internet import defer

        sid = self.get_symbol_id(symbol)
        if sid is None:
            return defer.fail(Exception(f"Símbolo '{symbol}' não encontrado"))

        tf_secs = {"M1":60,"M5":300,"M15":900,"M30":1800,"H1":3600,"H4":14400,"D1":86400}.get(timeframe, 900)
        to_ms = int(time.time()) * 1000
        from_ms = to_ms - (bars * tf_secs * 1000)

        msg = build_trendbars_req(self.account_id, sid, timeframe, from_ms, to_ms)
        d = self._client.send(msg, responseTimeoutInSeconds=30)
        d.addCallback(lambda r: self._parse_bars(r, symbol))
        return d

    def _parse_bars(self, response, symbol):
        from ctrader_open_api import Protobuf
        bars = parse_trendbars(Protobuf.extract(response), symbol)
        logger.info(f"[{symbol}] {len(bars)} barras recebidas")
        return bars

    # === ORDENS ===

    def open_order_deferred(self, symbol, direction, volume, sl=0, tp=0, comment=""):
        """Envia ordem a mercado. Retorna Deferred[OrderResult]."""
        from twisted.internet import defer

        sid = self.get_symbol_id(symbol)
        if sid is None:
            return defer.succeed(OrderResult(False, error=f"Símbolo '{symbol}' não encontrado"))

        msg = build_new_order_req(self.account_id, sid, direction, volume_to_units(volume), sl, tp, comment)
        d = self._client.send(msg, responseTimeoutInSeconds=10)
        d.addCallback(self._parse_order, symbol)
        d.addErrback(lambda f: OrderResult(False, error=str(f)))
        return d

    def _parse_order(self, response, symbol):
        from ctrader_open_api import Protobuf
        try:
            event = Protobuf.extract(response)
            if hasattr(event, 'position'):
                p = event.position
                logger.info(f"[{symbol}] Ordem executada T#{p.positionId}")
                return OrderResult(True, ticket=p.positionId, price=p.price/100000.0 if p.price else 0)
            if hasattr(event, 'order'):
                return OrderResult(True, ticket=event.order.orderId)
            return OrderResult(True)
        except Exception as e:
            return OrderResult(False, error=str(e))

    def close_position_deferred(self, position_id, volume=0):
        """Fecha posição. Retorna Deferred[OrderResult]."""
        units = volume_to_units(volume) if volume > 0 else 0
        msg = build_close_position_req(self.account_id, position_id, units)
        d = self._client.send(msg, responseTimeoutInSeconds=10)
        d.addCallback(lambda r: OrderResult(True, ticket=position_id))
        d.addErrback(lambda f: OrderResult(False, error=str(f)))
        return d

    def amend_sltp_deferred(self, position_id, sl=0, tp=0):
        """Modifica SL/TP. Retorna Deferred[OrderResult]."""
        msg = build_amend_position_sltp_req(self.account_id, position_id, sl, tp)
        d = self._client.send(msg, responseTimeoutInSeconds=10)
        d.addCallback(lambda r: OrderResult(True, ticket=position_id))
        d.addErrback(lambda f: OrderResult(False, error=str(f)))
        return d

    # === POSIÇÕES ===

    def get_positions_deferred(self):
        """Reconcile: retorna Deferred[List[Position]]."""
        msg = build_reconcile_req(self.account_id)
        d = self._client.send(msg, responseTimeoutInSeconds=10)
        d.addCallback(self._parse_reconcile)
        return d

    def _parse_reconcile(self, response):
        from ctrader_open_api import Protobuf
        positions = parse_positions(Protobuf.extract(response))
        for pos in positions:
            if pos.symbol.isdigit():
                pos.symbol = self._symbol_map_rev.get(int(pos.symbol), pos.symbol)
        return positions

    # === SUBSCRIPTIONS ===

    def subscribe_spots_deferred(self, symbols, timeframe, callback):
        """Assina spots + registra BarDetector. Retorna Deferred."""
        from twisted.internet import defer

        ids = []
        for s in symbols:
            sid = self.get_symbol_id(s)
            if sid:
                ids.append(sid)
                self.bar_detector.register(s, timeframe, callback)
                self._subscriptions[s] = callback
            else:
                logger.warning(f"Símbolo não encontrado: {s}")

        if not ids:
            return defer.succeed(None)

        msg = build_subscribe_spots_req(self.account_id, ids)
        d = self._client.send(msg)
        d.addCallback(lambda r: logger.info(f"Subscrito spots: {symbols}"))
        return d

    # =========================================================================
    # BaseConnector ABC — Bridge Twisted→AsyncIO
    # =========================================================================
    #
    # Os métodos abaixo implementam a interface BaseConnector (async).
    # Cada um delega para o método _deferred correspondente e converte
    # o resultado Twisted Deferred → asyncio Future via _deferred_to_future().
    #
    # REQUISITO: asyncioreactor deve estar instalado ANTES de importar
    # este módulo. Ver orchestrator/lifecycle.py → install_twisted_reactor()
    #
    # Docs completas: docs/notas/CONNECTOR_BRIDGE_PATTERN.md
    # =========================================================================

    # Converte Twisted Deferreds para asyncio Futures usando Deferred.asFuture().
    # Requer asyncioreactor instalado (ver orchestrator/lifecycle.py).

    def _deferred_to_future(self, deferred):
        """
        Converte Twisted Deferred → asyncio Future.

        Funciona quando o reactor do Twisted é asyncioreactor (rodando dentro
        do mesmo event loop do asyncio). Em ambientes sem Twisted, levanta
        RuntimeError.
        """
        import asyncio
        try:
            # Twisted >= 21.2: Deferred.asFuture(loop)
            loop = asyncio.get_running_loop()
            return deferred.asFuture(loop)
        except AttributeError:
            # Fallback: criar Future manualmente
            future = asyncio.get_running_loop().create_future()

            def on_success(result):
                if not future.done():
                    future.get_loop().call_soon_threadsafe(future.set_result, result)

            def on_error(failure):
                if not future.done():
                    future.get_loop().call_soon_threadsafe(
                        future.set_exception, failure.value
                    )

            deferred.addCallback(on_success)
            deferred.addErrback(on_error)
            return future

    async def connect(self) -> bool:
        """
        Inicia conexão, autentica e carrega símbolos.

        Requer asyncioreactor. O reactor Twisted deve ser instalado ANTES
        de importar este módulo:
            from twisted.internet import asyncioreactor
            asyncioreactor.install()
        """
        try:
            self.create_client()
            self._client.startService()

            # Aguarda conexão TCP
            import asyncio
            for _ in range(50):  # Max 5s
                if self._connected:
                    break
                await asyncio.sleep(0.1)

            if not self._connected:
                logger.error("Timeout na conexão TCP")
                return False

            # Autentica
            await self._deferred_to_future(self.authenticate())
            logger.info("Autenticação concluída")

            # Carrega símbolos
            await self._deferred_to_future(self.load_symbols())
            logger.info(f"Símbolos carregados: {len(self._symbol_map)}")

            return True
        except Exception as e:
            logger.error(f"Falha no connect: {e}")
            return False

    async def disconnect(self) -> None:
        if self._client:
            self._client.stopService()
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected and self._client and self._client.isConnected

    async def get_history(self, symbol, timeframe, bars):
        """Bridge: get_history_deferred → asyncio."""
        return await self._deferred_to_future(
            self.get_history_deferred(symbol, timeframe, bars)
        )

    async def subscribe_bars(self, symbols, timeframe, callback):
        """Bridge: subscribe_spots_deferred → asyncio."""
        return await self._deferred_to_future(
            self.subscribe_spots_deferred(symbols, timeframe, callback)
        )

    async def unsubscribe_bars(self, symbols):
        for s in symbols:
            self.bar_detector.unregister(s)
            self._subscriptions.pop(s, None)

    async def get_account(self):
        """Retorna AccountInfo com dados cacheados da conta."""
        return AccountInfo(
            balance=self._cached_account.get("balance", 0),
            equity=self._cached_account.get("equity", 0),
            margin=self._cached_account.get("margin", 0),
            free_margin=self._cached_account.get("free_margin", 0),
            margin_level=0,
            currency="USD"
        )

    async def get_positions(self):
        """Bridge: get_positions_deferred → asyncio."""
        return await self._deferred_to_future(
            self.get_positions_deferred()
        )

    async def get_position(self, symbol):
        """Busca posição específica de um símbolo."""
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                return pos
        return None

    async def get_order_history(self, since):
        raise NotImplementedError("get_order_history não implementado para cTrader")

    async def open_order(self, symbol, direction, volume, sl=0, tp=0, comment=""):
        """Bridge: open_order_deferred → asyncio."""
        return await self._deferred_to_future(
            self.open_order_deferred(symbol, direction, volume, sl, tp, comment)
        )

    async def close_order(self, ticket, volume=0):
        """Bridge: close_position_deferred → asyncio."""
        return await self._deferred_to_future(
            self.close_position_deferred(ticket, volume)
        )

    async def modify_order(self, ticket, sl=0, tp=0):
        """Bridge: amend_sltp_deferred → asyncio."""
        return await self._deferred_to_future(
            self.amend_sltp_deferred(ticket, sl, tp)
        )

    async def get_symbol_info(self, symbol): return self._symbol_details.get(symbol)
