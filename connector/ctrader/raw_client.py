"""
Oracle Trader v2.0 - cTrader Raw Client
=======================================

Wrapper async para o protocolo raw do cTrader.
Implementa a lógica de:
- Conexão SSL
- Future mapping (Request/Response)
- Event dispatching
- Reconexão automática
"""
import asyncio
import logging
from typing import Dict, Any, Callable, Optional, Awaitable
import ssl

from twisted.internet import reactor, protocol, ssl as twisted_ssl, defer
from twisted.python.failure import Failure

# Protocolo Raw
from .protocol import CTraderProtocol

# Mensagens Protobuf
from ctrader_open_api.messages import OpenApiMessages_pb2 as msg
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as mdl

logger = logging.getLogger("Connector.RawClient")

class RawCTraderClient(protocol.ClientFactory):
    """
    Cliente 'Raw' que gerencia a conexão Twisted e expõe métodos async.
    Substitui a classe 'Client' da lib ctrader-open-api.
    """
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.protocol: Optional[CTraderProtocol] = None
        self.connector = None   # Twisted Connector instance
        
        # Callbacks
        self.on_message: Optional[Callable[[int, bytes], Any]] = None
        self.on_connected: Optional[Callable[[], Any]] = None
        self.on_disconnected: Optional[Callable[[str], Any]] = None
        
        # Future mapping for Request/Response
        # Map: client_msg_id (str) -> asyncio.Future
        self._pending_requests: Dict[str, asyncio.Future] = {}

    def buildProtocol(self, addr):
        p = CTraderProtocol()
        p.factory = self
        return p

    def clientConnectionFailed(self, connector, reason):
        logger.error(f"Connection failed: {reason.getErrorMessage()}")
        if self.on_disconnected:
            self._dispatch(self.on_disconnected, f"Connection Failed: {reason.getErrorMessage()}")
            
    def clientConnectionLost(self, connector, reason):
        logger.warning(f"Connection lost: {reason.getErrorMessage()}")
        self.protocol = None
        if self.on_disconnected:
            self._dispatch(self.on_disconnected, reason.getErrorMessage())

    # === Protocol Callbacks ===

    def client_connected(self, protocol_instance):
        """Chamado pelo CTraderProtocol quando conexão TCP/SSL ok."""
        self.protocol = protocol_instance
        logger.info("RawClient connected logic")
        
        # Inicia Heartbeat
        self.start_heartbeat()
        
        if self.on_connected:
            self._dispatch(self.on_connected)

    def client_disconnected(self, reason):
        """Chamado pelo CTraderProtocol quando perde conexão."""
        self.stop_heartbeat()
        self.protocol = None
        # O ClientFactory também chama clientConnectionLost, então cuidado com duplicação

    # === Heartbeat ===
    
    def start_heartbeat(self):
        """Inicia task de envio periódico de Ping."""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
    def stop_heartbeat(self):
        """Para task de heartbeat."""
        if hasattr(self, '_heartbeat_task') and self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    async def _heartbeat_loop(self):
        """Loop infinito enviando Heartbeat a cada 10s."""
        try:
            while True:
                await asyncio.sleep(10)
                if self.protocol:
                    # Usa VersionReq (2104) como Heartbeat pois PingReq (52) não existe na lib
                    # VersionReq é leve e mantem a conexão ativa.
                    if hasattr(msg, 'ProtoOAPingReq'):
                        req = msg.ProtoOAPingReq()
                        req.timestamp = int(asyncio.get_event_loop().time() * 1000)
                        self.send_proto(req, mdl.PROTO_OA_PING_REQ)
                    else:
                        # Fallback seguro: VersionReq
                        req = msg.ProtoOAVersionReq()
                        self.send_proto(req, mdl.PROTO_OA_VERSION_REQ)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")

    def send_proto(self, protobuf_msg, payload_type):
        """Envia mensagem protobuf diretamente (sem aguardar resposta)."""
        if self.protocol:
            self.protocol.send_proto(protobuf_msg, payload_type)

    def message_received(self, payload_type: int, payload: bytes, client_msg_id: str):
        """Chamado pelo CTraderProtocol quando chega mensagem."""
        
        # 1. Verifica se é resposta para request pendente
        if client_msg_id and client_msg_id in self._pending_requests:
            future = self._pending_requests.pop(client_msg_id)
            if not future.done():
                future.set_result((payload_type, payload))
            return

        # 2. Se não, é evento push (spot, execution, etc)
        if self.on_message:
            self._dispatch(self.on_message, payload_type, payload)

    def _dispatch(self, callback, *args):
        """Despacha callback de forma segura para o loop asyncio."""
        if asyncio.iscoroutinefunction(callback):
             asyncio.create_task(callback(*args))
        else:
            try:
                callback(*args)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    # === Async Methods (Public API) ===

    async def connect(self):
        """Inicia conexão SSL via Twisted (rodando no asyncioreactor ou selector)."""
        logger.info(f"Connecting to {self.host}:{self.port}...")
        
        # Cria contexto SSL (padrão)
        context_factory = twisted_ssl.ClientContextFactory()
        
        # Inicia conexão
        self.connector = reactor.connectSSL(self.host, self.port, self, context_factory)
        
        # Aguarda conexão (pode-se usar um Future aqui se necessário, mas o on_connected cuida disso)
        # O connector connect() é não-bloqueante no Twisted.
        return True

    async def disconnect(self):
        if self.connector:
            self.connector.disconnect()
        elif self.protocol and self.protocol.transport:
            self.protocol.transport.loseConnection()

    async def send_request(self, protobuf_msg, payload_type: int, client_msg_id: str = None) -> (int, bytes):
        """
        Envia request e aguarda resposta correlacionada pelo client_msg_id.
        """
        if not self.protocol:
            raise ConnectionError("Not connected")
            
        if not client_msg_id:
            import uuid
            client_msg_id = str(uuid.uuid4())
            
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending_requests[client_msg_id] = future
        
        # Envia via protocolo
        self.protocol.send_proto(protobuf_msg, payload_type, client_msg_id)
        
        # Aguarda resposta (com timeout de segurança)
        try:
            return await asyncio.wait_for(future, timeout=10.0)
        except asyncio.TimeoutError:
            self._pending_requests.pop(client_msg_id, None)
            raise TimeoutError(f"Request {client_msg_id} timed out")

    def send_command(self, protobuf_msg, payload_type: int):
        """Envia comando sem aguardar resposta (fire-and-forget)."""
        if self.protocol:
            self.protocol.send_proto(protobuf_msg, payload_type)

