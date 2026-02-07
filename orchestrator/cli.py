"""
Oracle Trader v2.0 — CLI
==========================

Entry point de linha de comando.

Uso:
  python -m oracle_trader_v2 --config config/default.yaml
  python -m oracle_trader_v2 --dry-run
  python -m oracle_trader_v2 --log-level DEBUG
"""

import argparse
import asyncio
import logging
import sys


def main():
    """Entry point da CLI."""
    parser = argparse.ArgumentParser(description="Oracle Trader v2.0")

    parser.add_argument(
        "--config",
        "-c",
        default="config/default.yaml",
        help="Caminho para arquivo de configuração",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de log",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo dry-run (não executa ordens reais)",
    )

    args = parser.parse_args()

    # Logging básico (será reconfigurado pelo lifecycle)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ⚠️ CRÍTICO: Instala asyncioreactor ANTES de qualquer import Twisted.
    # Sem isso, o reactor padrão do Twisted é incompatível com asyncio
    # e o CTraderConnector não consegue fazer a bridge Deferred→Future.
    # Ver: docs/notas/CONNECTOR_BRIDGE_PATTERN.md
    from .lifecycle import install_twisted_reactor
    install_twisted_reactor()

    # Importar Orchestrator DEPOIS de instalar reactor
    # (Orchestrator importa Connector que importa ctrader-open-api que importa reactor)

    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(config_path=args.config)

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        orchestrator.setup_signal_handlers()
        loop.run_until_complete(orchestrator.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logging.error(f"Erro fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
