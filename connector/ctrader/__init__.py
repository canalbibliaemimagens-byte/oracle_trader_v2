"""
Oracle Trader v2.0 - cTrader Open API Connector
=================================================

Implementação completa usando ctrader-open-api (Twisted).
"""
try:
    from .client import CTraderConnector
    from .auth import OAuth2Manager
    from .messages import (
        TIMEFRAME_TO_PERIOD,
        build_app_auth_req,
        build_account_auth_req,
        build_trendbars_req,
        build_new_order_req,
        build_close_position_req,
        volume_to_units,
        units_to_volume,
    )
    from .bar_detector import BarDetector
    __all__ = ["CTraderConnector", "OAuth2Manager", "BarDetector",
               "TIMEFRAME_TO_PERIOD", "volume_to_units", "units_to_volume"]
except ImportError as e:
    import logging
    logging.getLogger("Connector.cTrader").warning(
        f"ctrader-open-api não disponível: {e}. Use MockConnector para testes."
    )
    __all__ = []
