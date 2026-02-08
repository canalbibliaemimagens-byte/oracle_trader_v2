"""
Oracle Trader v2.0 — Lot Mapper
================================

Converte a intensidade abstrata (1, 2, 3) do modelo PPO
em lotes reais configurados por símbolo.
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("Executor.LotMapper")


@dataclass
class SymbolConfig:
    """Configuração de execução por símbolo."""
    enabled: bool = True
    lot_weak: float = 0.01
    lot_moderate: float = 0.03
    lot_strong: float = 0.05
    sl_usd: float = 10.0
    tp_usd: float = 0.0
    max_spread_pips: float = 2.0


class LotMapper:
    """
    Mapeia intensidade do sinal para lotes reais.
    Configuração per-symbol via executor_symbols.json.
    """

    def __init__(self, configs: Dict[str, SymbolConfig]):
        self.configs = configs

    def map_lot(self, symbol: str, intensity: int) -> float:
        """
        Converte intensidade para volume em lotes.

        Args:
            symbol: Nome do símbolo.
            intensity: 1 (weak), 2 (moderate), 3 (strong).

        Returns:
            Volume em lotes. 0.0 se símbolo não configurado ou intensity inválido.
        """
        cfg = self.configs.get(symbol)
        if cfg is None:
            logger.warning(f"Sem config para {symbol}")
            return 0.0

        if intensity == 1:
            return cfg.lot_weak
        elif intensity == 2:
            return cfg.lot_moderate
        elif intensity == 3:
            return cfg.lot_strong

        return 0.0

    def get_config(self, symbol: str) -> Optional[SymbolConfig]:
        """Retorna configuração do símbolo."""
        return self.configs.get(symbol)


def load_symbol_configs(path: str) -> Dict[str, SymbolConfig]:
    """
    Carrega configurações de símbolo de um JSON.

    Ignora chaves que começam com '_' (metadados/comentários).
    """
    with open(path) as f:
        data = json.load(f)

    configs = {}
    for symbol, cfg in data.items():
        if symbol.startswith("_"):
            continue
        configs[symbol] = SymbolConfig(
            enabled=cfg.get("enabled", True),
            lot_weak=cfg.get("lot_weak", 0.01),
            lot_moderate=cfg.get("lot_moderate", 0.03),
            lot_strong=cfg.get("lot_strong", 0.05),
            sl_usd=cfg.get("sl_usd", 10.0),
            tp_usd=cfg.get("tp_usd", 0.0),
            max_spread_pips=cfg.get("max_spread_pips", 2.0),
        )

    return configs
