"""
Oracle Trader v2.0 — Risk Guard
================================

Última linha de defesa antes de enviar uma ordem.
Bloqueia ordens que violam regras de risco (drawdown, margem, circuit breaker).
"""

import logging
from dataclasses import dataclass

from core.models import AccountInfo
from .lot_mapper import SymbolConfig

logger = logging.getLogger("Executor.RiskGuard")


@dataclass
class RiskCheck:
    """Resultado de verificação de risco."""
    passed: bool
    reason: str = ""


class RiskGuard:
    """
    Validações de pré-trade.
    Cada check retorna RiskCheck. Todos devem passar para ordem ser enviada.
    """

    def __init__(self, config: dict):
        self.dd_limit_pct: float = config.get("dd_limit_pct", 5.0)
        self.dd_emergency_pct: float = config.get("dd_emergency_pct", 10.0)
        self.initial_balance: float = config.get("initial_balance", 0)
        self.max_consecutive_losses: int = config.get("max_consecutive_losses", 5)

        # Circuit breaker
        self.consecutive_losses: int = 0

        # Cache de spreads atuais (atualizado externamente pelo Orchestrator/Connector)
        self._current_spreads: dict = {}

    def update_spread(self, symbol: str, spread_pips: float):
        """Atualiza cache do spread atual de um símbolo."""
        self._current_spreads[symbol] = spread_pips

    def check_all(
        self,
        symbol: str,
        volume: float,
        account: AccountInfo,
        symbol_config: SymbolConfig,
    ) -> RiskCheck:
        """Executa todas as verificações de risco."""
        checks = [
            self._check_drawdown(account),
            self._check_margin(account, volume),
            self._check_spread(symbol, symbol_config),
            self._check_circuit_breaker(),
        ]

        for check in checks:
            if not check.passed:
                logger.warning(f"[{symbol}] Risk BLOCKED: {check.reason}")
                return check

        return RiskCheck(passed=True)

    def _check_drawdown(self, account: AccountInfo) -> RiskCheck:
        """Verifica se drawdown está dentro dos limites."""
        if self.initial_balance <= 0:
            return RiskCheck(passed=True)

        current_dd = (
            (self.initial_balance - account.equity) / self.initial_balance
        ) * 100

        if current_dd >= self.dd_emergency_pct:
            return RiskCheck(
                passed=False,
                reason=f"EMERGENCY: DD {current_dd:.1f}% >= {self.dd_emergency_pct}%",
            )

        if current_dd >= self.dd_limit_pct:
            return RiskCheck(
                passed=False,
                reason=f"DD_LIMIT: DD {current_dd:.1f}% >= {self.dd_limit_pct}%",
            )

        return RiskCheck(passed=True)

    def _check_margin(self, account: AccountInfo, volume: float) -> RiskCheck:
        """Verifica se há margem livre suficiente."""
        estimated_margin = volume * 1000  # Estimativa conservadora
        if account.free_margin < estimated_margin:
            return RiskCheck(
                passed=False,
                reason=(
                    f"MARGIN: Free {account.free_margin:.2f} "
                    f"< Required ~{estimated_margin:.2f}"
                ),
            )
        return RiskCheck(passed=True)

    def _check_spread(self, symbol: str, config: SymbolConfig) -> RiskCheck:
        """Verifica se spread atual está aceitável."""
        current_spread = self._current_spreads.get(symbol)

        # Se não temos dados de spread, permitir (fail-open)
        # Mas logar warning para visibilidade
        if current_spread is None:
            logger.debug(f"[{symbol}] Spread desconhecido — permitindo operação")
            return RiskCheck(passed=True)

        max_spread = config.max_spread_pips
        if current_spread > max_spread:
            return RiskCheck(
                passed=False,
                reason=(
                    f"SPREAD: atual {current_spread:.1f} pips "
                    f"> max {max_spread:.1f} pips"
                ),
            )
        return RiskCheck(passed=True)

    def _check_circuit_breaker(self) -> RiskCheck:
        """Verifica circuit breaker (perdas consecutivas)."""
        if self.consecutive_losses >= self.max_consecutive_losses:
            return RiskCheck(
                passed=False,
                reason=(
                    f"CIRCUIT_BREAKER: {self.consecutive_losses} "
                    f"losses consecutivas (max={self.max_consecutive_losses})"
                ),
            )
        return RiskCheck(passed=True)

    def record_trade_result(self, pnl: float):
        """Registra resultado para circuit breaker."""
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

    def reset_circuit_breaker(self):
        """Reseta circuit breaker manualmente."""
        self.consecutive_losses = 0
