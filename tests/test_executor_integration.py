"""
Testes de Integração — Executor + PriceConverter + Spread Loop.

Valida que o pipeline completo de abertura de ordem converte SL/TP
corretamente antes de enviar ao Connector.

Também testa a integração do spread update com o RiskGuard.
"""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from oracle_trader_v2.connector.mock.client import MockConnector
from oracle_trader_v2.executor.executor import Executor, ACK
from oracle_trader_v2.executor.price_converter import PriceConverter
from oracle_trader_v2.core.models import Signal, Position, OrderResult
from oracle_trader_v2.tests.conftest import make_signal, make_position


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_config_with_sl_tp(tmp_path):
    """Config com SL e TP em USD definidos."""
    config = {
        "_version": "2.0",
        "_risk": {
            "dd_limit_pct": 5.0,
            "dd_emergency_pct": 10.0,
            "initial_balance": 10000,
            "max_consecutive_losses": 5,
        },
        "EURUSD": {
            "enabled": True,
            "lot_weak": 0.01,
            "lot_moderate": 0.03,
            "lot_strong": 0.05,
            "sl_usd": 10.0,
            "tp_usd": 20.0,
            "max_spread_pips": 2.0,
        },
    }
    path = tmp_path / "executor_symbols.json"
    path.write_text(json.dumps(config))
    return str(path)


@pytest.fixture
def mock_connector():
    conn = MockConnector(initial_balance=10000.0)
    return conn


@pytest.fixture
def executor_with_converter(mock_connector, tmp_config_with_sl_tp):
    """Executor real com PriceConverter integrado."""
    executor = Executor(mock_connector, tmp_config_with_sl_tp)
    return executor


# ── Executor + PriceConverter ────────────────────────────────────────────────

class TestExecutorPriceConversion:
    """Testa que o Executor converte SL/TP antes de enviar ordens."""

    @pytest.mark.asyncio
    async def test_executor_has_price_converter(self, executor_with_converter):
        """Executor deve ter PriceConverter instanciado."""
        assert executor_with_converter.price_converter is not None
        assert isinstance(executor_with_converter.price_converter, PriceConverter)

    @pytest.mark.asyncio
    async def test_open_order_sl_is_price_not_usd(
        self, executor_with_converter, mock_connector
    ):
        """
        Teste de regressão CRÍTICO:
        Ao abrir ordem, o SL enviado ao Connector deve ser preço absoluto,
        NÃO o valor em USD.
        """
        await mock_connector.connect()

        # Simula preço atual
        mock_connector.set_price("EURUSD", 1.10000)

        # Configura posição para que process_signal abra
        # Primeiro sinal → WAIT_SYNC (sem posição real)
        s1 = make_signal(symbol="EURUSD", direction=1, action="LONG_WEAK", intensity=1)
        ack1 = await executor_with_converter.process_signal(s1)

        # Segundo sinal (mesmo) → deve abrir via SyncState
        s2 = make_signal(symbol="EURUSD", direction=1, action="LONG_WEAK", intensity=1)
        ack2 = await executor_with_converter.process_signal(s2)

        # Verifica posição criada
        pos = await mock_connector.get_position("EURUSD")
        if pos is not None:
            # SL deve ser preço absoluto (perto de 1.09), NÃO 10.0
            assert pos.sl != 10.0, \
                "BUG: SL está em USD (10.0) em vez de preço absoluto!"
            # Se tem SL, deve estar perto do preço do EURUSD
            if pos.sl > 0:
                assert 0.9 < pos.sl < 1.3, \
                    f"SL fora do range razoável: {pos.sl}"

    @pytest.mark.asyncio
    async def test_open_order_tp_is_price_not_usd(
        self, executor_with_converter, mock_connector
    ):
        """TP enviado ao Connector deve ser preço absoluto, não USD."""
        await mock_connector.connect()
        mock_connector.set_price("EURUSD", 1.10000)

        # Força abertura
        s1 = make_signal(symbol="EURUSD", direction=1, action="LONG_WEAK", intensity=1)
        await executor_with_converter.process_signal(s1)
        s2 = make_signal(symbol="EURUSD", direction=1, action="LONG_WEAK", intensity=1)
        await executor_with_converter.process_signal(s2)

        pos = await mock_connector.get_position("EURUSD")
        if pos is not None and pos.tp > 0:
            assert pos.tp != 20.0, \
                "BUG: TP está em USD (20.0) em vez de preço absoluto!"
            assert 0.9 < pos.tp < 1.3, \
                f"TP fora do range razoável: {pos.tp}"

    @pytest.mark.asyncio
    async def test_sl_zero_config_sends_zero(self, mock_connector, tmp_path):
        """Se sl_usd=0 no config, deve enviar sl=0 (sem stop)."""
        config = {
            "_version": "2.0",
            "_risk": {"dd_limit_pct": 5.0, "dd_emergency_pct": 10.0,
                      "initial_balance": 10000, "max_consecutive_losses": 5},
            "EURUSD": {
                "enabled": True,
                "lot_weak": 0.01, "lot_moderate": 0.03, "lot_strong": 0.05,
                "sl_usd": 0.0,
                "tp_usd": 0.0,
                "max_spread_pips": 3.0,
            },
        }
        path = tmp_path / "no_sl.json"
        path.write_text(json.dumps(config))

        executor = Executor(mock_connector, str(path))
        await mock_connector.connect()

        s1 = make_signal(symbol="EURUSD", direction=1, action="LONG_WEAK", intensity=1)
        await executor.process_signal(s1)
        s2 = make_signal(symbol="EURUSD", direction=1, action="LONG_WEAK", intensity=1)
        await executor.process_signal(s2)

        pos = await mock_connector.get_position("EURUSD")
        if pos is not None:
            assert pos.sl == 0.0
            assert pos.tp == 0.0


# ── Spread Integration ──────────────────────────────────────────────────────

class TestSpreadIntegration:
    """Testa integração spread: MockConnector → RiskGuard."""

    @pytest.mark.asyncio
    async def test_spread_update_flow(self, executor_with_converter, mock_connector):
        """Simula fluxo: symbol_info → update_spread → check_spread."""
        await mock_connector.connect()

        # MockConnector retorna spread_points para EURUSD
        info = await mock_connector.get_symbol_info("EURUSD")
        assert info is not None
        assert "spread_points" in info

        # Calcula spread em pips (como o orchestrator faria)
        point = info.get("point", 0.00001)
        spread_pips = info["spread_points"] * point * 10000
        # 7 * 0.00001 * 10000 = 0.7 pips

        # Atualiza RiskGuard
        executor_with_converter.risk_guard.update_spread("EURUSD", spread_pips)

        # Verifica que spread está no cache
        cached = executor_with_converter.risk_guard._current_spreads.get("EURUSD")
        assert cached is not None
        assert cached == pytest.approx(spread_pips)

    @pytest.mark.asyncio
    async def test_spread_blocks_high_spread(self, executor_with_converter):
        """Spread alto deve bloquear ordens."""
        from oracle_trader_v2.executor.lot_mapper import SymbolConfig

        # Injeta spread alto
        executor_with_converter.risk_guard.update_spread("EURUSD", 5.0)  # 5 pips

        # Config tem max_spread_pips = 2.0
        config = executor_with_converter.symbol_configs["EURUSD"]
        check = executor_with_converter.risk_guard._check_spread("EURUSD", config)
        assert not check.passed
        assert "SPREAD" in check.reason

    @pytest.mark.asyncio
    async def test_spread_allows_low_spread(self, executor_with_converter):
        """Spread baixo deve permitir ordens."""
        executor_with_converter.risk_guard.update_spread("EURUSD", 1.0)  # 1 pip
        config = executor_with_converter.symbol_configs["EURUSD"]
        check = executor_with_converter.risk_guard._check_spread("EURUSD", config)
        assert check.passed
