"""
Oracle Trader v2.0 — Hub Client (TelemetryPublisher)
======================================================

Client WebSocket assíncrono que conecta ao OTS Hub.
Publica telemetria e sinais, recebe comandos.

Uso no Orchestrator:
    hub = HubClient(url="ws://hub-ip:8000/ws/bot-01", token="xxx")
    await hub.connect()
    await hub.send_telemetry({"balance": 10000, "equity": 10050, ...})
"""

import asyncio
import json
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger("HubClient")


class HubClient:
    """
    Client WebSocket para OTS Hub.
    Reconecta automaticamente em caso de falha.
    """

    def __init__(
        self,
        url: str,
        token: str,
        instance_id: str = "bot-v2",
        reconnect_interval: float = 10.0,
        on_command: Optional[Callable] = None,
    ):
        """
        Args:
            url: WebSocket URL (ex: ws://hub-ip:8000/ws/bot-v2)
            token: ORACLE_TOKEN para autenticação
            instance_id: ID desta instância
            reconnect_interval: Segundos entre tentativas de reconexão
            on_command: Callback async para comandos recebidos do Hub
        """
        self.url = url
        self.token = token
        self.instance_id = instance_id
        self.reconnect_interval = reconnect_interval
        self.on_command = on_command

        self._ws = None
        self._connected = False
        self._authenticated = False
        self._running = False
        self._receive_task = None

    # ═══════════════════════════════════════════════════════
    # Conexão
    # ═══════════════════════════════════════════════════════

    async def connect(self) -> bool:
        """
        Conecta ao Hub e autentica.
        Returns True se conectou e autenticou com sucesso.
        """
        try:
            import websockets
        except ImportError:
            logger.error("websockets lib not installed: pip install websockets")
            return False

        try:
            self._ws = await websockets.connect(
                self.url,
                ping_interval=30,
                ping_timeout=10,
                close_timeout=5,
            )
            self._connected = True
            logger.info(f"Connected to Hub: {self.url}")

            # Auth handshake
            auth_msg = json.dumps({
                "type": "auth",
                "id": f"auth-{self.instance_id}",
                "payload": {
                    "token": self.token,
                    "role": "bot",
                    "instance_id": self.instance_id,
                }
            })
            await self._ws.send(auth_msg)

            # Espera resposta
            raw = await asyncio.wait_for(self._ws.recv(), timeout=5)
            resp = json.loads(raw)

            if resp.get("payload", {}).get("status") == "authenticated":
                self._authenticated = True
                logger.info("Hub auth OK")

                # Inicia listener de comandos
                self._running = True
                self._receive_task = asyncio.create_task(self._receive_loop())
                return True
            else:
                logger.error(f"Hub auth failed: {resp}")
                await self._ws.close()
                self._connected = False
                return False

        except Exception as e:
            logger.error(f"Hub connect failed: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Desconecta do Hub."""
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._connected = False
        self._authenticated = False
        logger.info("Disconnected from Hub")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._authenticated

    # ═══════════════════════════════════════════════════════
    # Envio de dados
    # ═══════════════════════════════════════════════════════

    async def send_telemetry(self, data: dict) -> bool:
        """
        Envia telemetria para o Hub.

        Args:
            data: Dict com balance, equity, status, open_positions, etc.

        Returns:
            True se enviou com sucesso.
        """
        return await self._send({
            "type": "telemetry",
            "id": f"tel-{int(time.time())}",
            "payload": data,
        })

    async def send_signal(self, signal_data: dict) -> bool:
        """
        Envia sinal de trading para o Hub.

        Args:
            signal_data: Dict com symbol, direction, action, intensity, etc.
        """
        return await self._send({
            "type": "signal",
            "id": f"sig-{int(time.time())}",
            "payload": signal_data,
        })

    async def send_ack(self, ref_id: str, status: str, result: dict = None) -> bool:
        """Envia ack de resposta a um comando."""
        return await self._send({
            "type": "ack",
            "payload": {
                "ref_id": ref_id,
                "status": status,
                "result": result or {},
            }
        })

    # ═══════════════════════════════════════════════════════
    # Internals
    # ═══════════════════════════════════════════════════════

    async def _send(self, data: dict) -> bool:
        """Envia JSON para o Hub."""
        if not self.is_connected:
            return False
        try:
            await self._ws.send(json.dumps(data))
            return True
        except Exception as e:
            logger.warning(f"Hub send failed: {e}")
            self._connected = False
            return False

    async def _receive_loop(self):
        """Loop que escuta mensagens do Hub (comandos)."""
        try:
            while self._running and self._ws:
                try:
                    raw = await self._ws.recv()
                    data = json.loads(raw)

                    msg_type = data.get("type")

                    if msg_type == "command" and self.on_command:
                        # Executa callback de comando
                        cmd_id = data.get("id", "")
                        payload = data.get("payload", {})
                        action = payload.get("action", "")

                        logger.info(f"Command received: {action} (id={cmd_id})")

                        try:
                            result = await self.on_command(action, payload.get("params", {}))
                            await self.send_ack(cmd_id, "success", result)
                        except Exception as e:
                            logger.error(f"Command handler error: {e}")
                            await self.send_ack(cmd_id, "error", {"message": str(e)})

                    elif msg_type == "ack":
                        # Ack de telemetria/signal — silencioso
                        pass

                except Exception as e:
                    if self._running:
                        logger.warning(f"Hub receive error: {e}")
                    break

        except asyncio.CancelledError:
            pass
        finally:
            self._connected = False

    async def reconnect_loop(self):
        """
        Loop de reconexão automática.
        Chame como task no orchestrator:
            asyncio.create_task(hub.reconnect_loop())
        """
        while self._running:
            if not self.is_connected:
                logger.info(f"Reconnecting to Hub in {self.reconnect_interval}s...")
                await asyncio.sleep(self.reconnect_interval)
                await self.connect()
            else:
                await asyncio.sleep(self.reconnect_interval)
