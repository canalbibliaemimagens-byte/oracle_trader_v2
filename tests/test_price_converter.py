"""
Testes do PriceConverter — conversão SL/TP USD → preço absoluto.

Cobre:
  - Conversão para pares XXX/USD (EURUSD, GBPUSD, AUDUSD)
  - Conversão para pares USD/XXX (USDJPY, USDCHF, USDCAD)
  - Direções LONG e SHORT
  - SL e TP zero (sem stop/take)
  - Fallback para tabela estática quando symbol_info indisponível
  - Cache de symbol_info
  - Edge cases: volume zero, preço zero
"""

import pytest
import asyncio
from unittest.mock import AsyncMock

from oracle_trader_v2.executor.price_converter import PriceConverter, DEFAULT_PIP_VALUES
from oracle_trader_v2.connector.mock.client import MockConnector


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_connector():
    return MockConnector(initial_balance=10000.0)


@pytest.fixture
def converter(mock_connector):
    return PriceConverter(mock_connector)


# ── EURUSD (quote = USD, pip_value fixo = 10 USD/pip/lot) ───────────────────

class TestEURUSD:
    """EURUSD: 5 dígitos, pip_value = 10 USD/pip por lote padrão."""

    @pytest.mark.asyncio
    async def test_sl_long_basic(self, converter):
        """SL $10 em LONG 0.01 lot → deve ficar ~100 pips abaixo."""
        sl = await converter.usd_to_sl_price(
            symbol="EURUSD", direction=1,
            sl_usd=10.0, volume=0.01, current_price=1.10000,
        )
        # pip_value_total = 10.0 * 0.01 = 0.10 USD/pip
        # distance_pips = 10.0 / 0.10 = 100 pips
        # distance_price = 100 * 0.00001 * 10 = 0.01000
        # sl_price = 1.10000 - 0.01000 = 1.09000
        assert sl == pytest.approx(1.09000, abs=0.00010)

    @pytest.mark.asyncio
    async def test_sl_short_basic(self, converter):
        """SL $10 em SHORT 0.01 lot → deve ficar ~100 pips acima."""
        sl = await converter.usd_to_sl_price(
            symbol="EURUSD", direction=-1,
            sl_usd=10.0, volume=0.01, current_price=1.10000,
        )
        assert sl == pytest.approx(1.11000, abs=0.00010)

    @pytest.mark.asyncio
    async def test_tp_long_basic(self, converter):
        """TP $20 em LONG 0.03 lot → deve ficar acima do preço."""
        tp = await converter.usd_to_tp_price(
            symbol="EURUSD", direction=1,
            tp_usd=20.0, volume=0.03, current_price=1.10000,
        )
        # pip_value_total = 10.0 * 0.03 = 0.30 USD/pip
        # distance_pips = 20.0 / 0.30 = 66.67 pips
        # distance_price = 66.67 * 0.0001 = 0.00667
        # tp_price = 1.10000 + 0.00667 = 1.10667
        assert tp == pytest.approx(1.10667, abs=0.00010)

    @pytest.mark.asyncio
    async def test_tp_short_basic(self, converter):
        """TP $20 em SHORT 0.03 lot → deve ficar abaixo do preço."""
        tp = await converter.usd_to_tp_price(
            symbol="EURUSD", direction=-1,
            tp_usd=20.0, volume=0.03, current_price=1.10000,
        )
        assert tp == pytest.approx(1.09333, abs=0.00010)

    @pytest.mark.asyncio
    async def test_sl_larger_volume_closer_stop(self, converter):
        """Volume maior → SL mais perto do preço (mesmo USD)."""
        sl_small = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 1.10000)
        sl_big = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.05, 1.10000)
        # 0.05 lot tem pip_value 5x maior → distância 5x menor
        assert sl_big > sl_small  # Mais perto do preço = valor maior para LONG


# ── USDJPY (base = USD, 3 dígitos) ──────────────────────────────────────────

class TestUSDJPY:
    """USDJPY: 3 dígitos, pip_value ≈ 6.7 USD/pip por lote (varia com taxa)."""

    @pytest.mark.asyncio
    async def test_sl_long_jpy(self, converter):
        """SL em par JPY (3 dígitos) deve funcionar corretamente."""
        sl = await converter.usd_to_sl_price(
            symbol="USDJPY", direction=1,
            sl_usd=10.0, volume=0.01, current_price=150.000,
        )
        # USDJPY pip_value ≈ 6.7 USD/pip/lot
        # pip_value_total = 6.7 * 0.01 = 0.067
        # distance_pips = 10.0 / 0.067 = 149.25 pips
        # distance_price = 149.25 * 0.001 * 10 = 1.4925
        # sl_price = 150.000 - 1.4925 ≈ 148.508
        assert sl < 150.000  # LONG → SL abaixo
        assert sl > 140.000  # Razoável (não absurdo)
        # Verificar que tem 3 casas decimais
        assert sl == round(sl, 3)

    @pytest.mark.asyncio
    async def test_sl_short_jpy(self, converter):
        """SHORT USDJPY → SL acima."""
        sl = await converter.usd_to_sl_price(
            symbol="USDJPY", direction=-1,
            sl_usd=10.0, volume=0.01, current_price=150.000,
        )
        assert sl > 150.000  # SHORT → SL acima


# ── Zero/Edge Cases ──────────────────────────────────────────────────────────

class TestEdgeCases:

    @pytest.mark.asyncio
    async def test_sl_zero_returns_zero(self, converter):
        """SL de $0 → sem stop loss (retorna 0)."""
        sl = await converter.usd_to_sl_price("EURUSD", 1, 0.0, 0.01, 1.10000)
        assert sl == 0.0

    @pytest.mark.asyncio
    async def test_tp_zero_returns_zero(self, converter):
        """TP de $0 → sem take profit (retorna 0)."""
        tp = await converter.usd_to_tp_price("EURUSD", 1, 0.0, 0.01, 1.10000)
        assert tp == 0.0

    @pytest.mark.asyncio
    async def test_negative_sl_returns_zero(self, converter):
        """SL negativo → tratado como zero."""
        sl = await converter.usd_to_sl_price("EURUSD", 1, -5.0, 0.01, 1.10000)
        assert sl == 0.0

    @pytest.mark.asyncio
    async def test_zero_volume_returns_zero(self, converter):
        """Volume zero → distância zero (evita divisão por zero)."""
        sl = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.0, 1.10000)
        assert sl == 0.0

    @pytest.mark.asyncio
    async def test_zero_price_no_crash(self, converter):
        """Preço zero → não deve crashar."""
        sl = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 0.0)
        # Com preço 0, o resultado pode ser negativo mas não deve crashar
        assert isinstance(sl, float)


# ── Simetria LONG/SHORT ─────────────────────────────────────────────────────

class TestSymmetry:

    @pytest.mark.asyncio
    async def test_sl_symmetry(self, converter):
        """SL LONG e SHORT devem ser equidistantes do preço."""
        price = 1.10000
        sl_long = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, price)
        sl_short = await converter.usd_to_sl_price("EURUSD", -1, 10.0, 0.01, price)

        dist_long = abs(price - sl_long)
        dist_short = abs(sl_short - price)
        assert dist_long == pytest.approx(dist_short, abs=0.00001)

    @pytest.mark.asyncio
    async def test_tp_symmetry(self, converter):
        """TP LONG e SHORT devem ser equidistantes do preço."""
        price = 1.10000
        tp_long = await converter.usd_to_tp_price("EURUSD", 1, 20.0, 0.01, price)
        tp_short = await converter.usd_to_tp_price("EURUSD", -1, 20.0, 0.01, price)

        dist_long = abs(tp_long - price)
        dist_short = abs(price - tp_short)
        assert dist_long == pytest.approx(dist_short, abs=0.00001)

    @pytest.mark.asyncio
    async def test_sl_tp_direction(self, converter):
        """LONG: SL abaixo, TP acima. SHORT: inverso."""
        price = 1.10000
        sl_long = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, price)
        tp_long = await converter.usd_to_tp_price("EURUSD", 1, 20.0, 0.01, price)
        assert sl_long < price < tp_long

        sl_short = await converter.usd_to_sl_price("EURUSD", -1, 10.0, 0.01, price)
        tp_short = await converter.usd_to_tp_price("EURUSD", -1, 20.0, 0.01, price)
        assert tp_short < price < sl_short


# ── Fallback e Cache ─────────────────────────────────────────────────────────

class TestFallbackAndCache:

    @pytest.mark.asyncio
    async def test_unknown_pair_uses_estimate(self, converter):
        """Par desconhecido usa estimativa (não crashar)."""
        sl = await converter.usd_to_sl_price("XYZABC", 1, 10.0, 0.01, 1.50000)
        assert isinstance(sl, float)
        assert sl > 0

    @pytest.mark.asyncio
    async def test_symbol_info_from_mock(self, converter):
        """MockConnector retorna symbol_info com pip_value."""
        info = await converter._connector.get_symbol_info("EURUSD")
        assert info is not None
        assert "pip_value" in info

    @pytest.mark.asyncio
    async def test_cache_populated_after_call(self, converter):
        """Após primeira chamada, symbol_info deve estar no cache."""
        assert "EURUSD" not in converter._symbol_cache
        await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 1.10000)
        assert "EURUSD" in converter._symbol_cache

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, converter):
        """invalidate_cache limpa o cache."""
        await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 1.10000)
        assert "EURUSD" in converter._symbol_cache
        converter.invalidate_cache("EURUSD")
        assert "EURUSD" not in converter._symbol_cache

    @pytest.mark.asyncio
    async def test_invalidate_all_cache(self, converter):
        """invalidate_cache() sem argumento limpa tudo."""
        await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 1.10000)
        await converter.usd_to_sl_price("GBPUSD", 1, 10.0, 0.01, 1.30000)
        converter.invalidate_cache()
        assert len(converter._symbol_cache) == 0

    @pytest.mark.asyncio
    async def test_connector_error_falls_back_to_table(self):
        """Se connector.get_symbol_info falha, usa tabela estática."""
        broken_connector = AsyncMock()
        broken_connector.get_symbol_info.side_effect = Exception("Disconnected")

        converter = PriceConverter(broken_connector)
        sl = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 1.10000)

        # Deve usar DEFAULT_PIP_VALUES["EURUSD"] = 10.0
        assert sl == pytest.approx(1.09000, abs=0.00010)


# ── Default Pip Values Table ─────────────────────────────────────────────────

class TestDefaultPipValues:

    def test_all_majors_present(self):
        """Todos os pares majors devem estar na tabela."""
        majors = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD",
                   "USDJPY", "USDCHF", "USDCAD"]
        for pair in majors:
            assert pair in DEFAULT_PIP_VALUES, f"{pair} faltando na tabela"

    def test_quote_usd_is_10(self):
        """Pares com quote USD devem ter pip_value = 10."""
        for pair in ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]:
            assert DEFAULT_PIP_VALUES[pair] == 10.0

    def test_jpy_pairs_reasonable(self):
        """Pares JPY devem ter pip_value entre 5 e 10."""
        for pair in ["USDJPY", "EURJPY", "GBPJPY"]:
            if pair in DEFAULT_PIP_VALUES:
                assert 5.0 <= DEFAULT_PIP_VALUES[pair] <= 10.0


# ── Sanity: Valores Realistas ────────────────────────────────────────────────

class TestSanityChecks:
    """Verifica que os SL/TP resultantes são realistas para forex."""

    @pytest.mark.asyncio
    async def test_eurusd_sl_10usd_reasonable(self, converter):
        """SL de $10 em 0.01 lot EURUSD deve ser ~100 pips (~0.01000)."""
        price = 1.10000
        sl = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, price)
        distance = abs(price - sl)
        assert 0.005 < distance < 0.020  # 50 a 200 pips (razoável)

    @pytest.mark.asyncio
    async def test_sl_not_equal_to_usd_value(self, converter):
        """
        Teste de regressão: SL NÃO deve ser igual ao valor USD.
        Bug original: sl=10.0 era passado direto como preço.
        """
        sl = await converter.usd_to_sl_price("EURUSD", 1, 10.0, 0.01, 1.10000)
        assert sl != 10.0  # O bug original!
        assert 1.0 < sl < 1.2  # Deve estar perto do preço do EURUSD

    @pytest.mark.asyncio
    async def test_tp_not_equal_to_usd_value(self, converter):
        """TP NÃO deve ser igual ao valor USD."""
        tp = await converter.usd_to_tp_price("EURUSD", 1, 20.0, 0.01, 1.10000)
        assert tp != 20.0
        assert 1.0 < tp < 1.3
