"""
Logging Module
==============

🎓 WHAT IS THIS FILE?
This file sets up structured logging for the entire system.
Every important event gets logged with timestamp, level, and context.

🎓 WHY LOGGING IS CRITICAL FOR QUANT SYSTEMS?

1. DEBUGGING: When something goes wrong at 2 PM, logs tell you why
2. AUDIT TRAIL: Track every decision the system made
3. LEARNING: Review logs to understand strategy behavior
4. COMPLIANCE: Professional systems must maintain records

🎓 LOG LEVELS EXPLAINED:
┌─────────┬─────────────────────────────────────────────────────┐
│ Level   │ When to Use                                         │
├─────────┼─────────────────────────────────────────────────────┤
│ DEBUG   │ Detailed info for developers (not in production)    │
│ INFO    │ Normal operations (started, connected, trade made)  │
│ WARNING │ Something unusual but not broken (high latency)     │
│ ERROR   │ Something failed (API error, trade rejected)        │
│ CRITICAL│ System cannot continue (kill-switch triggered)      │
└─────────┴─────────────────────────────────────────────────────┘

🎓 LOG FORMAT:
2024-12-17 10:30:45.123 | INFO | strategies.simulator | Strategy-A7B2 entered RELIANCE long @ 2450.50
│                           │     │                      │
│                           │     │                      └── Message
│                           │     └── Module name (where it happened)
│                           └── Level
└── Timestamp (precise to millisecond)
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


# Create logs directory
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class ColorFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to terminal output.
    
    🎓 WHY COLORS?
    Makes it easier to spot errors/warnings when watching live logs.
    Green = good, Yellow = warning, Red = error
    """
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'       # Reset
    }
    
    def format(self, record):
        # Add color to level name
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{color}{record.levelname:8}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logger(
    name: str = "quant_engine",
    level: int = logging.INFO,
    log_to_file: bool = True,
    log_to_console: bool = True
) -> logging.Logger:
    """
    Set up a logger with both file and console handlers.
    
    🎓 Args:
        name: Logger name (usually module name)
        level: Minimum level to log
        log_to_file: Whether to write to log files
        log_to_console: Whether to print to terminal
    
    🎓 Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent duplicate handlers
    if logger.handlers:
        return logger
    
    # Log format
    log_format = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # Console handler (with colors)
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(ColorFormatter(log_format, date_format))
        logger.addHandler(console_handler)
    
    # File handler (daily rotating)
    if log_to_file:
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = LOGS_DIR / f"{name}_{today}.log"
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        logger.addHandler(file_handler)
    
    return logger


# =========================================================
# SPECIALIZED LOGGERS
# =========================================================

def get_trade_logger() -> logging.Logger:
    """
    Logger specifically for trade events.
    
    🎓 WHY SEPARATE TRADE LOGGER?
    Trade logs are critical for auditing and analysis.
    Keeping them separate makes it easier to review trading activity.
    """
    logger = setup_logger("trades", level=logging.INFO)
    return logger


def get_evolution_logger() -> logging.Logger:
    """Logger for strategy evolution events."""
    return setup_logger("evolution", level=logging.INFO)


def get_market_logger() -> logging.Logger:
    """Logger for market data and regime changes."""
    return setup_logger("market", level=logging.INFO)


def get_risk_logger() -> logging.Logger:
    """
    Logger for risk management events.
    
    🎓 CRITICAL: Risk events are always logged at WARNING or higher
    because they indicate potential problems.
    """
    return setup_logger("risk", level=logging.WARNING)


# =========================================================
# CONVENIENCE FUNCTIONS
# =========================================================

# Main application logger
logger = setup_logger("quant_engine")


def log_trade(
    strategy_id: str,
    symbol: str,
    action: str,  # 'BUY' or 'SELL'
    price: float,
    quantity: int,
    exchange: str = "NSE",
    pnl: Optional[float] = None
):
    """
    Log a trade event with consistent format.
    
    🎓 Example output:
    2024-12-17 10:30:45.123 | INFO | trades | [Strategy-A7B2] BUY RELIANCE @ 2450.50 x 10 on NSE
    """
    trade_logger = get_trade_logger()
    msg = f"[{strategy_id}] {action} {symbol} @ {price:.2f} x {quantity} on {exchange}"
    if pnl is not None:
        msg += f" | P&L: ₹{pnl:+.2f}"
    trade_logger.info(msg)


def log_evolution_event(
    action: str,  # 'CREATED', 'MUTATED', 'RETIRED', 'PROMOTED'
    strategy_id: str,
    reason: str,
    parent_id: Optional[str] = None
):
    """
    Log a strategy evolution event.
    
    🎓 Example output:
    2024-12-17 10:30:45.123 | INFO | evolution | RETIRED Strategy-C3D4: Poor performance (Sharpe < 0)
    """
    evo_logger = get_evolution_logger()
    msg = f"{action} {strategy_id}"
    if parent_id:
        msg += f" (from {parent_id})"
    msg += f": {reason}"
    evo_logger.info(msg)


def log_regime_change(
    old_regime: Optional[dict],
    new_regime: dict
):
    """
    Log when market regime changes.
    
    🎓 Example output:
    2024-12-17 10:30:45.123 | INFO | market | Regime change: volatility low→high, session opening→mid
    """
    market_logger = get_market_logger()
    
    if old_regime is None:
        msg = f"Initial regime: volatility={new_regime['volatility']}, "
        msg += f"liquidity={new_regime['liquidity']}, session={new_regime['session']}"
    else:
        changes = []
        for key in ['volatility', 'liquidity', 'spread_behavior', 'session']:
            if old_regime.get(key) != new_regime.get(key):
                changes.append(f"{key} {old_regime.get(key)}→{new_regime.get(key)}")
        
        if changes:
            msg = f"Regime change: {', '.join(changes)}"
        else:
            return  # No changes, don't log
    
    market_logger.info(msg)


def log_risk_event(
    event_type: str,  # 'LIMIT_HIT', 'TRADE_BLOCKED', 'KILL_SWITCH'
    details: str
):
    """
    Log a risk management event.
    
    🎓 These are always WARNING or higher because they indicate
    the risk manager had to intervene.
    
    Example output:
    2024-12-17 10:30:45.123 | WARNING | risk | LIMIT_HIT: Daily loss limit reached (2.1%)
    """
    risk_logger = get_risk_logger()
    
    if event_type == 'KILL_SWITCH':
        risk_logger.critical(f"🚨 {event_type}: {details}")
    else:
        risk_logger.warning(f"⚠️ {event_type}: {details}")


# =========================================================
# MAIN - Test logging
# =========================================================

if __name__ == "__main__":
    print("🔧 Testing logging module...")
    print(f"📁 Logs directory: {LOGS_DIR}")
    print()
    
    # Test different log levels
    logger.debug("This is a DEBUG message (developers only)")
    logger.info("This is an INFO message (normal operation)")
    logger.warning("This is a WARNING message (something unusual)")
    logger.error("This is an ERROR message (something failed)")
    
    print()
    
    # Test specialized logging
    log_trade("Strategy-A7B2", "RELIANCE", "BUY", 2450.50, 10, "NSE")
    log_trade("Strategy-A7B2", "RELIANCE", "SELL", 2455.25, 10, "NSE", pnl=47.50)
    
    log_evolution_event("CREATED", "Strategy-X1Y2", "Initial population", None)
    log_evolution_event("MUTATED", "Strategy-Z9W8", "Spread threshold adjusted", "Strategy-A7B2")
    log_evolution_event("RETIRED", "Strategy-C3D4", "Poor performance (Sharpe < 0)")
    
    log_regime_change(None, {
        'volatility': 'high',
        'liquidity': 'normal',
        'spread_behavior': 'stable',
        'session': 'opening'
    })
    
    log_risk_event("LIMIT_HIT", "Daily loss limit reached (2.1%)")
    log_risk_event("TRADE_BLOCKED", "Position size exceeds 10% limit")
    
    print()
    print("✅ Logging test complete. Check the logs/ directory for log files.")
