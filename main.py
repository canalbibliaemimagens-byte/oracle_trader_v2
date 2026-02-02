#!/usr/bin/env python3
"""
Oracle Trader v2 - Ponto de Entrada

Inicializa e executa o sistema de trading.

Uso:
    python main.py
    python main.py --config config/oracle_config.json
    python main.py --models ./models --log-level DEBUG
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Adiciona diretório raiz ao path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from core.engine import OracleEngine, setup_signal_handlers, VERSION
from core.config import ConfigManager
from infra import MT5Client


def setup_logging(level: str = "INFO") -> None:
    """
    Configura logging do sistema.
    
    Args:
        level: Nível de log (DEBUG, INFO, WARNING, ERROR)
    """
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    date_format = '%H:%M:%S'
    
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=log_format,
        datefmt=date_format,
    )
    
    # Reduz verbosidade de bibliotecas externas
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


def load_env_file(filepath: str = ".env") -> None:
    """
    Carrega variáveis de ambiente de arquivo .env.
    
    Formato simples: KEY=value (uma por linha)
    """
    path = Path(filepath)
    if not path.exists():
        return
    
    logger = logging.getLogger("OracleTrader.Main")
    logger.info(f"Carregando variáveis de ambiente de {filepath}")
    
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            
            # Ignora comentários e linhas vazias
            if not line or line.startswith('#'):
                continue
            
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                
                if key and value:
                    os.environ[key] = value


def parse_args() -> argparse.Namespace:
    """
    Processa argumentos da linha de comando.
    """
    parser = argparse.ArgumentParser(
        description=f"Oracle Trader v{VERSION} - Sistema Autônomo de Trading com RL",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py                           # Usa config padrão
  python main.py --config myconfig.json    # Config customizada
  python main.py --paper-only              # Apenas Paper Trade (sem trades reais)
  python main.py --log-level DEBUG         # Log detalhado
        """
    )
    
    # Configuração
    parser.add_argument(
        "--config", 
        default="config/oracle_config.json",
        help="Arquivo de configuração (default: config/oracle_config.json)"
    )
    
    parser.add_argument(
        "--models",
        default=None,
        help="Diretório dos modelos (sobrescreve config)"
    )
    
    # Modos de operação
    parser.add_argument(
        "--paper-only",
        action="store_true",
        help="Executa apenas em modo Paper Trade (sem trades reais)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inicializa mas não executa loop (para testes)"
    )
    
    # Overrides de risco
    parser.add_argument(
        "--dd-limit",
        type=float,
        default=None,
        help="DD limit %% (bloqueia novas posições)"
    )
    
    parser.add_argument(
        "--dd-emergency",
        type=float,
        default=None,
        help="DD emergency %% (fecha tudo)"
    )
    
    parser.add_argument(
        "--dd-tp",
        type=float,
        default=None,
        help="DD take profit %% (fecha com lucro)"
    )
    
    # Overrides de SL
    parser.add_argument(
        "--sl-max",
        type=float,
        default=None,
        help="SL máximo (pips)"
    )
    
    parser.add_argument(
        "--sl-min",
        type=float,
        default=None,
        help="SL mínimo (pips)"
    )
    
    parser.add_argument(
        "--use-atr-sl",
        action="store_true",
        default=None,
        help="Usar ATR para SL"
    )
    
    parser.add_argument(
        "--no-atr-sl",
        action="store_false",
        dest="use_atr_sl",
        help="Não usar ATR para SL (SL fixo)"
    )
    
    # Broker
    parser.add_argument(
        "--magic",
        type=int,
        default=None,
        help="Magic number base"
    )
    
    # WebSocket (será usado quando implementado)
    parser.add_argument(
        "--ws-host",
        default=os.getenv("WS_HOST", "127.0.0.1"),
        help="WebSocket host"
    )
    
    parser.add_argument(
        "--ws-port",
        type=int,
        default=int(os.getenv("WS_PORT", "8765")),
        help="WebSocket porta"
    )
    
    parser.add_argument(
        "--no-ws",
        action="store_true",
        help="Desabilita WebSocket server"
    )
    
    # Logging
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nível de log"
    )
    
    return parser.parse_args()


def apply_cli_overrides(config_manager: ConfigManager, args: argparse.Namespace) -> None:
    """
    Aplica overrides da CLI na configuração.
    
    Argumentos da linha de comando têm prioridade sobre arquivo.
    """
    updates = {}
    
    # Risk
    if args.dd_limit is not None:
        updates['dd_limit_pct'] = args.dd_limit
    
    if args.dd_emergency is not None:
        updates['dd_emergency_pct'] = args.dd_emergency
    
    if args.dd_tp is not None:
        updates['dd_tp_pct'] = args.dd_tp
    
    # SL
    if args.sl_max is not None:
        updates['sl_max_pips'] = args.sl_max
    
    if args.sl_min is not None:
        updates['sl_min_pips'] = args.sl_min
    
    if args.use_atr_sl is not None:
        updates['use_atr_sl'] = args.use_atr_sl
    
    # Broker
    if args.magic is not None:
        config_manager.config.broker.magic_base = args.magic
    
    # Models dir
    if args.models is not None:
        updates['models_dir'] = args.models
    
    # WebSocket
    if args.no_ws:
        config_manager.config.websocket.enabled = False
    else:
        config_manager.config.websocket.host = args.ws_host
        config_manager.config.websocket.port = args.ws_port
    
    # Aplica updates
    if updates:
        config_manager.update(updates)


async def main() -> int:
    """
    Função principal.
    
    Returns:
        Código de saída (0 = sucesso)
    """
    # Carrega .env antes de tudo
    load_env_file()
    
    # Parse argumentos
    args = parse_args()
    
    # Configura logging
    setup_logging(args.log_level)
    logger = logging.getLogger("OracleTrader.Main")
    
    # Carrega configuração
    config_manager = ConfigManager(args.config)
    config_manager.load()
    
    # Aplica overrides da CLI
    apply_cli_overrides(config_manager, args)
    
    # Log da configuração final
    config = config_manager.config
    tp_str = f"+{config.risk.dd_tp_pct}%" if config.risk.dd_tp_pct > 0 else "OFF"
    logger.info(
        f"Config: DD=-{config.risk.dd_limit_pct}%/-{config.risk.dd_emergency_pct}% | "
        f"TP={tp_str} | SL={config.risk.sl_min_pips}-{config.risk.sl_max_pips}pips"
    )
    
    # Cria broker
    broker = MT5Client()
    
    # Cria engine
    engine = OracleEngine(
        broker=broker,
        config_manager=config_manager,
        predictor=None,  # TODO: Implementar quando ml/ estiver pronto
    )
    
    # Modo Paper-Only: força todos os símbolos para Paper Trade
    if args.paper_only:
        logger.info("Modo PAPER-ONLY ativado - sem trades reais")
        # TODO: Implementar lógica quando symbols forem carregados
    
    # Configura signal handlers
    loop = asyncio.get_event_loop()
    setup_signal_handlers(engine, loop)
    
    try:
        # Inicializa
        if not await engine.initialize():
            logger.error("Falha na inicialização")
            return 1
        
        # Dry run: sai após inicialização
        if args.dry_run:
            logger.info("Dry run: inicialização OK, saindo...")
            await engine.shutdown("DRY_RUN")
            return 0
        
        # Executa loop principal
        await engine.run()
        
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário")
        await engine.shutdown("USER_INTERRUPT")
    
    except Exception as e:
        logger.exception(f"Erro fatal: {e}")
        await engine.shutdown("ERROR")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
