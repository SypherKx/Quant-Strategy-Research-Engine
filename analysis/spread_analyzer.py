"""
Spread Analyzer Module
======================

🎓 WHAT IS THIS FILE?
This file analyzes the price difference (spread) between NSE and BSE
for the same stock, looking for arbitrage opportunities.

🎓 WHAT IS ARBITRAGE?

Arbitrage = Buying low on one exchange, selling high on another.

Example:
- RELIANCE on NSE: ₹2450.00
- RELIANCE on BSE: ₹2452.00
- Spread: ₹2.00

Theoretical trade:
1. Buy on NSE at ₹2450
2. Sell on BSE at ₹2452
3. Profit: ₹2 per share (before costs)

🎓 WHY CAN'T EVERYONE DO THIS?

Reality is more complex:
1. TRANSACTION COSTS: Brokerage, STT, stamps, GST
   Typically 0.03-0.05% per side = ~₹1.50 per ₹2500 trade

2. LATENCY: By the time you execute, prices may have changed

3. EXCHANGE SETTLEMENT: NSE and BSE settle differently
   You can't instantly transfer shares between exchanges

4. CAPITAL EFFICIENCY: Money is locked in both exchanges

🎓 WHAT THIS FILE DOES:

Instead of actual arbitrage (which requires real trading),
we analyze spreads to:
1. Track spread patterns over time
2. Identify when spreads are unusually wide
3. Measure spread stability (for regime analysis)
4. Generate signals for paper trading

📊 SPREAD METRICS:

┌────────────────────┬────────────────────────────────────────────┐
│ Metric             │ What It Tells Us                           │
├────────────────────┼────────────────────────────────────────────┤
│ Current Spread     │ Instant NSE-BSE difference                 │
│ Avg Spread         │ Typical spread (20-tick average)           │
│ Max Spread         │ Widest spread seen today                   │
│ Spread StdDev      │ How much spread varies                     │
│ Z-Score            │ Is current spread unusual?                 │
│                    │ z > 2 = unusually wide                     │
│ Persistence        │ How long spread stays wide                 │
│ Direction          │ Which exchange is consistently higher      │
└────────────────────┴────────────────────────────────────────────┘
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import logger
from data.websocket_streamer import SpreadData


# =========================================================
# SPREAD SIGNAL
# =========================================================

@dataclass
class SpreadSignal:
    """
    A trading signal based on spread analysis.
    
    🎓 This is what strategies consume.
    It tells them: "Hey, there might be an opportunity here!"
    """
    symbol: str
    timestamp: datetime
    
    # Spread values
    current_spread_pct: float   # Current spread as %
    avg_spread_pct: float       # Average spread as %
    z_score: float              # How unusual (in std devs)
    
    # Signal strength and direction
    signal_strength: float      # 0.0 to 1.0, how strong
    direction: str              # "NSE>BSE" or "BSE>NSE"
    
    # Stability
    ticks_stable: int           # How many ticks spread stayed favorable
    is_actionable: bool         # Meets minimum criteria?
    
    # Reason
    reason: str                 # Human-readable explanation
    
    def __str__(self) -> str:
        action = "📈 ACTION" if self.is_actionable else "👀 WATCH"
        return f"{action} {self.symbol}: spread={self.current_spread_pct:.3f}% z={self.z_score:.2f} [{self.direction}]"


# =========================================================
# SPREAD ANALYZER
# =========================================================

class SpreadAnalyzer:
    """
    Analyzes NSE-BSE spreads for trading opportunities.
    
    🎓 USAGE:
    analyzer = SpreadAnalyzer()
    
    # Feed it spread updates
    analyzer.add_spread(spread_data)
    
    # Get signal for a symbol
    signal = analyzer.get_signal("RELIANCE")
    
    # Get all active signals
    signals = analyzer.get_all_signals()
    """
    
    # Configuration
    WINDOW_SIZE = 50           # Spreads to keep in history
    MIN_Z_SCORE = 1.5          # Minimum z-score for actionable signal
    MIN_STABLE_TICKS = 3       # Minimum ticks spread must stay favorable
    MIN_SPREAD_PCT = 0.02      # Minimum spread % to consider (0.02% = 2 bps)
    
    def __init__(self):
        # Spread history per symbol
        self._spread_history: Dict[str, deque] = {}
        
        # Stability tracking (consecutive ticks in same direction)
        self._stability_count: Dict[str, int] = {}
        self._last_direction: Dict[str, str] = {}
        
        # Daily statistics
        self._daily_max: Dict[str, float] = {}
        self._daily_min: Dict[str, float] = {}
        self._signal_count: Dict[str, int] = {}
        
        # Last signal per symbol
        self._last_signals: Dict[str, SpreadSignal] = {}
    
    def add_spread(self, spread: SpreadData) -> Optional[SpreadSignal]:
        """
        Add a spread observation and potentially generate a signal.
        
        🎓 This is called every time we get a spread update.
        
        Returns:
            SpreadSignal if conditions are met, None otherwise
        """
        symbol = spread.symbol
        spread_pct = spread.spread_pct
        direction = spread.direction
        
        # Initialize if needed
        if symbol not in self._spread_history:
            self._spread_history[symbol] = deque(maxlen=self.WINDOW_SIZE)
            self._stability_count[symbol] = 0
            self._daily_max[symbol] = 0
            self._daily_min[symbol] = float('inf')
            self._signal_count[symbol] = 0
        
        # Add to history
        self._spread_history[symbol].append(spread_pct)
        
        # Update daily stats
        self._daily_max[symbol] = max(self._daily_max[symbol], spread_pct)
        self._daily_min[symbol] = min(self._daily_min[symbol], spread_pct)
        
        # Update stability count
        if direction == self._last_direction.get(symbol):
            self._stability_count[symbol] += 1
        else:
            self._stability_count[symbol] = 1
        self._last_direction[symbol] = direction
        
        # Generate signal
        signal = self._generate_signal(spread)
        
        if signal:
            self._last_signals[symbol] = signal
            if signal.is_actionable:
                self._signal_count[symbol] += 1
        
        return signal
    
    def _generate_signal(self, spread: SpreadData) -> SpreadSignal:
        """
        Generate a signal from spread data.
        
        🎓 This is where we decide if a spread is interesting.
        """
        symbol = spread.symbol
        current_spread = spread.spread_pct
        direction = spread.direction
        
        # Get history stats
        history = list(self._spread_history[symbol])
        
        if len(history) < 5:
            # Not enough data
            return SpreadSignal(
                symbol=symbol,
                timestamp=datetime.now(),
                current_spread_pct=current_spread,
                avg_spread_pct=current_spread,
                z_score=0.0,
                signal_strength=0.0,
                direction=direction,
                ticks_stable=self._stability_count[symbol],
                is_actionable=False,
                reason="Insufficient data (need 5+ observations)"
            )
        
        # Calculate statistics
        avg_spread = np.mean(history)
        std_spread = np.std(history)
        
        # Calculate z-score
        # 🎓 Z-score = How many standard deviations from mean
        # z = 2 means current spread is 2 std devs above average
        if std_spread > 0:
            z_score = (current_spread - avg_spread) / std_spread
        else:
            z_score = 0.0
        
        # Calculate signal strength (0 to 1)
        # Higher z-score + higher stability = stronger signal
        strength = min(1.0, abs(z_score) / 3.0) * min(1.0, self._stability_count[symbol] / 5.0)
        
        # Determine if actionable
        is_actionable = (
            abs(z_score) >= self.MIN_Z_SCORE and
            self._stability_count[symbol] >= self.MIN_STABLE_TICKS and
            current_spread >= self.MIN_SPREAD_PCT
        )
        
        # Generate reason
        reasons = []
        if abs(z_score) < self.MIN_Z_SCORE:
            reasons.append(f"z-score too low ({z_score:.2f} < {self.MIN_Z_SCORE})")
        if self._stability_count[symbol] < self.MIN_STABLE_TICKS:
            reasons.append(f"not stable enough ({self._stability_count[symbol]} < {self.MIN_STABLE_TICKS} ticks)")
        if current_spread < self.MIN_SPREAD_PCT:
            reasons.append(f"spread too small ({current_spread:.4f}% < {self.MIN_SPREAD_PCT}%)")
        
        if is_actionable:
            reason = f"Strong signal: z={z_score:.2f}, stable for {self._stability_count[symbol]} ticks"
        else:
            reason = "; ".join(reasons) if reasons else "Unknown"
        
        return SpreadSignal(
            symbol=symbol,
            timestamp=datetime.now(),
            current_spread_pct=current_spread,
            avg_spread_pct=avg_spread,
            z_score=z_score,
            signal_strength=strength,
            direction=direction,
            ticks_stable=self._stability_count[symbol],
            is_actionable=is_actionable,
            reason=reason
        )
    
    def get_signal(self, symbol: str) -> Optional[SpreadSignal]:
        """Get the last signal for a symbol."""
        return self._last_signals.get(symbol)
    
    def get_all_signals(self) -> List[SpreadSignal]:
        """Get all current signals."""
        return list(self._last_signals.values())
    
    def get_actionable_signals(self) -> List[SpreadSignal]:
        """Get only actionable signals."""
        return [s for s in self._last_signals.values() if s.is_actionable]
    
    def get_statistics(self, symbol: str) -> Dict:
        """
        Get comprehensive statistics for a symbol.
        
        🎓 Useful for dashboard display.
        """
        history = list(self._spread_history.get(symbol, []))
        
        if not history:
            return {
                "symbol": symbol,
                "has_data": False
            }
        
        return {
            "symbol": symbol,
            "has_data": True,
            "current_spread": history[-1] if history else 0,
            "avg_spread": float(np.mean(history)),
            "std_spread": float(np.std(history)),
            "max_spread_today": self._daily_max.get(symbol, 0),
            "min_spread_today": self._daily_min.get(symbol, 0),
            "observations": len(history),
            "signals_generated": self._signal_count.get(symbol, 0),
            "current_stability": self._stability_count.get(symbol, 0),
            "current_direction": self._last_direction.get(symbol, "N/A")
        }
    
    def reset_daily_stats(self):
        """Reset daily statistics (call at market open)."""
        self._daily_max = {}
        self._daily_min = {}
        self._signal_count = {}
        logger.info("Spread analyzer daily stats reset")


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_spread_analyzer: Optional[SpreadAnalyzer] = None


def get_spread_analyzer() -> SpreadAnalyzer:
    """Get or create the singleton spread analyzer."""
    global _spread_analyzer
    
    if _spread_analyzer is None:
        _spread_analyzer = SpreadAnalyzer()
    
    return _spread_analyzer


# =========================================================
# MAIN - Test spread analyzer
# =========================================================

if __name__ == "__main__":
    import random
    
    print("🔧 Testing spread analyzer...")
    print()
    
    analyzer = SpreadAnalyzer()
    
    # Simulate spread observations
    base_nse = 2450.0
    
    print("📊 Simulating spreads...")
    for i in range(60):
        # Random prices
        nse = base_nse + random.gauss(0, 2)
        bse = nse + random.gauss(0.5, 1)  # BSE slightly higher on average
        
        spread = SpreadData(
            symbol="RELIANCE",
            nse_price=nse,
            bse_price=bse,
            timestamp=datetime.now()
        )
        
        signal = analyzer.add_spread(spread)
        
        # Print actionable signals
        if signal and signal.is_actionable:
            print(f"  🔔 {signal}")
    
    print()
    
    # Show statistics
    stats = analyzer.get_statistics("RELIANCE")
    print("📈 Statistics:")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"   {key}: {value:.4f}")
        else:
            print(f"   {key}: {value}")
    
    print()
    
    # Show all signals
    signals = analyzer.get_all_signals()
    print(f"📊 Total signals: {len(signals)}")
    actionable = analyzer.get_actionable_signals()
    print(f"🎯 Actionable signals: {len(actionable)}")
