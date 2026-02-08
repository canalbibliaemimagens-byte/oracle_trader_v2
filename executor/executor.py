"""
Oracle Trader v2.0 — Executor
===============================

Processa sinais do Preditor e executa ordens reais no broker.

Flow por sinal:
  1. Verifica se símbolo está habilitado
  2. Obtém posição real do Connector
  3. Aplica lógica de sincronização (decide)
  4. Regra de borda (SyncState.should_open)
  5. Mapeia intensidade → lotes (LotMapper)
  6. Valida riscos (RiskGuard)
  7. Envia ordem ao Connector
  8. Retorna ACK
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from connector.base import BaseConnector
from core.actions import ACTION_TO_INDEX, Action
from core.models import OrderResult, Position, Signal
from .comment_builder import CommentBuilder
from .lot_mapper import LotMapper, SymbolConfig, load_symbol_configs
from .price_converter import PriceConverter
from .risk_guard import RiskGuard
from .sync_logic import Decision, SyncState, decide

logger = logging.getLogger("Executor")


@dataclass
class ACK:
    """Acknowledgement de processamento de sinal."""
    symbol: str
    action: str
    status: str       # OK, SKIP, ERROR
    reason: str = ""
    ticket: Optional[int] = None


class Executor:
    """
    Processa sinais do Preditor e executa ordens.
    """

    def __init__(self, connector: BaseConnector, config_path: str):
        self.connector = connector
        self.symbol_configs: Dict[str, SymbolConfig] = {}
        self.sync_states: Dict[str, SyncState] = {}
        self.lot_mapper: Optional[LotMapper] = None
        self.risk_guard: Optional[RiskGuard] = None
        self.price_converter: PriceConverter = PriceConverter(connector)
        self.paused = False

        self.load_config(config_path)

    def load_config(self, path: str):
        """Carrega configuração de símbolos do JSON."""
        import json

        with open(path) as f:
            data = json.load(f)

        self.symbol_configs = load_symbol_configs(path)

        for symbol in self.symbol_configs:
            if symbol not in self.sync_states:
                self.sync_states[symbol] = SyncState()

        self.lot_mapper = LotMapper(self.symbol_configs)

        risk_config = data.get("_risk", {})
        self.risk_guard = RiskGuard(risk_config)

        logger.info(
            f"Config carregada: {len(self.symbol_configs)} símbolos, "
            f"DD limit={self.risk_guard.dd_limit_pct}%"
        )

    async def process_signal(self, signal: Signal) -> ACK:
        """
        Processa sinal do Preditor.

        Returns:
            ACK com resultado da execução.
        """
        symbol = signal.symbol

        # 1. Verifica config
        if symbol not in self.symbol_configs:
            logger.warning(f"[{symbol}] SKIP: NO_CONFIG — adicione config via dashboard")
            return ACK(symbol, signal.action, "SKIP", "NO_CONFIG")

        config = self.symbol_configs[symbol]
        if not config.enabled:
            return ACK(symbol, signal.action, "SKIP", "DISABLED")

        # 2. Verifica pause
        if self.paused:
            return ACK(symbol, signal.action, "SKIP", "PAUSED")

        # 3. Obtém posição real
        real_pos = await self.connector.get_position(symbol)

        # 4. Decisão de sincronização
        decision = decide(signal, real_pos)

        # 5. Regra de Borda (SyncState)
        sync_state = self.sync_states.setdefault(symbol, SyncState())

        # 6. Executa decisão
        if decision == Decision.NOOP:
            sync_state.should_open(signal, decision)  # Atualiza estado
            return ACK(symbol, signal.action, "OK", "SYNCED")

        if decision == Decision.CLOSE:
            sync_state.should_open(signal, decision)  # Atualiza estado
            ack = await self._close_position(symbol, real_pos)
            return ack

        if decision == Decision.OPEN:
            if sync_state.should_open(signal, decision):
                return await self._open_position(signal, config)
            logger.debug(f"[{symbol}] OPEN blocked by edge rule (waiting transition)")
            return ACK(symbol, signal.action, "OK", "WAITING_EDGE")

        if decision == Decision.CLOSE_AND_OPEN:
            # Primeiro fecha
            close_ack = await self._close_position(symbol, real_pos)
            if close_ack.status == "ERROR":
                return close_ack
            # Depois abre (se regra de borda permitir)
            if sync_state.should_open(signal, decision):
                return await self._open_position(signal, config)
            return ACK(symbol, signal.action, "OK", "CLOSED_WAITING_EDGE")

        return ACK(symbol, signal.action, "ERROR", "UNKNOWN_DECISION")

    async def _open_position(self, signal: Signal, config: SymbolConfig) -> ACK:
        """Abre nova posição."""
        symbol = signal.symbol

        # Mapeia lote
        volume = self.lot_mapper.map_lot(symbol, signal.intensity)
        if volume <= 0:
            logger.warning(f"[{symbol}] SKIP: ZERO_LOT (intensity={signal.intensity})")
            return ACK(symbol, signal.action, "SKIP", "ZERO_LOT")

        # Valida risco
        account = await self.connector.get_account()
        risk_check = self.risk_guard.check_all(symbol, volume, account, config)
        if not risk_check.passed:
            return ACK(symbol, signal.action, "SKIP", risk_check.reason)

        # Calcula DD atual
        initial = self.risk_guard.initial_balance
        dd_pct = ((initial - account.equity) / initial * 100) if initial > 0 else 0

        # Monta comentário
        action_index = self._action_to_index(signal.action)
        comment = CommentBuilder.build(
            hmm_state=signal.hmm_state,
            action_index=action_index,
            intensity=signal.intensity,
            balance=account.balance,
            drawdown_pct=dd_pct,
            virtual_pnl=signal.virtual_pnl,
        )

        # Conversão SL/TP: USD → preço absoluto
        current_price = await self._get_current_price(symbol)
        sl_price = await self.price_converter.usd_to_sl_price(
            symbol=symbol,
            direction=signal.direction,
            sl_usd=config.sl_usd,
            volume=volume,
            current_price=current_price,
        )
        tp_price = await self.price_converter.usd_to_tp_price(
            symbol=symbol,
            direction=signal.direction,
            tp_usd=config.tp_usd,
            volume=volume,
            current_price=current_price,
        )

        # Executa ordem
        dir_name = "LONG" if signal.direction == 1 else "SHORT"
        logger.info(
            f"[{symbol}] OPENING {dir_name} vol={volume} "
            f"SL={sl_price} TP={tp_price} price={current_price}"
        )

        result: OrderResult = await self.connector.open_order(
            symbol=symbol,
            direction=signal.direction,
            volume=volume,
            sl=sl_price,
            tp=tp_price,
            comment=comment,
        )

        if result.success:
            logger.info(
                f"[{symbol}] ✓ OPENED {signal.action} "
                f"vol={volume} ticket={result.ticket}"
            )
            return ACK(symbol, signal.action, "OK", "OPENED", result.ticket)
        else:
            logger.error(f"[{symbol}] ✗ OPEN FAILED: {result.error}")
            return ACK(symbol, signal.action, "ERROR", result.error)

    async def _close_position(
        self, symbol: str, position: Optional[Position]
    ) -> ACK:
        """Fecha posição existente."""
        if position is None:
            return ACK(symbol, "CLOSE", "OK", "ALREADY_FLAT")

        result: OrderResult = await self.connector.close_order(position.ticket)

        if result.success:
            self.risk_guard.record_trade_result(position.pnl)
            logger.info(
                f"[{symbol}] ✓ CLOSED ticket={position.ticket} "
                f"pnl={position.pnl:.2f}"
            )
            return ACK(symbol, "CLOSE", "OK", "CLOSED", position.ticket)
        else:
            logger.error(f"[{symbol}] ✗ CLOSE FAILED: {result.error}")
            return ACK(symbol, "CLOSE", "ERROR", result.error)

    @staticmethod
    def _action_to_index(action_name: str) -> int:
        """Converte nome da ação para índice PPO."""
        try:
            action = Action(action_name)
            return ACTION_TO_INDEX.get(action, 0)
        except ValueError:
            return 0

    # =====================================================================
    # Helpers
    # =====================================================================

    async def _get_current_price(self, symbol: str) -> float:
        """
        Obtém preço atual do símbolo via posição existente ou symbol_info.
        """
        # Tenta posição aberta
        pos = await self.connector.get_position(symbol)
        if pos and pos.current_price > 0:
            return pos.current_price

        # Tenta todas posições
        try:
            positions = await self.connector.get_positions()
            for p in positions:
                if p.symbol == symbol and p.current_price > 0:
                    return p.current_price
        except Exception:
            pass

        # Fallback
        logger.warning(f"[{symbol}] Preço atual indisponível para conversão SL/TP")
        return 0.0

    # =====================================================================
    # Controles
    # =====================================================================

    def pause(self):
        """Pausa execução (não processa novos sinais)."""
        self.paused = True
        logger.info("Executor PAUSED")

    def resume(self):
        """Retoma execução."""
        self.paused = False
        logger.info("Executor RESUMED")

    async def close_position(self, symbol: str) -> bool:
        """Fecha posição de um símbolo específico."""
        pos = await self.connector.get_position(symbol)
        if pos:
            result = await self.connector.close_order(pos.ticket)
            return result.success
        return False

    async def close_all(self) -> int:
        """Fecha todas as posições. Retorna número de posições fechadas."""
        positions = await self.connector.get_positions()
        closed = 0
        for pos in positions:
            result = await self.connector.close_order(pos.ticket)
            if result.success:
                closed += 1
        logger.info(f"close_all: {closed}/{len(positions)} posições fechadas")
        return closed

    def get_state(self) -> dict:
        """Retorna estado para debug/dashboard."""
        return {
            "paused": self.paused,
            "consecutive_losses": self.risk_guard.consecutive_losses
            if self.risk_guard
            else 0,
            "symbols": {
                s: {
                    "enabled": cfg.enabled,
                    "lots": [cfg.lot_weak, cfg.lot_moderate, cfg.lot_strong],
                    "sl_usd": cfg.sl_usd,
                    "tp_usd": cfg.tp_usd,
                    "waiting_sync": self.sync_states.get(
                        s, SyncState()
                    ).waiting_sync,
                    "first_live": self.sync_states.get(
                        s, SyncState()
                    ).first_live,
                }
                for s, cfg in self.symbol_configs.items()
            },
        }
