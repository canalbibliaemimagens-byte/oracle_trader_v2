"""
Testes: orchestrator/ — lifecycle, health
"""

import os
import pytest
import time
import yaml
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from oracle_trader_v2.orchestrator.lifecycle import load_config, setup_logging
from oracle_trader_v2.orchestrator.health import HealthMonitor


# ═══════════════════════════════════════════════════════════════════════════
# lifecycle.py — load_config
# ═══════════════════════════════════════════════════════════════════════════

class TestLoadConfig:

    def test_load_basic_yaml(self, tmp_path):
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("version: '2.0'\ntimeframe: M15\n")
        config = load_config(str(cfg_file))
        assert config["version"] == "2.0"
        assert config["timeframe"] == "M15"

    def test_env_var_expansion(self, tmp_path):
        os.environ["TEST_ORACLE_KEY"] = "secret123"
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("api_key: '${TEST_ORACLE_KEY}'")
        config = load_config(str(cfg_file))
        assert config["api_key"] == "secret123"
        del os.environ["TEST_ORACLE_KEY"]

    def test_env_var_with_default(self, tmp_path):
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("port: '${NONEXISTENT_VAR:8080}'")
        config = load_config(str(cfg_file))
        assert config["port"] == "8080"

    def test_env_var_missing_no_default(self, tmp_path):
        cfg_file = tmp_path / "test.yaml"
        cfg_file.write_text("key: '${REALLY_MISSING_VAR}'")
        config = load_config(str(cfg_file))
        # Should keep the raw ${VAR} as-is
        assert "${REALLY_MISSING_VAR}" in config["key"]

    def test_empty_yaml(self, tmp_path):
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("")
        config = load_config(str(cfg_file))
        assert config == {}

    def test_nested_config(self, tmp_path):
        cfg_file = tmp_path / "nested.yaml"
        cfg_file.write_text("broker:\n  type: mock\n  env: demo\n")
        config = load_config(str(cfg_file))
        assert config["broker"]["type"] == "mock"


class TestSetupLogging:

    def test_setup_basic(self, tmp_path):
        config = {"logging": {"level": "DEBUG"}}
        setup_logging(config)
        import logging
        assert logging.getLogger().level <= logging.DEBUG

    def test_setup_with_file(self, tmp_path):
        log_file = str(tmp_path / "logs" / "test.log")
        config = {"logging": {"level": "INFO", "log_file": log_file}}
        setup_logging(config)
        assert Path(log_file).parent.exists()

    def test_setup_empty_config(self):
        # Should not crash
        setup_logging({})


# ═══════════════════════════════════════════════════════════════════════════
# health.py — HealthMonitor
# ═══════════════════════════════════════════════════════════════════════════

class TestHealthMonitor:

    @pytest.fixture
    def monitor(self):
        orchestrator = MagicMock()
        orchestrator.connector = MagicMock()
        orchestrator.connector.is_connected.return_value = True
        orchestrator.persistence = MagicMock()
        type(orchestrator.persistence).pending_count = PropertyMock(return_value=0)
        orchestrator.session_manager = MagicMock()
        orchestrator.session_manager.start_time = MagicMock()
        orchestrator.session_manager.start_time.timestamp.return_value = time.time() - 60
        return HealthMonitor(orchestrator)

    def test_healthy_state(self, monitor):
        monitor.update("EURUSD")
        result = monitor.check()
        assert result["healthy"] is True
        assert result["issues"] == []

    def test_connector_disconnected(self, monitor):
        monitor.orchestrator.connector.is_connected.return_value = False
        result = monitor.check()
        assert not result["healthy"]
        assert any("desconectado" in i for i in result["issues"])

    def test_symbol_heartbeat_timeout(self, monitor):
        monitor._symbol_heartbeats["EURUSD"] = time.time() - 600  # 10 min ago
        result = monitor.check()
        assert not result["healthy"]
        assert any("EURUSD" in i for i in result["issues"])

    def test_persistence_pending_warning(self, monitor):
        type(monitor.orchestrator.persistence).pending_count = PropertyMock(return_value=200)
        result = monitor.check()
        assert not result["healthy"]
        assert any("pendentes" in i for i in result["issues"])

    def test_memory_in_result(self, monitor):
        result = monitor.check()
        assert "memory_mb" in result
        assert isinstance(result["memory_mb"], float)

    def test_uptime_in_result(self, monitor):
        result = monitor.check()
        assert "uptime_s" in result
        assert result["uptime_s"] >= 0

    def test_update_and_check_heartbeat(self, monitor):
        monitor.update("EURUSD")
        result = monitor.check()
        assert result["healthy"]

    def test_reset_symbol(self, monitor):
        monitor.update("EURUSD")
        monitor.reset_symbol("EURUSD")
        assert "EURUSD" not in monitor._symbol_heartbeats

    def test_get_memory_fallback(self):
        """Test memory reading even without psutil."""
        mb = HealthMonitor._get_memory_mb()
        assert isinstance(mb, float)
        assert mb >= 0
