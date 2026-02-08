"""
Oracle Trader v2.0 — Price Converter
======================================

Converte SL/TP financeiro (em USD) para preço absoluto,
conforme requerido pela cTrader Open API.

⚠️ MÓDULO CRÍTICO ⚠️
Sem esta conversão, ordens enviadas com SL/TP em USD são
interpretadas como preço absoluto pela API do broker, resultando
em stops completamente errados (ex: SL=10.0 USD seria interpretado
como stop no nível de preço 10.00000 para EURUSD).

Fórmula geral:
  pip_value_per_lot = f(par, conta_currency)
  pip_value_total   = pip_value_per_lot * volume
  distance_points   = sl_usd / pip_value_total
  sl_price          = current_price ± (distance_points * point_size)

Referência:
  - SPEC_CONNECTOR.md §4.2 (previa _usd_to_pips, não implementada)
  - cTrader Open API: stopLoss/takeProfit são preços absolutos
"""

import logging
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from connector.base import BaseConnector

logger = logging.getLogger("Executor.PriceConverter")


# Pip value por lote padrão (1.0 lot = 100.000 unidades) para conta USD.
# Para pares XXX/USD (quote = USD): pip_value = 10 USD/pip (fixo)
# Para pares USD/XXX (base = USD): pip_value = 10 / rate USD/pip (variável)
# Para pares XXX/YYY (cross):      pip_value = 10 * (USD/YYY rate) USD/pip
#
# Esses defaults são usados como fallback quando symbol_info não está disponível.
DEFAULT_PIP_VALUES: Dict[str, float] = {
    # Majors (quote = USD) — pip_value fixo em 10 USD/pip/lot
    "EURUSD": 10.0,
    "GBPUSD": 10.0,
    "AUDUSD": 10.0,
    "NZDUSD": 10.0,
    # Majors (base = USD) — pip_value aproximado (varia com a taxa)
    "USDJPY": 6.7,
    "USDCHF": 10.5,
    "USDCAD": 7.3,
    # Crosses — aproximações para fallback
    "EURJPY": 6.7,
    "GBPJPY": 6.7,
    "EURGBP": 12.5,
    "AUDCAD": 7.3,
    "AUDNZD": 6.2,
    "AUDJPY": 6.7,
    "NZDJPY": 6.7,
    "CADJPY": 6.7,
    "EURAUD": 6.5,
    "EURCHF": 10.5,
    "EURCAD": 7.3,
    "GBPAUD": 6.5,
    "GBPCAD": 7.3,
    "GBPCHF": 10.5,
}

# Point size padrão por família de par
DEFAULT_POINT_SIZES: Dict[str, float] = {
    "JPY": 0.001,       # Pares com JPY: 3 dígitos
    "DEFAULT": 0.00001,  # Maioria dos pares forex: 5 dígitos
}


class PriceConverter:
    """
    Converte valores financeiros (USD) para distância de preço e vice-versa.

    Usado pelo Executor para converter sl_usd/tp_usd da SymbolConfig
    em preços absolutos antes de enviar ao Connector/broker.

    Usa symbol_info do Connector quando disponível, com fallback para
    tabelas estáticas de pip_value.
    """

    def __init__(self, connector: "BaseConnector"):
        self._connector = connector
        self._symbol_cache: Dict[str, dict] = {}

    async def usd_to_sl_price(
        self,
        symbol: str,
        direction: int,
        sl_usd: float,
        volume: float,
        current_price: float,
    ) -> float:
        """
        Converte Stop Loss em USD para preço absoluto.

        Args:
            symbol: Par forex (ex: "EURUSD").
            direction: 1 = LONG, -1 = SHORT.
            sl_usd: Valor do SL em USD (ex: 10.0).
            volume: Volume em lotes (ex: 0.01).
            current_price: Preço atual do ativo.

        Returns:
            Preço absoluto do SL. 0 se sl_usd <= 0.
        """
        if sl_usd <= 0:
            return 0.0

        distance = await self._usd_to_price_distance(symbol, sl_usd, volume, current_price)
        if distance <= 0:
            return 0.0

        if direction == 1:  # LONG → SL abaixo do preço
            sl_price = current_price - distance
        else:  # SHORT → SL acima do preço
            sl_price = current_price + distance

        point = self._get_point_size(symbol)
        digits = self._get_digits(symbol)
        sl_price = round(sl_price, digits)

        logger.debug(
            f"[{symbol}] SL USD→Price: ${sl_usd} → {distance:.{digits}f} pts "
            f"→ SL={sl_price:.{digits}f} (dir={direction}, vol={volume})"
        )
        return sl_price

    async def usd_to_tp_price(
        self,
        symbol: str,
        direction: int,
        tp_usd: float,
        volume: float,
        current_price: float,
    ) -> float:
        """
        Converte Take Profit em USD para preço absoluto.

        Args:
            symbol: Par forex (ex: "EURUSD").
            direction: 1 = LONG, -1 = SHORT.
            tp_usd: Valor do TP em USD (ex: 20.0).
            volume: Volume em lotes (ex: 0.01).
            current_price: Preço atual do ativo.

        Returns:
            Preço absoluto do TP. 0 se tp_usd <= 0.
        """
        if tp_usd <= 0:
            return 0.0

        distance = await self._usd_to_price_distance(symbol, tp_usd, volume, current_price)
        if distance <= 0:
            return 0.0

        if direction == 1:  # LONG → TP acima do preço
            tp_price = current_price + distance
        else:  # SHORT → TP abaixo do preço
            tp_price = current_price - distance

        digits = self._get_digits(symbol)
        tp_price = round(tp_price, digits)

        logger.debug(
            f"[{symbol}] TP USD→Price: ${tp_usd} → {distance:.{digits}f} pts "
            f"→ TP={tp_price:.{digits}f} (dir={direction}, vol={volume})"
        )
        return tp_price

    async def _usd_to_price_distance(
        self,
        symbol: str,
        usd_value: float,
        volume: float,
        current_price: float,
    ) -> float:
        """
        Converte valor em USD para distância de preço.

        Fórmula:
          pip_value_total = pip_value_per_lot * volume
          distance_pips   = usd_value / pip_value_total
          distance_price  = distance_pips * point_size * 10
            (× 10 porque 1 pip = 10 points para 5 dígitos)

        Para pares JPY (3 dígitos): 1 pip = 10 points (0.01 = 10 × 0.001)
        Para outros (5 dígitos):    1 pip = 10 points (0.0001 = 10 × 0.00001)
        """
        pip_value_per_lot = await self._get_pip_value(symbol, current_price)

        if volume <= 0 or pip_value_per_lot <= 0:
            logger.warning(
                f"[{symbol}] Conversão impossível: vol={volume}, "
                f"pip_value={pip_value_per_lot}"
            )
            return 0.0

        pip_value_total = pip_value_per_lot * volume
        distance_pips = usd_value / pip_value_total
        point_size = self._get_point_size(symbol)

        # 1 pip = 10 points (tanto para 5 dígitos quanto 3 dígitos)
        distance_price = distance_pips * point_size * 10

        return distance_price

    async def _get_pip_value(self, symbol: str, current_price: float) -> float:
        """
        Obtém pip value por lote padrão (1.0 lot).

        Tenta usar symbol_info do Connector, fallback para tabela estática.
        """
        # Tenta cache
        if symbol in self._symbol_cache:
            info = self._symbol_cache[symbol]
            if "pip_value" in info:
                return info["pip_value"]

        # Tenta Connector
        try:
            info = await self._connector.get_symbol_info(symbol)
            if info:
                self._symbol_cache[symbol] = info
                if "pip_value" in info:
                    return info["pip_value"]
        except Exception as e:
            logger.debug(f"[{symbol}] get_symbol_info falhou: {e}")

        # Fallback: tabela estática
        pip_value = DEFAULT_PIP_VALUES.get(symbol)
        if pip_value:
            return pip_value

        # Último recurso: calcular baseado no tipo do par
        return self._estimate_pip_value(symbol, current_price)

    def _estimate_pip_value(self, symbol: str, current_price: float) -> float:
        """
        Estima pip_value quando nem symbol_info nem tabela estão disponíveis.

        Regras simplificadas para conta USD:
          - XXX/USD: pip_value = 10 USD/pip/lot (fixo)
          - USD/XXX: pip_value = 10 / rate USD/pip/lot
          - XXX/YYY: ~10 USD/pip/lot (aproximação conservadora)
        """
        if len(symbol) < 6:
            logger.warning(f"[{symbol}] Símbolo não reconhecido, usando pip_value=10.0")
            return 10.0

        base = symbol[:3]
        quote = symbol[3:6]

        if quote == "USD":
            return 10.0
        elif base == "USD":
            if current_price > 0:
                return 10.0 / current_price
            return 10.0
        else:
            # Cross pair — usar 10.0 como aproximação conservadora
            logger.info(
                f"[{symbol}] Cross pair sem pip_value definido, "
                f"usando estimativa 10.0 USD/pip/lot"
            )
            return 10.0

    def _get_point_size(self, symbol: str) -> float:
        """Retorna point size do par (0.00001 para 5 dígitos, 0.001 para 3)."""
        if symbol in self._symbol_cache:
            info = self._symbol_cache[symbol]
            if "point" in info:
                return info["point"]

        # JPY pairs usam 3 dígitos
        if len(symbol) >= 6 and "JPY" in symbol:
            return DEFAULT_POINT_SIZES["JPY"]
        return DEFAULT_POINT_SIZES["DEFAULT"]

    def _get_digits(self, symbol: str) -> int:
        """Retorna número de casas decimais do par."""
        if symbol in self._symbol_cache:
            info = self._symbol_cache[symbol]
            if "digits" in info:
                return info["digits"]

        if len(symbol) >= 6 and "JPY" in symbol:
            return 3
        return 5

    def invalidate_cache(self, symbol: str = None):
        """Limpa cache de symbol_info (após reconexão, por ex.)."""
        if symbol:
            self._symbol_cache.pop(symbol, None)
        else:
            self._symbol_cache.clear()
