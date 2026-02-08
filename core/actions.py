"""
Oracle Trader v2.0 - Ações do Modelo PPO
=========================================

Centraliza a definição das 7 ações do espaço de ação.

Nomenclatura:
  - WAIT: Ficar fora (ação 0). NÃO confundir com FLAT (estado de posição).
  - WEAK/MODERATE/STRONG: Intensidade do sinal (1/2/3).
    O Executor mapeia intensidade → lote real via config por símbolo.
"""

from enum import Enum
from .constants import Direction


class Action(str, Enum):
    """
    Ações do modelo PPO (7 ações).

    Índice 0 = WAIT (ficar de fora)
    Índices 1-3 = LONG com intensidade crescente
    Índices 4-6 = SHORT com intensidade crescente
    """
    WAIT = "WAIT"
    LONG_WEAK = "LONG_WEAK"
    LONG_MODERATE = "LONG_MODERATE"
    LONG_STRONG = "LONG_STRONG"
    SHORT_WEAK = "SHORT_WEAK"
    SHORT_MODERATE = "SHORT_MODERATE"
    SHORT_STRONG = "SHORT_STRONG"


# Mapeamento índice PPO → Action
ACTIONS_MAP: dict[int, Action] = {
    0: Action.WAIT,
    1: Action.LONG_WEAK,
    2: Action.LONG_MODERATE,
    3: Action.LONG_STRONG,
    4: Action.SHORT_WEAK,
    5: Action.SHORT_MODERATE,
    6: Action.SHORT_STRONG,
}

# Mapeamento inverso Action → índice
ACTION_TO_INDEX: dict[Action, int] = {action: idx for idx, action in ACTIONS_MAP.items()}


def action_from_index(idx: int) -> Action:
    """
    Converte índice PPO (0-6) para Action.

    Args:
        idx: Índice retornado pelo modelo PPO.

    Returns:
        Action correspondente. Retorna WAIT para índice inválido.
    """
    return ACTIONS_MAP.get(idx, Action.WAIT)


def get_direction(action: Action) -> Direction:
    """
    Extrai direção de uma Action.

    Returns:
        Direction.LONG, Direction.SHORT ou Direction.FLAT.
    """
    if action.value.startswith("LONG"):
        return Direction.LONG
    elif action.value.startswith("SHORT"):
        return Direction.SHORT
    return Direction.FLAT


def get_intensity(action: Action) -> int:
    """
    Extrai intensidade de uma Action.

    Returns:
        0 (WAIT), 1 (WEAK), 2 (MODERATE) ou 3 (STRONG).
    """
    if action == Action.WAIT:
        return 0
    elif action.value.endswith("WEAK"):
        return 1
    elif action.value.endswith("MODERATE"):
        return 2
    elif action.value.endswith("STRONG"):
        return 3
    return 0


def get_action_properties(action_idx: int) -> tuple[Direction, int]:
    """
    Converte índice de ação para (Direction, intensity).

    Args:
        action_idx: Índice da ação (0-6).

    Returns:
        Tupla (Direction, int intensity).
    """
    action = action_from_index(action_idx)
    return get_direction(action), get_intensity(action)
