"""
Market Regime Analyzer
======================

🎓 WHAT IS THIS FILE?
This file classifies the market into different "regimes" based on:
- Volatility (how much prices move)
- Liquidity (how much volume is trading)
- Spread behavior (are NSE-BSE differences stable?)
- Session (opening, mid-session, closing)

🎓 WHY MARKET REGIME MATTERS?

Different market conditions require different strategies:

┌─────────────────┬─────────────────────────────────────────────┐
│ Regime          │ Strategy Implications                       │
├─────────────────┼─────────────────────────────────────────────┤
│ High Volatility │ Wider stops, smaller positions              │
│                 │ More opportunities but more risk            │
├─────────────────┼─────────────────────────────────────────────┤
│ Low Volatility  │ Tighter spreads, larger positions           │
│                 │ Fewer opportunities but safer trades        │
├─────────────────┼─────────────────────────────────────────────┤
│ Opening Session │ Wide spreads, high volatility               │
│ (9:15-10:00)    │ Avoid or be very careful                    │
├─────────────────┼─────────────────────────────────────────────┤
│ Mid Session     │ Stable spreads, normal volume               │
│ (10:00-14:30)   │ Best time for spread arbitrage              │
├─────────────────┼─────────────────────────────────────────────┤
│ Closing Session │ Position unwinding, volatility spikes       │
│ (14:30-15:30)   │ Close positions, avoid new trades           │
├─────────────────┼─────────────────────────────────────────────┤
│ Thin Liquidity  │ Orders may move price against you           │
│                 │ Use smaller position sizes                   │
├─────────────────┼─────────────────────────────────────────────┤
│ Heavy Liquidity │ Easy to enter/exit at desired price         │
│                 │ Can use larger positions                     │
└─────────────────┴─────────────────────────────────────────────┘

🎓 HOW VOLATILITY IS CALCULATED?

Volatility = Standard Deviation of Returns

Example with 5 price ticks: [100, 101, 99, 102, 100]
Returns: [+1%, -2%, +3%, -2%]
Volatility = std([+1, -2, +3, -2]) = 2.16%

Higher std = more volatility = more risk/opportunity

🎓 REGIME CLASSIFICATION THRESHOLDS:

These numbers come from historical analysis of NSE/BSE data:

VOLATILITY (rolling 20-tick returns std):
- Low:    < 0.5%  (calm market, small moves)
- Medium: 0.5-1.5% (normal trading)
- High:   > 1.5%  (active market, big moves)

LIQUIDITY (volume vs 20-day average):
- Thin:   < 50%   (low participation)
- Normal: 50-150% (typical activity)
- Heavy:  > 150%  (high participation)

SPREAD STABILITY (spread std vs spread mean):
- Stable: std < mean (consistent spread)
- Noisy:  std >= mean (erratic spread)
"""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional, Literal, Dict
from collections import deque
import numpy as np
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.logger import logger, log_regime_change
from core.scheduler import get_current_session, MarketSession
from data.websocket_streamer import PriceTick, SpreadData


# =========================================================
# REGIME DATA STRUCTURES
# =========================================================

@dataclass
class MarketRegime:
    """
    Current market regime classification.
    
    🎓 This is the output of the regime analyzer.
    Strategies use this to adjust their behavior.
    """
    volatility: Literal["low", "medium", "high"]
    liquidity: Literal["thin", "normal", "heavy"]
    spread_behavior: Literal["stable", "noisy"]
    session: Literal["pre_open", "opening", "mid", "closing", "closed"]
    
    # Numeric values for analysis
    volatility_value: float = 0.0  # Actual volatility %
    avg_spread: float = 0.0        # Average spread %
    spread_std: float = 0.0        # Spread standard deviation
    volume_ratio: float = 1.0      # Current vs average volume
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "volatility": self.volatility,
            "liquidity": self.liquidity,
            "spread_behavior": self.spread_behavior,
            "session": self.session,
            "volatility_value": round(self.volatility_value, 4),
            "avg_spread": round(self.avg_spread, 4),
            "spread_std": round(self.spread_std, 4),
            "volume_ratio": round(self.volume_ratio, 2),
            "timestamp": self.timestamp.isoformat()
        }
    
    def __str__(self) -> str:
        return f"Regime(vol={self.volatility}, liq={self.liquidity}, spread={self.spread_behavior}, session={self.session})"


# =========================================================
# REGIME ANALYZER
# =========================================================

class RegimeAnalyzer:
    """
    Analyzes market data to classify current regime.
    
    🎓 USAGE:
    analyzer = RegimeAnalyzer()
    
    # Feed it price ticks as they arrive
    analyzer.add_tick(tick)
    
    # Feed it spread updates
    analyzer.add_spread(spread)
    
    # Get current regime
    regime = analyzer.get_regime()
    """
    
    # Configuration constants
    WINDOW_SIZE = 20        # Number of ticks to analyze
    SPREAD_WINDOW = 50      # Number of spreads to analyze
    
    # Volatility thresholds (in percent)
    VOL_LOW_THRESHOLD = 0.5
    VOL_HIGH_THRESHOLD = 1.5
    
    # Liquidity thresholds (ratio vs average)
    LIQ_THIN_THRESHOLD = 0.5
    LIQ_HEAVY_THRESHOLD = 1.5
    
    def __init__(self):
        # Price history per symbol (for volatility)
        # Using deque for efficient fixed-size window
        self._price_history: Dict[str, deque] = {}
        
        # Spread history per symbol
        self._spread_history: Dict[str, deque] = {}
        
        # Volume history per symbol (for liquidity)
        self._volume_history: Dict[str, deque] = {}
        
        # Reference volumes (would ideally be 20-day averages)
        self._reference_volumes: Dict[str, float] = {}
        
        # Current regime
        self._current_regime: Optional[MarketRegime] = None
        
        # Last regime (for change detection)
        self._last_regime: Optional[MarketRegime] = None
    
    def add_tick(self, tick: PriceTick):
        """
        Add a price tick to the analyzer.
        
        🎓 Should be called for every price update.
        """
        key = f"{tick.symbol}_{tick.exchange}"
        
        # Initialize deque if needed
        if key not in self._price_history:
            self._price_history[key] = deque(maxlen=self.WINDOW_SIZE)
            self._volume_history[key] = deque(maxlen=self.WINDOW_SIZE * 10)
        
        # Add price and volume
        self._price_history[key].append(tick.ltp)
        if tick.volume > 0:
            self._volume_history[key].append(tick.volume)
            
            # Update reference volume (simple moving average)
            if key not in self._reference_volumes:
                self._reference_volumes[key] = tick.volume
            else:
                # Exponential moving average for reference
                alpha = 0.01  # Slow adaptation
                self._reference_volumes[key] = (
                    alpha * tick.volume + 
                    (1 - alpha) * self._reference_volumes[key]
                )
    
    def add_spread(self, spread: SpreadData):
        """
        Add a spread observation to the analyzer.
        
        🎓 Should be called for every spread update.
        """
        if spread.symbol not in self._spread_history:
            self._spread_history[spread.symbol] = deque(maxlen=self.SPREAD_WINDOW)
        
        self._spread_history[spread.symbol].append(spread.spread_pct)
    
    def _calculate_volatility(self) -> tuple:
        """
        Calculate aggregate volatility across all symbols.
        
        🎓 Volatility = Standard deviation of returns
        
        Returns:
            (volatility_category, volatility_value)
        """
        all_volatilities = []
        
        for key, prices in self._price_history.items():
            if len(prices) < 3:
                continue
            
            # Calculate returns
            prices_arr = np.array(list(prices))
            returns = np.diff(prices_arr) / prices_arr[:-1] * 100  # In percent
            
            if len(returns) > 0:
                vol = np.std(returns)
                all_volatilities.append(vol)
        
        if not all_volatilities:
            return "medium", 0.0
        
        # Average volatility across symbols
        avg_vol = np.mean(all_volatilities)
        
        # Classify
        if avg_vol < self.VOL_LOW_THRESHOLD:
            category = "low"
        elif avg_vol > self.VOL_HIGH_THRESHOLD:
            category = "high"
        else:
            category = "medium"
        
        return category, float(avg_vol)
    
    def _calculate_liquidity(self) -> tuple:
        """
        Calculate aggregate liquidity.
        
        🎓 Liquidity = Current volume / Reference volume
        
        Returns:
            (liquidity_category, volume_ratio)
        """
        ratios = []
        
        for key, volumes in self._volume_history.items():
            if len(volumes) < 10:
                continue
            
            ref = self._reference_volumes.get(key, 0)
            if ref > 0:
                current_vol = np.mean(list(volumes)[-10:])  # Recent average
                ratio = current_vol / ref
                ratios.append(ratio)
        
        if not ratios:
            return "normal", 1.0
        
        avg_ratio = np.mean(ratios)
        
        # Classify
        if avg_ratio < self.LIQ_THIN_THRESHOLD:
            category = "thin"
        elif avg_ratio > self.LIQ_HEAVY_THRESHOLD:
            category = "heavy"
        else:
            category = "normal"
        
        return category, float(avg_ratio)
    
    def _calculate_spread_behavior(self) -> tuple:
        """
        Calculate spread stability.
        
        🎓 Spread is stable if std < mean
        This means the spread is consistent, good for arbitrage.
        
        Returns:
            (behavior_category, avg_spread, spread_std)
        """
        all_spreads = []
        
        for symbol, spreads in self._spread_history.items():
            all_spreads.extend(list(spreads))
        
        if len(all_spreads) < 5:
            return "stable", 0.0, 0.0
        
        spreads_arr = np.array(all_spreads)
        avg_spread = np.mean(spreads_arr)
        spread_std = np.std(spreads_arr)
        
        # Classify
        # Spread is noisy if std is larger than mean (high coefficient of variation)
        if avg_spread > 0 and spread_std >= avg_spread:
            category = "noisy"
        else:
            category = "stable"
        
        return category, float(avg_spread), float(spread_std)
    
    def get_regime(self) -> MarketRegime:
        """
        Get the current market regime.
        
        🎓 This is the main function strategies call.
        It aggregates all analysis into a single Regime object.
        """
        # Get session
        session = get_current_session()
        
        # Calculate components
        vol_cat, vol_val = self._calculate_volatility()
        liq_cat, liq_ratio = self._calculate_liquidity()
        spread_cat, avg_spread, spread_std = self._calculate_spread_behavior()
        
        # Create regime
        regime = MarketRegime(
            volatility=vol_cat,
            liquidity=liq_cat,
            spread_behavior=spread_cat,
            session=session,
            volatility_value=vol_val,
            avg_spread=avg_spread,
            spread_std=spread_std,
            volume_ratio=liq_ratio,
            timestamp=datetime.now()
        )
        
        # Check for regime change
        if self._current_regime is not None:
            if (regime.volatility != self._current_regime.volatility or
                regime.liquidity != self._current_regime.liquidity or
                regime.spread_behavior != self._current_regime.spread_behavior or
                regime.session != self._current_regime.session):
                
                # Log regime change
                log_regime_change(
                    self._current_regime.to_dict() if self._current_regime else None,
                    regime.to_dict()
                )
                self._last_regime = self._current_regime
        
        self._current_regime = regime
        return regime
    
    def get_regime_summary(self) -> str:
        """
        Get a human-readable regime summary.
        
        🎓 Useful for dashboard display.
        """
        regime = self.get_regime()
        
        return f"""
Market Regime Summary
=====================
Session:     {regime.session}
Volatility:  {regime.volatility} ({regime.volatility_value:.3f}%)
Liquidity:   {regime.liquidity} ({regime.volume_ratio:.2f}x avg)
Spreads:     {regime.spread_behavior} (avg: {regime.avg_spread:.4f}%)
Time:        {regime.timestamp.strftime("%H:%M:%S")}
"""
    
    def is_favorable_for_trading(self) -> bool:
        """
        Quick check if current regime is favorable for trading.
        
        🎓 Favorable = stable spreads + normal/heavy liquidity + not closed
        """
        regime = self.get_regime()
        
        unfavorable_conditions = [
            regime.session == MarketSession.CLOSED,
            regime.session == MarketSession.PRE_OPEN,
            regime.liquidity == "thin",
            regime.spread_behavior == "noisy" and regime.volatility == "high"
        ]
        
        return not any(unfavorable_conditions)


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_regime_analyzer: Optional[RegimeAnalyzer] = None


def get_regime_analyzer() -> RegimeAnalyzer:
    """Get or create the singleton regime analyzer."""
    global _regime_analyzer
    
    if _regime_analyzer is None:
        _regime_analyzer = RegimeAnalyzer()
    
    return _regime_analyzer


# =========================================================
# MAIN - Test regime analyzer
# =========================================================

if __name__ == "__main__":
    import random
    
    print("🔧 Testing regime analyzer...")
    print()
    
    analyzer = RegimeAnalyzer()
    
    # Simulate some price ticks
    base_price = 2450.0
    
    print("📊 Simulating price ticks...")
    for i in range(30):
        # Random walk
        change = random.gauss(0, base_price * 0.002)  # 0.2% std
        base_price += change
        
        for exchange in ["NSE", "BSE"]:
            # BSE slightly different
            price = base_price + random.gauss(0, 1)
            
            tick = PriceTick(
                symbol="RELIANCE",
                exchange=exchange,
                ltp=round(price, 2),
                timestamp=datetime.now(),
                volume=random.randint(5000, 15000)
            )
            analyzer.add_tick(tick)
        
        # Calculate spread
        nse_price = base_price
        bse_price = base_price + random.gauss(0, 1)
        
        spread = SpreadData(
            symbol="RELIANCE",
            nse_price=nse_price,
            bse_price=bse_price,
            timestamp=datetime.now()
        )
        analyzer.add_spread(spread)
    
    # Get regime
    print(analyzer.get_regime_summary())
    
    print(f"🟢 Favorable for trading: {analyzer.is_favorable_for_trading()}")
