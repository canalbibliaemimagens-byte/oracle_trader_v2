"""
Oracle Trader v2 - Máquina de Estados

Gerencia transições de estado dos símbolos.
Centraliza a lógica de quando entrar/sair do Paper Trade.

Estados:
    NO_MODEL → PAPER_TRADE (ao carregar modelo)
    PAPER_TRADE → NORMAL (critérios de saída atingidos)
    NORMAL → PAPER_TRADE (SL hits, TP Global, DD Limit)
    NORMAL → BLOCKED (comando manual)
    BLOCKED → PAPER_TRADE (comando UNBLOCK)
"""

import logging
import time
from typing import Optional, Tuple
from dataclasses import dataclass

from models import (
    SymbolState,
    SymbolStatus,
    PaperTradeReason,
    TradeAction,
)

logger = logging.getLogger("OracleTrader.StateMachine")


@dataclass
class PaperTradeConfig:
    """Configuração dos critérios de Paper Trade"""
    exit_wins_required: int = 3      # Wins virtuais necessários para sair
    exit_streak_required: int = 2    # Streak mínimo de wins
    sl_window_minutes: int = 30      # Janela de tempo para SL hits
    sl_max_hits: int = 2             # Máximo de SL hits na janela


class StateMachine:
    """
    Gerencia transições de estado dos símbolos.
    
    Responsabilidades:
    - Decidir quando entrar em Paper Trade
    - Decidir quando sair do Paper Trade
    - Validar transições de estado
    """
    
    def __init__(self, config: PaperTradeConfig = None):
        self.config = config or PaperTradeConfig()
    
    # =========================================================================
    # Transições de Entrada em Paper Trade
    # =========================================================================
    
    def enter_paper_trade(
        self, 
        state: SymbolState, 
        reason: PaperTradeReason,
        last_direction: int = 0
    ) -> bool:
        """
        Coloca símbolo em modo Paper Trade.
        
        Args:
            state: Estado do símbolo
            reason: Motivo da entrada
            last_direction: Direção da última posição (para referência)
            
        Returns:
            True se transição foi realizada
        """
        old_status = state.status
        
        # BLOCKED não pode entrar em Paper Trade (precisa UNBLOCK primeiro)
        if old_status == SymbolStatus.BLOCKED:
            logger.warning(f"[{state.symbol}] Não pode entrar em Paper Trade - está BLOCKED")
            return False
        
        # Já está em Paper Trade - apenas atualiza motivo se necessário
        if old_status == SymbolStatus.PAPER_TRADE:
            if state.paper_trade_reason != reason:
                logger.info(f"[{state.symbol}] Paper Trade: motivo atualizado {state.paper_trade_reason} → {reason}")
                state.paper_trade_reason = reason
            return True
        
        # Realiza transição
        state.status = SymbolStatus.PAPER_TRADE
        state.paper_trade_reason = reason
        
        # Reseta estatísticas virtuais para nova "sessão" de paper trade
        state.virtual_stats.reset()
        state.virtual_stats.symbol = state.symbol
        
        # Guarda direção da última posição (útil para lógica de saída)
        if last_direction != 0:
            # Podemos usar isso para evitar reentrar na mesma direção
            pass
        
        logger.info(f"[{state.symbol}] {old_status.value} → PAPER_TRADE ({reason.value})")
        
        return True
    
    def enter_paper_trade_sl_protection(
        self, 
        state: SymbolState,
        last_direction: int = 0
    ) -> bool:
        """
        Entrada em Paper Trade por proteção de SL.
        
        Chamado quando múltiplos SL hits ocorrem em janela de tempo.
        """
        return self.enter_paper_trade(
            state, 
            PaperTradeReason.SL_PROTECTION,
            last_direction
        )
    
    def enter_paper_trade_tp_global(self, state: SymbolState, pnl: float) -> bool:
        """
        Entrada em Paper Trade por TP Global.
        
        Chamado quando o sistema atinge o target de lucro global.
        Símbolos que fecharam com lucro vão para Paper Trade.
        """
        if pnl >= 0:
            return self.enter_paper_trade(state, PaperTradeReason.TP_GLOBAL)
        else:
            # Símbolos com prejuízo voltam para NORMAL
            state.status = SymbolStatus.NORMAL
            state.paper_trade_reason = None
            logger.info(f"[{state.symbol}] TP Global: PnL negativo → NORMAL")
            return False
    
    def enter_paper_trade_dd_limit(self, state: SymbolState) -> bool:
        """
        Entrada em Paper Trade por DD Limit.
        
        Chamado quando o drawdown atinge o limite configurado.
        """
        return self.enter_paper_trade(state, PaperTradeReason.DD_LIMIT)
    
    # =========================================================================
    # Transições de Saída do Paper Trade
    # =========================================================================
    
    def check_exit_paper_trade(self, state: SymbolState) -> Tuple[bool, str]:
        """
        Verifica se o símbolo pode sair do Paper Trade.
        
        Args:
            state: Estado do símbolo
            
        Returns:
            Tuple (pode_sair, motivo)
        """
        if state.status != SymbolStatus.PAPER_TRADE:
            return False, "Não está em Paper Trade"
        
        reason = state.paper_trade_reason
        stats = state.virtual_stats
        
        # STARTUP: sai com primeira predição WAIT
        if reason == PaperTradeReason.STARTUP:
            if state.last_action == TradeAction.WAIT:
                return True, "Primeira predição WAIT"
            return False, "Aguardando predição WAIT"
        
        # MANUAL: só sai com comando UNBLOCK (tratado em outro lugar)
        if reason == PaperTradeReason.MANUAL:
            return False, "Bloqueio manual - use UNBLOCK"
        
        # SL_PROTECTION, TP_GLOBAL, DD_LIMIT: critérios de wins virtuais
        wins_ok = stats.virtual_wins >= self.config.exit_wins_required
        streak_ok = stats.current_streak >= self.config.exit_streak_required
        
        if wins_ok and streak_ok:
            return True, f"Critérios atingidos: {stats.virtual_wins} wins, streak {stats.current_streak}"
        
        # Detalhes do que falta
        missing = []
        if not wins_ok:
            missing.append(f"wins: {stats.virtual_wins}/{self.config.exit_wins_required}")
        if not streak_ok:
            missing.append(f"streak: {stats.current_streak}/{self.config.exit_streak_required}")
        
        return False, f"Falta: {', '.join(missing)}"
    
    def try_exit_paper_trade(self, state: SymbolState) -> bool:
        """
        Tenta sair do Paper Trade se critérios forem atingidos.
        
        Args:
            state: Estado do símbolo
            
        Returns:
            True se saiu do Paper Trade
        """
        can_exit, reason = self.check_exit_paper_trade(state)
        
        if can_exit:
            old_reason = state.paper_trade_reason
            state.status = SymbolStatus.NORMAL
            state.paper_trade_reason = None
            
            # Reseta contadores de SL para nova "vida"
            state.sl_hit_times = []
            state.sl_hits_in_window = 0
            
            logger.info(f"[{state.symbol}] PAPER_TRADE ({old_reason.value}) → NORMAL ({reason})")
            return True
        
        return False
    
    # =========================================================================
    # Outras Transições
    # =========================================================================
    
    def block_symbol(self, state: SymbolState) -> bool:
        """
        Bloqueia símbolo (comando manual).
        
        Args:
            state: Estado do símbolo
            
        Returns:
            True se bloqueou
        """
        if state.status == SymbolStatus.BLOCKED:
            return True  # Já está bloqueado
        
        old_status = state.status
        state.status = SymbolStatus.BLOCKED
        state.paper_trade_reason = None
        
        logger.info(f"[{state.symbol}] {old_status.value} → BLOCKED (manual)")
        return True
    
    def unblock_symbol(self, state: SymbolState) -> bool:
        """
        Desbloqueia símbolo (comando manual).
        Vai para PAPER_TRADE com motivo MANUAL.
        
        Args:
            state: Estado do símbolo
            
        Returns:
            True se desbloqueou
        """
        if state.status != SymbolStatus.BLOCKED:
            logger.warning(f"[{state.symbol}] Não está BLOCKED, está {state.status.value}")
            return False
        
        # Vai para Paper Trade para "aquecer"
        state.status = SymbolStatus.PAPER_TRADE
        state.paper_trade_reason = PaperTradeReason.STARTUP
        state.virtual_stats.reset()
        
        logger.info(f"[{state.symbol}] BLOCKED → PAPER_TRADE (STARTUP)")
        return True
    
    def force_normal(self, state: SymbolState) -> bool:
        """
        Força símbolo para NORMAL (ignora critérios).
        
        Use com cuidado - apenas para emergências ou testes.
        
        Args:
            state: Estado do símbolo
            
        Returns:
            True se forçou
        """
        old_status = state.status
        
        state.status = SymbolStatus.NORMAL
        state.paper_trade_reason = None
        state.sl_hit_times = []
        state.sl_hits_in_window = 0
        state.virtual_stats.reset()
        
        logger.warning(f"[{state.symbol}] {old_status.value} → NORMAL (FORÇADO)")
        return True
    
    # =========================================================================
    # SL Hit Tracking
    # =========================================================================
    
    def record_sl_hit(self, state: SymbolState) -> bool:
        """
        Registra um SL hit e verifica se deve entrar em Paper Trade.
        
        Args:
            state: Estado do símbolo
            
        Returns:
            True se entrou em Paper Trade por SL Protection
        """
        now = time.time()
        window_seconds = self.config.sl_window_minutes * 60
        
        # Remove hits antigos fora da janela
        state.sl_hit_times = [t for t in state.sl_hit_times if now - t < window_seconds]
        
        # Adiciona novo hit
        state.sl_hit_times.append(now)
        state.sl_hits_in_window = len(state.sl_hit_times)
        
        logger.info(f"[{state.symbol}] SL Hit #{state.sl_hits_in_window} (janela: {self.config.sl_window_minutes}min)")
        
        # Verifica se atingiu limite
        if state.sl_hits_in_window >= self.config.sl_max_hits:
            last_dir = state.position.direction if state.position.is_open else 0
            self.enter_paper_trade_sl_protection(state, last_dir)
            return True
        
        return False
    
    # =========================================================================
    # Utilitários
    # =========================================================================
    
    def get_status_summary(self, state: SymbolState) -> dict:
        """
        Retorna resumo do status para dashboard/logs.
        """
        summary = {
            'symbol': state.symbol,
            'status': state.status.value,
            'paper_trade_reason': state.paper_trade_reason.value if state.paper_trade_reason else None,
        }
        
        if state.status == SymbolStatus.PAPER_TRADE:
            can_exit, exit_reason = self.check_exit_paper_trade(state)
            summary['can_exit'] = can_exit
            summary['exit_reason'] = exit_reason
            summary['virtual_stats'] = state.virtual_stats.to_dict()
        
        if state.sl_hits_in_window > 0:
            summary['sl_hits'] = state.sl_hits_in_window
        
        return summary
