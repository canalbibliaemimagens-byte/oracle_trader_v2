"""
OTS Hub — Main Application

FastAPI server com WebSocket (auth obrigatória) e REST endpoints.
"""

import asyncio
import json
import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.websockets.manager import manager
from app.websockets.router import route_message
from app.modules.telemetry.service import telemetry_store
from app.modules.commands.service import command_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hub")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
)

# CORS
if settings.ALLOWED_ORIGINS:
    origins = (
        [str(o) for o in settings.ALLOWED_ORIGINS]
        if isinstance(settings.ALLOWED_ORIGINS, list)
        else ["*"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ═══════════════════════════════════════════════════════════
# REST Endpoints
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "service": "OTS Hub",
        "version": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "connections": manager.count,
        "authenticated": manager.authenticated_count,
        "uptime_s": round(time.time() - _start_time, 0),
    }


@app.get(f"{settings.API_V1_STR}/status")
async def status():
    """Status detalhado para dashboard."""
    return {
        "connections": manager.list_connections(),
        "telemetry": telemetry_store.get_all_latest(),
        "active_instances": telemetry_store.get_connected_instances(),
        "pending_commands": command_router.get_pending(),
    }


@app.get(f"{settings.API_V1_STR}/telemetry/{{instance_id}}")
async def get_telemetry(instance_id: str):
    """Retorna última telemetria de uma instância."""
    data = telemetry_store.get_latest(instance_id)
    if not data:
        return {"error": "not found"}
    return data


@app.post(f"{settings.API_V1_STR}/command")
async def send_command(body: dict):
    """
    Envia comando para um bot via REST.
    Body: {"target": "bot-id", "action": "pause", "params": {}, "token": "..."}
    """
    token = body.get("token", "")
    from app.modules.auth.service import validate_token
    if not validate_token(token):
        return {"error": "unauthorized"}

    target = body.get("target")
    action = body.get("action")
    params = body.get("params", {})

    if not target or not action:
        return {"error": "target and action required"}

    cmd = command_router.create_command(action, target, "rest-api", params)
    if not cmd:
        return {"error": f"invalid action: {action}"}

    sent = await manager.send(target, json.dumps(cmd))
    return {
        "status": "sent" if sent else "bot_not_connected",
        "cmd_id": cmd["id"],
    }


# ═══════════════════════════════════════════════════════════
# WebSocket Endpoint
# ═══════════════════════════════════════════════════════════

@app.websocket("/ws/{instance_id}")
async def websocket_endpoint(websocket: WebSocket, instance_id: str):
    """
    Endpoint WebSocket principal.
    """
    conn = await manager.connect(websocket, instance_id)

    try:
        # ── Auth Handshake (obrigatório) ──────────────────
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=settings.AUTH_TIMEOUT,
            )
            response = await route_message(raw, instance_id)
            if response:
                await websocket.send_text(response)

            if not manager.is_authenticated(instance_id):
                logger.warning(f"Auth failed for {instance_id}, closing")
                await websocket.close(code=4001, reason="Unauthorized")
                return

        except asyncio.TimeoutError:
            logger.warning(f"Auth timeout for {instance_id}")
            await websocket.close(code=4001, reason="Auth timeout")
            return

        # ── Message Loop ──────────────────────────────────
        while True:
            raw = await websocket.receive_text()
            response = await route_message(raw, instance_id)
            if response:
                await websocket.send_text(response)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Error with {instance_id}: {e}")
    finally:
        manager.disconnect(instance_id)
        telemetry_store.remove(instance_id)


# Startup timestamp
_start_time = time.time()


@app.on_event("startup")
async def startup():
    logger.info(f"OTS Hub v{settings.VERSION} starting on {settings.HOST}:{settings.PORT}")
    asyncio.create_task(_stale_connection_cleanup())


async def _stale_connection_cleanup():
    """
    Remove conexões stale com timeouts diferenciados por role.
    
    Bots enviam telemetria a cada 1-5s, então 5min sem mensagem é stale.
    Dashboards são interativos (clicam quando querem), 30min é razoável.
    """
    BOT_TIMEOUT = 300       # 5 min para bots
    DASH_TIMEOUT = 1800     # 30 min para dashboards/admins
    
    while True:
        await asyncio.sleep(60)  # Verifica a cada 60s
        now = time.time()

        stale = []
        for conn_info in manager.list_connections():
            last_msg = conn_info.get("last_message_at", 0)
            if last_msg <= 0:
                continue
            
            elapsed = now - last_msg
            role = conn_info.get("role", "bot")
            timeout = DASH_TIMEOUT if role in ("dashboard", "admin") else BOT_TIMEOUT
            
            if elapsed > timeout:
                stale.append(conn_info["instance_id"])

        for iid in stale:
            logger.warning(f"Removing stale connection: {iid}")
            manager.disconnect(iid)


@app.on_event("shutdown")
async def shutdown():
    logger.info("OTS Hub shutting down")
