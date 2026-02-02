"""
Oracle Trader v2 - WebSocket Server

Servidor WebSocket para comunicação com Dashboard e ferramentas externas.

Funcionalidades:
- Broadcast de estado em tempo real
- Recepção e processamento de comandos
- Integração com Engine via callbacks

Mensagens enviadas (Server → Client):
- full_state: Estado completo do sistema
- tick: Atualização periódica (a cada segundo)
- trade: Quando abre/fecha posição
- event: Eventos do sistema (SL_PROTECTION, TP_GLOBAL, etc.)
- log: Mensagens de log
- response: Resposta a comandos

Mensagens recebidas (Client → Server):
- GET_STATE, PAUSE, RESUME, CLOSE_ALL, etc.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Set, Dict, Any, Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from core.engine import OracleEngine

logger = logging.getLogger("OracleTrader.WebSocket")

# Tenta importar websockets
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    WebSocketServerProtocol = Any


class WebSocketServer:
    """
    Servidor WebSocket para comunicação com Dashboard.
    
    Uso com Engine:
        ws_server = WebSocketServer(host, port)
        ws_server.set_engine(engine)
        await ws_server.start()
        
    Uso standalone (callbacks manuais):
        ws_server = WebSocketServer(host, port)
        ws_server.on_command = my_command_handler
        ws_server.get_state = my_state_getter
        await ws_server.start()
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        """
        Args:
            host: Endereço para bind
            port: Porta para bind
        """
        self.host = host
        self.port = port
        self.clients: Set[WebSocketServerProtocol] = set()
        self.server = None
        
        # Referência ao Engine (opcional)
        self._engine: Optional['OracleEngine'] = None
        
        # Callbacks manuais (usados se engine não estiver configurado)
        self.on_command: Optional[Callable] = None
        self.get_state: Optional[Callable] = None
    
    def set_engine(self, engine: 'OracleEngine') -> None:
        """
        Conecta o WebSocket ao Engine.
        
        Configura callbacks automaticamente.
        """
        self._engine = engine
        
        # Configura callbacks do engine para broadcast
        engine.on_trade = self._on_trade_callback
        engine.on_event = self._on_event_callback
        engine.on_tick = self._on_tick_callback
        
        logger.info("WebSocket conectado ao Engine")
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> bool:
        """
        Inicia o servidor WebSocket.
        
        Returns:
            True se iniciou com sucesso
        """
        if not HAS_WEBSOCKETS:
            logger.warning("websockets não instalado (pip install websockets)")
            return False
        
        try:
            self.server = await websockets.serve(
                self._handle_client,
                self.host,
                self.port,
                ping_interval=30,
                ping_timeout=10,
            )
            logger.info(f"WebSocket Server: ws://{self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Falha ao iniciar WebSocket: {e}")
            return False
    
    async def stop(self) -> None:
        """Para o servidor WebSocket."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            logger.info("WebSocket Server parado")
    
    @property
    def is_running(self) -> bool:
        """Retorna True se servidor está rodando."""
        return self.server is not None
    
    @property
    def client_count(self) -> int:
        """Número de clientes conectados."""
        return len(self.clients)
    
    # =========================================================================
    # Client Handling
    # =========================================================================
    
    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str = None) -> None:
        """
        Trata conexão de um cliente.
        
        - Envia estado inicial
        - Processa mensagens em loop
        - Remove cliente ao desconectar
        """
        client_id = id(websocket)
        self.clients.add(websocket)
        logger.info(f"WS Cliente conectado: {client_id} | Total: {len(self.clients)}")
        
        try:
            # Envia estado inicial
            await self._send_initial_state(websocket)
            
            # Loop de mensagens
            async for message in websocket:
                try:
                    response = await self._process_message(message)
                    if response:
                        await websocket.send(json.dumps(response))
                except Exception as e:
                    logger.error(f"Erro processando mensagem: {e}")
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": str(e),
                        "timestamp": self._timestamp(),
                    }))
        
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Erro WS cliente {client_id}: {e}")
        finally:
            self.clients.discard(websocket)
            logger.info(f"WS Cliente desconectado: {client_id} | Total: {len(self.clients)}")
    
    async def _send_initial_state(self, websocket: WebSocketServerProtocol) -> None:
        """Envia estado completo ao cliente recém-conectado."""
        state = self._get_full_state()
        if state:
            await websocket.send(json.dumps({
                "type": "full_state",
                "data": state,
                "timestamp": self._timestamp(),
            }))
    
    async def _process_message(self, message: str) -> Optional[dict]:
        """
        Processa mensagem recebida de um cliente.
        
        Returns:
            Resposta para enviar ao cliente
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return {"type": "error", "message": "JSON inválido"}
        
        cmd_type = data.get("type", "")
        
        # Comando GET_STATE é tratado localmente
        if cmd_type == "GET_STATE":
            state = self._get_full_state()
            if state:
                return {
                    "type": "full_state",
                    "data": state,
                    "timestamp": self._timestamp(),
                }
            return {"type": "error", "message": "Estado não disponível"}
        
        # Outros comandos são delegados ao handler
        return await self._handle_command(cmd_type, data)
    
    async def _handle_command(self, cmd: str, data: dict) -> dict:
        """
        Processa comando recebido.
        
        Tenta usar Engine primeiro, depois callback manual.
        """
        # Se tem Engine, usa o command handler integrado
        if self._engine:
            return await handle_command(self._engine, cmd, data)
        
        # Se tem callback manual, usa ele
        if self.on_command:
            return await self.on_command(cmd, data)
        
        return {
            "type": "response",
            "cmd": cmd,
            "status": "ERROR",
            "error": f"Comando desconhecido: {cmd}",
        }
    
    def _get_full_state(self) -> Optional[dict]:
        """Obtém estado completo do sistema."""
        if self._engine:
            return self._engine.get_full_state()
        if self.get_state:
            return self.get_state()
        return None
    
    # =========================================================================
    # Broadcast Methods
    # =========================================================================
    
    async def broadcast(self, message: dict) -> None:
        """
        Envia mensagem para todos os clientes conectados.
        
        Erros de envio individual são ignorados.
        """
        if not self.clients:
            return
        
        data = json.dumps(message)
        
        await asyncio.gather(
            *[self._safe_send(client, data) for client in self.clients],
            return_exceptions=True,
        )
    
    async def _safe_send(self, websocket: WebSocketServerProtocol, data: str) -> None:
        """Envia mensagem tratando erros silenciosamente."""
        try:
            await websocket.send(data)
        except Exception:
            pass
    
    async def broadcast_tick(self, data: dict) -> None:
        """Broadcast de atualização periódica."""
        await self.broadcast({
            "type": "tick",
            "data": data,
            "timestamp": self._timestamp(),
        })
    
    async def broadcast_trade(self, trade: dict) -> None:
        """Broadcast de abertura/fechamento de posição."""
        await self.broadcast({
            "type": "trade",
            "data": trade,
            "timestamp": self._timestamp(),
        })
    
    async def broadcast_event(self, event_type: str, data: dict) -> None:
        """Broadcast de evento do sistema."""
        await self.broadcast({
            "type": "event",
            "event": event_type,
            "data": data,
            "timestamp": self._timestamp(),
        })
    
    async def broadcast_log(self, level: str, message: str, symbol: str = None) -> None:
        """Broadcast de mensagem de log."""
        await self.broadcast({
            "type": "log",
            "level": level,
            "message": message,
            "symbol": symbol,
            "timestamp": self._timestamp(),
        })
    
    # =========================================================================
    # Engine Callbacks
    # =========================================================================
    
    async def _on_trade_callback(self, trade: dict) -> None:
        """Callback chamado pelo Engine quando há trade."""
        await self.broadcast_trade(trade)
    
    async def _on_event_callback(self, event_type: str, data: dict) -> None:
        """Callback chamado pelo Engine para eventos."""
        await self.broadcast_event(event_type, data)
    
    async def _on_tick_callback(self, tick_data: dict) -> None:
        """Callback chamado pelo Engine para ticks."""
        await self.broadcast_tick(tick_data)
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def _timestamp(self) -> float:
        """Retorna timestamp atual."""
        return datetime.now(timezone.utc).timestamp()


# =============================================================================
# Command Handler
# =============================================================================

# Comandos disponíveis
AVAILABLE_COMMANDS = {
    # Sistema
    "PAUSE": "Pausa o sistema",
    "RESUME": "Retoma o sistema",
    "EMERGENCY_STOP": "Fecha tudo e para",
    
    # Posições
    "CLOSE_ALL": "Fecha todas as posições",
    "CLOSE_POSITION": "Fecha posição de um símbolo (symbol)",
    
    # Símbolos
    "BLOCK_SYMBOL": "Bloqueia símbolo (symbol)",
    "UNBLOCK_SYMBOL": "Desbloqueia símbolo → Paper Trade (symbol)",
    "FORCE_NORMAL": "Força símbolo para NORMAL (symbol)",
    
    # Configuração
    "GET_CONFIG": "Retorna configuração atual",
    "SET_CONFIG": "Atualiza configuração (config: dict)",
    
    # Estado
    "GET_STATE": "Retorna estado completo",
    "GET_SYMBOL_STATE": "Retorna estado de um símbolo (symbol)",
    "GET_POSITIONS": "Retorna posições abertas",
    "GET_STATS": "Retorna estatísticas",
    
    # Modelos
    "LIST_MODELS": "Lista modelos carregados",
    "RELOAD_MODEL": "Recarrega modelo (symbol)",
    
    # Ajuda
    "GET_COMMANDS": "Lista comandos disponíveis",
}


async def handle_command(engine: 'OracleEngine', cmd: str, data: dict) -> dict:
    """
    Processa comando para o Engine.
    
    Args:
        engine: Instância do OracleEngine
        cmd: Nome do comando
        data: Dados do comando
        
    Returns:
        Resposta formatada
    """
    response = {
        "type": "response",
        "cmd": cmd,
        "status": "OK",
        "timestamp": datetime.now(timezone.utc).timestamp(),
    }
    
    try:
        # === Sistema ===
        if cmd == "PAUSE":
            engine.pause()
            response["message"] = "Sistema pausado"
        
        elif cmd == "RESUME":
            engine.resume()
            response["message"] = "Sistema retomado"
        
        elif cmd == "EMERGENCY_STOP":
            await engine._emergency_stop()
            response["message"] = "Emergency stop ativado"
        
        # === Posições ===
        elif cmd == "CLOSE_ALL":
            if engine.executor:
                results = await engine.executor.close_all_positions(
                    engine.symbols, 
                    engine.system, 
                    "WS_COMMAND"
                )
                response["message"] = f"Fechadas {len(results)} posições"
                response["results"] = results
            else:
                response["status"] = "ERROR"
                response["error"] = "Executor não disponível"
        
        elif cmd == "CLOSE_POSITION":
            symbol = data.get("symbol")
            if not symbol:
                response["status"] = "ERROR"
                response["error"] = "symbol não especificado"
            elif symbol not in engine.symbols:
                response["status"] = "ERROR"
                response["error"] = f"Símbolo {symbol} não encontrado"
            else:
                state = engine.symbols[symbol]
                if state.position.is_open and engine.executor:
                    await engine.executor._close_position(state, "WS_COMMAND", engine.system)
                    response["message"] = f"Posição {symbol} fechada"
                else:
                    response["message"] = f"{symbol} sem posição aberta"
        
        # === Símbolos ===
        elif cmd == "BLOCK_SYMBOL":
            symbol = data.get("symbol")
            if not symbol:
                response["status"] = "ERROR"
                response["error"] = "symbol não especificado"
            elif symbol not in engine.symbols:
                response["status"] = "ERROR"
                response["error"] = f"Símbolo {symbol} não encontrado"
            else:
                engine.state_machine.block_symbol(engine.symbols[symbol])
                response["message"] = f"{symbol} bloqueado"
                response["new_status"] = "BLOCKED"
        
        elif cmd == "UNBLOCK_SYMBOL":
            symbol = data.get("symbol")
            if not symbol:
                response["status"] = "ERROR"
                response["error"] = "symbol não especificado"
            elif symbol not in engine.symbols:
                response["status"] = "ERROR"
                response["error"] = f"Símbolo {symbol} não encontrado"
            else:
                engine.state_machine.unblock_symbol(engine.symbols[symbol])
                response["message"] = f"{symbol} desbloqueado → PAPER_TRADE"
                response["new_status"] = "PAPER_TRADE"
        
        elif cmd == "FORCE_NORMAL":
            symbol = data.get("symbol")
            if not symbol:
                response["status"] = "ERROR"
                response["error"] = "symbol não especificado"
            elif symbol not in engine.symbols:
                response["status"] = "ERROR"
                response["error"] = f"Símbolo {symbol} não encontrado"
            else:
                engine.state_machine.force_normal(engine.symbols[symbol])
                response["message"] = f"{symbol} forçado para NORMAL"
                response["new_status"] = "NORMAL"
        
        # === Configuração ===
        elif cmd == "GET_CONFIG":
            response["config"] = engine.config.to_dict()
        
        elif cmd == "SET_CONFIG":
            updates = data.get("config", {})
            if updates:
                engine.config_manager.update(updates)
                engine.config_manager.save()
                response["message"] = "Configuração atualizada"
                response["config"] = engine.config.to_dict()
            else:
                response["status"] = "ERROR"
                response["error"] = "config não especificado"
        
        # === Estado ===
        elif cmd == "GET_STATE":
            response["data"] = engine.get_full_state()
        
        elif cmd == "GET_SYMBOL_STATE":
            symbol = data.get("symbol")
            if not symbol:
                response["status"] = "ERROR"
                response["error"] = "symbol não especificado"
            elif symbol not in engine.symbols:
                response["status"] = "ERROR"
                response["error"] = f"Símbolo {symbol} não encontrado"
            else:
                response["symbol"] = engine.symbols[symbol].to_dict()
        
        elif cmd == "GET_POSITIONS":
            positions = {}
            for s, st in engine.symbols.items():
                if st.position.is_open:
                    positions[s] = {
                        "direction": st.position.direction_str,
                        "size": st.position.size,
                        "open_price": st.position.open_price,
                        "pnl": round(st.position.pnl, 2),
                        "pnl_pips": round(st.position.pnl_pips, 1),
                    }
            response["positions"] = positions
        
        elif cmd == "GET_STATS":
            response["stats"] = {
                "system": engine.system.get_summary_dict(),
                "symbols": {s: st.get_stats_dict() for s, st in engine.symbols.items()},
            }
        
        # === Modelos ===
        elif cmd == "LIST_MODELS":
            models = {}
            for s, st in engine.symbols.items():
                models[s] = {
                    "timeframe": st.config.timeframe if st.config else "?",
                    "status": st.status.value,
                    "n_states": st.config.n_states if st.config else 0,
                }
            response["models"] = models
        
        elif cmd == "RELOAD_MODEL":
            symbol = data.get("symbol")
            response["status"] = "ERROR"
            response["error"] = "Reload de modelo não implementado na v2"
        
        # === Ajuda ===
        elif cmd == "GET_COMMANDS":
            response["commands"] = AVAILABLE_COMMANDS
        
        # === Desconhecido ===
        else:
            response["status"] = "ERROR"
            response["error"] = f"Comando desconhecido: {cmd}"
    
    except Exception as e:
        response["status"] = "ERROR"
        response["error"] = str(e)
        logger.error(f"Erro no comando {cmd}: {e}")
    
    return response


def get_commands_help() -> dict:
    """Retorna lista de comandos disponíveis."""
    return AVAILABLE_COMMANDS
