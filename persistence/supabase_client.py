"""
Oracle Trader v2.0 — Supabase Client
======================================

Cliente assíncrono para Supabase com fila de retry.
Nunca bloqueia o trading — falhas são enfileiradas para reenvio.
"""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Persistence.Supabase")


class SupabaseClient:
    """
    Cliente assíncrono para Supabase.
    Implementa fila de retry para resiliência.
    """

    def __init__(self, url: str = "", key: str = "", enabled: bool = True):
        self.url = url
        self.key = key
        self.enabled = enabled and bool(url) and bool(key)
        self.client = None
        self._retry_queue: deque = deque(maxlen=1000)
        self._connected = False

        if self.enabled:
            self._init_client()

    def _init_client(self):
        """Inicializa cliente Supabase."""
        try:
            from supabase import create_client

            self.client = create_client(self.url, self.key)
            self._connected = True
            logger.info("Supabase conectado")
        except Exception as e:
            logger.error(f"Supabase init erro: {e}")
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self.client is not None

    async def _execute(
        self, table: str, data: dict, operation: str = "insert"
    ) -> bool:
        """
        Executa operação com fallback para retry queue.

        Returns:
            True se sucesso.
        """
        if not self.enabled or not self.client:
            return False

        try:
            if operation == "insert":
                await asyncio.to_thread(
                    lambda: self.client.table(table).insert(data).execute()
                )
            elif operation == "upsert":
                await asyncio.to_thread(
                    lambda: self.client.table(table).upsert(data).execute()
                )
            elif operation == "update":
                filter_key = data.get("_filter_key")
                filter_val = data.get("_filter_val")
                clean_data = {
                    k: v for k, v in data.items() if not k.startswith("_filter")
                }
                if filter_key and filter_val:
                    await asyncio.to_thread(
                        lambda: self.client.table(table)
                        .update(clean_data)
                        .eq(filter_key, filter_val)
                        .execute()
                    )
            return True
        except Exception as e:
            logger.warning(f"Supabase {operation} falhou ({table}): {e}")
            self._retry_queue.append(
                {
                    "table": table,
                    "data": data,
                    "operation": operation,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            return False

    async def _query(
        self,
        table: str,
        select: str = "*",
        filters: Optional[Dict] = None,
        order: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """Executa query com filtros."""
        if not self.enabled or not self.client:
            return []

        try:
            query = self.client.table(table).select(select)

            if filters:
                for key, value in filters.items():
                    if isinstance(value, tuple):
                        op, val = value
                        getattr(query, op)(key, val)
                    else:
                        query = query.eq(key, value)

            if order:
                desc = order.startswith("-")
                field = order[1:] if desc else order
                query = query.order(field, desc=desc)

            if limit:
                query = query.limit(limit)

            response = await asyncio.to_thread(lambda: query.execute())
            return response.data or []
        except Exception as e:
            logger.error(f"Supabase query erro ({table}): {e}")
            return []

    async def log_trade(self, trade_data: dict):
        """
        Insere trade na tabela 'trades'.

        Aceita qualquer dict — garante campos mínimos com defaults.
        Campos extras no dict são ignorados pelo Supabase.
        """
        required_defaults = {
            "session_id": "",
            "trade_id": "",
            "symbol": "",
            "direction": 0,
            "intensity": 0,
            "action": "",
            "volume": 0,
            "entry_price": 0,
            "exit_price": 0,
            "pnl": 0,
            "pnl_pips": 0,
            "commission": 0,
            "hmm_state": 0,
            "is_paper": False,
            "comment": "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        # Merge: defaults ← trade_data (trade_data vence)
        data = {**required_defaults, **{k: v for k, v in trade_data.items() if k in required_defaults}}
        # Garante que 'id' vira 'trade_id'
        if "id" in trade_data and not data.get("trade_id"):
            data["trade_id"] = trade_data["id"]
        await self._execute("trades", data)

    async def log_event(
        self, event_type: str, data: Optional[dict] = None, session_id: str = ""
    ):
        """Insere evento na tabela 'events'."""
        record = {
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "data": json.dumps(data or {}),
        }
        await self._execute("events", record)

    async def get_trades(
        self,
        session_id: Optional[str] = None,
        is_paper: Optional[bool] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Query trades com filtros."""
        filters = {}
        if session_id:
            filters["session_id"] = session_id
        if is_paper is not None:
            filters["is_paper"] = is_paper
        if symbol:
            filters["symbol"] = symbol
        return await self._query("trades", filters=filters, order="-timestamp", limit=limit)

    async def retry_pending(self) -> int:
        """Tenta reenviar operações pendentes. Retorna número de sucessos."""
        if not self._retry_queue:
            return 0

        success = 0
        failed = []

        while self._retry_queue:
            item = self._retry_queue.popleft()
            try:
                if item["operation"] == "insert":
                    await asyncio.to_thread(
                        lambda t=item["table"], d=item["data"]: self.client.table(t)
                        .insert(d)
                        .execute()
                    )
                success += 1
            except Exception:
                failed.append(item)

        for item in failed:
            self._retry_queue.append(item)

        if success > 0:
            logger.info(
                f"Retry: {success} OK, {len(failed)} pendentes"
            )
        return success

    @property
    def pending_count(self) -> int:
        return len(self._retry_queue)
