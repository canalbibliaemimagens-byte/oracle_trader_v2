"""
Fixtures compartilhadas para toda a suíte de testes.
"""

import json
import time
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from oracle_trader_v2.core.models import (
    AccountInfo, Bar, OrderResult, Position, Signal, VirtualPosition,
)
from oracle_trader_v2.connector.mock.client import MockConnector


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_bar(
    symbol="EURUSD", close=1.10000, offset=0, volume=500.0,
    open_=None, high=None, low=None,
):
    """Cria Bar de teste com defaults razoáveis."""
    o = open_ or close - 0.0001
    h = high or close + 0.0002
    lo = low or close - 0.0003
    return Bar(
        symbol=symbol,
        time=1700000000 + offset * 900,
        open=o, high=h, low=lo, close=close,
        volume=volume,
    )


def make_bars(symbol="EURUSD", n=400, base_price=1.10000):
    """Gera lista de N barras sequenciais com variação realista."""
    import numpy as np
    np.random.seed(42)
    bars = []
    price = base_price
    for i in range(n):
        change = np.random.randn() * 0.0003
        o = price
        c = round(price + change, 5)
        h = round(max(o, c) + abs(np.random.randn() * 0.0001), 5)
        lo = round(min(o, c) - abs(np.random.randn() * 0.0001), 5)
        bars.append(Bar(
            symbol=symbol,
            time=1700000000 + i * 900,
            open=o, high=h, low=lo, close=c,
            volume=float(np.random.randint(100, 1000)),
        ))
        price = c
    return bars


def make_signal(
    symbol="EURUSD", action="LONG_WEAK", direction=1, intensity=1,
    hmm_state=2, virtual_pnl=0.0,
):
    """Cria Signal de teste."""
    return Signal(
        symbol=symbol,
        action=action,
        direction=direction,
        intensity=intensity,
        hmm_state=hmm_state,
        virtual_pnl=virtual_pnl,
        timestamp=time.time(),
    )


def make_account(balance=10000, equity=10000, free_margin=9000):
    """Cria AccountInfo de teste."""
    return AccountInfo(
        balance=balance, equity=equity,
        margin=equity - free_margin,
        free_margin=free_margin,
        margin_level=0, currency="USD",
    )


def make_position(symbol="EURUSD", direction=1, ticket=1000, pnl=0.0):
    """Cria Position de teste."""
    return Position(
        ticket=ticket, symbol=symbol, direction=direction,
        volume=0.01, open_price=1.10000, current_price=1.10010,
        pnl=pnl, sl=0, tp=0, open_time=int(time.time()), comment="",
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_connector():
    return MockConnector(initial_balance=10000.0)


@pytest.fixture
def sample_bars():
    return make_bars("EURUSD", 400)


@pytest.fixture
def sample_signal():
    return make_signal()


@pytest.fixture
def sample_account():
    return make_account()


@pytest.fixture
def tmp_config(tmp_path):
    """Cria executor_symbols.json temporário com _risk."""
    config = {
        "_comment": "test",
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
            "tp_usd": 0,
            "max_spread_pips": 2.0,
        },
        "GBPUSD": {
            "enabled": False,
            "lot_weak": 0.01,
            "lot_moderate": 0.03,
            "lot_strong": 0.05,
            "sl_usd": 15.0,
            "tp_usd": 0,
            "max_spread_pips": 3.0,
        },
    }
    path = tmp_path / "executor_symbols.json"
    path.write_text(json.dumps(config))
    return str(path)


@pytest.fixture
def tmp_yaml_config(tmp_path):
    """Cria default.yaml temporário."""
    yaml_content = """
version: "2.0"
broker:
  type: "mock"
timeframe: "M15"
initial_balance: 10000
close_on_exit: false
close_on_day_change: false
preditor:
  models_dir: "./models"
  warmup_bars: 1000
  min_bars: 350
  buffer_size: 350
executor:
  config_file: "{config_file}"
paper:
  enabled: true
persistence:
  enabled: false
supabase_url: ""
supabase_key: ""
logging:
  level: "DEBUG"
"""
    path = tmp_path / "default.yaml"
    path.write_text(yaml_content)
    return str(path)


@pytest.fixture
def training_config():
    """Config de treino padrão."""
    return {
        "spread_points": 7,
        "slippage_points": 2,
        "commission_per_lot": 7.0,
        "point": 0.00001,
        "pip_value": 10.0,
        "lot_sizes": [0, 0.01, 0.03, 0.05],
        "digits": 5,
    }
