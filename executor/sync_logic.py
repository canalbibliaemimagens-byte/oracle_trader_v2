"""
Oracle Trader v2.0 — Lógica de Sincronização
=============================================

Determina se uma ordem deve ser aberta, mantida, fechada ou ignorada,
comparando o sinal do Preditor com a posição real no broker.

Regra de Borda: A abertura só ocorre na TRANSIÇÃO de sinal, evitando
entrar no "meio" de um trade já em andamento.
"""

from enum import Enum
from typing import Optional

from ..core.models import Signal, Position


class Decision(str, Enum):
    """Decisões possíveis da lógica de sincronização."""
    NOOP = "NOOP"            # Não fazer nada (já alinhado)
    CLOSE = "CLOSE"          # Fechar posição atual
    WAIT_SYNC = "WAIT_SYNC"  # Aguardar sincronização (entrada perdida)


def decide(signal: Signal, real_position: Optional[Position]) -> Decision:
    """
    Decide ação baseado no sinal do Preditor vs posição real.

    Tabela de decisão:

    | Real   | Signal     | Decisão    |
    |--------|------------|------------|
    | FLAT   | WAIT       | NOOP       |
    | FLAT   | LONG/SHORT | WAIT_SYNC  |
    | LONG   | LONG       | NOOP       |
    | SHORT  | SHORT      | NOOP       |
    | LONG   | WAIT       | CLOSE      |
    | SHORT  | WAIT       | CLOSE      |
    | LONG   | SHORT      | CLOSE      |
    | SHORT  | LONG       | CLOSE      |
    """
    signal_dir = signal.direction
    real_dir = real_position.direction if real_position else 0

    # Ambos FLAT
    if real_dir == 0 and signal_dir == 0:
        return Decision.NOOP

    # Real FLAT, Sinal posicionado → Entrada perdida
    if real_dir == 0 and signal_dir != 0:
        return Decision.WAIT_SYNC

    # Mesma direção → Alinhado
    if real_dir == signal_dir:
        return Decision.NOOP

    # Qualquer outra diferença → Fecha
    return Decision.CLOSE


class SyncState:
    """
    Mantém estado de sincronização por símbolo.
    Implementa a "Regra de Borda": abertura só na transição de sinal.
    """

    def __init__(self):
        self.last_signal_dir: int = 0
        self.waiting_sync: bool = False

    def update(self, signal: Signal, decision: Decision) -> bool:
        """
        Atualiza estado e retorna se deve abrir posição.

        Returns:
            True se deve abrir posição agora (transição detectada)
        """
        current_dir = signal.direction

        # Se estava em WAIT_SYNC e sinal mudou → pode abrir
        if self.waiting_sync and current_dir != self.last_signal_dir:
            self.waiting_sync = False
            self.last_signal_dir = current_dir
            return current_dir != 0

        # Se decisão é WAIT_SYNC → entra em espera
        if decision == Decision.WAIT_SYNC:
            self.waiting_sync = True
            self.last_signal_dir = current_dir
            return False

        # Atualiza último sinal
        self.last_signal_dir = current_dir
        return False

    def reset(self):
        """Reseta estado de sincronização."""
        self.last_signal_dir = 0
        self.waiting_sync = False
