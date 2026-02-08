"""
Oracle Trader v2.0 — Health Monitor
=====================================

Monitora saúde dos componentes: heartbeats por símbolo,
memória, pendências de persistência.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from .orchestrator import Orchestrator

logger = logging.getLogger("Health")


class HealthMonitor:
    """Monitora saúde dos componentes do sistema."""

    HEARTBEAT_TIMEOUT = 1200  # 20 min sem heartbeat → unhealthy (acomoda M15+delays)

    def __init__(self, orchestrator: "Orchestrator"):
        self.orchestrator = orchestrator
        self._symbol_heartbeats: Dict[str, float] = {}

    def update(self, symbol: str):
        """Atualiza heartbeat de um símbolo."""
        self._symbol_heartbeats[symbol] = time.time()

    def check(self) -> dict:
        """
        Verifica saúde do sistema.

        Returns:
            Dict com 'healthy' (bool), 'issues' (list), 'memory_mb' (float).
        """
        issues = []
        now = time.time()

        # Connector
        if (
            self.orchestrator.connector
            and not self.orchestrator.connector.is_connected()
        ):
            issues.append("Connector desconectado")

        # Heartbeats por símbolo
        for symbol, last_hb in self._symbol_heartbeats.items():
            elapsed = now - last_hb
            if elapsed > self.HEARTBEAT_TIMEOUT:
                issues.append(f"{symbol}: sem heartbeat há {int(elapsed)}s")

        # Memória
        memory_mb = self._get_memory_mb()
        if memory_mb > 1000:
            issues.append(f"Memória alta: {memory_mb:.0f}MB")

        # Persistência pendente
        if (
            self.orchestrator.persistence
            and self.orchestrator.persistence.pending_count > 100
        ):
            issues.append(
                f"Persistence: {self.orchestrator.persistence.pending_count} pendentes"
            )

        uptime = 0.0
        if (
            self.orchestrator.session_manager
            and self.orchestrator.session_manager.start_time
        ):
            uptime = now - self.orchestrator.session_manager.start_time.timestamp()

        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "memory_mb": round(memory_mb, 1),
            "uptime_s": round(uptime, 0),
        }

    def reset_symbol(self, symbol: str):
        """Reseta estado de um símbolo."""
        self._symbol_heartbeats.pop(symbol, None)

    @staticmethod
    def _get_memory_mb() -> float:
        """Retorna uso de memória do processo em MB."""
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1024 / 1024
        except ImportError:
            # Fallback Linux
            try:
                with open(f"/proc/{os.getpid()}/status") as f:
                    for line in f:
                        if line.startswith("VmRSS:"):
                            return int(line.split()[1]) / 1024
            except Exception:
                pass
        return 0.0
