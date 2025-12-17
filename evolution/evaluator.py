"""
Performance Evaluator Module
=============================

🎓 WHAT IS THIS FILE?
This file calculates performance metrics for each strategy.
These metrics determine which strategies survive and which die.

🎓 WHY MULTIPLE METRICS?

A single metric (like P&L) can be misleading:

Strategy A: Made ₹10,000 with wild 50% swings
Strategy B: Made ₹5,000 with steady 5% swings

Which is better? Depends on your perspective:
- Pure profit: A wins
- Risk-adjusted: B wins (more consistent)
- Survivability: B wins (less likely to blow up)

🎓 METRICS EXPLAINED:

┌─────────────────┬────────────────────────────────────────────────────┐
│ Metric          │ Formula & Meaning                                  │
├─────────────────┼────────────────────────────────────────────────────┤
│ Net P&L         │ Total profit minus losses                          │
│                 │ Simple but can be misleading                       │
├─────────────────┼────────────────────────────────────────────────────┤
│ Return %        │ (P&L / Initial Capital) × 100                      │
│                 │ Percentage gain/loss                               │
├─────────────────┼────────────────────────────────────────────────────┤
│ Sharpe Ratio    │ (Avg Return - Risk-free) / Std Dev of Returns      │
│                 │ Risk-adjusted performance                          │
│                 │ > 1 = acceptable, > 2 = very good, > 3 = excellent │
├─────────────────┼────────────────────────────────────────────────────┤
│ Sortino Ratio   │ Like Sharpe but only penalizes downside volatility │
│                 │ Better for strategies with occasional big wins     │
├─────────────────┼────────────────────────────────────────────────────┤
│ Max Drawdown    │ Largest peak-to-trough decline                     │
│                 │ Shows worst-case scenario                          │
│                 │ < 10% = conservative, < 20% = moderate             │
├─────────────────┼────────────────────────────────────────────────────┤
│ Win Rate        │ (Winning Trades / Total Trades) × 100              │
│                 │ Note: 40% win rate can still be profitable!        │
├─────────────────┼────────────────────────────────────────────────────┤
│ Profit Factor   │ Gross Profit / Gross Loss                          │
│                 │ > 1.5 = good, > 2.0 = excellent                    │
├─────────────────┼────────────────────────────────────────────────────┤
│ Avg Trade       │ Total P&L / Number of Trades                       │
│                 │ Must exceed transaction costs!                     │
├─────────────────┼────────────────────────────────────────────────────┤
│ Trade Frequency │ Trades per day                                     │
│                 │ Too many = overtrading, too few = missed opps      │
└─────────────────┴────────────────────────────────────────────────────┘

🎓 COMPOSITE SCORE:

We combine metrics into a single score for ranking:

Score = w1 × Sharpe + w2 × Return% + w3 × (1 - MaxDD) + w4 × WinRate

Weights can be adjusted based on preferences.
Default weights favor consistency over raw returns.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import logger
from strategies.simulator import StrategyState, Trade


# =========================================================
# PERFORMANCE METRICS
# =========================================================

@dataclass
class PerformanceMetrics:
    """
    Complete performance metrics for a strategy.
    
    🎓 This is the "report card" for each strategy.
    """
    strategy_id: str
    strategy_name: str
    generation: int
    
    # Basic metrics
    net_pnl: float = 0.0
    return_pct: float = 0.0
    
    # Risk-adjusted metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    
    # Drawdown
    max_drawdown: float = 0.0
    avg_drawdown: float = 0.0
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # Profit metrics
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    
    # Time metrics
    avg_hold_time: timedelta = field(default_factory=lambda: timedelta())
    trades_per_day: float = 0.0
    
    # Composite score
    composite_score: float = 0.0
    
    # Timestamp
    calculated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "generation": self.generation,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "total_trades": self.total_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "avg_trade_pnl": self.avg_trade_pnl,
            "composite_score": self.composite_score,
            "calculated_at": self.calculated_at.isoformat()
        }


# =========================================================
# EVALUATOR
# =========================================================

class PerformanceEvaluator:
    """
    Evaluates strategy performance and calculates metrics.
    
    🎓 USAGE:
    evaluator = PerformanceEvaluator()
    
    # Calculate metrics for a strategy
    metrics = evaluator.calculate(strategy_state)
    
    # Rank multiple strategies
    ranked = evaluator.rank_strategies(states)
    """
    
    # Weights for composite score
    WEIGHT_SHARPE = 0.35
    WEIGHT_RETURN = 0.25
    WEIGHT_DRAWDOWN = 0.20
    WEIGHT_WIN_RATE = 0.10
    WEIGHT_PROFIT_FACTOR = 0.10
    
    # Risk-free rate (annualized, for Sharpe calculation)
    RISK_FREE_RATE = 0.05  # 5% per year
    
    def __init__(self):
        pass
    
    def calculate(
        self, 
        state: StrategyState,
        trading_days: int = 1
    ) -> PerformanceMetrics:
        """
        Calculate comprehensive performance metrics.
        
        🎓 Args:
            state: Strategy state with trades and capital
            trading_days: Number of days the strategy has been running
        
        Returns:
            PerformanceMetrics object
        """
        trades = state.completed_trades
        
        # Initialize metrics
        metrics = PerformanceMetrics(
            strategy_id=state.dna.id,
            strategy_name=state.dna.name,
            generation=state.dna.generation
        )
        
        # Basic metrics
        metrics.net_pnl = state.total_pnl
        metrics.return_pct = state.total_pnl_pct
        
        # Trade statistics
        metrics.total_trades = len(trades)
        
        if not trades:
            # No trades, return minimal metrics
            return metrics
        
        # Separate wins and losses
        winning_trades = [t for t in trades if t.pnl > 0]
        losing_trades = [t for t in trades if t.pnl <= 0]
        
        metrics.winning_trades = len(winning_trades)
        metrics.losing_trades = len(losing_trades)
        metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100
        
        # Profit metrics
        metrics.gross_profit = sum(t.pnl for t in winning_trades)
        metrics.gross_loss = abs(sum(t.pnl for t in losing_trades))
        
        if metrics.gross_loss > 0:
            metrics.profit_factor = metrics.gross_profit / metrics.gross_loss
        else:
            metrics.profit_factor = float('inf') if metrics.gross_profit > 0 else 0
        
        metrics.avg_trade_pnl = metrics.net_pnl / metrics.total_trades
        
        if winning_trades:
            metrics.avg_win = metrics.gross_profit / len(winning_trades)
        if losing_trades:
            metrics.avg_loss = metrics.gross_loss / len(losing_trades)
        
        # Time metrics
        hold_times = [(t.exit_time - t.entry_time).total_seconds() for t in trades]
        metrics.avg_hold_time = timedelta(seconds=np.mean(hold_times))
        metrics.trades_per_day = metrics.total_trades / max(1, trading_days)
        
        # Drawdown
        metrics.max_drawdown = state.max_drawdown
        
        # Risk-adjusted metrics
        metrics.sharpe_ratio = self._calculate_sharpe(trades, trading_days)
        metrics.sortino_ratio = self._calculate_sortino(trades, trading_days)
        
        # Composite score
        metrics.composite_score = self._calculate_composite_score(metrics)
        
        return metrics
    
    def _calculate_sharpe(
        self, 
        trades: List[Trade],
        trading_days: int
    ) -> float:
        """
        Calculate Sharpe ratio.
        
        🎓 Sharpe = (Avg Return - Risk-free) / Std Dev
        
        Higher Sharpe = better risk-adjusted returns.
        """
        if len(trades) < 2:
            return 0.0
        
        # Calculate daily returns (simplified)
        returns = [t.pnl_pct for t in trades]
        
        avg_return = np.mean(returns)
        std_return = np.std(returns)
        
        if std_return == 0:
            return 0.0
        
        # Daily risk-free rate
        daily_rf = self.RISK_FREE_RATE / 252
        
        # Sharpe ratio (annualized)
        sharpe = (avg_return - daily_rf) / std_return * np.sqrt(252 / max(1, trading_days))
        
        return float(sharpe)
    
    def _calculate_sortino(
        self, 
        trades: List[Trade],
        trading_days: int
    ) -> float:
        """
        Calculate Sortino ratio.
        
        🎓 Sortino = (Avg Return - Target) / Downside Deviation
        
        Only penalizes negative volatility, unlike Sharpe.
        """
        if len(trades) < 2:
            return 0.0
        
        returns = [t.pnl_pct for t in trades]
        avg_return = np.mean(returns)
        
        # Downside deviation (only negative returns)
        negative_returns = [r for r in returns if r < 0]
        
        if not negative_returns:
            return float('inf') if avg_return > 0 else 0.0
        
        downside_std = np.std(negative_returns)
        
        if downside_std == 0:
            return 0.0
        
        sortino = avg_return / downside_std * np.sqrt(252 / max(1, trading_days))
        
        return float(sortino)
    
    def _calculate_composite_score(self, metrics: PerformanceMetrics) -> float:
        """
        Calculate composite score for ranking.
        
        🎓 Combines all metrics into single score.
        Normalized to roughly 0-100 scale.
        """
        # Normalize each component to 0-1 range (approximately)
        
        # Sharpe: -2 to 4 typical range
        sharpe_norm = min(1, max(0, (metrics.sharpe_ratio + 2) / 6))
        
        # Return: -50% to 50% typical range
        return_norm = min(1, max(0, (metrics.return_pct + 50) / 100))
        
        # Drawdown: 0 to 50% range (inverted, lower is better)
        drawdown_norm = 1 - min(1, metrics.max_drawdown * 2)
        
        # Win rate: 0 to 100%
        winrate_norm = metrics.win_rate / 100
        
        # Profit factor: 0 to 3 typical range (capped)
        pf_norm = min(1, metrics.profit_factor / 3)
        
        # Weighted sum
        score = (
            self.WEIGHT_SHARPE * sharpe_norm * 100 +
            self.WEIGHT_RETURN * return_norm * 100 +
            self.WEIGHT_DRAWDOWN * drawdown_norm * 100 +
            self.WEIGHT_WIN_RATE * winrate_norm * 100 +
            self.WEIGHT_PROFIT_FACTOR * pf_norm * 100
        )
        
        return float(score)
    
    def rank_strategies(
        self, 
        states: Dict[str, StrategyState],
        trading_days: int = 1
    ) -> List[tuple]:
        """
        Rank all strategies by performance.
        
        🎓 Returns list sorted by composite score (best first).
        
        Returns:
            List of (StrategyDNA, PerformanceMetrics) tuples
        """
        results = []
        
        for state in states.values():
            metrics = self.calculate(state, trading_days)
            results.append((state.dna, metrics))
        
        # Sort by composite score (descending)
        results.sort(key=lambda x: x[1].composite_score, reverse=True)
        
        return results
    
    def get_performance_summary(
        self, 
        metrics_list: List[PerformanceMetrics]
    ) -> str:
        """
        Get a text summary of strategy performance.
        
        🎓 Useful for reports and logging.
        """
        lines = [
            "Strategy Performance Summary",
            "=" * 70,
            f"{'Rank':<5} {'Strategy':<15} {'P&L':>10} {'Sharpe':>8} {'Win%':>7} {'DD%':>7} {'Score':>8}",
            "-" * 70,
        ]
        
        for i, m in enumerate(metrics_list, 1):
            lines.append(
                f"{i:<5} {m.strategy_name:<15} "
                f"₹{m.net_pnl:>9,.0f} "
                f"{m.sharpe_ratio:>8.2f} "
                f"{m.win_rate:>6.1f}% "
                f"{m.max_drawdown*100:>6.2f}% "
                f"{m.composite_score:>8.1f}"
            )
        
        return "\n".join(lines)


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_evaluator: Optional[PerformanceEvaluator] = None


def get_performance_evaluator() -> PerformanceEvaluator:
    """Get or create the singleton performance evaluator."""
    global _evaluator
    
    if _evaluator is None:
        _evaluator = PerformanceEvaluator()
    
    return _evaluator


# =========================================================
# MAIN - Test evaluator
# =========================================================

if __name__ == "__main__":
    from strategies.strategy_dna import StrategyDNA
    from strategies.simulator import StrategyState, Trade
    import random
    
    print("📊 Testing Performance Evaluator...")
    print()
    
    # Create mock strategy states
    states = {}
    
    for i in range(5):
        dna = StrategyDNA.random()
        state = StrategyState(dna=dna)
        
        # Generate random trades
        for j in range(random.randint(5, 20)):
            pnl = random.gauss(20, 50)  # Mean profit of 20, std 50
            trade = Trade(
                id=j,
                strategy_id=dna.id,
                symbol="RELIANCE",
                entry_exchange="NSE",
                exit_exchange="BSE",
                side="BUY",
                quantity=10,
                entry_price=2450.0,
                exit_price=2450.0 + pnl/10,
                entry_time=datetime.now() - timedelta(minutes=j*10),
                exit_time=datetime.now() - timedelta(minutes=j*10-5),
                pnl=pnl,
                pnl_pct=pnl / 2450.0 * 100,
                exit_reason="take_profit" if pnl > 0 else "stop_loss"
            )
            state.completed_trades.append(trade)
            state.total_pnl += pnl
            if pnl > 0:
                state.win_count += 1
            else:
                state.loss_count += 1
        
        state.current_capital = state.initial_capital + state.total_pnl
        state.max_drawdown = random.uniform(0.02, 0.15)
        
        states[dna.id] = state
    
    # Evaluate
    evaluator = PerformanceEvaluator()
    ranked = evaluator.rank_strategies(states, trading_days=1)
    
    # Print summary
    metrics_list = [m for _, m in ranked]
    print(evaluator.get_performance_summary(metrics_list))
