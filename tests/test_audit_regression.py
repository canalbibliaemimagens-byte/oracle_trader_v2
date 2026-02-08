"""
Testes de Regressão — Verifica que todas as 12 correções da auditoria estão ativas.

Cada teste aqui corresponde diretamente a um item do AUDIT_REPORT_FINAL.md.
Se algum destes falhar, a correção foi revertida acidentalmente.
"""

import json
import pytest

from oracle_trader_v2.executor.sync_logic import Decision
from oracle_trader_v2.executor.lot_mapper import SymbolConfig
from oracle_trader_v2.executor.risk_guard import RiskGuard
from oracle_trader_v2.persistence.supabase_client import SupabaseClient
from .helpers import make_account


class TestAuditC2_RiskInJson:
    """C2: _risk section must exist in executor_symbols.json."""

    def test_risk_section_exists(self):
        with open("config/executor_symbols.json") as f:
            data = json.load(f)
        assert "_risk" in data
        assert data["_risk"]["initial_balance"] > 0
        assert data["_risk"]["dd_limit_pct"] > 0

    def test_risk_guard_loads_from_json(self):
        with open("config/executor_symbols.json") as f:
            data = json.load(f)
        guard = RiskGuard(data["_risk"])
        assert guard.initial_balance == 10000
        assert guard.dd_limit_pct == 5.0


class TestAuditC3_YamlStructure:
    """C3: default.yaml must have all fields Orchestrator expects."""

    def test_yaml_has_required_fields(self):
        import yaml
        with open("config/default.yaml") as f:
            config = yaml.safe_load(f)
        required = [
            "broker", "timeframe", "initial_balance",
            "supabase_url", "supabase_key", "close_on_exit",
        ]
        for field in required:
            assert field in config, f"Missing field: {field}"

    def test_yaml_broker_has_type(self):
        import yaml
        with open("config/default.yaml") as f:
            config = yaml.safe_load(f)
        assert "type" in config["broker"]


class TestAuditS1_DataPopFix:
    """S1: data.get instead of data.pop for _filter keys."""

    @pytest.mark.asyncio
    async def test_filter_keys_preserved_after_execute(self):
        client = SupabaseClient(url="", key="", enabled=False)
        data = {
            "balance": 10000,
            "_filter_key": "session_id",
            "_filter_val": "abc",
        }
        await client._execute("sessions", data, operation="update")
        assert "_filter_key" in data
        assert "_filter_val" in data


class TestAuditS2_SpreadCheck:
    """S2: spread check must actually block when spread is too high."""

    def test_spread_blocks_when_high(self):
        guard = RiskGuard({"initial_balance": 10000})
        guard.update_spread("EURUSD", 5.0)
        cfg = SymbolConfig(max_spread_pips=2.0)
        result = guard._check_spread("EURUSD", cfg)
        assert not result.passed
        assert "SPREAD" in result.reason

    def test_spread_passes_when_low(self):
        guard = RiskGuard({"initial_balance": 10000})
        guard.update_spread("EURUSD", 1.2)
        cfg = SymbolConfig(max_spread_pips=2.0)
        result = guard._check_spread("EURUSD", cfg)
        assert result.passed

    def test_spread_failopen_when_unknown(self):
        guard = RiskGuard({"initial_balance": 10000})
        cfg = SymbolConfig(max_spread_pips=2.0)
        result = guard._check_spread("UNKNOWN", cfg)
        assert result.passed  # fail-open


class TestAuditS3_MaxSpreadInJson:
    """S3: max_spread_pips must exist per symbol in JSON."""

    def test_max_spread_pips_present(self):
        with open("config/executor_symbols.json") as f:
            data = json.load(f)
        for key, val in data.items():
            if not key.startswith("_"):
                assert "max_spread_pips" in val, f"{key} missing max_spread_pips"


class TestAuditS5_NoDecisionOpen:
    """S5: Decision enum must NOT have OPEN value."""

    def test_no_open_decision(self):
        values = [d.value for d in Decision]
        assert "OPEN" not in values

    def test_only_three_decisions(self):
        assert len(Decision) == 3


class TestAuditM2M3_Requirements:
    """M2+M3: psutil and supabase in requirements.txt."""

    def test_requirements_has_psutil(self):
        with open("requirements.txt") as f:
            content = f.read()
        assert "psutil" in content

    def test_requirements_has_supabase(self):
        with open("requirements.txt") as f:
            content = f.read()
        assert "supabase" in content
