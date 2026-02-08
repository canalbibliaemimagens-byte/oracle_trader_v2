"""
Oracle Trader v2.0 — CLI
==========================

Entry point de linha de comando.

Uso:
  python -m orchestrator --config config/default.yaml
  python -m orchestrator --dry-run
  python -m orchestrator --log-level DEBUG
"""

import argparse
import asyncio
import logging
import sys
from dotenv import load_dotenv

load_dotenv()


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

    # =====================================================================
    # TWISTED + ASYNCIO BRIDGE (Windows Compatible)
    # =====================================================================
    # 1. Windows: usar SelectorEventLoopPolicy (ProactorEventLoop não compatível)
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 2. Instalar asyncioreactor ANTES de importar o reactor
    try:
        import twisted.internet.asyncioreactor as asyncioreactor
        if 'twisted.internet.reactor' not in sys.modules:
            asyncioreactor.install()
            logging.info("asyncioreactor instalado")
    except Exception as e:
        logging.warning(f"Reactor warning: {e}")

    # Importar reactor DEPOIS de instalar asyncioreactor
    from twisted.internet import reactor
    
    # Importar Orchestrator DEPOIS de instalar reactor
    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(config_path=args.config)

    async def runner():
        """Runner async que executa o orchestrator."""
        try:
            await orchestrator.start()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            logging.error(f"Erro fatal: {e}", exc_info=True)
        finally:
            if reactor.running:
                reactor.stop()

    # Setup signal handlers (se possível no Windows)
    try:
        orchestrator.setup_signal_handlers()
    except Exception:
        pass  # Windows não suporta signal handlers no asyncio

    # Inicia task e roda o reactor (main loop do Twisted)
    # installSignalHandlers=False permite que o asyncio (via orchestrator.setup_signal_handlers)
    # gerencie os sinais SIGINT/SIGTERM para graceful shutdown.
    loop = asyncio.get_event_loop()
    loop.create_task(runner())
    reactor.run(installSignalHandlers=False)


if __name__ == "__main__":
    main()
