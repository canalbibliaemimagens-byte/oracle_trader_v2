"""
Oracle Trader v2.0 — Comment Builder
======================================

Monta comentário estruturado para rastreabilidade em ordens cTrader.

Formato: O|{V}|{H}|{A}|{I}|{B}|{D}|{VP}

Campos:
  V  = Versão do sistema
  H  = HMM State (0-4)
  A  = Action Index (0-6)
  I  = Intensity (0-3)
  B  = Balance (USD, inteiro)
  D  = Drawdown % (1 decimal)
  VP = Virtual PnL (2 decimais)

Limite cTrader Label: 100 caracteres.
"""


class CommentBuilder:
    """Monta e parseia comentários estruturados de ordens."""

    VERSION = "2.0"
    MAX_LENGTH = 100

    @staticmethod
    def build(
        hmm_state: int,
        action_index: int,
        intensity: int,
        balance: float,
        drawdown_pct: float,
        virtual_pnl: float,
    ) -> str:
        """
        Constrói comentário estruturado.

        Returns:
            String formatada (max 100 chars).
        """
        comment = (
            f"O|{CommentBuilder.VERSION}|"
            f"{hmm_state}|{action_index}|{intensity}|"
            f"{int(balance)}|{drawdown_pct:.1f}|{virtual_pnl:.2f}"
        )

        if len(comment) > CommentBuilder.MAX_LENGTH:
            comment = comment[: CommentBuilder.MAX_LENGTH]

        return comment

    @staticmethod
    def parse(comment: str) -> dict:
        """
        Parseia comentário estruturado.

        Returns:
            Dict com campos, ou {} se inválido.
        """
        if not comment or not comment.startswith("O|"):
            return {}

        parts = comment.split("|")
        if len(parts) < 8:
            return {}

        try:
            return {
                "version": parts[1],
                "hmm_state": int(parts[2]),
                "action_index": int(parts[3]),
                "intensity": int(parts[4]),
                "balance": int(parts[5]),
                "drawdown_pct": float(parts[6]),
                "virtual_pnl": float(parts[7]),
            }
        except (ValueError, IndexError):
            return {}
