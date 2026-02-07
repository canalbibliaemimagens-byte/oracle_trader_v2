"""
Oracle Trader v2.0 — Orchestrator
===================================

Coordena todos os módulos: Connector, Preditor, Executor, Paper, Persistence.
Ponto de entrada principal do sistema.

Sequência de bootstrap (ordem importa!):
  1. Config  →  2. Persistence  →  3. Preditor  →  4. Connector
  5. Executor →  6. Paper       →  7. Sync      →  8. Warmup
  9. Session →  10. Tasks

NOTA: Executor (5) vem DEPOIS do Connector (4) porque precisa dele
no construtor. Difere da spec original mas é a ordem correta.
"""

import asyncio
import logging
import signal as signal_mod
import time
from pathlib import Path
from typing import List, Optional

from ..core.models import Bar, Signal
from ..persistence.session_manager import SessionEndReason
from .health import HealthMonitor
from .lifecycle import load_config, setup_logging

logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """
    Coordena todos os módulos do sistema.
    Roda como um único processo Python assíncrono.
    """

    def __init__(self, config_path: str = "config/default.yaml"):
        self.config_path = config_path
        self.config: dict = {}

        # Módulos (inicializados em start)
        self.connector = None
        self.preditor = None
        self.executor = None
        self.paper = None
        self.persistence = None
        self.session_manager = None
        self.trade_logger = None
        self.health: Optional[HealthMonitor] = None
        self.hub_client = None  # HubClient para OTS Hub

        # Estado
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: List[asyncio.Task] = []

    async def start(self):
        """Inicia o sistema completo."""
        logger.info("=" * 60)
        logger.info("  ORACLE TRADER v2.0")
        logger.info("=" * 60)

        try:
            # 1. Config
            self.config = load_config(self.config_path)
            setup_logging(self.config)
            logger.info("✓ Config carregada")

            # 2. Persistence
            await self._init_persistence()
            logger.info("✓ Persistence inicializado")

            # 3. Preditor
            await self._init_preditor()
            models = self.preditor.list_models()
            logger.info(f"✓ Preditor inicializado ({len(models)} modelos)")

            # 4. Connector (precisa estar ativo antes do Executor)
            await self._init_connector()
            logger.info("✓ Connector conectado")

            # 5. Executor
            await self._init_executor()
            logger.info("✓ Executor inicializado")

            # 6. Paper Trader
            await self._init_paper()
            logger.info("✓ Paper Trader inicializado")

            # 7. Sincroniza estado inicial
            await self._sync_initial_state()
            logger.info("✓ Estado sincronizado")

            # 8. Warmup modelos
            await self._warmup_models()
            logger.info("✓ Warmup concluído")

            # 9. Inicia Session
            initial_balance = self.config.get("initial_balance", 10000)
            session_id = await self.session_manager.start_session(
                initial_balance=initial_balance,
                symbols=models,
            )
            self.trade_logger.session_id = session_id
            logger.info(f"✓ Sessão iniciada: {session_id}")

            # 9b. Hub Client
            await self._init_hub_client()

            # 10. Health + Tasks
            self.health = HealthMonitor(self)
            self.running = True
            await self._start_tasks()

            logger.info("=" * 60)
            logger.info("  Sistema PRONTO")
            logger.info("=" * 60)

            # Aguarda shutdown
            await self._shutdown_event.wait()

        except Exception as e:
            logger.error(f"Erro fatal: {e}", exc_info=True)
            raise
        finally:
            await self.stop()

    async def stop(self, reason: SessionEndReason = SessionEndReason.NORMAL):
        """Para o sistema de forma limpa."""
        if not self.running:
            return

        logger.info("Encerrando sistema...")
        self.running = False

        # 1. Cancela tasks
        for task in self._tasks:
            task.cancel()

        # 2. Fecha posições se configurado
        if self.config.get("close_on_exit", False) and self.executor:
            closed = await self.executor.close_all()
            logger.info(f"✓ {closed} posições fechadas")

        # 3. Encerra sessão
        if self.session_manager:
            stats = await self._get_session_stats()
            await self.session_manager.end_session(stats, reason)
            logger.info("✓ Sessão encerrada")

        # 4. Desconecta broker
        if self.connector:
            await self.connector.disconnect()
            logger.info("✓ Connector desconectado")

        # 5. Desconecta Hub
        if self.hub_client:
            await self.hub_client.disconnect()
            logger.info("✓ Hub Client desconectado")

        logger.info("Sistema encerrado")

    # =====================================================================
    # Tasks assíncronas
    # =====================================================================

    async def _start_tasks(self):
        """Inicia todas as tasks."""
        self._tasks = [
            asyncio.create_task(self._main_loop()),
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._health_loop()),
            asyncio.create_task(self._persistence_retry_loop()),
            asyncio.create_task(self._spread_update_loop()),
            asyncio.create_task(self._hub_reconnect_loop()),
        ]

    async def _main_loop(self):
        """Loop principal — assina barras e processa sinais."""
        symbols = self.preditor.list_models()
        timeframe = self.config.get("timeframe", "M15")

        async def on_bar(bar: Bar):
            if not self.running:
                return
            await self._process_bar(bar)

        # Assina barras
        await self.connector.subscribe_bars(
            symbols=symbols,
            timeframe=timeframe,
            callback=on_bar,
        )

        # Mantém vivo
        while self.running:
            await asyncio.sleep(1)

    async def _process_bar(self, bar: Bar):
        """Processa uma nova barra: Preditor → Signal → Executor + Paper."""
        symbol = bar.symbol

        try:
            # 1. Preditor gera sinal
            signal_obj = self.preditor.process_bar(symbol, bar)

            if signal_obj is None:
                return  # Ainda em warmup

            # 2. Executor (real)
            executor_task = asyncio.create_task(
                self.executor.process_signal(signal_obj)
            )

            # 3. Paper (simulado, em paralelo)
            paper_trade = self.paper.process_signal(signal_obj, bar)

            # 4. Aguarda executor
            ack = await executor_task

            # 5. Loga paper trade
            if paper_trade and self.trade_logger:
                await self.trade_logger.log_paper_trade(paper_trade)

            # 6. Log
            logger.info(
                f"[{symbol}] {signal_obj.action} | "
                f"HMM:{signal_obj.hmm_state} | "
                f"VPnL:${signal_obj.virtual_pnl:.2f} | "
                f"Exec:{ack.status}"
            )

            # 7. Health
            if self.health:
                self.health.update(symbol)

        except Exception as e:
            logger.error(f"[{symbol}] Erro processando barra: {e}", exc_info=True)

    async def _heartbeat_loop(self):
        """
        Telemetria híbrida:
        - Com posições: 1s (PnL flutuante live)
        - Sem posições: 30s (heartbeat)
        """
        while self.running:
            try:
                positions = []
                if self.connector:
                    positions = await self.connector.get_positions()

                # Intervalo dinâmico
                interval = 1 if positions else 30

                if self.session_manager and self.connector:
                    account = await self.connector.get_account()
                    self.session_manager.update_heartbeat(account.balance)

                    if self.session_manager.check_day_boundary():
                        logger.info("Virada de dia detectada")
                        await self._handle_day_change()

                # Publica telemetria no Hub
                if self.hub_client and self.hub_client.is_connected:
                    telemetry = await self._build_telemetry(positions)
                    await self.hub_client.send_telemetry(telemetry)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.warning(f"Heartbeat erro: {e}")
                await asyncio.sleep(5)

    async def _health_loop(self):
        """Health check periódico (30s)."""
        while self.running:
            await asyncio.sleep(30)
            if self.health:
                report = self.health.check()
                if not report["healthy"]:
                    logger.warning(f"Health: {report['issues']}")

    async def _persistence_retry_loop(self):
        """Retry de pendências do Supabase (5min)."""
        while self.running:
            await asyncio.sleep(300)
            if self.persistence:
                await self.persistence.retry_pending()

    async def _spread_update_loop(self):
        """
        Atualiza spreads no RiskGuard periodicamente (30s).

        Consulta symbol_info do Connector para cada símbolo ativo
        e alimenta o cache de spreads do RiskGuard. Sem isso, o
        _check_spread opera em modo fail-open (permite tudo).
        """
        while self.running:
            await asyncio.sleep(30)
            if not self.executor or not self.executor.risk_guard:
                continue
            try:
                for symbol in self.preditor.list_models():
                    info = await self.connector.get_symbol_info(symbol)
                    if info and "spread_points" in info:
                        point = info.get("point", 0.00001)
                        # Converte spread em points para pips (1 pip = 10 points)
                        spread_pips = info["spread_points"] * point * 10000
                        if "JPY" in symbol:
                            spread_pips = info["spread_points"] * point * 100
                        self.executor.risk_guard.update_spread(symbol, spread_pips)
            except Exception as e:
                logger.debug(f"Spread update erro: {e}")

    async def _handle_day_change(self):
        """Trata virada de dia."""
        if self.config.get("close_on_day_change", False) and self.executor:
            await self.executor.close_all()
            stats = await self._get_session_stats()
            await self.session_manager.end_session(stats, SessionEndReason.DAY_CHANGE)

            account = await self.connector.get_account()
            await self.session_manager.start_session(
                initial_balance=account.balance,
                symbols=self.preditor.list_models(),
            )

    async def _build_telemetry(self, positions: list) -> dict:
        """Monta payload de telemetria para o Hub."""
        account = await self.connector.get_account() if self.connector else None
        floating_pnl = sum(p.pnl for p in positions)

        return {
            "balance": account.balance if account else 0,
            "equity": account.equity if account else 0,
            "floating_pnl": floating_pnl,
            "status": "RUNNING" if self.running else "STOPPED",
            "open_positions": [
                {
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "volume": p.volume,
                    "pnl": p.pnl,
                    "open_price": p.open_price,
                    "current_price": p.current_price,
                }
                for p in positions
            ],
            "timestamp": time.time(),
        }

    async def _hub_reconnect_loop(self):
        """Reconexão automática ao Hub."""
        while self.running:
            await asyncio.sleep(15)
            if self.hub_client and not self.hub_client.is_connected:
                logger.info("Reconectando ao Hub...")
                await self.hub_client.connect()

    async def _init_hub_client(self):
        """Inicializa conexão com OTS Hub se configurado."""
        hub_cfg = self.config.get("hub", {})
        if not hub_cfg.get("enabled", False):
            logger.info("✗ Hub desabilitado")
            return

        from ..connector.hub_client import HubClient

        self.hub_client = HubClient(
            url=hub_cfg.get("url", "ws://localhost:8000/ws/bot-v2"),
            token=hub_cfg.get("token", ""),
            instance_id=hub_cfg.get("instance_id", "bot-v2"),
            on_command=self._handle_hub_command,
        )
        if await self.hub_client.connect():
            logger.info("✓ Hub Client conectado")
        else:
            logger.warning("✗ Hub: falha na conexão")

    async def _handle_hub_command(self, action: str, params: dict) -> dict:
        """Processa comandos do Hub."""
        logger.info(f"Hub command: {action}")
        if action == "pause":
            self.running = False
            return {"message": "paused"}
        elif action == "resume":
            self.running = True
            return {"message": "resumed"}
        elif action == "close_all":
            closed = await self.executor.close_all() if self.executor else 0
            return {"closed": closed}
        elif action == "status":
            return self.health.check() if self.health else {}
        return {"error": f"unknown: {action}"}

    # =====================================================================
    # Inicialização dos módulos
    # =====================================================================

    async def _init_persistence(self):
        from ..persistence import SupabaseClient, SessionManager, TradeLogger

        self.persistence = SupabaseClient(
            url=self.config.get("supabase_url", ""),
            key=self.config.get("supabase_key", ""),
            enabled=self.config.get("persistence_enabled", True),
        )
        self.session_manager = SessionManager(self.persistence)
        self.trade_logger = TradeLogger(self.persistence, "")

    async def _init_preditor(self):
        from ..preditor import Preditor

        self.preditor = Preditor()
        models_dir = Path(
            self.config.get("preditor", {}).get("models_dir", "./models")
        )
        if models_dir.exists():
            for model_file in sorted(models_dir.glob("*.zip")):
                self.preditor.load_model(str(model_file))

    async def _init_connector(self):
        broker_cfg = self.config.get("broker", {})
        broker_type = broker_cfg.get("type", "mock")

        if broker_type == "ctrader":
            from ..connector.ctrader import CTraderConnector

            self.connector = CTraderConnector(broker_cfg)
        else:
            from ..connector.mock import MockConnector

            self.connector = MockConnector(broker_cfg)

        connected = await self.connector.connect()
        if not connected:
            raise RuntimeError("Falha ao conectar ao broker")

    async def _init_executor(self):
        from ..executor import Executor

        config_file = self.config.get("executor", {}).get(
            "config_file", "./config/executor_symbols.json"
        )
        self.executor = Executor(
            connector=self.connector,
            config_path=config_file,
        )

    async def _init_paper(self):
        from ..paper import PaperTrader

        self.paper = PaperTrader(
            initial_balance=self.config.get("initial_balance", 10000)
        )
        for symbol in self.preditor.list_models():
            model = self.preditor.models.get(symbol)
            if model and hasattr(model, "metadata"):
                training_cfg = model.metadata.get("training_config", {})
                self.paper.load_config(symbol, training_cfg)

    async def _sync_initial_state(self):
        """Verifica posições abertas no broker."""
        positions = await self.connector.get_positions()
        models = self.preditor.list_models()
        for pos in positions:
            if pos.symbol in models:
                logger.info(
                    f"[{pos.symbol}] Posição existente: "
                    f"dir={pos.direction} vol={pos.volume} @ {pos.open_price}"
                )
            else:
                logger.warning(f"[{pos.symbol}] Posição ÓRFÃ (sem modelo)")

    async def _warmup_models(self):
        """Warmup dos modelos com histórico."""
        warmup_bars = self.config.get("preditor", {}).get("warmup_bars", 1000)
        for symbol in self.preditor.list_models():
            model = self.preditor.models.get(symbol)
            timeframe = "M15"
            if model and hasattr(model, "metadata"):
                timeframe = model.metadata.get("symbol", {}).get(
                    "timeframe", "M15"
                )
            try:
                bars = await self.connector.get_history(
                    symbol, timeframe, warmup_bars
                )
                self.preditor.warmup(symbol, bars)
                logger.info(f"[{symbol}] Warmup: {len(bars)} barras")
            except Exception as e:
                logger.error(f"[{symbol}] Warmup falhou: {e}")

    async def _get_session_stats(self) -> dict:
        """Coleta estatísticas da sessão."""
        stats = {"balance": 0, "total_trades": 0, "total_pnl": 0}
        try:
            if self.connector:
                account = await self.connector.get_account()
                stats["balance"] = account.balance
            if self.paper:
                metrics = self.paper.get_metrics()
                stats["total_trades"] = metrics.get("total_trades", 0)
                stats["total_pnl"] = metrics.get("total_pnl", 0)
        except Exception:
            pass
        return stats

    # =====================================================================
    # Signal Handlers
    # =====================================================================

    def setup_signal_handlers(self):
        """Configura handlers para SIGINT/SIGTERM."""
        loop = asyncio.get_event_loop()
        for sig in (signal_mod.SIGINT, signal_mod.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._handle_signal()),
            )

    async def _handle_signal(self):
        logger.info("Sinal de encerramento recebido")
        self._shutdown_event.set()
