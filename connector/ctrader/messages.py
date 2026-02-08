"""
Oracle Trader v2.0 - cTrader Protobuf Message Helpers
======================================================

Wrappers para construir e parsear mensagens da cTrader Open API.
Converte entre protobuf nativo e modelos do core (Bar, Position, etc).

Usa:
  - ctrader_open_api.Protobuf para construção de mensagens
  - ctrader_open_api.messages.OpenApiMessages_pb2 para tipos
  - ctrader_open_api.messages.OpenApiModelMessages_pb2 para modelos
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger("Connector.cTrader.Messages")

# Mapeamento de timeframe string → ProtoOATrendbarPeriod enum value
TIMEFRAME_TO_PERIOD: Dict[str, int] = {
    "M1": 1,
    "M2": 2,
    "M3": 3,
    "M4": 4,
    "M5": 5,
    "M10": 6,
    "M15": 7,
    "M30": 8,
    "H1": 9,
    "H4": 10,
    "H12": 11,
    "D1": 12,
    "W1": 13,
    "MN1": 14,
}

PERIOD_TO_TIMEFRAME: Dict[int, str] = {v: k for k, v in TIMEFRAME_TO_PERIOD.items()}


def build_app_auth_req(client_id: str, client_secret: str) -> "ProtoMessage":
    """
    Constrói ProtoOAApplicationAuthReq.

    Primeiro passo da autenticação: identifica a aplicação.
    """
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAApplicationAuthReq
    from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAPayloadType

    msg = ProtoOAApplicationAuthReq()
    msg.clientId = client_id
    msg.clientSecret = client_secret

    return Protobuf.extract(msg)


def build_account_auth_req(access_token: str, account_id: int) -> "ProtoMessage":
    """
    Constrói ProtoOAAccountAuthReq.

    Segundo passo: autentica uma conta específica.
    """
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAccountAuthReq

    msg = ProtoOAAccountAuthReq()
    msg.accessToken = access_token
    msg.ctidTraderAccountId = int(account_id)

    return Protobuf.extract(msg)


def build_symbols_list_req(account_id: int) -> "ProtoMessage":
    """Constrói ProtoOASymbolsListReq para obter todos os símbolos."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASymbolsListReq

    msg = ProtoOASymbolsListReq()
    msg.ctidTraderAccountId = int(account_id)

    return Protobuf.extract(msg)


def build_symbol_by_id_req(account_id: int, symbol_ids: List[int]) -> "ProtoMessage":
    """Constrói ProtoOASymbolByIdReq para detalhes de símbolos específicos."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASymbolByIdReq

    msg = ProtoOASymbolByIdReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.symbolId.extend(symbol_ids)

    return Protobuf.extract(msg)


def build_trendbars_req(
    account_id: int,
    symbol_id: int,
    timeframe: str,
    from_timestamp_ms: int,
    to_timestamp_ms: int,
) -> "ProtoMessage":
    """
    Constrói ProtoOAGetTrendbarsReq para baixar barras históricas.

    Args:
        account_id: ID da conta cTrader.
        symbol_id: ID numérico do símbolo.
        timeframe: String do timeframe (ex: "M15").
        from_timestamp_ms: Timestamp início em MILIssegundos.
        to_timestamp_ms: Timestamp fim em MILIssegundos.
    """
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAGetTrendbarsReq

    msg = ProtoOAGetTrendbarsReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.symbolId = symbol_id
    msg.period = TIMEFRAME_TO_PERIOD[timeframe]
    msg.fromTimestamp = from_timestamp_ms
    msg.toTimestamp = to_timestamp_ms

    return Protobuf.extract(msg)


def build_subscribe_spots_req(account_id: int, symbol_ids: List[int]) -> "ProtoMessage":
    """Constrói ProtoOASubscribeSpotsReq para receber ticks em tempo real."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASubscribeSpotsReq

    msg = ProtoOASubscribeSpotsReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.symbolId.extend(symbol_ids)

    return Protobuf.extract(msg)


def build_subscribe_live_trendbar_req(
    account_id: int, symbol_id: int, timeframe: str
) -> "ProtoMessage":
    """Constrói ProtoOASubscribeLiveTrendbarReq para barras em tempo real."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOASubscribeLiveTrendbarReq

    msg = ProtoOASubscribeLiveTrendbarReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.symbolId = symbol_id
    msg.period = TIMEFRAME_TO_PERIOD[timeframe]

    return Protobuf.extract(msg)


def build_new_order_req(
    account_id: int,
    symbol_id: int,
    direction: int,
    volume_units: int,
    sl_price: float = 0,
    tp_price: float = 0,
    comment: str = "",
) -> "ProtoMessage":
    """
    Constrói ProtoOANewOrderReq (ordem a mercado).

    Args:
        account_id: ID da conta.
        symbol_id: ID do símbolo.
        direction: 1 = BUY, -1 = SELL.
        volume_units: Volume em centavos de lote (0.01 lot = 1000 units).
        sl_price: Stop Loss em preço absoluto (0 = sem SL).
        tp_price: Take Profit em preço absoluto (0 = sem TP).
        comment: Comentário (max 100 chars).
    """
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOANewOrderReq

    msg = ProtoOANewOrderReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.symbolId = symbol_id
    msg.orderType = 1  # MARKET
    msg.tradeSide = 1 if direction == 1 else 2  # BUY=1, SELL=2
    msg.volume = volume_units
    msg.comment = comment[:100] if comment else ""

    if sl_price > 0:
        msg.stopLoss = sl_price
    if tp_price > 0:
        msg.takeProfit = tp_price

    return Protobuf.extract(msg)


def build_close_position_req(
    account_id: int,
    position_id: int,
    volume_units: int,
) -> "ProtoMessage":
    """
    Constrói ProtoOAClosePositionReq.

    Args:
        position_id: ID da posição a fechar.
        volume_units: Volume a fechar em centavos (0 = não suportado, precisa passar volume total).
    """
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAClosePositionReq

    msg = ProtoOAClosePositionReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.positionId = position_id
    msg.volume = volume_units

    return Protobuf.extract(msg)


def build_amend_position_sltp_req(
    account_id: int,
    position_id: int,
    sl_price: float = 0,
    tp_price: float = 0,
) -> "ProtoMessage":
    """Constrói ProtoOAAmendPositionSLTPReq."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAAmendPositionSLTPReq

    msg = ProtoOAAmendPositionSLTPReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.positionId = position_id

    if sl_price > 0:
        msg.stopLoss = sl_price
    if tp_price > 0:
        msg.takeProfit = tp_price

    return Protobuf.extract(msg)


def build_reconcile_req(account_id: int) -> "ProtoMessage":
    """Constrói ProtoOAReconcileReq para sincronizar posições/ordens."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOAReconcileReq

    msg = ProtoOAReconcileReq()
    msg.ctidTraderAccountId = int(account_id)

    return Protobuf.extract(msg)


def build_trader_req(account_id: int) -> "ProtoMessage":
    """Constrói ProtoOATraderReq para obter informações da conta."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOATraderReq

    msg = ProtoOATraderReq()
    msg.ctidTraderAccountId = int(account_id)

    return Protobuf.extract(msg)


def build_deal_list_req(account_id: int, from_ts_ms: int, to_ts_ms: int) -> "ProtoMessage":
    """Constrói ProtoOADealListReq para histórico de deals."""
    from ctrader_open_api import Protobuf
    from ctrader_open_api.messages.OpenApiMessages_pb2 import ProtoOADealListReq

    msg = ProtoOADealListReq()
    msg.ctidTraderAccountId = int(account_id)
    msg.fromTimestamp = from_ts_ms
    msg.toTimestamp = to_ts_ms

    return Protobuf.extract(msg)


# =========================================================================
# PARSERS: Protobuf → Core models
# =========================================================================

def parse_trendbars(response, symbol_name: str) -> List:
    """
    Parseia resposta de ProtoOAGetTrendbarsRes para lista de Bar.

    Args:
        response: Mensagem protobuf response.
        symbol_name: Nome do símbolo (para incluir no Bar).

    Returns:
        Lista de core.models.Bar.
    """
    from core.models import Bar

    bars = []
    if not hasattr(response, 'trendbar'):
        return bars

    for tb in response.trendbar:
        # cTrader retorna preços como inteiros (multiplicados por 100000 para forex)
        # O deltaOpen, deltaClose, etc. são deltas relativos ao low
        low = tb.low / 100000.0 if tb.low else 0
        bar = Bar(
            symbol=symbol_name,
            time=int(tb.utcTimestampInMinutes * 60) if hasattr(tb, 'utcTimestampInMinutes') else int(tb.timestamp / 1000),
            open=low + (tb.deltaOpen / 100000.0 if hasattr(tb, 'deltaOpen') else 0),
            high=low + (tb.deltaHigh / 100000.0 if hasattr(tb, 'deltaHigh') else 0),
            low=low,
            close=low + (tb.deltaClose / 100000.0 if hasattr(tb, 'deltaClose') else 0),
            volume=float(tb.volume) if hasattr(tb, 'volume') else 0,
        )
        bars.append(bar)

    # Ordenar por timestamp (mais antigo primeiro)
    bars.sort(key=lambda b: b.time)
    return bars


def parse_positions(response) -> List:
    """Parseia ProtoOAReconcileRes para lista de core.models.Position."""
    from core.models import Position

    positions = []
    if not hasattr(response, 'position'):
        return positions

    for pos in response.position:
        direction = 1 if pos.tradeData.tradeSide == 1 else -1  # BUY=1 → LONG, SELL=2 → SHORT
        positions.append(Position(
            ticket=pos.positionId,
            symbol=str(pos.tradeData.symbolId),  # Será mapeado para nome pelo SymbolMapper
            direction=direction,
            volume=units_to_volume(pos.tradeData.volume),  # cTrader units → lotes (100000 units = 1.00 lot)
            open_price=pos.price / 100000.0 if pos.price else 0,
            current_price=0,  # Será atualizado via spots
            pnl=0,  # Será calculado
            sl=pos.stopLoss / 100000.0 if hasattr(pos, 'stopLoss') and pos.stopLoss else 0,
            tp=pos.takeProfit / 100000.0 if hasattr(pos, 'takeProfit') and pos.takeProfit else 0,
            open_time=int(pos.tradeData.openTimestamp / 1000) if pos.tradeData.openTimestamp else 0,
            comment=pos.tradeData.comment if hasattr(pos.tradeData, 'comment') else "",
        ))

    return positions


def volume_to_units(lots: float) -> int:
    """
    Converte lotes para unidades cTrader.

    cTrader usa centavos de lote:
      0.01 lot = 1000 units
      1.00 lot = 100000 units

    Args:
        lots: Volume em lotes (ex: 0.01, 0.03, 0.05).

    Returns:
        Volume em unidades cTrader (int).
    """
    return int(round(lots * 100000))


def units_to_volume(units: int) -> float:
    """
    Converte unidades cTrader para lotes.

    Args:
        units: Volume em unidades cTrader.

    Returns:
        Volume em lotes.
    """
    return units / 100000.0
