"""
Paper Trading Engine
====================

🎓 WHAT IS THIS FILE?
This file handles the "Champion" strategy's paper trading execution.
While all strategies are simulated in parallel, only the Champion
executes trades that count towards the main virtual portfolio.

🎓 CHAMPION-CHALLENGER MODEL:

┌─────────────────────────────────────────────────────────────────┐
│                      ALL STRATEGIES                             │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │
│  │ Strat A │  │ Strat B │  │ Strat C │  │ Strat D │            │
│  │ (CHAMP) │  │(Chall.) │  │(Chall.) │  │(Chall.) │            │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘            │
│       │            │            │            │                  │
│       │ EXECUTES   │ SHADOW     │ SHADOW     │ SHADOW          │
│       ▼            ▼            ▼            ▼                  │
│  ┌─────────┐  ┌─────────────────────────────────┐              │
│  │ MAIN    │  │      SHADOW PORTFOLIOS          │              │
│  │ VIRTUAL │  │      (Track but don't count)    │              │
│  │ CAPITAL │  │                                 │              │
│  └─────────┘  └─────────────────────────────────┘              │
│                                                                 │
│  End of period: Best challenger → New Champion                  │
└─────────────────────────────────────────────────────────────────┘

🎓 WHY CHAMPION-CHALLENGER?

1. STABILITY: Main portfolio follows proven strategy
2. TESTING: New strategies prove themselves before promotion
3. ADAPTABILITY: If market changes, better strategy takes over
4. SAFETY: Bad strategies never affect main capital

🎓 PROMOTION CRITERIA:

A Challenger becomes Champion if:
- Outperforms Champion for X consecutive days
- Has higher Sharpe ratio
- Has acceptable drawdown
- Has sufficient trade count (not just lucky)

This prevents:
- Frequent switching (transaction costs)
- Lucky one-day wonders becoming Champion
- Unstable performance
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional
import asyncio
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger, log_evolution_event
from core.database import save_trade, log_evolution
from strategies.strategy_dna import StrategyDNA
from strategies.simulator import StrategySimulator, StrategyState, get_simulator


@dataclass
class DailyPerformance:
    """Daily performance record for comparison."""
    date: date
    strategy_id: str
    pnl: float
    pnl_pct: float
    trade_count: int
    win_rate: float
    max_drawdown: float


@dataclass
class PromotionCandidate:
    """A challenger being evaluated for promotion."""
    strategy_id: str
    days_outperforming: int
    total_outperformance: float  # Cumulative P&L advantage
    

class PaperTradingEngine:
    """
    Manages Champion-Challenger execution model.
    
    🎓 USAGE:
    engine = PaperTradingEngine(simulator)
    
    # Set initial champion
    engine.set_champion(best_strategy_id)
    
    # After each day, evaluate promotion
    engine.evaluate_promotions()
    
    # Get main portfolio value
    value = engine.get_portfolio_value()
    """
    
    # Promotion criteria
    DAYS_TO_OUTPERFORM = 3       # Must outperform for 3 days
    MIN_TRADES_FOR_PROMOTION = 5  # Must have at least 5 trades
    MAX_DRAWDOWN_THRESHOLD = 0.10  # Must have <10% drawdown
    
    def __init__(self, simulator: StrategySimulator):
        self.simulator = simulator
        
        # Champion tracking
        self.champion_id: Optional[str] = None
        self.champion_history: List[str] = []  # Past champions
        
        # Challenger tracking
        self.promotion_candidates: Dict[str, PromotionCandidate] = {}
        
        # Main portfolio (follows Champion)
        self.main_capital: float = settings.INITIAL_CAPITAL
        self.main_pnl: float = 0.0
        self.main_trades: List[Dict] = []
        
        # Daily records
        self.daily_records: Dict[str, List[DailyPerformance]] = {}
    
    def set_champion(self, strategy_id: str):
        """
        Set the current champion strategy.
        
        🎓 Called at initialization with best strategy.
        """
        if self.champion_id:
            self.champion_history.append(self.champion_id)
        
        self.champion_id = strategy_id
        
        # Get strategy name
        state = self.simulator.get_state(strategy_id)
        name = state.dna.name if state else strategy_id
        
        log_evolution_event(
            "PROMOTED", strategy_id,
            f"Became Champion (replacing {self.champion_history[-1] if self.champion_history else 'N/A'})"
        )
        
        logger.info(f"👑 New Champion: {name}")
    
    def record_daily_performance(self):
        """
        Record daily performance for all strategies.
        
        🎓 Should be called at end of each trading day.
        """
        today = date.today()
        
        for strategy_id, state in self.simulator.get_all_states().items():
            record = DailyPerformance(
                date=today,
                strategy_id=strategy_id,
                pnl=state.daily_pnl,
                pnl_pct=state.daily_pnl_pct,
                trade_count=state.daily_trades,
                win_rate=state.win_rate,
                max_drawdown=state.max_drawdown
            )
            
            if strategy_id not in self.daily_records:
                self.daily_records[strategy_id] = []
            self.daily_records[strategy_id].append(record)
        
        # Update main portfolio with Champion's P&L
        if self.champion_id:
            champ_state = self.simulator.get_state(self.champion_id)
            if champ_state:
                self.main_pnl += champ_state.daily_pnl
                self.main_capital = settings.INITIAL_CAPITAL + self.main_pnl
        
        logger.info(f"📊 Recorded daily performance for {len(self.daily_records)} strategies")
    
    def evaluate_promotions(self) -> Optional[str]:
        """
        Evaluate if any challenger should be promoted.
        
        🎓 Called after each evaluation period.
        
        Returns:
            New champion ID if promotion occurred, None otherwise
        """
        if not self.champion_id:
            logger.warning("No champion set, cannot evaluate promotions")
            return None
        
        champ_state = self.simulator.get_state(self.champion_id)
        if not champ_state:
            return None
        
        # Get champion's recent performance
        champ_records = self.daily_records.get(self.champion_id, [])
        if not champ_records:
            return None
        
        champ_recent_pnl = sum(r.pnl for r in champ_records[-self.DAYS_TO_OUTPERFORM:])
        
        # Evaluate each challenger
        for strategy_id, state in self.simulator.get_all_states().items():
            if strategy_id == self.champion_id:
                continue
            
            # Get challenger's records
            challenger_records = self.daily_records.get(strategy_id, [])
            if len(challenger_records) < self.DAYS_TO_OUTPERFORM:
                continue
            
            challenger_recent_pnl = sum(r.pnl for r in challenger_records[-self.DAYS_TO_OUTPERFORM:])
            
            # Check if outperforming
            if challenger_recent_pnl > champ_recent_pnl:
                # Update or create promotion candidate
                if strategy_id not in self.promotion_candidates:
                    self.promotion_candidates[strategy_id] = PromotionCandidate(
                        strategy_id=strategy_id,
                        days_outperforming=1,
                        total_outperformance=challenger_recent_pnl - champ_recent_pnl
                    )
                else:
                    candidate = self.promotion_candidates[strategy_id]
                    candidate.days_outperforming += 1
                    candidate.total_outperformance += challenger_recent_pnl - champ_recent_pnl
                
                candidate = self.promotion_candidates[strategy_id]
                
                # Check promotion criteria
                if self._meets_promotion_criteria(state, candidate):
                    # Promote!
                    old_champion = self.champion_id
                    self.set_champion(strategy_id)
                    
                    # Clear candidate
                    del self.promotion_candidates[strategy_id]
                    
                    logger.info(
                        f"🎉 Promotion! {state.dna.name} replaces {old_champion} "
                        f"after {candidate.days_outperforming} days of outperformance"
                    )
                    
                    return strategy_id
            else:
                # Reset candidate if not outperforming
                if strategy_id in self.promotion_candidates:
                    del self.promotion_candidates[strategy_id]
        
        return None
    
    def _meets_promotion_criteria(
        self, 
        state: StrategyState, 
        candidate: PromotionCandidate
    ) -> bool:
        """
        Check if challenger meets all promotion criteria.
        
        🎓 Criteria:
        1. Outperformed for enough days
        2. Sufficient trade count
        3. Acceptable drawdown
        """
        # Days criterion
        if candidate.days_outperforming < self.DAYS_TO_OUTPERFORM:
            return False
        
        # Trade count criterion
        if len(state.completed_trades) < self.MIN_TRADES_FOR_PROMOTION:
            logger.debug(
                f"{state.dna.name} needs more trades ({len(state.completed_trades)}/{self.MIN_TRADES_FOR_PROMOTION})"
            )
            return False
        
        # Drawdown criterion
        if state.max_drawdown > self.MAX_DRAWDOWN_THRESHOLD:
            logger.debug(
                f"{state.dna.name} drawdown too high ({state.max_drawdown*100:.1f}%)"
            )
            return False
        
        return True
    
    def get_champion_state(self) -> Optional[StrategyState]:
        """Get the current champion's state."""
        if self.champion_id:
            return self.simulator.get_state(self.champion_id)
        return None
    
    def get_portfolio_value(self) -> float:
        """Get current main portfolio value."""
        return self.main_capital
    
    def get_portfolio_pnl(self) -> float:
        """Get main portfolio P&L."""
        return self.main_pnl
    
    def get_portfolio_pnl_pct(self) -> float:
        """Get main portfolio P&L as percentage."""
        return (self.main_pnl / settings.INITIAL_CAPITAL) * 100
    
    def get_status_report(self) -> str:
        """
        Get a status report of the paper trading engine.
        
        🎓 Useful for dashboard display.
        """
        champ_state = self.get_champion_state()
        
        lines = [
            "Paper Trading Engine Status",
            "=" * 50,
            "",
            f"Main Portfolio:",
            f"  Capital:     ₹{self.main_capital:,.2f}",
            f"  P&L:         ₹{self.main_pnl:+,.2f} ({self.get_portfolio_pnl_pct():+.2f}%)",
            "",
        ]
        
        if champ_state:
            lines.extend([
                f"👑 Champion: {champ_state.dna.name}",
                f"  Generation:  {champ_state.dna.generation}",
                f"  Win Rate:    {champ_state.win_rate:.1f}%",
                f"  Trades:      {len(champ_state.completed_trades)}",
                f"  Max DD:      {champ_state.max_drawdown*100:.2f}%",
                "",
            ])
        
        # Challenger info
        if self.promotion_candidates:
            lines.append("Promotion Candidates:")
            for sid, candidate in self.promotion_candidates.items():
                state = self.simulator.get_state(sid)
                name = state.dna.name if state else sid
                lines.append(
                    f"  • {name}: {candidate.days_outperforming} days outperforming"
                )
            lines.append("")
        
        # History
        if self.champion_history:
            lines.append(f"Previous Champions: {len(self.champion_history)}")
            for cid in self.champion_history[-3:]:
                lines.append(f"  • {cid}")
        
        return "\n".join(lines)


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_engine: Optional[PaperTradingEngine] = None


def get_paper_trading_engine() -> PaperTradingEngine:
    """Get or create the singleton paper trading engine."""
    global _engine
    
    if _engine is None:
        simulator = get_simulator()
        _engine = PaperTradingEngine(simulator)
    
    return _engine


# =========================================================
# MAIN - Test paper trading engine
# =========================================================

if __name__ == "__main__":
    from strategies.generator import StrategyGenerator
    
    print("📝 Testing Paper Trading Engine...")
    print()
    
    # Create strategies
    generator = StrategyGenerator(population_size=5)
    strategies = generator.create_initial_population()
    
    # Initialize simulator
    simulator = StrategySimulator()
    simulator.initialize(strategies)
    
    # Create paper trading engine
    engine = PaperTradingEngine(simulator)
    
    # Set initial champion (first strategy)
    engine.set_champion(strategies[0].id)
    
    print(engine.get_status_report())
