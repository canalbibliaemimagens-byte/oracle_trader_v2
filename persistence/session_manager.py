"""
Oracle Trader v2.0 — Session Manager
======================================

Gerencia ciclo de vida da sessão: start, heartbeat, recovery de crash,
detecção de virada de dia, e shutdown.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("Persistence.Session")


class SessionEndReason(Enum):
    """Motivos de encerramento de sessão."""
    NORMAL = "NORMAL"
    EMERGENCY = "EMERGENCY"
    DAY_CHANGE = "DAY_CHANGE"
    RECOVERED = "RECOVERED"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class SessionManager:
    """Gerencia estado da sessão com heartbeat e recuperação."""

    STATE_FILE = ".session_state.json"

    def __init__(self, supabase_client, base_dir: Optional[Path] = None):
        self.db = supabase_client
        self.base_dir = base_dir or Path.cwd()
        self.state_file = self.base_dir / self.STATE_FILE

        self.session_id: str = ""
        self.start_time: Optional[datetime] = None
        self.is_recovered: bool = False
        self.day_start: Optional[datetime] = None

        self._running = False

    async def start_session(
        self, initial_balance: float, symbols: list
    ) -> str:
        """
        Inicia ou recupera sessão.

        Returns:
            session_id (novo ou recuperado)
        """
        # Verifica sessão anterior não fechada
        recovered_state = self._load_state()

        if recovered_state and recovered_state.get("status") == "RUNNING":
            self.session_id = recovered_state.get("session_id", "")
            self.is_recovered = True
            self.start_time = datetime.now(timezone.utc)
            self._running = True

            await self.db.log_event(
                "SESSION_RECOVERED",
                {"old_session_id": self.session_id},
                self.session_id,
            )
            logger.info(f"Sessão recuperada: {self.session_id}")
            return self.session_id

        # Nova sessão
        self.session_id = str(uuid.uuid4())[:8]
        self.start_time = datetime.now(timezone.utc)
        self.day_start = self._get_day_start()
        self.is_recovered = False
        self._running = True

        self._save_state(
            {
                "session_id": self.session_id,
                "start_time": self.start_time.isoformat(),
                "initial_balance": initial_balance,
                "symbols": symbols,
                "status": "RUNNING",
            }
        )

        await self.db._execute(
            "sessions",
            {
                "session_id": self.session_id,
                "start_time": self.start_time.isoformat(),
                "initial_balance": initial_balance,
                "symbols": symbols,
                "status": "RUNNING",
            },
        )

        logger.info(f"Nova sessão: {self.session_id}")
        return self.session_id

    async def end_session(
        self,
        stats: dict,
        reason: SessionEndReason = SessionEndReason.NORMAL,
    ):
        """Encerra sessão com estatísticas."""
        if not self._running:
            return

        self._running = False

        update_data = {
            "end_time": datetime.now(timezone.utc).isoformat(),
            "final_balance": stats.get("balance", 0),
            "total_trades": stats.get("total_trades", 0),
            "total_pnl": stats.get("total_pnl", 0),
            "end_reason": reason.value,
            "status": "STOPPED",
            "_filter_key": "session_id",
            "_filter_val": self.session_id,
        }

        try:
            await self.db._execute("sessions", update_data, operation="update")
        except Exception as e:
            logger.error(f"Erro ao encerrar sessão no Supabase: {e}")

        self._clear_state()
        logger.info(f"Sessão encerrada: {self.session_id} ({reason.value})")

    def update_heartbeat(self, balance: float = 0):
        """Atualiza heartbeat (chamar periodicamente)."""
        if not self._running:
            return

        state = self._load_state() or {}
        state.update(
            {
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "current_balance": balance,
                "status": "RUNNING",
            }
        )
        self._save_state(state)

    def check_day_boundary(self) -> bool:
        """Verifica se virou o dia (UTC)."""
        if not self.day_start:
            self.day_start = self._get_day_start()
            return False

        current_day = self._get_day_start()
        if current_day > self.day_start:
            self.day_start = current_day
            return True
        return False

    def _save_state(self, state: dict):
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception:
            pass

    def _load_state(self) -> Optional[dict]:
        if not self.state_file.exists():
            return None
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _clear_state(self):
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass

    @staticmethod
    def _get_day_start() -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
