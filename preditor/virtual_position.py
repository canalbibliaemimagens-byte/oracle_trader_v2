"""
Oracle Trader v2.0 - Posição Virtual (Digital Twin)
====================================================

Replica EXATAMENTE a lógica do TradingEnv._execute_action() do notebook.

O Preditor "acredita" que suas ordens são executadas instantaneamente,
sem erro, sem rejeição. Isso mantém as features de posição
(direction, size, pnl) matematicamente consistentes com o treinamento.

⚠️ REGRA DE OURO: Esta lógica deve ser idêntica ao TradingEnv.
Não otimize, não refatore, não "melhore".
"""

from dataclasses import dataclass, field

from core.actions import Action, get_direction, get_intensity


@dataclass
class VirtualPositionManager:
    """
    Gerencia posição virtual de UM símbolo.

    Parâmetros de custo vêm do metadata do modelo (training_config),
    garantindo que a simulação seja idêntica ao treino.
    """
    # Estado da posição
    direction: int = 0          # -1, 0, 1
    intensity: int = 0          # 0, 1, 2, 3
    entry_price: float = 0.0
    current_pnl: float = 0.0

    # Parâmetros do treino (carregados do metadata)
    spread_points: float = 7.0
    slippage_points: float = 2.0
    commission_per_lot: float = 7.0
    point: float = 0.00001
    pip_value: float = 10.0
    digits: int = 5
    lot_sizes: list[float] = field(default_factory=lambda: [0, 0.01, 0.03, 0.05])

    # Acumulador de PnL realizado
    total_realized_pnl: float = 0.0

    @classmethod
    def from_training_config(cls, training_config: dict) -> "VirtualPositionManager":
        """
        Cria instância a partir do training_config do metadata do modelo.

        Args:
            training_config: Dicionário com campos do ZIP header:
                point, pip_value, spread_points, slippage_points,
                commission_per_lot, lot_sizes.
        """
        return cls(
            spread_points=training_config.get('spread_points', 7.0),
            slippage_points=training_config.get('slippage_points', 2.0),
            commission_per_lot=training_config.get('commission_per_lot', 7.0),
            point=training_config.get('point', 0.00001),
            pip_value=training_config.get('pip_value', 10.0),
            digits=training_config.get('digits', 5),
            lot_sizes=training_config.get('lot_sizes', [0, 0.01, 0.03, 0.05]),
        )

    def update(self, action: Action, current_price: float) -> float:
        """
        Atualiza posição virtual baseado na ação do modelo.

        Lógica (idêntica ao TradingEnv):
          - Se mesma direção e intensidade: NOOP (mantém, atualiza PnL flutuante)
          - Qualquer mudança: fecha posição atual + abre nova
          - WAIT: fecha posição se aberta

        Args:
            action: Ação do modelo PPO.
            current_price: Preço de fechamento da barra atual.

        Returns:
            PnL realizado se fechou posição, 0.0 se manteve.
        """
        target_dir = get_direction(action).value
        target_intensity = get_intensity(action)

        # Mesma posição → NOOP (atualiza floating PnL)
        if target_dir == self.direction and target_intensity == self.intensity:
            self._update_floating_pnl(current_price)
            return 0.0

        # Qualquer mudança → fecha + abre
        realized_pnl = 0.0
        if self.direction != 0:
            realized_pnl = self._close(current_price)
            self.total_realized_pnl += realized_pnl

        if target_dir != 0:
            self._open(target_dir, target_intensity, current_price)
            self._update_floating_pnl(current_price)

        return realized_pnl

    @property
    def is_open(self) -> bool:
        """True se tem posição aberta."""
        return self.direction != 0

    @property
    def points_per_pip(self) -> int:
        """Points por pip — idêntico ao TradingEnv."""
        return 10 if self.digits in [5, 3] else 1

    @property
    def size(self) -> float:
        """Lote correspondente à intensidade (tabela do treino)."""
        if 0 <= self.intensity < len(self.lot_sizes):
            return self.lot_sizes[self.intensity]
        return 0.0

    @property
    def direction_name(self) -> str:
        if self.direction == 1:
            return "LONG"
        elif self.direction == -1:
            return "SHORT"
        return "FLAT"

    def as_core_virtual_position(self):
        """
        Converte para o VirtualPosition do core (usado pelo FeatureCalculator).
        Injeta size calculado para manter paridade com TradingEnv._get_obs().
        """
        from core.models import VirtualPosition
        return VirtualPosition(
            direction=self.direction,
            intensity=self.intensity,
            entry_price=self.entry_price,
            current_pnl=self.current_pnl,
            size=self.size,
        )

    # =========================================================================
    # LÓGICA INTERNA (idêntica ao TradingEnv)
    # =========================================================================

    def _open(self, direction: int, intensity: int, price: float) -> None:
        """Abre posição virtual com custos do treino."""
        spread_cost = self.spread_points * self.point
        slippage = self.slippage_points * self.point

        if direction == 1:   # LONG
            self.entry_price = price + spread_cost + slippage
        else:                # SHORT
            self.entry_price = price - spread_cost - slippage

        self.direction = direction
        self.intensity = intensity
        self.current_pnl = 0.0

        # Deduz comissão de entrada (metade)
        lot_size = self.lot_sizes[intensity]
        self._apply_commission(lot_size, half=True)

    def _close(self, price: float) -> float:
        """Fecha posição virtual, retorna PnL realizado."""
        if self.direction == 0:
            return 0.0

        slippage = self.slippage_points * self.point

        if self.direction == 1:   # LONG
            exit_price = price - slippage
        else:                     # SHORT
            exit_price = price + slippage

        # Calcula PnL
        price_diff = (exit_price - self.entry_price) * self.direction
        pips = price_diff / self.point / self.points_per_pip
        lot_size = self.lot_sizes[self.intensity]
        pnl = pips * self.pip_value * lot_size

        # Deduz comissão de saída (metade)
        pnl -= (self.commission_per_lot * lot_size) / 2

        # Reset
        self.direction = 0
        self.intensity = 0
        self.entry_price = 0.0
        self.current_pnl = 0.0

        return pnl

    def _update_floating_pnl(self, current_price: float) -> None:
        """Atualiza PnL flutuante (usado como feature de posição)."""
        if self.direction == 0:
            self.current_pnl = 0.0
            return

        price_diff = (current_price - self.entry_price) * self.direction
        pips = price_diff / self.point / self.points_per_pip
        lot_size = self.lot_sizes[self.intensity]
        self.current_pnl = pips * self.pip_value * lot_size

    def _apply_commission(self, lot_size: float, half: bool = False) -> None:
        """Aplica comissão (metade na entrada, metade na saída)."""
        comm = self.commission_per_lot * lot_size
        if half:
            comm /= 2
        self.current_pnl -= comm
