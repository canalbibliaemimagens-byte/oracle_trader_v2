"""
Oracle Trader v2.0 - Preditor (Cérebro)
========================================

Digital Twin do TradingEnv. Carrega modelos HMM+PPO, processa barras
e gera sinais de trading baseados exclusivamente em posição virtual.
"""

from .preditor import Preditor
from .buffer import BarBuffer
from .virtual_position import VirtualPositionManager
from .model_loader import ModelLoader, ModelBundle
from .warmup import run_warmup

__all__ = [
    "Preditor",
    "BarBuffer",
    "VirtualPositionManager",
    "ModelLoader",
    "ModelBundle",
    "run_warmup",
]
