"""
Risk Manager Module
===================

🎓 WHAT IS THIS FILE?
This is the ABSOLUTE LAW of the trading system.
No strategy, no signal, no trade can bypass risk management.

🎓 WHY RISK MANAGEMENT IS NON-NEGOTIABLE:

"It's not about how much money you make,
 it's about how much money you don't lose."
 - Every successful trader ever

Professional trading follows strict rules:
┌─────────────────────────────────────────────────────────────────┐
│                      RISK HIERARCHY                             │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           KILL SWITCH (NUCLEAR OPTION)                   │   │
│  │  Triggered by: Market crash, API failure, abnormal vol  │   │
│  │  Action: STOP ALL TRADING IMMEDIATELY                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            ↑                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           DAILY LOSS CAP                                 │   │
│  │  If daily loss > 2% → No more trades today              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            ↑                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           POSITION LIMITS                                │   │
│  │  Max 10% of capital in any single position              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                            ↑                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │           TRADE FREQUENCY                                │   │
│  │  Max 50 trades per day                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Strategy can only trade if ALL levels approve.                │
└─────────────────────────────────────────────────────────────────┘

🎓 RISK MANAGEMENT PRINCIPLES:

1. CAPITAL PRESERVATION > PROFIT
   - Never risk more than you can afford to lose
   - Protect the principal, profits will follow

2. DIVERSIFICATION
   - No single position too large
   - No single strategy controls all capital

3. HARD LIMITS
   - Daily loss cap is ABSOLUTE
   - No "just one more trade"

4. FAIL-SAFE DEFAULTS
   - When in doubt, don't trade
   - Better to miss opportunity than take bad risk
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict
from enum import Enum
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger, log_risk_event


# =========================================================
# RISK ENUMS
# =========================================================

class RiskDecision(Enum):
    """Risk manager decision on a trade."""
    APPROVED = "approved"
    REJECTED_DAILY_LOSS = "rejected_daily_loss"
    REJECTED_POSITION_SIZE = "rejected_position_size"
    REJECTED_TRADE_LIMIT = "rejected_trade_limit"
    REJECTED_KILL_SWITCH = "rejected_kill_switch"
    REJECTED_VOLATILITY = "rejected_volatility"
    REJECTED_EXPOSURE = "rejected_exposure"


@dataclass
class TradeRequest:
    """
    Request to execute a trade.
    
    🎓 All trade requests must be approved by RiskManager.
    """
    strategy_id: str
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    price: float
    exchange: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class RiskCheckResult:
    """
    Result of a risk check.
    
    🎓 Contains decision and reason.
    """
    decision: RiskDecision
    reason: str
    modified_quantity: Optional[int] = None  # If position was reduced


# =========================================================
# RISK STATE
# =========================================================

@dataclass
class RiskState:
    """
    Current risk state of the system.
    
    🎓 Tracks daily metrics and limits.
    """
    # Daily tracking
    daily_pnl: float = 0.0
    daily_trades: int = 0
    daily_date: date = field(default_factory=date.today)
    
    # Position tracking
    total_exposure: float = 0.0
    positions_by_symbol: Dict[str, float] = field(default_factory=dict)
    
    # Kill switch
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    
    # Volatility tracking
    current_volatility: float = 0.0
    avg_volatility: float = 0.0
    
    def reset_daily(self):
        """Reset daily counters."""
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_date = date.today()


# =========================================================
# RISK MANAGER
# =========================================================

class RiskManager:
    """
    Central risk management for all trading activities.
    
    🎓 USAGE:
    risk_manager = RiskManager()
    
    # Before any trade
    result = risk_manager.check_trade(request)
    if result.decision == RiskDecision.APPROVED:
        execute_trade(...)
    else:
        log_rejection(result.reason)
    
    # After trade completes
    risk_manager.record_trade(pnl)
    """
    
    def __init__(self):
        self.state = RiskState()
        
        # Configuration from settings
        self.max_daily_loss_pct = settings.MAX_DAILY_LOSS_PERCENT
        self.max_trades_per_day = settings.MAX_TRADES_PER_DAY
        self.max_position_size_pct = settings.MAX_POSITION_SIZE_PERCENT
        self.initial_capital = settings.INITIAL_CAPITAL
        
        # Additional safety limits
        self.max_total_exposure_pct = 50.0  # Max 50% of capital at risk
        self.volatility_multiplier_threshold = 3.0  # Kill if vol > 3x normal
        
        logger.info("🛡️ Risk Manager initialized")
    
    def check_trade(
        self, 
        request: TradeRequest,
        current_capital: float
    ) -> RiskCheckResult:
        """
        Check if a trade should be allowed.
        
        🎓 This is the GATEKEEPER function.
        Every trade must pass through here.
        
        Args:
            request: Trade request to evaluate
            current_capital: Current portfolio value
        
        Returns:
            RiskCheckResult with decision and reason
        """
        # Reset daily if needed
        self._check_daily_reset()
        
        # Check kill switch first (highest priority)
        if self.state.kill_switch_active:
            log_risk_event("TRADE_BLOCKED", f"Kill switch active: {self.state.kill_switch_reason}")
            return RiskCheckResult(
                decision=RiskDecision.REJECTED_KILL_SWITCH,
                reason=f"Kill switch active: {self.state.kill_switch_reason}"
            )
        
        # Check daily loss limit
        daily_loss_pct = (self.state.daily_pnl / self.initial_capital) * 100
        if daily_loss_pct <= -self.max_daily_loss_pct:
            log_risk_event("TRADE_BLOCKED", f"Daily loss limit reached ({daily_loss_pct:.2f}%)")
            return RiskCheckResult(
                decision=RiskDecision.REJECTED_DAILY_LOSS,
                reason=f"Daily loss limit reached: {daily_loss_pct:.2f}% (max: {self.max_daily_loss_pct}%)"
            )
        
        # Check trade count limit
        if self.state.daily_trades >= self.max_trades_per_day:
            log_risk_event("TRADE_BLOCKED", f"Trade limit reached ({self.state.daily_trades})")
            return RiskCheckResult(
                decision=RiskDecision.REJECTED_TRADE_LIMIT,
                reason=f"Daily trade limit reached: {self.state.daily_trades} (max: {self.max_trades_per_day})"
            )
        
        # Check position size
        trade_value = request.quantity * request.price
        position_pct = (trade_value / current_capital) * 100
        
        if position_pct > self.max_position_size_pct:
            # Calculate maximum allowed quantity
            max_value = current_capital * (self.max_position_size_pct / 100)
            max_qty = int(max_value / request.price)
            
            if max_qty < 1:
                log_risk_event("TRADE_BLOCKED", f"Position too small after size limit")
                return RiskCheckResult(
                    decision=RiskDecision.REJECTED_POSITION_SIZE,
                    reason=f"Position size {position_pct:.1f}% exceeds limit {self.max_position_size_pct}%"
                )
            
            # Return approved but with modified quantity
            log_risk_event("LIMIT_HIT", f"Position size reduced from {request.quantity} to {max_qty}")
            return RiskCheckResult(
                decision=RiskDecision.APPROVED,
                reason=f"Position size reduced to comply with {self.max_position_size_pct}% limit",
                modified_quantity=max_qty
            )
        
        # Check total exposure
        new_exposure = self.state.total_exposure + trade_value
        exposure_pct = (new_exposure / current_capital) * 100
        
        if exposure_pct > self.max_total_exposure_pct:
            log_risk_event("TRADE_BLOCKED", f"Total exposure limit reached ({exposure_pct:.1f}%)")
            return RiskCheckResult(
                decision=RiskDecision.REJECTED_EXPOSURE,
                reason=f"Total exposure {exposure_pct:.1f}% would exceed limit {self.max_total_exposure_pct}%"
            )
        
        # Check volatility
        if self.state.avg_volatility > 0:
            vol_ratio = self.state.current_volatility / self.state.avg_volatility
            if vol_ratio > self.volatility_multiplier_threshold:
                log_risk_event("TRADE_BLOCKED", f"Volatility too high ({vol_ratio:.1f}x normal)")
                return RiskCheckResult(
                    decision=RiskDecision.REJECTED_VOLATILITY,
                    reason=f"Volatility {vol_ratio:.1f}x normal exceeds threshold {self.volatility_multiplier_threshold}x"
                )
        
        # All checks passed
        return RiskCheckResult(
            decision=RiskDecision.APPROVED,
            reason="All risk checks passed"
        )
    
    def record_trade(self, pnl: float):
        """
        Record a completed trade.
        
        🎓 Must be called after each trade to update risk state.
        """
        self.state.daily_pnl += pnl
        self.state.daily_trades += 1
        
        # Check if we should trigger kill switch
        daily_loss_pct = (self.state.daily_pnl / self.initial_capital) * 100
        if daily_loss_pct <= -(self.max_daily_loss_pct * 1.5):
            self.activate_kill_switch(f"Severe daily loss: {daily_loss_pct:.2f}%")
    
    def update_exposure(self, symbol: str, value: float):
        """Update position exposure."""
        if value == 0:
            self.state.positions_by_symbol.pop(symbol, None)
        else:
            self.state.positions_by_symbol[symbol] = value
        
        self.state.total_exposure = sum(self.state.positions_by_symbol.values())
    
    def update_volatility(self, current_vol: float, avg_vol: float):
        """Update volatility metrics."""
        self.state.current_volatility = current_vol
        self.state.avg_volatility = avg_vol
        
        # Check for kill switch trigger
        if avg_vol > 0:
            vol_ratio = current_vol / avg_vol
            if vol_ratio > self.volatility_multiplier_threshold * 1.5:
                self.activate_kill_switch(f"Extreme volatility: {vol_ratio:.1f}x normal")
    
    def activate_kill_switch(self, reason: str):
        """
        Activate the kill switch.
        
        🎓 NUCLEAR OPTION - Stops all trading immediately.
        """
        if not self.state.kill_switch_active:
            self.state.kill_switch_active = True
            self.state.kill_switch_reason = reason
            log_risk_event("KILL_SWITCH", reason)
            logger.critical(f"🚨 KILL SWITCH ACTIVATED: {reason}")
    
    def deactivate_kill_switch(self):
        """
        Deactivate the kill switch.
        
        🎓 Should only be done manually after review.
        """
        self.state.kill_switch_active = False
        self.state.kill_switch_reason = ""
        logger.info("🟢 Kill switch deactivated")
    
    def _check_daily_reset(self):
        """Reset daily counters if it's a new day."""
        if self.state.daily_date != date.today():
            self.state.reset_daily()
            logger.info("📅 Daily risk counters reset")
    
    def get_status(self) -> Dict:
        """
        Get current risk status.
        
        🎓 Useful for dashboard display.
        """
        daily_loss_pct = (self.state.daily_pnl / self.initial_capital) * 100
        trades_remaining = self.max_trades_per_day - self.state.daily_trades
        loss_remaining = self.max_daily_loss_pct + daily_loss_pct
        
        return {
            "kill_switch_active": self.state.kill_switch_active,
            "kill_switch_reason": self.state.kill_switch_reason,
            "daily_pnl": self.state.daily_pnl,
            "daily_pnl_pct": daily_loss_pct,
            "daily_trades": self.state.daily_trades,
            "trades_remaining": max(0, trades_remaining),
            "loss_remaining_pct": max(0, loss_remaining),
            "total_exposure": self.state.total_exposure,
            "exposure_pct": (self.state.total_exposure / self.initial_capital) * 100,
            "can_trade": not self.state.kill_switch_active and trades_remaining > 0 and loss_remaining > 0
        }
    
    def get_status_display(self) -> str:
        """Get formatted status for display."""
        status = self.get_status()
        
        # Status indicator
        if status["kill_switch_active"]:
            indicator = "🚨 KILL SWITCH ACTIVE"
        elif not status["can_trade"]:
            indicator = "⚠️ TRADING PAUSED"
        else:
            indicator = "🟢 TRADING ACTIVE"
        
        lines = [
            "Risk Manager Status",
            "=" * 40,
            indicator,
            "",
            f"Daily P&L:       ₹{status['daily_pnl']:+,.2f} ({status['daily_pnl_pct']:+.2f}%)",
            f"Loss Remaining:  {status['loss_remaining_pct']:.2f}%",
            f"Trades Today:    {status['daily_trades']} / {self.max_trades_per_day}",
            f"Total Exposure:  ₹{status['total_exposure']:,.2f} ({status['exposure_pct']:.1f}%)",
        ]
        
        if status["kill_switch_active"]:
            lines.append(f"\n⚠️ Reason: {status['kill_switch_reason']}")
        
        return "\n".join(lines)


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """Get or create the singleton risk manager."""
    global _risk_manager
    
    if _risk_manager is None:
        _risk_manager = RiskManager()
    
    return _risk_manager


# =========================================================
# MAIN - Test risk manager
# =========================================================

if __name__ == "__main__":
    print("🛡️ Testing Risk Manager...")
    print()
    
    rm = RiskManager()
    capital = 100000.0  # ₹1 lakh
    
    # Test normal trade
    request = TradeRequest(
        strategy_id="test-1",
        symbol="RELIANCE",
        side="BUY",
        quantity=10,
        price=2450.0,
        exchange="NSE"
    )
    
    result = rm.check_trade(request, capital)
    print(f"Normal trade: {result.decision.value}")
    print(f"  Reason: {result.reason}")
    print()
    
    # Test oversized trade
    oversized_request = TradeRequest(
        strategy_id="test-2",
        symbol="TCS",
        side="BUY",
        quantity=100,
        price=3800.0,
        exchange="NSE"
    )
    
    result = rm.check_trade(oversized_request, capital)
    print(f"Oversized trade: {result.decision.value}")
    print(f"  Reason: {result.reason}")
    if result.modified_quantity:
        print(f"  Modified qty: {result.modified_quantity}")
    print()
    
    # Simulate losses and hit limit
    print("Simulating trades with losses...")
    for i in range(5):
        result = rm.check_trade(request, capital)
        if result.decision == RiskDecision.APPROVED:
            rm.record_trade(-500)  # ₹500 loss each
            print(f"  Trade {i+1}: Loss recorded")
        else:
            print(f"  Trade {i+1}: Blocked - {result.reason}")
    
    print()
    print(rm.get_status_display())
