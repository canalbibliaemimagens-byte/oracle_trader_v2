"""
Oracle Trader v2 - Lot Calculator

Calcula tamanhos de lote dinamicamente baseado em:
- Classe do ativo (forex, índice, commodity, etc.)
- Saldo atual da conta (escalonamento em degraus)

Design:
    O MODELO não se preocupa com risco - apenas prediz direção e intensidade.
    O LOT CALCULATOR traduz a intensidade (small/medium/large) para lotes reais.
    O EXECUTOR gerencia o risco global (DD limits, Paper Trade).

Escalonamento:
    - Degraus de 10k (configurável)
    - Saldo 10k-19k = 1x, 20k-29k = 2x, etc.
    - Sem limite superior (escala indefinidamente)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger("OracleTrader.LotCalc")


class AssetClass(str, Enum):
    """Classes de ativos suportadas"""
    FOREX = "FOREX"
    INDEX = "INDEX"
    COMMODITY = "COMMODITY"
    METAL = "METAL"
    CRYPTO = "CRYPTO"
    STOCK = "STOCK"


@dataclass
class AssetClassConfig:
    """
    Configuração de lotes para uma classe de ativo.
    
    Definido no treinamento e salvo nos metadados do modelo.
    """
    asset_class: AssetClass
    base_lot_sizes: List[float]  # [small, medium, large] para balance base
    base_balance: float = 10000.0  # Saldo base de referência
    scale_step: float = 10000.0    # Degrau de escalonamento
    min_lot: float = 0.01          # Lote mínimo do broker
    lot_step: float = 0.01         # Step do broker
    
    def __post_init__(self):
        # Garante 3 tamanhos
        if len(self.base_lot_sizes) != 3:
            raise ValueError("base_lot_sizes deve ter exatamente 3 valores [small, medium, large]")


# Configurações padrão por classe de ativo
DEFAULT_ASSET_CONFIGS: Dict[AssetClass, AssetClassConfig] = {
    AssetClass.FOREX: AssetClassConfig(
        asset_class=AssetClass.FOREX,
        base_lot_sizes=[0.01, 0.03, 0.05],
        base_balance=10000.0,
        scale_step=10000.0,
        min_lot=0.01,
        lot_step=0.01,
    ),
    AssetClass.INDEX: AssetClassConfig(
        asset_class=AssetClass.INDEX,
        base_lot_sizes=[0.1, 0.3, 0.5],
        base_balance=10000.0,
        scale_step=10000.0,
        min_lot=0.1,
        lot_step=0.1,
    ),
    AssetClass.COMMODITY: AssetClassConfig(
        asset_class=AssetClass.COMMODITY,
        base_lot_sizes=[0.01, 0.03, 0.05],
        base_balance=10000.0,
        scale_step=10000.0,
        min_lot=0.01,
        lot_step=0.01,
    ),
    AssetClass.METAL: AssetClassConfig(
        asset_class=AssetClass.METAL,
        base_lot_sizes=[0.01, 0.03, 0.05],
        base_balance=10000.0,
        scale_step=10000.0,
        min_lot=0.01,
        lot_step=0.01,
    ),
    AssetClass.CRYPTO: AssetClassConfig(
        asset_class=AssetClass.CRYPTO,
        base_lot_sizes=[0.001, 0.003, 0.005],  # BTC é caro
        base_balance=10000.0,
        scale_step=10000.0,
        min_lot=0.001,
        lot_step=0.001,
    ),
    AssetClass.STOCK: AssetClassConfig(
        asset_class=AssetClass.STOCK,
        base_lot_sizes=[1, 3, 5],  # Ações em unidades
        base_balance=10000.0,
        scale_step=10000.0,
        min_lot=1,
        lot_step=1,
    ),
}


class LotCalculator:
    """
    Calcula tamanhos de lote com escalonamento dinâmico.
    
    Uso:
        calc = LotCalculator.from_asset_class(AssetClass.FOREX)
        lots = calc.get_lot_sizes(current_balance=25000)
        # Com 25k e forex: [0.02, 0.06, 0.10] (2x scale)
        
        lot = calc.get_lot_for_action(action_idx=2, current_balance=25000)
        # action 2 = BUY_MEDIUM = 0.06
    """
    
    def __init__(self, config: AssetClassConfig):
        self.config = config
        self._last_scale = 1.0
        self._last_balance = 0.0
    
    @classmethod
    def from_asset_class(cls, asset_class: AssetClass) -> 'LotCalculator':
        """
        Cria calculator a partir da classe de ativo.
        
        Usa configurações padrão.
        """
        if asset_class not in DEFAULT_ASSET_CONFIGS:
            logger.warning(f"Classe {asset_class} não encontrada, usando FOREX")
            asset_class = AssetClass.FOREX
        
        return cls(DEFAULT_ASSET_CONFIGS[asset_class])
    
    @classmethod
    def from_model_metadata(cls, metadata: dict) -> 'LotCalculator':
        """
        Cria calculator a partir dos metadados do modelo.
        
        Args:
            metadata: Dict com training_info do modelo
        """
        training_info = metadata.get('training_info', {})
        
        # Tenta pegar classe do ativo
        asset_class_str = training_info.get('asset_class', 'FOREX')
        try:
            asset_class = AssetClass(asset_class_str.upper())
        except ValueError:
            logger.warning(f"Classe '{asset_class_str}' inválida, usando FOREX")
            asset_class = AssetClass.FOREX
        
        # Usa config padrão como base
        base_config = DEFAULT_ASSET_CONFIGS.get(asset_class, DEFAULT_ASSET_CONFIGS[AssetClass.FOREX])
        
        # Sobrescreve com valores do modelo se existirem
        config = AssetClassConfig(
            asset_class=asset_class,
            base_lot_sizes=training_info.get('lot_sizes', base_config.base_lot_sizes)[1:4],  # Ignora o 0
            base_balance=training_info.get('base_balance', base_config.base_balance),
            scale_step=training_info.get('scale_step', base_config.scale_step),
            min_lot=training_info.get('min_lot', base_config.min_lot),
            lot_step=training_info.get('lot_step', base_config.lot_step),
        )
        
        return cls(config)
    
    def calculate_scale(self, current_balance: float) -> float:
        """
        Calcula o multiplicador de escala baseado no saldo.
        
        Escalonamento em degraus:
            - 10k-19.9k = 1x
            - 20k-29.9k = 2x
            - 30k-39.9k = 3x
            - ...
            - Sem limite superior
        
        Args:
            current_balance: Saldo atual da conta
            
        Returns:
            Multiplicador de escala (1.0, 2.0, 3.0, ...)
        """
        if current_balance <= 0:
            return 1.0
        
        # Calcula tier (degrau)
        tier = int(current_balance / self.config.scale_step)
        
        # Mínimo 1x
        scale = max(1.0, float(tier))
        
        # Cache para log
        if scale != self._last_scale:
            logger.info(
                f"[LotCalc] Scale atualizado: {self._last_scale}x → {scale}x "
                f"(balance: ${current_balance:,.0f})"
            )
            self._last_scale = scale
            self._last_balance = current_balance
        
        return scale
    
    def get_lot_sizes(self, current_balance: float) -> List[float]:
        """
        Retorna os 3 tamanhos de lote ajustados para o saldo atual.
        
        Args:
            current_balance: Saldo atual
            
        Returns:
            Lista [small, medium, large] ajustados
        """
        scale = self.calculate_scale(current_balance)
        
        lots = []
        for base_lot in self.config.base_lot_sizes:
            scaled = base_lot * scale
            
            # Arredonda para lot_step
            scaled = round(scaled / self.config.lot_step) * self.config.lot_step
            
            # Garante mínimo
            scaled = max(self.config.min_lot, scaled)
            
            lots.append(round(scaled, 3))
        
        return lots
    
    def get_lot_for_action(self, action_idx: int, current_balance: float) -> float:
        """
        Retorna o lote para uma ação específica do modelo.
        
        Mapeamento de ações:
            0 = WAIT (retorna 0)
            1 = BUY_SMALL, 4 = SELL_SMALL
            2 = BUY_MEDIUM, 5 = SELL_MEDIUM
            3 = BUY_LARGE, 6 = SELL_LARGE
        
        Args:
            action_idx: Índice da ação do modelo (0-6)
            current_balance: Saldo atual
            
        Returns:
            Tamanho do lote
        """
        if action_idx == 0:
            return 0.0
        
        lots = self.get_lot_sizes(current_balance)
        
        # Índice do tamanho: 0=small, 1=medium, 2=large
        size_idx = (action_idx - 1) % 3
        
        return lots[size_idx]
    
    def get_info(self, current_balance: float = None) -> dict:
        """
        Retorna informações para debug/dashboard.
        """
        info = {
            'asset_class': self.config.asset_class.value,
            'base_lot_sizes': self.config.base_lot_sizes,
            'base_balance': self.config.base_balance,
            'scale_step': self.config.scale_step,
            'min_lot': self.config.min_lot,
        }
        
        if current_balance is not None:
            info['current_balance'] = current_balance
            info['current_scale'] = self.calculate_scale(current_balance)
            info['current_lot_sizes'] = self.get_lot_sizes(current_balance)
        
        return info


# =============================================================================
# Documentação: Requisitos para Atualização do Notebook
# =============================================================================
"""
REQUISITOS PARA NOTEBOOK DE TREINAMENTO v2
==========================================

O notebook deve salvar os seguintes metadados no exec_config.json:

{
    "training_info": {
        "asset_class": "FOREX",           # FOREX, INDEX, COMMODITY, METAL, CRYPTO, STOCK
        "base_balance": 10000,            # Saldo base usado no treinamento
        "scale_step": 10000,              # Degrau de escalonamento
        "lot_sizes": [0, 0.01, 0.03, 0.05],  # [FLAT, small, medium, large]
        "min_lot": 0.01,                  # Lote mínimo do símbolo
        "lot_step": 0.01,                 # Step de lote do símbolo
        
        # Metadados adicionais (informativos)
        "symbol_type": "currency_pair",   # currency_pair, index, commodity, etc.
        "typical_spread_points": 10,
        "typical_slippage_points": 2,
    }
}

CONFIGURAÇÕES SUGERIDAS POR CLASSE:

FOREX (EURUSD, GBPUSD, etc.):
    lot_sizes: [0, 0.01, 0.03, 0.05]
    min_lot: 0.01
    typical_spread: 5-15 points

INDEX (US500, US30, GER40, etc.):
    lot_sizes: [0, 0.1, 0.3, 0.5]
    min_lot: 0.1
    typical_spread: 30-100 points

COMMODITY (XAUUSD, XTIUSD, etc.):
    lot_sizes: [0, 0.01, 0.03, 0.05]
    min_lot: 0.01
    typical_spread: 20-50 points

METAL (XAUUSD, XAGUSD):
    lot_sizes: [0, 0.01, 0.03, 0.05]
    min_lot: 0.01
    typical_spread: 15-40 points

CRYPTO (BTCUSD, ETHUSD):
    lot_sizes: [0, 0.001, 0.003, 0.005]
    min_lot: 0.001
    typical_spread: varies widely

O notebook NÃO deve incluir "risk_per_trade_pct" ou similar.
O modelo deve operar com "risco infinito" - a gestão de risco
é responsabilidade do Executor, não do modelo.
"""
