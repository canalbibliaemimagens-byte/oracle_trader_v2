"""
Oracle Trader v2.0 - Preditor (Cérebro)
========================================

Digital Twin do TradingEnv. Mantém posição virtual e gera sinais
baseados EXCLUSIVAMENTE em dados de mercado e estado virtual.

O Preditor é CEGO para a realidade:
  - Não conhece conta real
  - Não conhece posições reais
  - Não conhece margem, spread real, slippage real
  - Não recebe ACKs do Executor para alterar estado

Flow por barra:
  1. Adiciona barra ao buffer FIFO
  2. Se buffer < MIN_BARS: return None (warmup)
  3. Calcula features HMM → prediz estado HMM
  4. Calcula features RL (com posição virtual) → prediz ação PPO
  5. Atualiza posição virtual conforme ação
  6. Retorna Signal
"""

import logging
import time
from typing import Dict, List, Optional
from datetime import datetime, timezone

import numpy as np

from core.actions import Action, action_from_index, get_direction, get_intensity
from core.constants import MIN_BARS_FOR_PREDICTION
from core.features import FeatureCalculator
from core.models import Bar, Signal
from .buffer import BarBuffer
from .model_loader import ModelBundle, ModelLoader
from .virtual_position import VirtualPositionManager

logger = logging.getLogger("Preditor")


class Preditor:
    """
    Digital Twin do TradingEnv.
    Gerencia múltiplos modelos (um por símbolo) simultaneamente.
    """

    def __init__(self):
        self.models: Dict[str, ModelBundle] = {}
        self.buffers: Dict[str, BarBuffer] = {}
        self.virtual_positions: Dict[str, VirtualPositionManager] = {}
        self.feature_calculators: Dict[str, FeatureCalculator] = {}

    # =========================================================================
    # GESTÃO DE MODELOS
    # =========================================================================

    def load_model(self, zip_path: str) -> bool:
        """
        Carrega modelo do ZIP.

        1. Extrai metadata do zip.comment
        2. Carrega HMM e PPO
        3. Inicializa buffer FIFO vazio
        4. Inicializa posição virtual FLAT
        5. Inicializa FeatureCalculator com config do modelo

        Args:
            zip_path: Caminho para o arquivo ZIP.

        Returns:
            True se carregou com sucesso.
        """
        bundle = ModelLoader.load(zip_path)
        if bundle is None:
            return False

        symbol = bundle.symbol

        # Registra modelo
        self.models[symbol] = bundle

        # Inicializa buffer FIFO
        min_bars = bundle.metadata.get("preditor", {}).get(
            "min_bars", MIN_BARS_FOR_PREDICTION
        )
        self.buffers[symbol] = BarBuffer(maxlen=min_bars)

        # Inicializa posição virtual com custos do treino
        self.virtual_positions[symbol] = VirtualPositionManager.from_training_config(
            bundle.training_config
        )

        # Inicializa FeatureCalculator com config unificada (hmm + rl)
        unified_config = {**bundle.hmm_config, **bundle.rl_config}
        self.feature_calculators[symbol] = FeatureCalculator(unified_config)

        logger.info(
            f"[{symbol}] Modelo carregado: {bundle.timeframe}, "
            f"buffer={min_bars} barras, "
            f"HMM states={bundle.hmm_config.get('n_states', 5)}"
        )
        return True

    def unload_model(self, symbol: str) -> bool:
        """Remove modelo da memória."""
        if symbol not in self.models:
            return False

        del self.models[symbol]
        del self.buffers[symbol]
        del self.virtual_positions[symbol]
        del self.feature_calculators[symbol]

        logger.info(f"[{symbol}] Modelo descarregado")
        return True

    def list_models(self) -> List[str]:
        """Retorna lista de símbolos com modelos carregados."""
        return list(self.models.keys())

    # =========================================================================
    # WARMUP
    # =========================================================================

    def warmup(self, symbol: str, bars: List[Bar]) -> int:
        """
        Fast-forward do modelo com histórico.

        Alimenta o buffer e executa predições silenciosas (sem emitir sinais
        externamente). Alinha a posição virtual com o que o modelo "teria feito".

        Fluxo do warmup (spec 5.1):
          - Histórico carregado: Últimas 1000 barras
          - Estabilização: Primeiras 350 barras (preenche buffer, sem sinais)
          - Fast Forward: Próximas 650 barras (simulação para alinhar estado)

        Args:
            symbol: Símbolo do ativo.
            bars: Lista de barras históricas (mais antigas primeiro).

        Returns:
            Número de barras processadas com predição (após buffer ready).
        """
        from .warmup import run_warmup
        return run_warmup(self, symbol, bars)

    # =========================================================================
    # CICLO PRINCIPAL
    # =========================================================================

    def process_bar(self, symbol: str, bar: Bar) -> Optional[Signal]:
        """
        Processa uma nova barra fechada.

        Flow:
          1. Adiciona barra ao buffer FIFO
          2. Se buffer < MIN_BARS: return None (ainda em warmup)
          3. Calcula features HMM → prediz estado
          4. Calcula features RL (com posição virtual) → prediz ação
          5. Atualiza posição virtual
          6. Retorna Signal

        Args:
            symbol: Símbolo do ativo.
            bar: Barra OHLCV fechada.

        Returns:
            Signal se pronto, None se ainda em warmup.
        """
        if symbol not in self.models:
            logger.warning(f"[{symbol}] process_bar: modelo não carregado")
            return None

        # 1. Adiciona ao buffer
        self.buffers[symbol].append(bar)

        # 2. Verifica se pronto
        if not self.buffers[symbol].is_ready():
            return None

        # 3-6. Prediz e retorna Signal
        signal = self._predict_and_signal(symbol, bar)
        
        # Format time for log
        dt_str = datetime.fromtimestamp(bar.time, timezone.utc).strftime('%H:%M')
        logger.info(
            f"[{symbol}] Bar processed: {dt_str} | "
            f"Action: {signal.action} ({signal.intensity}) | "
            f"State: {signal.hmm_state}"
        )
        return signal

    # =========================================================================
    # CONSULTAS
    # =========================================================================

    def get_virtual_position(self, symbol: str) -> Optional[VirtualPositionManager]:
        """Retorna posição virtual atual do símbolo."""
        return self.virtual_positions.get(symbol)

    def get_state(self) -> dict:
        """Retorna estado completo para debug/dashboard."""
        return {
            "models": list(self.models.keys()),
            "positions": {
                s: {
                    "direction": vp.direction,
                    "direction_name": vp.direction_name,
                    "intensity": vp.intensity,
                    "entry_price": vp.entry_price,
                    "pnl": round(vp.current_pnl, 2),
                    "total_realized": round(vp.total_realized_pnl, 2),
                }
                for s, vp in self.virtual_positions.items()
            },
            "buffers": {
                s: {"size": len(b), "maxlen": b.maxlen, "ready": b.is_ready()}
                for s, b in self.buffers.items()
            },
        }

    # =========================================================================
    # LÓGICA INTERNA
    # =========================================================================

    def _predict_internal(self, symbol: str, bar: Bar) -> tuple:
        """
        Executa predição completa (HMM + PPO) e atualiza posição virtual.
        Usado tanto no warmup quanto no ciclo normal.

        Returns:
            Tupla (Action, hmm_state) escolhida pelo modelo.
        """
        bundle = self.models[symbol]
        calc = self.feature_calculators[symbol]
        vp = self.virtual_positions[symbol]
        df = self.buffers[symbol].to_dataframe()

        # 1. Features HMM → Prediz estado
        hmm_features = calc.calc_hmm_features(df)
        hmm_state = int(bundle.hmm_model.predict(hmm_features)[0])

        # 2. Features RL (com posição virtual) → Prediz ação
        core_vp = vp.as_core_virtual_position()
        rl_features = calc.calc_rl_features(df, hmm_state, core_vp)
        action_idx, _ = bundle.ppo_model.predict(rl_features, deterministic=True)
        if hasattr(action_idx, 'item'):
            action_idx = action_idx.item()
        action_idx = int(action_idx)
        action = action_from_index(action_idx)

        # 3. Atualiza posição virtual
        old_dir = vp.direction
        realized_pnl = vp.update(action, bar.close)

        # 4. Log de mudança de posição
        if old_dir != vp.direction:
            logger.info(
                f"[{symbol}] Virtual: {_dir_name(old_dir)} → {vp.direction_name} | "
                f"Realized: ${realized_pnl:.2f}"
            )

        logger.debug(
            f"[{symbol}] HMM:{hmm_state} → {action.value} | "
            f"VPos: {vp.direction_name}@{vp.entry_price:.5f} | "
            f"VPnL: ${vp.current_pnl:.2f}"
        )

        return action, hmm_state

    def _predict_and_signal(self, symbol: str, bar: Bar) -> Signal:
        """
        Executa predição e constrói Signal para emissão externa.
        Reutiliza _predict_internal e envelopa o resultado no objeto Signal.
        """
        vp = self.virtual_positions[symbol]

        action, hmm_state = self._predict_internal(symbol, bar)

        return Signal(
            symbol=symbol,
            action=action.value,
            direction=get_direction(action).value,
            intensity=get_intensity(action),
            hmm_state=hmm_state,
            virtual_pnl=vp.current_pnl,
            timestamp=time.time(),
        )


def _dir_name(direction: int) -> str:
    """Helper: int → nome de direção."""
    if direction == 1:
        return "LONG"
    elif direction == -1:
        return "SHORT"
    return "FLAT"
