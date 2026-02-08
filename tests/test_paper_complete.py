"""
Testes: paper/ — PaperAccount, PaperTrader, stats
"""

import pytest

from oracle_trader_v2.paper.account import PaperAccount, PaperPosition, PaperTrade
from oracle_trader_v2.paper.paper_trader import PaperTrader
from oracle_trader_v2.paper.stats import (
    calculate_sharpe, calculate_max_drawdown, calculate_profit_factor,
)
from oracle_trader_v2.core.models import Bar, Signal
from .helpers import make_bar, make_signal


# ═══════════════════════════════════════════════════════════════════════════
# PaperAccount
# ═══════════════════════════════════════════════════════════════════════════

class TestPaperAccount:

    @pytest.fixture
    def account(self, training_config):
        return PaperAccount(initial_balance=10000, training_config=training_config)

    def test_initial_state(self, account):
        assert account.balance == 10000
        assert account.equity == 10000
        assert len(account.positions) == 0
        assert len(account.closed_trades) == 0

    def test_open_position_long(self, account):
        result = account.open_position("EURUSD", 1, 1, 1.10000, 1000.0)
        assert result is True
        assert "EURUSD" in account.positions
        pos = account.positions["EURUSD"]
        assert pos.direction == 1
        assert pos.volume == 0.01
        # Entry price should include spread + slippage
        expected_entry = 1.10000 + 7 * 0.00001 + 2 * 0.00001
        assert abs(pos.entry_price - expected_entry) < 1e-10

    def test_open_position_short(self, account):
        account.open_position("EURUSD", -1, 1, 1.10000, 1000.0)
        pos = account.positions["EURUSD"]
        expected_entry = 1.10000 - 7 * 0.00001 - 2 * 0.00001
        assert abs(pos.entry_price - expected_entry) < 1e-10

    def test_open_duplicate_fails(self, account):
        account.open_position("EURUSD", 1, 1, 1.10000, 1000.0)
        result = account.open_position("EURUSD", -1, 1, 1.10000, 1001.0)
        assert result is False

    def test_open_invalid_intensity(self, account):
        assert account.open_position("EURUSD", 1, -1, 1.1, 0) is False
        assert account.open_position("EURUSD", 1, 10, 1.1, 0) is False

    def test_open_zero_volume_intensity(self, account):
        # intensity 0 → lot_sizes[0] = 0 → volume <= 0
        result = account.open_position("EURUSD", 1, 0, 1.10000, 1000.0)
        assert result is False

    def test_close_position(self, account):
        account.open_position("EURUSD", 1, 1, 1.10000, 1000.0)
        trade = account.close_position("EURUSD", 1.10100, 2000.0, hmm_state=3)
        assert trade is not None
        assert isinstance(trade, PaperTrade)
        assert trade.symbol == "EURUSD"
        assert trade.hmm_state == 3
        assert "EURUSD" not in account.positions
        assert len(account.closed_trades) == 1

    def test_close_nonexistent(self, account):
        result = account.close_position("GBPUSD", 1.1, 0, 0)
        assert result is None

    def test_commission_deducted(self, account):
        initial = account.balance
        account.open_position("EURUSD", 1, 1, 1.10000, 0)
        # Entry commission = 7.0 * 0.01 / 2 = 0.035
        assert account.balance < initial

    def test_pnl_calculation_long_profit(self, account):
        account.open_position("EURUSD", 1, 2, 1.10000, 0)
        trade = account.close_position("EURUSD", 1.11000, 1000, 0)
        # Price moved 100 pips up for LONG → profit
        assert trade.pnl > 0
        assert trade.pnl_pips > 0

    def test_pnl_calculation_long_loss(self, account):
        account.open_position("EURUSD", 1, 2, 1.10000, 0)
        trade = account.close_position("EURUSD", 1.09000, 1000, 0)
        assert trade.pnl < 0

    def test_update_equity(self, account):
        account.open_position("EURUSD", 1, 1, 1.10000, 0)
        account.update_equity({"EURUSD": 1.11000})
        assert account.equity > account.balance  # Floating profit

    def test_commission_total_tracks(self, account):
        account.open_position("EURUSD", 1, 1, 1.10000, 0)
        account.close_position("EURUSD", 1.10100, 1000, 0)
        # Entry + exit commission
        assert account.total_commission > 0


# ═══════════════════════════════════════════════════════════════════════════
# PaperTrader
# ═══════════════════════════════════════════════════════════════════════════

class TestPaperTrader:

    @pytest.fixture
    def trader(self, training_config):
        pt = PaperTrader(initial_balance=10000)
        pt.load_config("EURUSD", training_config)
        return pt

    def test_load_config(self, trader):
        assert "EURUSD" in trader.accounts

    def test_process_signal_open(self, trader):
        s = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        bar = make_bar(close=1.10000)
        trade = trader.process_signal(s, bar)
        assert trade is None  # Opening, no closed trade
        assert "EURUSD" in trader.accounts["EURUSD"].positions

    def test_process_signal_close(self, trader):
        s1 = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        bar1 = make_bar(close=1.10000)
        trader.process_signal(s1, bar1)

        s2 = make_signal(direction=0, intensity=0, action="WAIT")
        bar2 = make_bar(close=1.10100, offset=1)
        trade = trader.process_signal(s2, bar2)
        assert trade is not None
        assert isinstance(trade, PaperTrade)

    def test_process_signal_reverse(self, trader):
        s1 = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        trader.process_signal(s1, make_bar(close=1.10000))

        s2 = make_signal(direction=-1, intensity=2, action="SHORT_MODERATE")
        trade = trader.process_signal(s2, make_bar(close=1.10050, offset=1))
        assert trade is not None  # Closed LONG
        # Should have opened SHORT
        assert "EURUSD" in trader.accounts["EURUSD"].positions
        pos = trader.accounts["EURUSD"].positions["EURUSD"]
        assert pos.direction == -1

    def test_process_signal_same_noop(self, trader):
        s = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        trader.process_signal(s, make_bar(close=1.10000))
        trade = trader.process_signal(s, make_bar(close=1.10050, offset=1))
        assert trade is None  # Same signal → NOOP

    def test_process_signal_intensity_change(self, trader):
        """S4 fix: intensity change with same direction should close+reopen."""
        s1 = make_signal(direction=1, intensity=1, action="LONG_WEAK")
        trader.process_signal(s1, make_bar(close=1.10000))

        s2 = make_signal(direction=1, intensity=3, action="LONG_STRONG")
        trade = trader.process_signal(s2, make_bar(close=1.10050, offset=1))
        assert trade is not None  # Should close WEAK and open STRONG

    def test_process_signal_unknown_symbol(self, trader):
        s = make_signal(symbol="GBPUSD")
        result = trader.process_signal(s, make_bar(symbol="GBPUSD"))
        assert result is None

    def test_get_metrics_empty(self, trader):
        m = trader.get_metrics()
        assert m["total_trades"] == 0

    def test_get_metrics_with_trades(self, trader):
        s1 = make_signal(direction=1, intensity=1)
        trader.process_signal(s1, make_bar(close=1.10000))
        s2 = make_signal(direction=0, intensity=0, action="WAIT")
        trader.process_signal(s2, make_bar(close=1.10100, offset=1))

        m = trader.get_metrics()
        assert m["total_trades"] == 1
        assert "win_rate" in m
        assert "total_commission" in m

    def test_get_trades(self, trader):
        s1 = make_signal(direction=1, intensity=1)
        trader.process_signal(s1, make_bar(close=1.10000))
        s2 = make_signal(direction=0, intensity=0, action="WAIT")
        trader.process_signal(s2, make_bar(close=1.10100, offset=1))

        trades = trader.get_trades("EURUSD")
        assert len(trades) == 1

    def test_get_trades_all(self, trader):
        trades = trader.get_trades()
        assert isinstance(trades, list)

    def test_compare_with_real(self, trader):
        s1 = make_signal(direction=1, intensity=1)
        trader.process_signal(s1, make_bar(close=1.10000))
        s2 = make_signal(direction=0, intensity=0, action="WAIT")
        trader.process_signal(s2, make_bar(close=1.10100, offset=1))

        real = [{"pnl": 5.0}]
        report = trader.compare_with_real(real)
        assert "paper_pnl" in report
        assert "real_pnl" in report
        assert "pnl_drift" in report

    def test_compare_with_real_empty(self, trader):
        report = trader.compare_with_real([])
        assert report["paper_trades"] == 0
        assert report["real_trades"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# stats.py
# ═══════════════════════════════════════════════════════════════════════════

class TestStats:

    def _make_trades(self, pnls):
        return [
            PaperTrade(
                symbol="EURUSD", direction=1, intensity=1, volume=0.01,
                entry_price=1.1, exit_price=1.1, entry_time=0, exit_time=0,
                pnl=p, pnl_pips=0, commission=0, hmm_state=0,
            )
            for p in pnls
        ]

    def test_sharpe_empty(self):
        assert calculate_sharpe([]) == 0.0

    def test_sharpe_one_trade(self):
        trades = self._make_trades([10])
        assert calculate_sharpe(trades) == 0.0

    def test_sharpe_positive(self):
        trades = self._make_trades([10, 20, 15, 25, 10])
        result = calculate_sharpe(trades)
        assert result > 0

    def test_sharpe_constant_returns(self):
        trades = self._make_trades([5, 5, 5, 5])
        result = calculate_sharpe(trades)
        assert result == 0.0  # std=0 → 0

    def test_max_drawdown_empty(self):
        assert calculate_max_drawdown([], 10000) == 0.0

    def test_max_drawdown_no_loss(self):
        trades = self._make_trades([10, 20, 30])
        assert calculate_max_drawdown(trades, 10000) == 0.0

    def test_max_drawdown_with_loss(self):
        trades = self._make_trades([100, -50, -30, 200])
        dd = calculate_max_drawdown(trades, 10000)
        assert dd > 0

    def test_profit_factor_no_trades(self):
        assert calculate_profit_factor([]) == 0.0

    def test_profit_factor_all_wins(self):
        trades = self._make_trades([10, 20])
        assert calculate_profit_factor(trades) == float("inf")

    def test_profit_factor_mixed(self):
        trades = self._make_trades([100, -50, 80, -30])
        pf = calculate_profit_factor(trades)
        assert pf == pytest.approx(180 / 80, abs=0.01)

    def test_profit_factor_all_losses(self):
        trades = self._make_trades([-10, -20])
        assert calculate_profit_factor(trades) == 0.0
