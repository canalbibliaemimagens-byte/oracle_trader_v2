"""
Oracle Trader v2.0 - Core
==========================

Núcleo compartilhado: constantes, modelos de dados, ações, features e utils.
NENHUMA dependência de I/O, rede ou libs externas complexas (exceto numpy/pandas).
"""

from .constants import (
    VERSION,
    Direction,
    Timeframe,
    TIMEFRAME_SECONDS,
    TRAINING_LOT_SIZES,
    MIN_BARS_FOR_PREDICTION,
    WARMUP_BARS,
)
from .actions import (
    Action,
    ACTIONS_MAP,
    ACTION_TO_INDEX,
    action_from_index,
    get_direction,
    get_intensity,
    get_action_properties,
)
from .models import (
    Bar,
    Signal,
    AccountInfo,
    Position,
    OrderResult,
    VirtualPosition,
)
from .features import FeatureCalculator, calc_atr
from .utils import bars_to_dataframe, timestamp_to_datetime, datetime_to_timestamp

__all__ = [
    "VERSION", "Direction", "Timeframe", "TIMEFRAME_SECONDS",
    "TRAINING_LOT_SIZES", "MIN_BARS_FOR_PREDICTION", "WARMUP_BARS",
    "Action", "ACTIONS_MAP", "ACTION_TO_INDEX",
    "action_from_index", "get_direction", "get_intensity", "get_action_properties",
    "Bar", "Signal", "AccountInfo", "Position", "OrderResult", "VirtualPosition",
    "FeatureCalculator", "calc_atr",
    "bars_to_dataframe", "timestamp_to_datetime", "datetime_to_timestamp",
]
