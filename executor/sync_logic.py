"""
Oracle Trader v2.0 — Lógica de Sincronização
=============================================

Determina se uma ordem deve ser aberta, mantida, fechada ou ignorada,
comparando o sinal do Preditor com a posição real no broker.

Regra de Borda: A abertura só ocorre na TRANSIÇÃO de sinal, evitando
entrar no "meio" de um trade já em andamento.

EXCEÇÃO (v2.0.1): Após startup/warmup, a primeira entrada é permitida
mesmo sem transição, pois o modelo já convergiu durante o warmup e
a primeira barra ao vivo é efetivamente uma "transição" de offline→live.
"""

from enum import Enum
from typing import Optional

from core.models import Signal, Position


class Decision(str, Enum):
    """Decisões possíveis da lógica de sincronização."""
    NOOP = "NOOP"            # Não fazer nada (já alinhado)
    CLOSE = "CLOSE"          # Fechar posição atual
    OPEN = "OPEN"            # Abrir posição nova
    CLOSE_AND_OPEN = "CLOSE_AND_OPEN"  # Fechar atual + abrir nova


def decide(signal: Signal, real_position: Optional[Position]) -> Decision:
    """
    Decide ação baseado no sinal do Preditor vs posição real.

    Tabela de decisão:

    | Real   | Signal     | Decisão        |
    |--------|------------|----------------|
    | FLAT   | WAIT       | NOOP           |
    | FLAT   | LONG/SHORT | OPEN           |
    | LONG   | LONG       | NOOP           |
    | SHORT  | SHORT      | NOOP           |
    | LONG   | WAIT       | CLOSE          |
    | SHORT  | WAIT       | CLOSE          |
    | LONG   | SHORT      | CLOSE_AND_OPEN |
    | SHORT  | LONG       | CLOSE_AND_OPEN |
    """
    signal_dir = signal.direction
    real_dir = real_position.direction if real_position else 0

    # Ambos FLAT
    if real_dir == 0 and signal_dir == 0:
        return Decision.NOOP

    # Real FLAT, Sinal posicionado → Deve abrir
    if real_dir == 0 and signal_dir != 0:
        return Decision.OPEN

    # Mesma direção → Alinhado
    if real_dir == signal_dir:
        return Decision.NOOP

    # Sinal WAIT, real posicionado → Fechar
    if signal_dir == 0 and real_dir != 0:
        return Decision.CLOSE

    # Direções opostas → Fechar e abrir na nova direção
    return Decision.CLOSE_AND_OPEN


class SyncState:
    """
    Mantém estado de sincronização por símbolo.

    Implementa a "Regra de Borda": abertura só na transição de sinal,
    evitando entrar no meio de um trade. 
    
    A primeira entrada pós-warmup é SEMPRE permitida (first_live=True),
    porque o warmup já alinhou o modelo e a primeira barra ao vivo 
    representa efetivamente uma transição de offline → live.
    """

    def __init__(self):
        self.last_signal_dir: int = 0
        self.last_signal_intensity: int = 0
        self.waiting_sync: bool = False
        self.first_live: bool = True  # Permite primeira entrada pós-warmup

    def should_open(self, signal: Signal, decision: Decision) -> bool:
        """
        Avalia se deve efetivamente abrir a posição baseado na Regra de Borda.
        
        Regra de Borda: Só abre na TRANSIÇÃO de sinal (direção ou intensidade mudou).
        Exceção: Primeira entrada ao vivo pós-warmup é permitida (first_live=True).

        Args:
            signal: Sinal atual do Preditor.
            decision: Decisão do decide().

        Returns:
            True se deve abrir posição agora.
        """
        current_dir = signal.direction
        current_intensity = signal.intensity

        # Decisões que não envolvem abertura
        if decision in (Decision.NOOP, Decision.CLOSE):
            if current_dir == 0:
                self.first_live = False  # Já viu um WAIT, reset
            self.last_signal_dir = current_dir
            self.last_signal_intensity = current_intensity
            self.waiting_sync = False
            return False

        # Decisões OPEN ou CLOSE_AND_OPEN: verificar Regra de Borda
        is_transition = (
            current_dir != self.last_signal_dir or
            current_intensity != self.last_signal_intensity
        )

        # Primeira entrada pós-warmup: permitir sempre
        if self.first_live and current_dir != 0:
            self.first_live = False
            self.last_signal_dir = current_dir
            self.last_signal_intensity = current_intensity
            self.waiting_sync = False
            return True

        # Transição detectada: permitir
        if is_transition and current_dir != 0:
            self.last_signal_dir = current_dir
            self.last_signal_intensity = current_intensity
            self.waiting_sync = False
            return True

        # Mesmo sinal repetido, sem transição: bloquear (meio do trade)
        self.last_signal_dir = current_dir
        self.last_signal_intensity = current_intensity
        self.waiting_sync = True
        return False

    def reset(self):
        """Reseta estado de sincronização."""
        self.last_signal_dir = 0
        self.last_signal_intensity = 0
        self.waiting_sync = False
        self.first_live = True
