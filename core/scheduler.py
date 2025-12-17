"""
Market Hours Scheduler
======================

🎓 WHAT IS THIS FILE?
This file handles automatic start/stop based on Indian market hours.
The system only runs during trading hours to:
- Save resources (no point analyzing when market is closed)
- Avoid stale data issues
- Match professional trading system behavior

🎓 INDIAN MARKET HOURS (IST):
┌────────────────┬─────────────────┬────────────────────────┐
│ Session        │ Time            │ What Happens           │
├────────────────┼─────────────────┼────────────────────────┤
│ Pre-open       │ 9:00 - 9:15     │ Order matching only    │
│ Opening        │ 9:15 - 10:00    │ High volatility        │
│ Mid-session    │ 10:00 - 14:30   │ Normal trading         │
│ Closing        │ 14:30 - 15:30   │ Position unwinding     │
│ Post-market    │ 15:40 - 16:00   │ No regular trading     │
└────────────────┴─────────────────┴────────────────────────┘

🎓 WHY CARE ABOUT SESSIONS?
Different times have different characteristics:
- Opening: Wide spreads, high moves, risky
- Mid: Stable spreads, predictable
- Closing: Moves as funds adjust positions

Our strategies can prefer specific sessions!

🎓 HOLIDAY HANDLING:
NSE/BSE are closed on weekends and Indian holidays.
We maintain a holiday calendar to avoid running on closed days.
"""

from datetime import datetime, time, timedelta
from typing import Optional, Callable, Literal
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger


# =========================================================
# MARKET SESSION DEFINITIONS
# =========================================================

class MarketSession:
    """
    Enum-like class for market sessions.
    
    🎓 WHY NOT JUST STRINGS?
    Classes give us:
    - Type hints
    - IDE autocomplete
    - Validation
    - Constants in one place
    """
    PRE_OPEN = "pre_open"
    OPENING = "opening"
    MID_SESSION = "mid"
    CLOSING = "closing"
    CLOSED = "closed"


# Session time boundaries
SESSION_TIMES = {
    MarketSession.PRE_OPEN: (time(9, 0), time(9, 15)),
    MarketSession.OPENING: (time(9, 15), time(10, 0)),
    MarketSession.MID_SESSION: (time(10, 0), time(14, 30)),
    MarketSession.CLOSING: (time(14, 30), time(15, 30)),
}


# =========================================================
# HOLIDAY CALENDAR (2024-2025)
# =========================================================

# 🎓 NSE/BSE holiday list
# These are days when markets are completely closed
MARKET_HOLIDAYS_2024 = [
    datetime(2024, 1, 26),   # Republic Day
    datetime(2024, 3, 8),    # Maha Shivaratri
    datetime(2024, 3, 25),   # Holi
    datetime(2024, 3, 29),   # Good Friday
    datetime(2024, 4, 11),   # Idul Fitr
    datetime(2024, 4, 17),   # Ram Navami
    datetime(2024, 4, 21),   # Mahavir Jayanti
    datetime(2024, 5, 1),    # May Day
    datetime(2024, 5, 23),   # Buddha Pournami
    datetime(2024, 6, 17),   # Id-Ul-Adha
    datetime(2024, 7, 17),   # Muharram
    datetime(2024, 8, 15),   # Independence Day
    datetime(2024, 10, 2),   # Gandhi Jayanti
    datetime(2024, 11, 1),   # Diwali Laxmi Pujan
    datetime(2024, 11, 15),  # Guru Nanak Jayanti
    datetime(2024, 12, 25),  # Christmas
]

MARKET_HOLIDAYS_2025 = [
    datetime(2025, 1, 26),   # Republic Day
    datetime(2025, 2, 26),   # Maha Shivaratri
    datetime(2025, 3, 14),   # Holi
    datetime(2025, 3, 31),   # Idul Fitr
    datetime(2025, 4, 6),    # Ram Navami
    datetime(2025, 4, 10),   # Mahavir Jayanti
    datetime(2025, 4, 14),   # Ambedkar Jayanti
    datetime(2025, 4, 18),   # Good Friday
    datetime(2025, 5, 1),    # May Day
    datetime(2025, 6, 7),    # Id-Ul-Adha
    datetime(2025, 7, 6),    # Muharram
    datetime(2025, 8, 15),   # Independence Day
    datetime(2025, 8, 27),   # Janmashtami
    datetime(2025, 10, 2),   # Gandhi Jayanti
    datetime(2025, 10, 21),  # Diwali Laxmi Pujan
    datetime(2025, 11, 5),   # Guru Nanak Jayanti
    datetime(2025, 12, 25),  # Christmas
]

ALL_HOLIDAYS = set(
    [h.date() for h in MARKET_HOLIDAYS_2024] + 
    [h.date() for h in MARKET_HOLIDAYS_2025]
)


# =========================================================
# MARKET STATUS FUNCTIONS
# =========================================================

def is_market_holiday(date: datetime = None) -> bool:
    """
    Check if given date is a market holiday.
    
    🎓 Returns True if market is closed for holiday.
    """
    if date is None:
        date = datetime.now()
    return date.date() in ALL_HOLIDAYS


def is_weekend(date: datetime = None) -> bool:
    """
    Check if given date is a weekend.
    
    🎓 In Python: Monday=0, Sunday=6
    Weekend = Saturday(5) or Sunday(6)
    """
    if date is None:
        date = datetime.now()
    return date.weekday() >= 5


def is_trading_day(date: datetime = None) -> bool:
    """
    Check if given date is a trading day.
    
    🎓 Trading day = Not weekend AND not holiday
    """
    if date is None:
        date = datetime.now()
    return not is_weekend(date) and not is_market_holiday(date)


def get_current_session() -> str:
    """
    Get the current market session.
    
    🎓 Returns one of:
    - 'pre_open': 9:00-9:15
    - 'opening': 9:15-10:00
    - 'mid': 10:00-14:30
    - 'closing': 14:30-15:30
    - 'closed': Outside market hours
    """
    now = datetime.now()
    
    # Check if it's a trading day
    if not is_trading_day(now):
        return MarketSession.CLOSED
    
    current_time = now.time()
    
    # Check each session
    for session, (start, end) in SESSION_TIMES.items():
        if start <= current_time < end:
            return session
    
    return MarketSession.CLOSED


def is_market_open() -> bool:
    """
    Check if market is currently open for trading.
    
    🎓 Market is "open" during opening, mid, and closing sessions.
    Pre-open is not considered "open" because regular trading isn't allowed.
    """
    session = get_current_session()
    return session in [
        MarketSession.OPENING, 
        MarketSession.MID_SESSION, 
        MarketSession.CLOSING
    ]


def time_until_market_open() -> Optional[timedelta]:
    """
    Get time remaining until market opens.
    
    🎓 Returns None if market is already open.
    Returns timedelta if market is closed.
    """
    if is_market_open():
        return None
    
    now = datetime.now()
    
    # Market open time today
    market_open = now.replace(
        hour=settings.MARKET_OPEN_HOUR,
        minute=settings.MARKET_OPEN_MINUTE,
        second=0,
        microsecond=0
    )
    
    # If market open time has passed, calculate for next trading day
    if now.time() >= time(settings.MARKET_CLOSE_HOUR, settings.MARKET_CLOSE_MINUTE):
        # Market closed for today, find next trading day
        next_day = now + timedelta(days=1)
        while not is_trading_day(next_day):
            next_day += timedelta(days=1)
        
        market_open = next_day.replace(
            hour=settings.MARKET_OPEN_HOUR,
            minute=settings.MARKET_OPEN_MINUTE,
            second=0,
            microsecond=0
        )
    
    return market_open - now


def time_until_market_close() -> Optional[timedelta]:
    """
    Get time remaining until market closes.
    
    🎓 Returns None if market is already closed.
    """
    if not is_market_open():
        return None
    
    now = datetime.now()
    market_close = now.replace(
        hour=settings.MARKET_CLOSE_HOUR,
        minute=settings.MARKET_CLOSE_MINUTE,
        second=0,
        microsecond=0
    )
    
    return market_close - now


# =========================================================
# SCHEDULER CLASS
# =========================================================

class MarketScheduler:
    """
    Scheduler that runs tasks only during market hours.
    
    🎓 HOW IT WORKS:
    1. Uses APScheduler (advanced Python scheduler)
    2. Tasks are scheduled using cron-like syntax
    3. Tasks automatically skip weekends and holidays
    4. Can attach callbacks for market open/close events
    
    🎓 EXAMPLE USAGE:
    scheduler = MarketScheduler()
    scheduler.on_market_open(start_trading)
    scheduler.on_market_close(stop_trading)
    scheduler.start()
    """
    
    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone='Asia/Kolkata')
        self._on_open_callbacks = []
        self._on_close_callbacks = []
        self._is_running = False
    
    def on_market_open(self, callback: Callable):
        """Register a callback for market open."""
        self._on_open_callbacks.append(callback)
    
    def on_market_close(self, callback: Callable):
        """Register a callback for market close."""
        self._on_close_callbacks.append(callback)
    
    async def _trigger_market_open(self):
        """Called when market opens."""
        if not is_trading_day():
            logger.info("Skipping market open - not a trading day")
            return
        
        logger.info("🔔 Market is OPEN - Starting trading session")
        for callback in self._on_open_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in market open callback: {e}")
    
    async def _trigger_market_close(self):
        """Called when market closes."""
        if not is_trading_day():
            return
        
        logger.info("🔔 Market is CLOSED - Ending trading session")
        for callback in self._on_close_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error in market close callback: {e}")
    
    def add_market_hours_task(
        self, 
        callback: Callable, 
        interval_minutes: int = 1,
        task_id: str = None
    ):
        """
        Add a task that runs only during market hours.
        
        🎓 This is useful for:
        - Periodic data collection
        - Strategy evaluation
        - Dashboard updates
        """
        async def wrapped_callback():
            if is_market_open():
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
        
        self._scheduler.add_job(
            wrapped_callback,
            'interval',
            minutes=interval_minutes,
            id=task_id or f"task_{id(callback)}"
        )
    
    def start(self):
        """Start the scheduler."""
        if self._is_running:
            return
        
        # Schedule market open trigger (9:15 AM on weekdays)
        self._scheduler.add_job(
            self._trigger_market_open,
            CronTrigger(
                hour=settings.MARKET_OPEN_HOUR,
                minute=settings.MARKET_OPEN_MINUTE,
                day_of_week='mon-fri'
            ),
            id='market_open'
        )
        
        # Schedule market close trigger (3:30 PM on weekdays)
        self._scheduler.add_job(
            self._trigger_market_close,
            CronTrigger(
                hour=settings.MARKET_CLOSE_HOUR,
                minute=settings.MARKET_CLOSE_MINUTE,
                day_of_week='mon-fri'
            ),
            id='market_close'
        )
        
        self._scheduler.start()
        self._is_running = True
        logger.info("📅 Market scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        if not self._is_running:
            return
        
        self._scheduler.shutdown()
        self._is_running = False
        logger.info("📅 Market scheduler stopped")


# =========================================================
# CONVENIENCE FUNCTIONS
# =========================================================

async def wait_for_market_open():
    """
    Wait until market opens.
    
    🎓 Useful for startup logic - wait until trading can begin.
    """
    while not is_market_open():
        remaining = time_until_market_open()
        if remaining:
            logger.info(f"⏳ Market opens in {remaining}")
            # Sleep for 1 minute intervals
            await asyncio.sleep(min(60, remaining.total_seconds()))
        else:
            await asyncio.sleep(1)
    
    logger.info("🟢 Market is now open!")


def get_session_info() -> dict:
    """
    Get current market session information.
    
    🎓 Returns a dict with all relevant info for display.
    """
    now = datetime.now()
    session = get_current_session()
    
    return {
        'current_time': now.strftime('%H:%M:%S'),
        'current_date': now.strftime('%Y-%m-%d'),
        'day_of_week': now.strftime('%A'),
        'session': session,
        'is_trading_day': is_trading_day(now),
        'is_market_open': is_market_open(),
        'is_holiday': is_market_holiday(now),
        'is_weekend': is_weekend(now),
        'time_to_open': str(time_until_market_open()) if time_until_market_open() else None,
        'time_to_close': str(time_until_market_close()) if time_until_market_close() else None,
    }


# =========================================================
# MAIN - Test scheduler
# =========================================================

if __name__ == "__main__":
    import json
    
    print("🔧 Testing scheduler module...")
    print()
    
    # Get current session info
    info = get_session_info()
    print("📊 Current Market Status:")
    print(json.dumps(info, indent=2))
    print()
    
    # Test holiday detection
    print("📅 Holiday Detection:")
    print(f"   Is today a holiday? {is_market_holiday()}")
    print(f"   Is today a weekend? {is_weekend()}")
    print(f"   Is today a trading day? {is_trading_day()}")
    print()
    
    # Test session detection
    print(f"🕐 Current Session: {get_current_session()}")
    print(f"🟢 Market Open: {is_market_open()}")
    
    if time_until_market_open():
        print(f"⏳ Time until open: {time_until_market_open()}")
    if time_until_market_close():
        print(f"⏳ Time until close: {time_until_market_close()}")
