"""
Oracle Trader v2.0 — Lifecycle
================================

Funções auxiliares de startup (bootstrap) e shutdown.
Ordem de inicialização é crítica — ver SPEC_ORCHESTRATOR.md §4.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict

import yaml

logger = logging.getLogger("Lifecycle")


def install_twisted_reactor():
    """
    Instala asyncioreactor do Twisted ANTES de qualquer import do reactor.

    ┌─────────────────────────────────────────────────────────────────────┐
    │  BRIDGE TWISTED→ASYNCIO                                             │
    │                                                                     │
    │  Esta função é o ponto de entrada da bridge entre os dois mundos:  │
    │                                                                     │
    │  - O SDK ctrader-open-api usa Twisted (reactor + Deferreds)        │
    │  - O Oracle Trader v2 usa asyncio (event loop + coroutines)        │
    │                                                                     │
    │  asyncioreactor substitui o reactor padrão do Twisted por um que   │
    │  roda DENTRO do event loop do asyncio. Com isso:                   │
    │    - Deferred.asFuture(loop) converte Deferred → asyncio.Future   │
    │    - O CTraderConnector expõe métodos async normais               │
    │    - Orchestrator/Executor usam await sem saber do Twisted         │
    │                                                                     │
    │  DEVE ser chamado ANTES de qualquer import de:                     │
    │    - twisted.internet.reactor                                       │
    │    - ctrader_open_api (que importa reactor internamente)           │
    │                                                                     │
    │  Chamado por: orchestrator/cli.py (entry point da aplicação)       │
    │  Docs: docs/notas/CONNECTOR_BRIDGE_PATTERN.md                      │
    └─────────────────────────────────────────────────────────────────────┘
    """
    try:
        from twisted.internet import asyncioreactor
        asyncioreactor.install()
        logger.info("asyncioreactor instalado (Twisted bridge ativo)")
    except Exception as e:
        logger.warning(f"asyncioreactor não disponível: {e}. cTrader connector não funcionará.")


def load_config(config_path: str) -> dict:
    """
    Carrega configuração YAML com expansão de variáveis de ambiente.

    Suporta ${VAR} e ${VAR:default} no YAML.
    """
    with open(config_path) as f:
        raw = f.read()

    # Expande ${VAR} e ${VAR:default}
    def _expand(match):
        var = match.group(1)
        if ":" in var:
            name, default = var.split(":", 1)
            return os.environ.get(name, default)
        return os.environ.get(var, match.group(0))

    expanded = re.sub(r"\$\{([^}]+)\}", _expand, raw)
    config = yaml.safe_load(expanded)
    return config or {}


def setup_logging(config: dict):
    """Configura logging a partir da config."""
    level = config.get("logging", {}).get("level", "INFO")
    log_file = config.get("logging", {}).get("log_file")

    handlers = [logging.StreamHandler()]

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
        force=True,
    )
