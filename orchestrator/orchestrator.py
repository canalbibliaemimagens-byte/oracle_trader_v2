"""
Oracle Trader v2.0 — Orchestrator
===================================

Coordena todos os módulos: Connector, Preditor, Executor, Paper, Persistence.
Ponto de entrada principal do sistema.

Sequência de bootstrap (ordem importa!):
  1. Config  →  2. Persistence  →  3. Preditor  →  4. Connector
  5. Executor →  6. Paper       →  7. Sync      →  8. Warmup
  9. Session →  10. Tasks
"""

import asyncio
import json
import logging
import signal as signal_mod
import time
import os
import threading
from pathlib import Path
from typing import List, Optional

import yaml

from core.models import Bar, Signal
from persistence.session_manager import SessionEndReason
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
        self.hub_client = None

        # Estado
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: List[asyncio.Task] = []

    # =================================================================
    # Config helpers — leitura com paths corretos
    # =================================================================

    def _cfg(self, *keys, default=None):
        """
        Lê config com path aninhado.
        Exemplo: self._cfg("executor", "default_sl_usd", default=10.0)
        """
        node = self.config
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
            if node is None:
                return default
        return node

    def _executor_config_path(self) -> str:
        return self._cfg("executor", "config_file", default="./config/executor_symbols.json")

    # =================================================================
    # Config persistence — salva alterações nos arquivos
    # =================================================================

    def _save_yaml_config(self):
        """Persiste self.config no arquivo YAML (default.yaml)."""
        try:
            with open(self.config_path, "w") as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info(f"Config YAML salva: {self.config_path}")
        except Exception as e:
            logger.error(f"Falha ao salvar YAML: {e}")

    def _save_executor_json(self):
        """Persiste executor symbol_configs no JSON."""
        if not self.executor:
            return
        path = self._executor_config_path()
        try:
            # Carregar JSON existente para preservar _comment, _risk etc.
            existing = {}
            if Path(path).exists():
                with open(path) as f:
                    existing = json.load(f)

            # Atualizar apenas símbolos (preservar _keys)
            for symbol, cfg in self.executor.symbol_configs.items():
                existing[symbol] = {
                    "enabled": cfg.enabled,
                    "lot_weak": cfg.lot_weak,
                    "lot_moderate": cfg.lot_moderate,
                    "lot_strong": cfg.lot_strong,
                    "sl_usd": cfg.sl_usd,
                    "tp_usd": cfg.tp_usd,
                    "max_spread_pips": cfg.max_spread_pips,
                }

            with open(path, "w") as f:
                json.dump(existing, f, indent=4)
            logger.info(f"Config JSON salva: {path}")
        except Exception as e:
            logger.error(f"Falha ao salvar JSON: {e}")

    # =================================================================
    # Startup / Shutdown
    # =================================================================

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

            # 4. Connector
            await self._init_connector()
            logger.info("✓ Connector conectado")

            # 5. Executor (+ auto-create configs para modelos sem entry no JSON)
            await self._init_executor()
            logger.info("✓ Executor inicializado")

            # 6. Paper Trader
            await self._init_paper()
            logger.info("✓ Paper Trader inicializado")

            # 7. Hub Client
            await self._init_hub_client()

            # 8. Sincroniza estado inicial
            await self._sync_initial_state()
            logger.info("✓ Estado sincronizado")

            # 9. Warmup modelos
            await self._warmup_models()
            logger.info("✓ Warmup concluído")

            # 10. Session
            initial_balance = self._cfg("initial_balance", default=10000)
            session_id = await self.session_manager.start_session(
                initial_balance=initial_balance,
                symbols=models,
            )
            self.trade_logger.session_id = session_id
            logger.info(f"✓ Sessão iniciada: {session_id}")

            # 11. Health + Tasks
            self.health = HealthMonitor(self)
            self.running = True
            await self._start_tasks()

            logger.info("=" * 60)
            logger.info("  Sistema PRONTO")
            logger.info("=" * 60)

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

        for task in self._tasks:
            task.cancel()

        if self._cfg("close_on_exit", default=False) and self.executor:
            closed = await self.executor.close_all()
            logger.info(f"✓ {closed} posições fechadas")

        if self.session_manager:
            stats = await self._get_session_stats()
            await self.session_manager.end_session(stats, reason)
            logger.info("✓ Sessão encerrada")

        if self.connector:
            await self.connector.disconnect()
            logger.info("✓ Connector desconectado")

        if self.hub_client:
            await self.hub_client.disconnect()
            logger.info("✓ Hub Client desconectado")

        logger.info("Sistema encerrado")

    # =====================================================================
    # Tasks assíncronas
    # =====================================================================

    async def _start_tasks(self):
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
        timeframe = self._cfg("timeframe", default="M15")

        async def on_bar(bar: Bar):
            if not self.running:
                return
            await self._process_bar(bar)

        await self.connector.subscribe_bars(
            symbols=symbols,
            timeframe=timeframe,
            callback=on_bar,
        )

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
            ack = await self.executor.process_signal(signal_obj)

            # 3. Paper (simulado)
            paper_trade = None
            if self.paper:
                paper_trade = self.paper.process_signal(signal_obj, bar)

            # 4. Loga paper trade
            if paper_trade and self.trade_logger:
                await self.trade_logger.log_paper_trade(paper_trade)

            # 5. Log com razão do ACK
            log_msg = (
                f"[{symbol}] {signal_obj.action} | "
                f"HMM:{signal_obj.hmm_state} | "
                f"VPnL:${signal_obj.virtual_pnl:.2f} | "
                f"Exec:{ack.status}"
            )
            if ack.reason:
                log_msg += f"({ack.reason})"
            if ack.ticket:
                log_msg += f" ticket={ack.ticket}"
            logger.info(log_msg)

            # 6. Health
            if self.health:
                self.health.update(symbol)

            # 7. Send signal to Hub
            if self.hub_client and self.hub_client.is_connected:
                await self.hub_client.send_signal({
                    "symbol": symbol,
                    "action": signal_obj.action,
                    "direction": signal_obj.direction,
                    "intensity": signal_obj.intensity,
                    "hmm_state": signal_obj.hmm_state,
                    "virtual_pnl": round(signal_obj.virtual_pnl, 2),
                    "exec_status": ack.status,
                    "exec_reason": ack.reason,
                    "timestamp": signal_obj.timestamp,
                })

        except Exception as e:
            logger.error(f"[{symbol}] Erro processando barra: {e}", exc_info=True)

    async def _heartbeat_loop(self):
        """
        Telemetria híbrida:
        - Com posições: 1s
        - Sem posições: 5s
        - Analytics pesado: a cada 30s
        """
        analytics_interval = 30
        last_analytics = 0

        while self.running:
            try:
                positions = []
                if self.connector:
                    positions = await self.connector.get_positions()

                interval = 1 if positions else 5

                if self.session_manager and self.connector:
                    account = await self.connector.get_account()
                    self.session_manager.update_heartbeat(account.balance)

                    if self.session_manager.check_day_boundary():
                        logger.info("Virada de dia detectada")
                        await self._handle_day_change()

                if self.hub_client and self.hub_client.is_connected:
                    now = time.time()
                    include_analytics = (now - last_analytics) >= analytics_interval
                    telemetry = await self._build_telemetry(positions, include_analytics=include_analytics)
                    await self.hub_client.send_telemetry(telemetry)
                    if include_analytics:
                        last_analytics = now

                await asyncio.sleep(interval)

            except Exception as e:
                logger.warning(f"Heartbeat erro: {e}")
                await asyncio.sleep(5)

    async def _health_loop(self):
        while self.running:
            await asyncio.sleep(30)
            if self.health:
                report = self.health.check()
                if not report["healthy"]:
                    logger.warning(f"Health: {report['issues']}")

    async def _persistence_retry_loop(self):
        while self.running:
            await asyncio.sleep(300)
            if self.persistence:
                await self.persistence.retry_pending()

    async def _spread_update_loop(self):
        while self.running:
            await asyncio.sleep(30)
            if not self.executor or not self.executor.risk_guard:
                continue
            try:
                for symbol in self.preditor.list_models():
                    info = await self.connector.get_symbol_info(symbol)
                    if info and "spread_points" in info:
                        point = info.get("point", 0.00001)
                        spread_pips = info["spread_points"] * point * 10000
                        if "JPY" in symbol:
                            spread_pips = info["spread_points"] * point * 100
                        self.executor.risk_guard.update_spread(symbol, spread_pips)
            except Exception as e:
                logger.debug(f"Spread update erro: {e}")

    async def _handle_day_change(self):
        if self._cfg("close_on_day_change", default=False) and self.executor:
            await self.executor.close_all()
            stats = await self._get_session_stats()
            await self.session_manager.end_session(stats, SessionEndReason.DAY_CHANGE)

            account = await self.connector.get_account()
            await self.session_manager.start_session(
                initial_balance=account.balance,
                symbols=self.preditor.list_models(),
            )

    async def _build_telemetry(self, positions: list, include_analytics: bool = True) -> dict:
        """Monta payload de telemetria para o Hub."""
        account = await self.connector.get_account() if self.connector else None
        floating_pnl = sum(p.pnl for p in positions)

        telemetry = {
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
                    "pnl_pips": getattr(p, 'pnl_pips', 0),
                    "open_price": p.open_price,
                    "current_price": p.current_price,
                }
                for p in positions
            ],
            "timestamp": time.time(),
        }

        # Métricas leves do paper (sempre)
        if self.paper:
            pm = self.paper.get_metrics()
            telemetry["net_profit"] = pm.get("total_pnl", 0)
            telemetry["win_rate"] = pm.get("win_rate", 0)
            telemetry["total_trades"] = pm.get("total_trades", 0)

        # Métricas pesadas (periódicas)
        if include_analytics and self.paper:
            from paper.stats import calculate_max_drawdown, calculate_profit_factor, calculate_sharpe
            all_trades = self.paper.get_trades()
            if all_trades:
                initial_bal = self._cfg("initial_balance", default=10000)
                wins = [t for t in all_trades if t.pnl > 0]
                losses = [t for t in all_trades if t.pnl < 0]
                telemetry["max_drawdown"] = -calculate_max_drawdown(all_trades, initial_bal)
                telemetry["profit_factor"] = calculate_profit_factor(all_trades)
                telemetry["sharpe_ratio"] = calculate_sharpe(all_trades)
                telemetry["expectancy"] = round(
                    sum(t.pnl for t in all_trades) / len(all_trades), 2
                )
                telemetry["avg_win"] = round(
                    sum(t.pnl for t in wins) / len(wins), 2
                ) if wins else 0
                telemetry["avg_loss"] = round(
                    sum(t.pnl for t in losses) / len(losses), 2
                ) if losses else 0
                equity_curve = []
                equity = initial_bal
                step = max(1, len(all_trades) // 50)
                for i, t in enumerate(all_trades):
                    equity += t.pnl
                    if i % step == 0 or i == len(all_trades) - 1:
                        equity_curve.append({
                            "trade": i + 1,
                            "equity": round(equity, 2),
                            "pnl": round(t.pnl, 2),
                        })
                telemetry["equity_curve"] = equity_curve

        return telemetry

    async def _hub_reconnect_loop(self):
        while self.running:
            await asyncio.sleep(15)
            if self.hub_client and not self.hub_client.is_connected:
                logger.info("Reconectando ao Hub...")
                await self.hub_client.connect()

    # =====================================================================
    # Hub Client + Comandos
    # =====================================================================

    async def _init_hub_client(self):
        hub_cfg = self._cfg("hub", default={})
        if not hub_cfg or not hub_cfg.get("enabled", False):
            logger.info("✗ Hub desabilitado")
            return

        from connector.hub_client import HubClient

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

        # === Controle ===
        if action == "pause":
            self.running = False
            if self.executor:
                self.executor.pause()
            return {"message": "paused"}

        elif action == "resume":
            self.running = True
            if self.executor:
                self.executor.resume()
            return {"message": "resumed"}

        elif action == "close_all":
            closed = await self.executor.close_all() if self.executor else 0
            return {"closed": closed}

        elif action == "close_position":
            symbol = params.get("symbol", "")
            if self.executor and symbol:
                result = await self.executor.close_position(symbol)
                return {"symbol": symbol, "result": result}
            return {"error": "symbol required"}

        elif action == "status":
            return self.health.check() if self.health else {}

        # === Estado ===
        elif action == "get_state":
            telemetry = {}
            if self.connector:
                positions = await self.connector.get_positions()
                telemetry = await self._build_telemetry(positions)

            return {
                "running": self.running,
                "preditor": self.preditor.get_state() if self.preditor else {},
                "executor": self.executor.get_state() if self.executor else {},
                "paper": self.paper.get_metrics() if self.paper else {},
                **telemetry
            }

        # === Modelos ===
        elif action == "list_models":
            if self.preditor:
                return {"models": self.preditor.list_models()}
            return {"models": []}

        elif action == "get_available_models":
            from pathlib import Path
            models_dir = Path(self._cfg("preditor", "models_dir", default="./models"))
            if models_dir.exists():
                zips = [f.name for f in models_dir.glob("*.zip")]
                return {"available": zips}
            return {"available": []}

        elif action == "load_model":
            return await self._cmd_load_model(params)

        elif action == "unload_model":
            symbol = params.get("symbol", "")
            if not symbol or not self.preditor:
                return {"success": False, "error": "symbol required"}
            ok = self.preditor.unload_model(symbol)
            return {"success": ok}

        # === Config por símbolo ===
        elif action == "get_symbol_config":
            return self._cmd_get_symbol_config(params)

        elif action == "set_symbol_config":
            return self._cmd_set_symbol_config(params)

        # === Config geral ===
        elif action == "get_general_config":
            return self._cmd_get_general_config()

        elif action == "set_general_config":
            return self._cmd_set_general_config(params)

        return {"error": f"unknown: {action}"}

    # =====================================================================
    # Implementação dos comandos
    # =====================================================================

    async def _cmd_load_model(self, params: dict) -> dict:
        """Carrega modelo e faz setup completo (config, paper, warmup, subscribe)."""
        path = params.get("path", "")
        if not path or not self.preditor:
            return {"success": False, "error": "path required"}

        try:
            ok = self.preditor.load_model(path)
            if not ok:
                return {"success": False, "error": "load failed"}

            # IMPORTANTE: Pegar o símbolo do Preditor (maiúsculo, do metadata)
            # NÃO do filename (que pode ser minúsculo: btcusd_m15.zip)
            filename = Path(path).stem  # "btcusd_m15"
            file_symbol = filename.split("_")[0].upper()  # "BTCUSD"

            # Verificar no Preditor qual key foi realmente registrada
            symbol = None
            for s in self.preditor.models:
                if s.upper() == file_symbol:
                    symbol = s
                    break

            if not symbol:
                logger.error(f"Modelo carregado mas symbol não encontrado: {file_symbol}")
                return {"success": False, "error": f"symbol not found after load: {file_symbol}"}

            model = self.preditor.models[symbol]
            timeframe = "M15"
            if hasattr(model, "metadata") and model.metadata:
                timeframe = (
                    model.metadata.get("symbol", {}).get("timeframe") or
                    model.metadata.get("timeframe") or
                    "M15"
                )

            # 1. Criar config no Executor se não existir
            self._ensure_executor_config(symbol)

            # 2. Registrar no PaperTrader
            if self.paper and hasattr(model, "metadata"):
                training_cfg = model.metadata.get("training_config", {})
                self.paper.load_config(symbol, training_cfg)
                logger.info(f"[{symbol}] PaperTrader configurado")

            # 3. Warmup
            warmup_bars = self._cfg("preditor", "warmup_bars", default=1000)
            if self.connector:
                bars = await self.connector.get_history(symbol, timeframe, warmup_bars)
                self.preditor.warmup(symbol, bars)
                logger.info(f"[{symbol}] Warmup: {len(bars)} barras ({timeframe})")

            # 4. Subscribe barras
            if self.connector:
                async def on_bar(bar: Bar):
                    if not self.running:
                        return
                    await self._process_bar(bar)
                await self.connector.subscribe_bars([symbol], timeframe, on_bar)
                logger.info(f"[{symbol}] Subscrito para barras {timeframe}")

            # 5. HealthMonitor
            if self.health:
                self.health.update(symbol)

            return {"success": True, "symbol": symbol}

        except Exception as e:
            logger.error(f"load_model error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _ensure_executor_config(self, symbol: str):
        """Garante que um símbolo tenha SymbolConfig no Executor + persiste no JSON."""
        if not self.executor or symbol in self.executor.symbol_configs:
            return

        from executor.lot_mapper import SymbolConfig, LotMapper
        from executor.sync_logic import SyncState

        default_sl = self._cfg("executor", "default_sl_usd", default=10.0)
        default_tp = self._cfg("executor", "default_tp_usd", default=0.0)

        self.executor.symbol_configs[symbol] = SymbolConfig(
            enabled=True,
            lot_weak=0.01,
            lot_moderate=0.03,
            lot_strong=0.05,
            sl_usd=default_sl,
            tp_usd=default_tp,
            max_spread_pips=2.0,
        )
        self.executor.sync_states[symbol] = SyncState()
        self.executor.lot_mapper = LotMapper(self.executor.symbol_configs)

        # Persistir no JSON
        self._save_executor_json()
        logger.info(f"[{symbol}] Executor config criada e persistida (SL=${default_sl}, TP=${default_tp})")

    def _cmd_get_symbol_config(self, params: dict) -> dict:
        symbol = params.get("symbol", "")
        if not self.executor:
            return {"error": "executor not initialized"}

        # Auto-criar config se modelo existe mas config não
        if symbol not in self.executor.symbol_configs:
            if self.preditor and symbol in self.preditor.models:
                self._ensure_executor_config(symbol)
            else:
                return {"error": f"config not found: {symbol}"}

        cfg = self.executor.symbol_configs[symbol]
        return {
            "symbol": symbol,
            "config": {
                "enabled": cfg.enabled,
                "lot_weak": cfg.lot_weak,
                "lot_moderate": cfg.lot_moderate,
                "lot_strong": cfg.lot_strong,
                "sl_usd": cfg.sl_usd,
                "tp_usd": cfg.tp_usd,
                "max_spread_pips": cfg.max_spread_pips,
            }
        }

    def _cmd_set_symbol_config(self, params: dict) -> dict:
        symbol = params.get("symbol", "")
        updates = params.get("config", {})
        if not self.executor:
            return {"success": False, "error": "executor not initialized"}

        # Auto-criar se não existir
        if symbol not in self.executor.symbol_configs:
            if self.preditor and symbol in self.preditor.models:
                self._ensure_executor_config(symbol)
            else:
                return {"success": False, "error": f"symbol not found: {symbol}"}

        cfg = self.executor.symbol_configs[symbol]
        for key, value in updates.items():
            if hasattr(cfg, key):
                setattr(cfg, key, value)

        # Persistir no JSON
        self._save_executor_json()
        logger.info(f"[{symbol}] Config updated e persistida: {updates}")
        return {"success": True, "symbol": symbol}

    def _cmd_get_general_config(self) -> dict:
        """Retorna config geral lendo dos paths corretos do YAML."""
        broker_cfg = self._cfg("broker", default={})
        return {
            "broker_type": broker_cfg.get("type", "unknown"),
            "broker_env": broker_cfg.get("environment", "unknown"),
            "timeframe": self._cfg("timeframe", default="M15"),
            "initial_balance": self._cfg("initial_balance", default=0),
            "warmup_bars": self._cfg("preditor", "warmup_bars", default=1000),
            "persistence_enabled": self._cfg("persistence", "enabled", default=False),
            "hub_connected": bool(self.hub_client and self.hub_client.is_connected),
            "models_dir": self._cfg("preditor", "models_dir", default="./models"),
            "close_on_exit": self._cfg("close_on_exit", default=False),
            "close_on_day_change": self._cfg("close_on_day_change", default=False),
            "default_sl_usd": self._cfg("executor", "default_sl_usd", default=0),
            "default_tp_usd": self._cfg("executor", "default_tp_usd", default=0),
        }

    def _cmd_set_general_config(self, params: dict) -> dict:
        """Atualiza config geral e persiste no YAML + aplica no Executor."""
        updated = {}

        # Campos que ficam no toplevel do YAML
        toplevel_keys = {"close_on_exit", "close_on_day_change"}
        for key in toplevel_keys:
            if key in params:
                self.config[key] = params[key]
                updated[key] = params[key]

        # Campos que ficam em executor.*
        executor_keys = {"default_sl_usd", "default_tp_usd"}
        for key in executor_keys:
            if key in params:
                if "executor" not in self.config:
                    self.config["executor"] = {}
                self.config["executor"][key] = params[key]
                updated[key] = params[key]

        # Aplicar SL/TP em todos os símbolos do Executor
        if self.executor and ("default_sl_usd" in updated or "default_tp_usd" in updated):
            for symbol, cfg in self.executor.symbol_configs.items():
                if "default_sl_usd" in updated:
                    cfg.sl_usd = updated["default_sl_usd"]
                if "default_tp_usd" in updated:
                    cfg.tp_usd = updated["default_tp_usd"]
            # Persistir no JSON também
            self._save_executor_json()
            logger.info(f"SL/TP applied to all symbols: SL={updated.get('default_sl_usd')}, TP={updated.get('default_tp_usd')}")

        if updated:
            # Persistir no YAML
            self._save_yaml_config()
            logger.info(f"General config updated e persistida: {updated}")

        return {"success": True, "updated": updated}

    # =====================================================================
    # Inicialização dos módulos
    # =====================================================================

    async def _init_persistence(self):
        from persistence import SupabaseClient, SessionManager, TradeLogger

        self.persistence = SupabaseClient(
            url=self._cfg("supabase_url", default=""),
            key=self._cfg("supabase_key", default=""),
            enabled=self._cfg("persistence", "enabled", default=False),
        )
        self.session_manager = SessionManager(self.persistence)
        self.trade_logger = TradeLogger(self.persistence, "")

    async def _init_preditor(self):
        from preditor import Preditor

        self.preditor = Preditor()
        models_dir = Path(
            self._cfg("preditor", "models_dir", default="./models")
        )
        if models_dir.exists():
            for model_file in sorted(models_dir.glob("*.zip")):
                self.preditor.load_model(str(model_file))

    async def _init_connector(self):
        broker_cfg = self._cfg("broker", default={})
        broker_type = broker_cfg.get("type", "mock")

        if broker_type == "ctrader":
            from connector.ctrader import CTraderConnector
            self.connector = CTraderConnector(broker_cfg)
        else:
            from connector.mock import MockConnector
            self.connector = MockConnector(broker_cfg)

        connected = await self.connector.connect()
        if not connected:
            raise RuntimeError("Falha ao conectar ao broker")

    async def _init_executor(self):
        from executor import Executor

        config_file = self._executor_config_path()
        self.executor = Executor(
            connector=self.connector,
            config_path=config_file,
        )

        # Auto-criar configs para modelos carregados que não estão no JSON
        created = []
        for symbol in self.preditor.list_models():
            if symbol not in self.executor.symbol_configs:
                self._ensure_executor_config(symbol)
                created.append(symbol)

        if created:
            logger.info(f"Auto-created executor configs: {created}")

    async def _init_paper(self):
        from paper import PaperTrader

        self.paper = PaperTrader(
            initial_balance=self._cfg("initial_balance", default=10000)
        )
        for symbol in self.preditor.list_models():
            model = self.preditor.models.get(symbol)
            if model and hasattr(model, "metadata"):
                training_cfg = model.metadata.get("training_config", {})
                self.paper.load_config(symbol, training_cfg)

    async def _sync_initial_state(self):
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
        warmup_bars = self._cfg("preditor", "warmup_bars", default=1000)
        for symbol in self.preditor.list_models():
            model = self.preditor.models.get(symbol)
            timeframe = "M15"
            if model and hasattr(model, "metadata"):
                timeframe = (
                    model.metadata.get("symbol", {}).get("timeframe") or
                    model.metadata.get("timeframe") or
                    "M15"
                )
            try:
                bars = await self.connector.get_history(
                    symbol, timeframe, warmup_bars
                )
                self.preditor.warmup(symbol, bars)
                logger.info(f"[{symbol}] Warmup: {len(bars)} barras ({timeframe})")
            except Exception as e:
                logger.error(f"[{symbol}] Warmup falhou: {e}")

    async def _get_session_stats(self) -> dict:
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
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("Sinal recebido. Iniciando shutdown gracioso...")
            asyncio.create_task(self._handle_signal())

            def force_kill():
                logger.warning("Shutdown timeout! Forçando saída (os._exit).")
                os._exit(1)

            t = threading.Timer(5.0, force_kill)
            t.daemon = True
            t.start()

        for sig in (signal_mod.SIGINT, signal_mod.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    async def _handle_signal(self):
        logger.info("Sinal de encerramento recebido")
        self._shutdown_event.set()
