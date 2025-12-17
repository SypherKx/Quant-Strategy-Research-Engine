"""
Parallel Strategy Simulator
============================

🎓 WHAT IS THIS FILE?
This file runs multiple strategies in parallel on the same market data.
Each strategy makes independent decisions without knowing about others.

🎓 WHY PARALLEL SIMULATION?

Wrong approach (sequential):
┌─────────────────────────────────────────────────────────────────┐
│ 1. Run Strategy A                                               │
│ 2. See results                                                  │
│ 3. Tune Strategy A based on results                             │
│ 4. Repeat                                                       │
│                                                                 │
│ Problem: You're OVERFITTING to historical data!                 │
│ The "improvements" may just be fitting noise.                   │
└─────────────────────────────────────────────────────────────────┘

Correct approach (parallel):
┌─────────────────────────────────────────────────────────────────┐
│                      SAME MARKET DATA                           │
│                            │                                    │
│         ┌──────────────────┼──────────────────┐                │
│         ▼                  ▼                  ▼                │
│    ┌─────────┐       ┌─────────┐        ┌─────────┐            │
│    │Strategy │       │Strategy │        │Strategy │            │
│    │    A    │       │    B    │        │    C    │            │
│    └────┬────┘       └────┬────┘        └────┬────┘            │
│         │                 │                  │                  │
│         ▼                 ▼                  ▼                  │
│    Own P&L            Own P&L            Own P&L               │
│    Own Trades         Own Trades         Own Trades            │
│                                                                 │
│ Each strategy: INDEPENDENT, NO HINDSIGHT, FAIR COMPARISON      │
└─────────────────────────────────────────────────────────────────┘

🎓 STATE MANAGEMENT:

Each strategy maintains its own:
- Virtual capital (starts same for all)
- Open positions
- Trade history
- P&L calculations
- Risk limits

This isolation ensures fair comparison.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import asyncio
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger, log_trade
from strategies.strategy_dna import StrategyDNA
from analysis.spread_analyzer import SpreadSignal
from analysis.regime_analyzer import MarketRegime
from data.websocket_streamer import SpreadData


# =========================================================
# POSITION AND TRADE STRUCTURES
# =========================================================

class Side(Enum):
    """Trade direction."""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Position:
    """
    An open position held by a strategy.
    
    🎓 In spread trading:
    - BUY on lower exchange
    - SELL on higher exchange
    - Hope prices converge
    """
    symbol: str
    entry_exchange: str      # Where we bought
    exit_exchange: str       # Where we'll sell
    side: Side
    quantity: int
    entry_price: float
    entry_time: datetime
    max_hold_time: timedelta
    take_profit_price: float
    stop_loss_price: float
    
    # Current state
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    
    def update_price(self, price: float):
        """Update position with new price."""
        self.current_price = price
        if self.side == Side.BUY:
            self.unrealized_pnl = (price - self.entry_price) * self.quantity
        else:
            self.unrealized_pnl = (self.entry_price - price) * self.quantity
    
    def should_exit(self, current_time: datetime) -> tuple:
        """
        Check if position should be exited.
        
        Returns:
            (should_exit: bool, reason: str)
        """
        # Time-based exit
        if current_time - self.entry_time > self.max_hold_time:
            return True, "max_hold_time"
        
        # P&L based exits
        pnl_pct = (self.unrealized_pnl / (self.entry_price * self.quantity)) * 100
        
        if self.side == Side.BUY:
            if pnl_pct >= (self.take_profit_price - self.entry_price) / self.entry_price * 100:
                return True, "take_profit"
            if pnl_pct <= -(self.stop_loss_price - self.entry_price) / self.entry_price * -100:
                return True, "stop_loss"
        
        return False, ""


@dataclass
class Trade:
    """
    A completed trade record.
    
    🎓 Immutable record of what happened.
    """
    id: int
    strategy_id: str
    symbol: str
    entry_exchange: str
    exit_exchange: str
    side: str
    quantity: int
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    exit_reason: str


# =========================================================
# STRATEGY STATE
# =========================================================

@dataclass
class StrategyState:
    """
    Complete state of a running strategy.
    
    🎓 Each strategy has its own isolated state.
    """
    dna: StrategyDNA
    
    # Capital
    initial_capital: float = field(default_factory=lambda: settings.INITIAL_CAPITAL)
    current_capital: float = field(default_factory=lambda: settings.INITIAL_CAPITAL)
    
    # Positions and trades
    open_positions: Dict[str, Position] = field(default_factory=dict)
    completed_trades: List[Trade] = field(default_factory=list)
    trade_counter: int = 0
    
    # Daily tracking
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_start_capital: float = field(default_factory=lambda: settings.INITIAL_CAPITAL)
    
    # Statistics
    total_pnl: float = 0.0
    win_count: int = 0
    loss_count: int = 0
    max_drawdown: float = 0.0
    peak_capital: float = field(default_factory=lambda: settings.INITIAL_CAPITAL)
    
    # Activity
    is_active: bool = True
    last_trade_time: Optional[datetime] = None
    ticks_since_signal: int = 0
    
    def reset_daily_stats(self):
        """Reset daily counters (call at market open)."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_start_capital = self.current_capital
    
    @property
    def daily_pnl_pct(self) -> float:
        """Daily P&L as percentage."""
        if self.daily_start_capital > 0:
            return (self.daily_pnl / self.daily_start_capital) * 100
        return 0.0
    
    @property
    def total_pnl_pct(self) -> float:
        """Total P&L as percentage."""
        if self.initial_capital > 0:
            return (self.total_pnl / self.initial_capital) * 100
        return 0.0
    
    @property
    def win_rate(self) -> float:
        """Win rate as percentage."""
        total = self.win_count + self.loss_count
        if total > 0:
            return (self.win_count / total) * 100
        return 0.0


# =========================================================
# SIMULATOR
# =========================================================

class StrategySimulator:
    """
    Runs multiple strategies in parallel on market data.
    
    🎓 USAGE:
    simulator = StrategySimulator()
    
    # Initialize with strategies
    simulator.initialize(strategies)
    
    # Feed market data
    simulator.on_spread_update(spread_data)
    simulator.on_regime_update(regime)
    
    # Get results
    results = simulator.get_results()
    """
    
    def __init__(self):
        self._strategies: Dict[str, StrategyState] = {}
        self._current_regime: Optional[MarketRegime] = None
        self._last_spreads: Dict[str, SpreadData] = {}
    
    def initialize(self, strategies: List[StrategyDNA]):
        """
        Initialize simulation with a set of strategies.
        
        🎓 Each strategy gets its own isolated state.
        """
        self._strategies.clear()
        
        for dna in strategies:
            self._strategies[dna.id] = StrategyState(dna=dna)
        
        logger.info(f"🎮 Simulator initialized with {len(strategies)} strategies")
    
    def update_regime(self, regime: MarketRegime):
        """Update current market regime."""
        self._current_regime = regime
    
    async def on_spread_update(self, spread: SpreadData, signal: Optional[SpreadSignal] = None):
        """
        Process a spread update for all strategies.
        
        🎓 Each strategy independently decides whether to trade.
        """
        self._last_spreads[spread.symbol] = spread
        
        for strategy_id, state in self._strategies.items():
            if not state.is_active:
                continue
            
            # Update existing positions
            self._update_positions(state, spread)
            
            # Check for new trade opportunity
            if signal and signal.is_actionable:
                await self._evaluate_entry(state, spread, signal)
    
    def _update_positions(self, state: StrategyState, spread: SpreadData):
        """Update positions and check for exits."""
        symbol = spread.symbol
        
        if symbol not in state.open_positions:
            return
        
        position = state.open_positions[symbol]
        
        # Update price based on position side
        if position.exit_exchange == "NSE":
            position.update_price(spread.nse_price)
        else:
            position.update_price(spread.bse_price)
        
        # Check for exit
        should_exit, reason = position.should_exit(datetime.now())
        
        if should_exit:
            self._close_position(state, position, reason)
    
    async def _evaluate_entry(
        self, 
        state: StrategyState, 
        spread: SpreadData, 
        signal: SpreadSignal
    ):
        """
        Evaluate whether strategy should enter a new trade.
        
        🎓 Entry decision based on:
        1. Strategy DNA parameters
        2. Current market regime
        3. Risk limits
        4. Signal strength
        """
        dna = state.dna
        
        # Check if already has position in this symbol
        if spread.symbol in state.open_positions:
            return
        
        # Check regime compatibility
        if self._current_regime:
            if not dna.is_compatible_with_regime(
                self._current_regime.session,
                self._current_regime.volatility
            ):
                return
        
        # Check spread threshold
        if signal.current_spread_pct < dna.min_spread_threshold:
            return
        
        # Check stability
        if signal.ticks_stable < dna.stability_ticks:
            state.ticks_since_signal = signal.ticks_stable
            return
        
        # Check daily limits
        if state.daily_trades >= settings.MAX_TRADES_PER_DAY:
            return
        
        if state.daily_pnl_pct <= -settings.MAX_DAILY_LOSS_PERCENT:
            return
        
        # Calculate position size
        position_value = state.current_capital * (dna.position_size_pct / 100)
        
        # Limit position size
        max_position = state.current_capital * (settings.MAX_POSITION_SIZE_PERCENT / 100)
        position_value = min(position_value, max_position)
        
        # Determine entry price and quantity
        if signal.direction == "BSE>NSE":
            # NSE is cheaper, buy there
            entry_price = spread.nse_price
            exit_price = spread.bse_price
            entry_exchange = "NSE"
            exit_exchange = "BSE"
        else:
            # BSE is cheaper, buy there
            entry_price = spread.bse_price
            exit_price = spread.nse_price
            entry_exchange = "BSE"
            exit_exchange = "NSE"
        
        # Account for latency buffer
        effective_spread = signal.current_spread_pct - dna.latency_buffer_pct
        if effective_spread <= 0:
            return
        
        quantity = int(position_value / entry_price)
        if quantity < 1:
            return
        
        # Create position
        position = Position(
            symbol=spread.symbol,
            entry_exchange=entry_exchange,
            exit_exchange=exit_exchange,
            side=Side.BUY,
            quantity=quantity,
            entry_price=entry_price,
            entry_time=datetime.now(),
            max_hold_time=timedelta(seconds=dna.max_hold_seconds),
            take_profit_price=entry_price * (1 + dna.take_profit_pct / 100),
            stop_loss_price=entry_price * (1 - dna.stop_loss_pct / 100),
            current_price=entry_price
        )
        
        state.open_positions[spread.symbol] = position
        state.daily_trades += 1
        state.last_trade_time = datetime.now()
        
        # Log trade
        log_trade(
            dna.id, spread.symbol, "BUY", 
            entry_price, quantity, entry_exchange
        )
        
        logger.debug(
            f"📈 {dna.name} ENTRY: {spread.symbol} @ {entry_price:.2f} "
            f"(spread: {signal.current_spread_pct:.4f}%)"
        )
    
    def _close_position(self, state: StrategyState, position: Position, reason: str):
        """Close a position and record the trade."""
        exit_price = position.current_price
        pnl = position.unrealized_pnl
        pnl_pct = (pnl / (position.entry_price * position.quantity)) * 100
        
        # Record trade
        state.trade_counter += 1
        trade = Trade(
            id=state.trade_counter,
            strategy_id=state.dna.id,
            symbol=position.symbol,
            entry_exchange=position.entry_exchange,
            exit_exchange=position.exit_exchange,
            side=position.side.value,
            quantity=position.quantity,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=datetime.now(),
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason
        )
        state.completed_trades.append(trade)
        
        # Update capital
        state.current_capital += pnl
        state.daily_pnl += pnl
        state.total_pnl += pnl
        
        # Update stats
        if pnl > 0:
            state.win_count += 1
        else:
            state.loss_count += 1
        
        # Update drawdown
        if state.current_capital > state.peak_capital:
            state.peak_capital = state.current_capital
        else:
            drawdown = (state.peak_capital - state.current_capital) / state.peak_capital
            state.max_drawdown = max(state.max_drawdown, drawdown)
        
        # Remove position
        del state.open_positions[position.symbol]
        
        # Log
        log_trade(
            state.dna.id, position.symbol, "SELL",
            exit_price, position.quantity, position.exit_exchange, pnl
        )
        
        logger.debug(
            f"📉 {state.dna.name} EXIT: {position.symbol} @ {exit_price:.2f} "
            f"P&L: ₹{pnl:+.2f} ({reason})"
        )
    
    def get_state(self, strategy_id: str) -> Optional[StrategyState]:
        """Get state for a specific strategy."""
        return self._strategies.get(strategy_id)
    
    def get_all_states(self) -> Dict[str, StrategyState]:
        """Get all strategy states."""
        return self._strategies
    
    def get_leaderboard(self) -> List[tuple]:
        """
        Get strategies ranked by performance.
        
        Returns:
            List of (StrategyDNA, score) tuples, sorted best-first
        """
        results = []
        
        for state in self._strategies.values():
            # Calculate composite score
            # 🎓 Score = Sharpe-like metric
            # Higher P&L + Higher win rate + Lower drawdown = Better
            
            pnl_score = state.total_pnl_pct
            win_rate_score = state.win_rate / 100  # 0 to 1
            drawdown_penalty = state.max_drawdown * 100  # 0 to 100
            
            # Weighted score
            score = (
                pnl_score * 0.5 +
                win_rate_score * 30 -
                drawdown_penalty * 0.5
            )
            
            results.append((state.dna, score))
        
        # Sort by score (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def get_summary(self) -> str:
        """Get a text summary of all strategies."""
        lines = [
            "Strategy Performance Summary",
            "=" * 60,
        ]
        
        leaderboard = self.get_leaderboard()
        
        for i, (dna, score) in enumerate(leaderboard, 1):
            state = self._strategies[dna.id]
            lines.append(
                f"{i}. {dna.name} (Gen {dna.generation})"
            )
            lines.append(
                f"   P&L: ₹{state.total_pnl:+,.2f} ({state.total_pnl_pct:+.2f}%)"
            )
            lines.append(
                f"   Trades: {len(state.completed_trades)} | "
                f"Win Rate: {state.win_rate:.1f}% | "
                f"Max DD: {state.max_drawdown*100:.2f}%"
            )
            lines.append(f"   Score: {score:.2f}")
            lines.append("")
        
        return "\n".join(lines)


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_simulator: Optional[StrategySimulator] = None


def get_simulator() -> StrategySimulator:
    """Get or create the singleton simulator."""
    global _simulator
    
    if _simulator is None:
        _simulator = StrategySimulator()
    
    return _simulator


# =========================================================
# MAIN - Test simulator
# =========================================================

if __name__ == "__main__":
    import random
    from strategies.generator import StrategyGenerator
    
    async def main():
        print("🎮 Testing Strategy Simulator...")
        print()
        
        # Create strategies
        generator = StrategyGenerator(population_size=5)
        strategies = generator.create_initial_population()
        
        # Initialize simulator
        simulator = StrategySimulator()
        simulator.initialize(strategies)
        
        # Simulate market data
        print("📊 Simulating market data...")
        base_nse = 2450.0
        
        for i in range(100):
            # Random prices
            nse = base_nse + random.gauss(0, 5)
            bse = nse + random.gauss(1, 2)  # BSE slightly higher
            
            spread = SpreadData(
                symbol="RELIANCE",
                nse_price=nse,
                bse_price=bse,
                timestamp=datetime.now()
            )
            
            # Create signal (simplified)
            signal = SpreadSignal(
                symbol="RELIANCE",
                timestamp=datetime.now(),
                current_spread_pct=abs(nse - bse) / nse * 100,
                avg_spread_pct=0.05,
                z_score=abs(nse - bse) / 2,
                signal_strength=0.5,
                direction="BSE>NSE" if bse > nse else "NSE>BSE",
                ticks_stable=random.randint(1, 8),
                is_actionable=abs(nse - bse) > 2,
                reason="Test signal"
            )
            
            await simulator.on_spread_update(spread, signal)
            
            await asyncio.sleep(0.01)  # Small delay
        
        print()
        print(simulator.get_summary())
    
    asyncio.run(main())
