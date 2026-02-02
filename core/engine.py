"""
Oracle Trader v2 - Engine

Loop principal orquestrador do sistema.

Responsabilidades:
- Inicializar e coordenar todos os módulos
- Executar ciclo: dados → predição → execução → update
- Gerenciar tasks assíncronas paralelas
- Graceful shutdown

Este é o coração do sistema - mantém tudo funcionando.
"""

import asyncio
import logging
import signal
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Callable, Any

from models import (
    SymbolState,
    SystemState,
    SymbolStatus,
    SystemStatus,
    TradeAction,
)
from core.config import ConfigManager, RuntimeConfig
from core.state_machine import StateMachine, PaperTradeConfig
from trading.executor import Executor
from trading.risk_manager import RiskManager
from trading.position_manager import PositionManager
from trading.paper_trade import PaperTradeManager
from infra import BrokerBase

logger = logging.getLogger("OracleTrader.Engine")

# Versão do Engine
VERSION = "2.0.0"


class OracleEngine:
    """
    Engine principal do Oracle Trader.
    
    Orquestra todos os módulos e executa o loop de trading.
    
    Uso:
        engine = OracleEngine(broker, config_manager)
        await engine.initialize()
        await engine.run()  # Bloqueia até shutdown
    """
    
    def __init__(
        self,
        broker: BrokerBase,
        config_manager: ConfigManager,
        predictor: Optional[Any] = None,  # Será tipado quando ml/ for criado
    ):
        """
        Args:
            broker: Cliente do broker (MT5, etc.)
            config_manager: Gerenciador de configuração
            predictor: Componente de predição ML (opcional por enquanto)
        """
        self.broker = broker
        self.config_manager = config_manager
        self.predictor = predictor
        
        # Carrega configuração
        self.config = config_manager.load()
        
        # Inicializa módulos core
        self.state_machine = StateMachine(self.config.paper_trade)
        self.risk_manager = RiskManager(self.config.risk)
        self.paper_trade = PaperTradeManager()
        self.position_manager = PositionManager()
        
        # Executor será inicializado após conectar broker
        self.executor: Optional[Executor] = None
        
        # Estados
        self.system = SystemState()
        self.symbols: Dict[str, SymbolState] = {}
        
        # Controle de execução
        self.running = False
        self._shutdown_event = asyncio.Event()
        self._tasks: list = []
        
        # Callbacks opcionais (para WebSocket, etc.)
        self.on_trade: Optional[Callable] = None
        self.on_event: Optional[Callable] = None
        self.on_tick: Optional[Callable] = None
    
    # =========================================================================
    # Inicialização
    # =========================================================================
    
    async def initialize(self) -> bool:
        """
        Inicializa o sistema.
        
        Returns:
            True se inicialização foi bem sucedida
        """
        logger.info("=" * 60)
        logger.info(f"  ORACLE TRADER v{VERSION}")
        logger.info("=" * 60)
        
        # 1. Conecta ao broker
        if not await self._connect_broker():
            return False
        
        # 2. Carrega informações da conta
        await self._load_account_info()
        
        # 3. Inicializa executor (precisa do broker conectado)
        self.executor = Executor(
            broker=self.broker,
            risk_manager=self.risk_manager,
            paper_trade=self.paper_trade,
            magic_base=self.config.broker.magic_base,
        )
        
        # 4. Carrega modelos (se predictor disponível)
        if self.predictor:
            await self._load_models()
        else:
            logger.warning("Predictor não configurado - sistema iniciará sem modelos")
        
        # 5. Inicializa cache de barras
        await self._initialize_cache()
        
        # 6. Escaneia posições existentes
        await self._scan_existing_positions()
        
        # 7. Carrega símbolos habilitados
        self._load_symbols_config()
        
        # 8. Predições iniciais (popula estado)
        await self._initial_predictions()
        
        # Sistema pronto
        self.system.status = SystemStatus.RUNNING
        
        self._log_startup_summary()
        
        return True
    
    async def _connect_broker(self) -> bool:
        """Conecta ao broker."""
        logger.info("Conectando ao broker...")
        
        if not await self.broker.connect():
            logger.error("Falha ao conectar ao broker")
            return False
        
        # Log info do broker
        info = await self.broker.get_terminal_info()
        logger.info(f"Broker: {info.get('name', '?')} (build {info.get('build', '?')})")
        
        return True
    
    async def _load_account_info(self) -> None:
        """Carrega informações iniciais da conta."""
        account = await self.broker.get_account_info()
        
        self.system.balance = account.get('balance', 0)
        self.system.equity = account.get('equity', 0)
        self.system.initial_balance = account.get('balance', 0)
        self.system.peak_balance = account.get('equity', 0)
        self.system.daily_start_balance = account.get('balance', 0)
        
        logger.info(f"Conta: {account.get('login', '?')} | {account.get('server', '?')}")
        logger.info(f"Balance: ${self.system.balance:.2f} | Equity: ${self.system.equity:.2f}")
    
    async def _load_models(self) -> None:
        """Carrega modelos de ML."""
        # TODO: Implementar quando ml/model_loader.py for criado
        logger.info("Carregando modelos...")
        
        models_dir = self.config.models_dir
        # count = await self.predictor.load_models(models_dir)
        # logger.info(f"Modelos carregados: {count}")
        pass
    
    async def _initialize_cache(self) -> None:
        """Inicializa cache de barras OHLCV."""
        logger.info("Inicializando cache de barras...")
        
        for symbol, state in self.symbols.items():
            config = state.config
            if not config:
                continue
            
            df = await self.broker.get_bars(symbol, config.timeframe, 300)
            
            if df is not None and len(df) >= 200:
                for _, row in df.iterrows():
                    state.bars.append(row.to_dict())
                state.last_bar_time = int(df.iloc[-1]['time'])
                state.last_update = time.time()
                logger.info(f"  {symbol}: {len(df)} barras")
            else:
                # Símbolo com problema vai para Paper Trade
                self.state_machine.enter_paper_trade(state, state.paper_trade_reason)
                state.failures = 1
                logger.warning(f"  {symbol}: falha ao carregar barras")
    
    async def _scan_existing_positions(self) -> None:
        """Escaneia posições já abertas no broker."""
        logger.info("Escaneando posições existentes...")
        
        positions = await self.broker.get_positions(self.config.broker.magic_base)
        
        for pos in positions:
            symbol = pos['symbol']
            if symbol not in self.symbols:
                continue
            
            state = self.symbols[symbol]
            
            # Sincroniza posição
            self.position_manager.sync_position(state, pos)
            
            # Símbolo com posição aberta vai direto para NORMAL
            state.status = SymbolStatus.NORMAL
            state.paper_trade_reason = None
            
            logger.info(f"  {symbol}: {state.position.direction_str} {state.position.size}")
    
    def _load_symbols_config(self) -> None:
        """Carrega configuração individual dos símbolos."""
        symbols_config = self.config_manager.load_symbols_config()
        
        # Marca símbolos não configurados como BLOCKED
        for symbol, state in self.symbols.items():
            if not self.config_manager.is_symbol_enabled(symbol):
                self.state_machine.block_symbol(state)
                logger.warning(f"  {symbol}: Não configurado → BLOCKED")
    
    async def _initial_predictions(self) -> None:
        """Faz predições iniciais para popular estado."""
        if not self.predictor:
            return
        
        logger.info("Executando predições iniciais...")
        
        for symbol, state in self.symbols.items():
            if state.status == SymbolStatus.BLOCKED:
                continue
            
            if len(state.bars) < 200:
                continue
            
            # TODO: Implementar predição quando ml/ estiver pronto
            # action, hmm_state, lot_size = await self.predictor.predict(symbol, state.bars)
            # state.last_action = action
            # state.last_hmm_state = hmm_state
            # state.last_lot_size = lot_size
            pass
        
        logger.info("Predições iniciais concluídas")
    
    def _log_startup_summary(self) -> None:
        """Log do resumo de inicialização."""
        normal = sum(1 for s in self.symbols.values() if s.status == SymbolStatus.NORMAL)
        paper = sum(1 for s in self.symbols.values() if s.status == SymbolStatus.PAPER_TRADE)
        blocked = sum(1 for s in self.symbols.values() if s.status == SymbolStatus.BLOCKED)
        
        risk = self.config.risk
        
        logger.info("=" * 60)
        logger.info("  Sistema inicializado")
        logger.info(f"  Símbolos: {len(self.symbols)} (Normal: {normal}, Paper: {paper}, Blocked: {blocked})")
        logger.info(f"  DD Limits: -{risk.dd_limit_pct}% / -{risk.dd_emergency_pct}%")
        tp_str = f"+{risk.dd_tp_pct}%" if risk.dd_tp_pct > 0 else "OFF"
        logger.info(f"  TP Global: {tp_str}")
        logger.info("=" * 60)
    
    # =========================================================================
    # Loop Principal
    # =========================================================================
    
    async def run(self) -> None:
        """
        Executa o loop principal.
        
        Bloqueia até shutdown ser chamado.
        """
        self.running = True
        logger.info("Loop principal iniciado")
        
        # Cria tasks paralelas
        self._tasks = [
            asyncio.create_task(self._main_loop(), name="main_loop"),
            asyncio.create_task(self._update_loop(), name="update_loop"),
            asyncio.create_task(self._broadcast_loop(), name="broadcast_loop"),
            asyncio.create_task(self._status_loop(), name="status_loop"),
        ]
        
        try:
            # Aguarda sinal de shutdown
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            logger.info("Run cancelado")
        finally:
            self.running = False
            
            # Cancela todas as tasks
            for task in self._tasks:
                if not task.done():
                    task.cancel()
            
            # Aguarda conclusão
            await asyncio.gather(*self._tasks, return_exceptions=True)
    
    async def _main_loop(self) -> None:
        """
        Loop principal - verifica novas barras e processa.
        
        Ciclo: dados → predição → execução
        """
        while self.running:
            try:
                if self.system.status == SystemStatus.RUNNING:
                    await self._process_cycle()
                
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.system.error_count += 1
                self.system.last_error = str(e)
                self.system.last_error_time = time.time()
                logger.error(f"Main loop erro: {e}")
                await asyncio.sleep(1)
    
    async def _update_loop(self) -> None:
        """
        Loop de atualização - conta, posições, risco.
        
        Executa a cada 1 segundo.
        """
        while self.running:
            try:
                # Atualiza conta
                await self._update_account()
                
                # Atualiza posições
                await self._update_positions()
                
                # Verifica limites de risco
                await self._check_risk()
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Update loop erro: {e}")
                await asyncio.sleep(1)
    
    async def _broadcast_loop(self) -> None:
        """
        Loop de broadcast - envia updates via callback.
        
        Executa a cada 1 segundo.
        """
        while self.running:
            try:
                if self.on_tick:
                    tick_data = self._build_tick_data()
                    await self._safe_callback(self.on_tick, tick_data)
                
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Broadcast loop erro: {e}")
                await asyncio.sleep(1)
    
    async def _status_loop(self) -> None:
        """
        Loop de status - log periódico.
        
        Executa a cada 60 segundos.
        """
        while self.running:
            try:
                await asyncio.sleep(60)
                
                self._log_status()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Status loop erro: {e}")
    
    # =========================================================================
    # Ciclo de Trading
    # =========================================================================
    
    async def _process_cycle(self) -> None:
        """Processa um ciclo - verifica novas barras."""
        new_bars = []
        
        for symbol, state in self.symbols.items():
            if state.status in [SymbolStatus.BLOCKED]:
                continue
            
            config = state.config
            if not config:
                continue
            
            # Busca últimas barras
            df = await self.broker.get_bars(symbol, config.timeframe, 5)
            
            if df is None or len(df) == 0:
                continue
            
            bar_time = int(df.iloc[-1]['time'])
            
            # Nova barra detectada?
            if bar_time > state.last_bar_time:
                new_bars.append(symbol)
                state.last_bar_time = bar_time
                
                # Atualiza cache
                self._update_bars_cache(state, df)
                state.last_update = time.time()
        
        if not new_bars:
            return
        
        # Processa símbolos com nova barra
        self.system.cycle_count += 1
        cycle_start = time.time()
        
        for symbol in new_bars:
            await self._process_symbol(symbol)
        
        self.system.last_cycle_time = time.time() - cycle_start
        
        logger.info(f"[CYCLE {self.system.cycle_count}] Nova barra: {', '.join(new_bars)}")
    
    async def _process_symbol(self, symbol: str) -> None:
        """Processa predição e execução para um símbolo."""
        state = self.symbols[symbol]
        
        # Verifica se tem dados suficientes
        if len(state.bars) < 200:
            return
        
        # Atualiza posição antes de processar
        await self._update_symbol_position(symbol)
        
        try:
            # Faz predição
            action, action_idx, hmm_state = await self._predict(symbol, state)
            
            # Atualiza estado
            state.last_action = action
            state.last_model_action_idx = action_idx
            state.last_hmm_state = hmm_state
            state.last_prediction_time = time.time()
            
            # Log
            self._log_prediction(state, action)
            
            # Tenta sair do Paper Trade (se aplicável)
            if state.status == SymbolStatus.PAPER_TRADE:
                self.state_machine.try_exit_paper_trade(state)
            
            # Executa ação
            if self.executor:
                current_price = state.bars[-1]['close']
                await self.executor.execute_action(
                    state=state,
                    action=action,
                    action_idx=action_idx,
                    current_price=current_price,
                    system=self.system,
                )
            
            # Reset falhas
            state.failures = 0
            
        except Exception as e:
            logger.error(f"[{symbol}] Erro no processamento: {e}")
            state.failures += 1
    
    async def _predict(self, symbol: str, state: SymbolState) -> tuple:
        """
        Faz predição para um símbolo.
        
        Returns:
            Tuple (action, action_idx, hmm_state)
        """
        if not self.predictor:
            # Sem predictor, retorna WAIT
            return TradeAction.WAIT, 0, 0
        
        # TODO: Implementar quando ml/ estiver pronto
        # return await self.predictor.predict(symbol, state.bars, state.position)
        return TradeAction.WAIT, 0, 0
    
    # =========================================================================
    # Updates
    # =========================================================================
    
    async def _update_account(self) -> None:
        """Atualiza informações da conta."""
        account = await self.broker.get_account_info()
        
        if not account:
            return
        
        self.system.balance = account.get('balance', self.system.balance)
        self.system.equity = account.get('equity', self.system.equity)
        self.system.margin = account.get('margin', 0)
        self.system.free_margin = account.get('free_margin', 0)
        self.system.margin_level = account.get('margin_level', 0)
        
        # Atualiza drawdown
        self.risk_manager.update_drawdown(self.system)
    
    async def _update_positions(self) -> None:
        """Atualiza posições de todos os símbolos."""
        positions = await self.broker.get_positions(self.config.broker.magic_base)
        
        # Sincroniza com PositionManager
        closed_positions = self.position_manager.sync_all_positions(
            self.symbols, positions
        )
        
        # Trata posições fechadas externamente
        for symbol, close_info in closed_positions.items():
            state = self.symbols.get(symbol)
            if state:
                await self._handle_closed_position(state, close_info)
    
    async def _update_symbol_position(self, symbol: str) -> None:
        """Atualiza posição de um símbolo específico."""
        state = self.symbols.get(symbol)
        if not state:
            return
        
        positions = await self.broker.get_positions(self.config.broker.magic_base)
        
        for pos in positions:
            if pos['symbol'] == symbol:
                self.position_manager.sync_position(state, pos)
                return
        
        # Posição não encontrada - pode ter sido fechada
        if state.position.is_open:
            close_info = await self.broker.get_closed_position_info(state.position.ticket)
            if close_info:
                await self._handle_closed_position(state, close_info)
    
    async def _handle_closed_position(self, state: SymbolState, close_info: dict) -> None:
        """Trata posição fechada externamente (SL, TP, manual)."""
        close_reason = close_info.get('close_reason', 'UNKNOWN')
        pnl = close_info.get('pnl', 0)
        
        logger.warning(f"[{state.symbol}] Posição fechada externamente: {close_reason} | PnL: ${pnl:.2f}")
        
        # Atualiza estatísticas
        state.total_pnl += pnl
        self.system.total_pnl += pnl
        
        if pnl >= 0:
            state.wins += 1
            self.system.total_wins += 1
        else:
            state.losses += 1
            self.system.total_losses += 1
        
        # Se foi SL, registra hit
        if close_reason == "SL":
            entered_paper = self.state_machine.record_sl_hit(state)
            if entered_paper and self.on_event:
                await self._safe_callback(self.on_event, "SL_PROTECTION", {"symbol": state.symbol})
        
        # Callback de trade
        if self.on_trade:
            await self._safe_callback(self.on_trade, {
                "symbol": state.symbol,
                "action": "CLOSE",
                "reason": close_reason,
                "pnl": pnl,
            })
        
        # Limpa posição
        state.position = state.position.__class__()  # Reset
    
    async def _check_risk(self) -> None:
        """Verifica limites de risco."""
        # Atualiza status de risk limit
        self.risk_manager.update_risk_limit_status(self.system)
        
        # Verifica DD Emergency
        if self.risk_manager.should_emergency_close(self.system):
            await self._emergency_stop()
            return
        
        # Verifica TP Global
        if self.risk_manager.should_take_profit_global(self.system):
            await self._take_profit_global()
    
    async def _emergency_stop(self) -> None:
        """Executa emergency stop - fecha tudo."""
        logger.critical(f"[EMERGENCY] DD: {self.system.current_dd:.2f}%")
        
        self.system.status = SystemStatus.EMERGENCY_STOP
        
        if self.executor:
            await self.executor.close_all_positions(self.symbols, self.system, "EMERGENCY")
        
        if self.on_event:
            await self._safe_callback(self.on_event, "EMERGENCY_STOP", {
                "dd_pct": self.system.current_dd
            })
    
    async def _take_profit_global(self) -> None:
        """Executa Take Profit Global."""
        logger.info(f"[TP GLOBAL] DD: {self.system.current_dd:+.2f}%")
        
        if self.executor:
            results = await self.executor.close_all_positions(
                self.symbols, self.system, "TP_GLOBAL"
            )
        
        # Símbolos com lucro → Paper Trade
        # Símbolos com prejuízo → NORMAL
        for symbol, pnl in results.items():
            state = self.symbols.get(symbol)
            if state:
                self.state_machine.enter_paper_trade_tp_global(state, pnl)
        
        if self.on_event:
            await self._safe_callback(self.on_event, "TP_GLOBAL", {
                "dd_pct": self.system.current_dd,
                "results": results,
            })
    
    # =========================================================================
    # Utilitários
    # =========================================================================
    
    def _update_bars_cache(self, state: SymbolState, df) -> None:
        """Atualiza cache de barras."""
        for _, row in df.iterrows():
            bar = row.to_dict()
            
            # Substitui barra existente ou adiciona nova
            if state.bars and state.bars[-1]['time'] == bar['time']:
                state.bars[-1] = bar
            elif bar['time'] > (state.bars[-1]['time'] if state.bars else 0):
                state.bars.append(bar)
    
    def _build_tick_data(self) -> dict:
        """Constrói dados para broadcast de tick."""
        return {
            'system': self.system.get_summary_dict(),
            'positions': {
                s: {
                    'dir': st.position.direction_str,
                    'size': st.position.size,
                    'pnl': round(st.position.pnl, 2),
                    'pips': round(st.position.pnl_pips, 1),
                }
                for s, st in self.symbols.items()
                if st.position.is_open
            },
            'symbol_updates': {
                s: {
                    'status': st.status.value,
                    'prediction': {
                        'action': st.last_action.value if st.last_action else "WAIT",
                        'hmm_state': st.last_hmm_state,
                    }
                }
                for s, st in self.symbols.items()
            }
        }
    
    def _log_prediction(self, state: SymbolState, action: TradeAction) -> None:
        """Log da predição."""
        pos_str = "FLAT"
        if state.position.is_open:
            pos_str = f"{state.position.direction_str} {state.position.size}"
        
        status_tag = f"[{state.status.value}] " if state.status != SymbolStatus.NORMAL else ""
        
        logger.info(
            f"[{state.symbol}] {status_tag}HMM:{state.last_hmm_state} → "
            f"{action.value} {state.last_lot_size:.2f} | Pos:{pos_str}"
        )
    
    def _log_status(self) -> None:
        """Log periódico de status."""
        open_pos = sum(1 for s in self.symbols.values() if s.position.is_open)
        paper = sum(1 for s in self.symbols.values() if s.status == SymbolStatus.PAPER_TRADE)
        normal = sum(1 for s in self.symbols.values() if s.status == SymbolStatus.NORMAL)
        blocked = sum(1 for s in self.symbols.values() if s.status == SymbolStatus.BLOCKED)
        open_pnl = sum(s.position.pnl for s in self.symbols.values() if s.position.is_open)
        
        risk_str = " | RISK_LIMIT" if self.system.risk_limit_active else ""
        
        logger.info(
            f"[STATUS] Balance: ${self.system.balance:.2f} | "
            f"Equity: ${self.system.equity:.2f} | "
            f"DD: {self.system.current_dd:+.2f}% | "
            f"Open: {open_pos} (${open_pnl:.2f}) | "
            f"Normal: {normal} | Paper: {paper} | Blocked: {blocked} | "
            f"Trades: {self.system.total_trades} | "
            f"PnL: ${self.system.total_pnl:.2f}{risk_str}"
        )
    
    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Executa callback de forma segura."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args)
            else:
                callback(*args)
        except Exception as e:
            logger.error(f"Callback erro: {e}")
    
    # =========================================================================
    # Controle e Shutdown
    # =========================================================================
    
    def pause(self) -> None:
        """Pausa o sistema."""
        self.system.status = SystemStatus.PAUSED
        logger.info("Sistema PAUSADO")
    
    def resume(self) -> None:
        """Retoma o sistema."""
        if self.system.status == SystemStatus.PAUSED:
            self.system.status = SystemStatus.RUNNING
            logger.info("Sistema RETOMADO")
    
    async def shutdown(self, reason: str = "NORMAL") -> None:
        """
        Encerra o sistema graciosamente.
        
        Args:
            reason: Motivo do encerramento
        """
        logger.info(f"Encerrando Oracle Trader ({reason})...")
        
        self.running = False
        self._shutdown_event.set()
        
        # Desconecta broker
        if self.broker:
            await self.broker.disconnect()
        
        logger.info(f"Oracle Trader encerrado ({reason})")
    
    def get_full_state(self) -> dict:
        """
        Retorna estado completo para dashboard/WebSocket.
        """
        return {
            "version": VERSION,
            "timestamp": time.time(),
            "system": {
                **self.system.get_summary_dict(),
                "margin": self.system.margin,
                "free_margin": self.system.free_margin,
                "initial_balance": self.system.initial_balance,
                "peak_balance": self.system.peak_balance,
            },
            "config": self.config.to_dict(),
            "symbols": {s: st.to_dict() for s, st in self.symbols.items()},
        }


def setup_signal_handlers(engine: OracleEngine, loop: asyncio.AbstractEventLoop) -> None:
    """
    Configura handlers para SIGINT e SIGTERM.
    
    Permite graceful shutdown com Ctrl+C.
    """
    def handler(sig, frame):
        logger.info("Sinal de encerramento recebido")
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(engine.shutdown("SIGNAL"))
        )
    
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
