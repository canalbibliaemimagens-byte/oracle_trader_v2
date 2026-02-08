"""
Oracle Trader v2.0 - cTrader Protocol Implementation
====================================================

Implementação "Raw" do protocolo Twisted para cTrader Open API.
Substitui a dependência da library `ctrader-open-api` e sua state machine quebrada.

Features:
- Encapsulamento de mensagens Protobuf (OpenApiCommonMessages)
- Frame handling (4-byte length prefix)
- Callback dispatching
"""
import struct
import logging
from typing import Callable, Optional

from twisted.internet import protocol

# Import Protobuf definitions from the library (definitions are fine, client logic is bypassed)
from ctrader_open_api.messages import OpenApiCommonMessages_pb2 as common
from ctrader_open_api.messages import OpenApiModelMessages_pb2 as mdl

logger = logging.getLogger("Connector.Protocol")

class CTraderProtocol(protocol.Protocol):
    """
    Protocolo TCP/SSL para cTrader Open API.
    Lida apenas com o transporte e framing das mensagens.
    """
    
    def __init__(self):
        self._buffer = b""
        self._msg_len: Optional[int] = None
        self.factory = None  # Set by factory buildProtocol

    def connectionMade(self):
        """Conexão TCP/SSL estabelecida."""
        logger.info("TCP/SSL Connection established.")
        if self.factory and hasattr(self.factory, "client_connected"):
            self.factory.client_connected(self)

    def connectionLost(self, reason):
        """Conexão perdida."""
        logger.warning(f"TCP Connection lost: {reason.getErrorMessage()}")
        if self.factory and hasattr(self.factory, "client_disconnected"):
            self.factory.client_disconnected(reason)

    def dataReceived(self, data: bytes):
        """Recebimento de dados brutos (stream)."""
        self._buffer += data
        self._process_buffer()

    def _process_buffer(self):
        """Processa o buffer acumulado para extrair mensagens completas."""
        while True:
            # 1. Lê o tamanho (4 bytes big-endian) se ainda não leu
            if self._msg_len is None:
                if len(self._buffer) < 4:
                    return # Aguarda mais dados
                
                self._msg_len = struct.unpack(">I", self._buffer[:4])[0]
                self._buffer = self._buffer[4:]

            # 2. Verifica se tem a mensagem completa
            if len(self._buffer) < self._msg_len:
                return # Aguarda o resto da mensagem

            # 3. Extrai e processa
            msg_bytes = self._buffer[:self._msg_len]
            self._buffer = self._buffer[self._msg_len:]
            
            # Reset para a próxima mensagem antes de processar (segurança contra reentrância)
            current_len = self._msg_len
            self._msg_len = None
            
            try:
                self._decode_message(msg_bytes)
            except Exception as e:
                logger.error(f"Error decoding frame ({current_len} bytes): {e}", exc_info=True)

    def _decode_message(self, data: bytes):
        """Decodifica o envelope ProtoMessage e despacha."""
        try:
            wrapper = common.ProtoMessage()
            wrapper.ParseFromString(data)
            
            payload_type = wrapper.payloadType
            payload = wrapper.payload
            client_msg_id = wrapper.clientMsgId
            
            # Repassa para o factory/client lidar com a lógica de negócio
            if self.factory and hasattr(self.factory, "message_received"):
                self.factory.message_received(payload_type, payload, client_msg_id)
                
        except Exception as e:
            logger.error(f"Protobuf decode error: {e}")

    def send_proto(self, protobuf_msg, payload_type: int, client_msg_id: str = None):
        """
        Envia uma mensagem Protobuf.
        
        Args:
            protobuf_msg: Objeto protobuf (ex: ProtoOAAccountAuthReq)
            payload_type: Enum do tipo (ex: PROTO_OA_ACCOUNT_AUTH_REQ)
            client_msg_id: ID opcional para correlação Request-Response
        """
        if not self.transport:
            logger.error("Attempt callback send_proto without transport")
            return

        try:
            # 1. Serializa o payload específico
            payload_bytes = protobuf_msg.SerializeToString()
            
            # 2. Cria o envelope
            wrapper = common.ProtoMessage()
            wrapper.payloadType = payload_type
            wrapper.payload = payload_bytes
            if client_msg_id:
                wrapper.clientMsgId = client_msg_id
            
            # 3. Serializa o envelope
            wrapper_bytes = wrapper.SerializeToString()
            
            # 4. Adiciona prefixo de tamanho (4 bytes)
            length_bytes = struct.pack(">I", len(wrapper_bytes))
            
            # 5. Envia
            self.transport.write(length_bytes + wrapper_bytes)
            
        except Exception as e:
            logger.error(f"Serialization error: {e}")
