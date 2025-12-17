"""
Database Module
===============

🎓 WHAT IS THIS FILE?
This file sets up SQLite database for storing:
- Strategy definitions and their DNA
- Trade history (paper trades)
- Performance metrics
- Market regime snapshots
- Evolution history

🎓 WHY SQLITE?
- FREE (no server costs)
- No setup required (just a file)
- Perfect for single-user applications
- Fast enough for our needs (<1000 trades/day)
- Data persists across restarts

🎓 WHY ASYNC (aiosqlite)?
Trading systems handle many events simultaneously:
- WebSocket data arriving
- Multiple strategies making decisions
- Dashboard queries

If database operations blocked the main thread,
we'd miss market data. Async keeps everything responsive.

DATABASE SCHEMA:
┌─────────────────────────────────────────────────────────────┐
│ strategies - Each strategy variant                          │
├─────────────────────────────────────────────────────────────┤
│ id, name, generation, parent_id, dna_json, status,          │
│ created_at, retired_at                                       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ trades - All paper trades                                    │
├─────────────────────────────────────────────────────────────┤
│ id, strategy_id, symbol, exchange, side, quantity, price,   │
│ timestamp, pnl                                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ performance - Daily performance snapshots                    │
├─────────────────────────────────────────────────────────────┤
│ id, strategy_id, date, pnl, sharpe, max_drawdown,           │
│ win_rate, trade_count                                        │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ market_regimes - Market condition snapshots                  │
├─────────────────────────────────────────────────────────────┤
│ id, timestamp, volatility, liquidity, spread_behavior,      │
│ session                                                     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ evolution_log - Strategy evolution history                   │
├─────────────────────────────────────────────────────────────┤
│ id, timestamp, action, strategy_id, parent_id, reason,      │
│ market_regime_id                                            │
└─────────────────────────────────────────────────────────────┘
"""

import aiosqlite
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import asyncio


# Database file path (in project root)
DB_PATH = Path(__file__).parent.parent / "quant_engine.db"


async def init_database():
    """
    Initialize database with all required tables.
    
    🎓 WHY 'IF NOT EXISTS'?
    This query is safe to run multiple times.
    First run: creates tables
    Subsequent runs: does nothing (tables exist)
    This is called "idempotent" - same result regardless of repetition.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Strategies table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                generation INTEGER DEFAULT 1,
                parent_id TEXT,
                dna_json TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retired_at TIMESTAMP,
                retirement_reason TEXT
            )
        """)
        
        # Trades table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                entry_time TIMESTAMP NOT NULL,
                exit_time TIMESTAMP,
                pnl REAL DEFAULT 0,
                status TEXT DEFAULT 'open',
                FOREIGN KEY (strategy_id) REFERENCES strategies(id)
            )
        """)
        
        # Performance snapshots
        await db.execute("""
            CREATE TABLE IF NOT EXISTS performance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                date DATE NOT NULL,
                capital REAL NOT NULL,
                pnl REAL NOT NULL,
                pnl_percent REAL NOT NULL,
                sharpe REAL,
                max_drawdown REAL,
                win_rate REAL,
                trade_count INTEGER,
                avg_trade_pnl REAL,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id),
                UNIQUE(strategy_id, date)
            )
        """)
        
        # Market regime snapshots
        await db.execute("""
            CREATE TABLE IF NOT EXISTS market_regimes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP NOT NULL,
                volatility TEXT NOT NULL,
                liquidity TEXT NOT NULL,
                spread_behavior TEXT NOT NULL,
                session TEXT NOT NULL,
                volatility_value REAL,
                avg_spread REAL,
                volume_ratio REAL
            )
        """)
        
        # Evolution log
        await db.execute("""
            CREATE TABLE IF NOT EXISTS evolution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                strategy_id TEXT NOT NULL,
                parent_id TEXT,
                reason TEXT,
                market_regime_id INTEGER,
                old_dna_json TEXT,
                new_dna_json TEXT,
                FOREIGN KEY (strategy_id) REFERENCES strategies(id),
                FOREIGN KEY (market_regime_id) REFERENCES market_regimes(id)
            )
        """)
        
        # Price history (for analysis)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS price_ticks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                price REAL NOT NULL,
                volume INTEGER,
                timestamp TIMESTAMP NOT NULL
            )
        """)
        
        # Create indexes for faster queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_strategy 
            ON trades(strategy_id)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_time 
            ON trades(entry_time)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_performance_strategy_date 
            ON performance(strategy_id, date)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_ticks_symbol_time 
            ON price_ticks(symbol, timestamp)
        """)
        
        await db.commit()
        print("✅ Database initialized successfully")


# =========================================================
# HELPER FUNCTIONS FOR DATABASE OPERATIONS
# =========================================================

async def save_strategy(strategy_data: Dict[str, Any]) -> str:
    """
    Save a new strategy to the database.
    
    🎓 Returns the strategy ID for reference.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO strategies (id, name, generation, parent_id, dna_json, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            strategy_data['id'],
            strategy_data['name'],
            strategy_data.get('generation', 1),
            strategy_data.get('parent_id'),
            json.dumps(strategy_data['dna']),
            'active'
        ))
        await db.commit()
        return strategy_data['id']


async def get_active_strategies() -> List[Dict[str, Any]]:
    """Get all active (non-retired) strategies."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM strategies WHERE status = 'active'
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def retire_strategy(strategy_id: str, reason: str):
    """Mark a strategy as retired."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE strategies 
            SET status = 'retired', 
                retired_at = ?, 
                retirement_reason = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), reason, strategy_id))
        await db.commit()


async def save_trade(trade_data: Dict[str, Any]) -> int:
    """Save a trade and return its ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO trades 
            (strategy_id, symbol, exchange, side, quantity, entry_price, entry_time, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            trade_data['strategy_id'],
            trade_data['symbol'],
            trade_data['exchange'],
            trade_data['side'],
            trade_data['quantity'],
            trade_data['entry_price'],
            trade_data['entry_time'],
            'open'
        ))
        await db.commit()
        return cursor.lastrowid


async def close_trade(trade_id: int, exit_price: float, pnl: float):
    """Close a trade with exit price and P&L."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE trades 
            SET exit_price = ?, 
                exit_time = ?, 
                pnl = ?,
                status = 'closed'
            WHERE id = ?
        """, (exit_price, datetime.now().isoformat(), pnl, trade_id))
        await db.commit()


async def save_market_regime(regime_data: Dict[str, Any]) -> int:
    """Save a market regime snapshot."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
            INSERT INTO market_regimes 
            (timestamp, volatility, liquidity, spread_behavior, session,
             volatility_value, avg_spread, volume_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            regime_data['volatility'],
            regime_data['liquidity'],
            regime_data['spread_behavior'],
            regime_data['session'],
            regime_data.get('volatility_value'),
            regime_data.get('avg_spread'),
            regime_data.get('volume_ratio')
        ))
        await db.commit()
        return cursor.lastrowid


async def log_evolution(
    action: str, 
    strategy_id: str, 
    parent_id: Optional[str] = None,
    reason: Optional[str] = None,
    market_regime_id: Optional[int] = None,
    old_dna: Optional[Dict] = None,
    new_dna: Optional[Dict] = None
):
    """Log an evolution event (creation, mutation, retirement)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO evolution_log 
            (action, strategy_id, parent_id, reason, market_regime_id, 
             old_dna_json, new_dna_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            action,
            strategy_id,
            parent_id,
            reason,
            market_regime_id,
            json.dumps(old_dna) if old_dna else None,
            json.dumps(new_dna) if new_dna else None
        ))
        await db.commit()


async def get_strategy_performance(strategy_id: str, days: int = 7) -> List[Dict]:
    """Get performance history for a strategy."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM performance 
            WHERE strategy_id = ?
            ORDER BY date DESC
            LIMIT ?
        """, (strategy_id, days)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def get_evolution_history() -> List[Dict]:
    """Get full evolution history for reporting."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT e.*, s.name as strategy_name
            FROM evolution_log e
            LEFT JOIN strategies s ON e.strategy_id = s.id
            ORDER BY e.timestamp DESC
        """) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


# =========================================================
# MAIN - Test database initialization
# =========================================================

if __name__ == "__main__":
    async def main():
        print("🔧 Initializing database...")
        await init_database()
        print(f"📁 Database file: {DB_PATH}")
        
        # Test saving a strategy
        test_strategy = {
            'id': 'test-001',
            'name': 'Test Strategy',
            'generation': 1,
            'dna': {
                'min_spread_threshold': 0.5,
                'stability_ticks': 3
            }
        }
        await save_strategy(test_strategy)
        print("✅ Test strategy saved")
        
        # Retrieve it
        strategies = await get_active_strategies()
        print(f"📊 Active strategies: {len(strategies)}")
        
        # Clean up test data
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM strategies WHERE id = 'test-001'")
            await db.commit()
        print("🧹 Test data cleaned up")
    
    asyncio.run(main())
