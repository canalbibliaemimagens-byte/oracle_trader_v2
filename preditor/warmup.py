"""
Oracle Trader v2.0 - Warmup do Preditor
=========================================

Fast-forward do modelo com histórico para alinhar estado virtual.

Fluxo do warmup (spec 5.1):
  - Histórico carregado: Últimas 1000 barras
  - Estabilização: Primeiras 350 barras (preenche buffer, sem sinais)
  - Fast Forward: Próximas 650 barras (simulação para alinhar estado)
"""

import logging
from typing import TYPE_CHECKING, List

from core.models import Bar

if TYPE_CHECKING:
    from .preditor import Preditor

logger = logging.getLogger("Preditor.Warmup")


def run_warmup(preditor: "Preditor", symbol: str, bars: List[Bar]) -> int:
    """
    Fast-forward do modelo com histórico.

    Alimenta o buffer e executa predições silenciosas (sem emitir sinais
    externamente). Alinha a posição virtual com o que o modelo "teria feito".

    Args:
        preditor: Instância do Preditor.
        symbol: Símbolo do ativo.
        bars: Lista de barras históricas (mais antigas primeiro).

    Returns:
        Número de barras processadas com predição (após buffer ready).
    """
    if symbol not in preditor.models:
        logger.warning(f"[{symbol}] warmup: modelo não carregado")
        return 0

    predicted = 0
    for bar in bars:
        # Adiciona ao buffer
        preditor.buffers[symbol].append(bar)

        # Se buffer pronto, executa predição silenciosa
        if preditor.buffers[symbol].is_ready():
            preditor._predict_internal(symbol, bar)
            predicted += 1

    vp = preditor.virtual_positions[symbol]
    logger.info(
        f"[{symbol}] Warmup concluído: {len(bars)} barras, "
        f"{predicted} predições, "
        f"VPos={vp.direction_name} PnL=${vp.current_pnl:.2f}"
    )
    return predicted
