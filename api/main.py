"""
FastAPI Backend
===============

🎓 WHAT IS THIS FILE?
This is the main API server that:
1. Runs the trading engine
2. Provides REST API for dashboard
3. Serves the web interface
4. Handles WebSocket updates

🎓 API ENDPOINTS:

┌─────────────────────┬────────────────────────────────────────┐
│ Endpoint            │ Description                            │
├─────────────────────┼────────────────────────────────────────┤
│ GET /               │ Dashboard HTML                         │
│ GET /api/status     │ System status                          │
│ GET /api/strategies │ All strategies with performance        │
│ GET /api/champion   │ Current champion details               │
│ GET /api/regime     │ Current market regime                  │
│ GET /api/trades     │ Recent trades                          │
│ GET /api/evolution  │ Evolution history                      │
│ POST /api/killswitch│ Toggle kill switch                     │
└─────────────────────┴────────────────────────────────────────┘
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime
from typing import Optional
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger
from core.database import init_database
from core.scheduler import MarketScheduler, get_session_info, is_market_open
from data.websocket_streamer import get_market_streamer, SpreadData, PriceTick
from data.angelone_auth import get_auth_client
from analysis.regime_analyzer import get_regime_analyzer
from analysis.spread_analyzer import get_spread_analyzer
from strategies.generator import get_strategy_generator
from strategies.simulator import get_simulator
from strategies.paper_trader import get_paper_trading_engine
from evolution.evaluator import get_performance_evaluator
from risk.risk_manager import get_risk_manager


# =========================================================
# GLOBAL STATE
# =========================================================

class AppState:
    """Global application state."""
    streamer = None
    scheduler = None
    is_running = False
    last_update = None
    tick_count = 0
    
app_state = AppState()


# =========================================================
# LIFESPAN (STARTUP/SHUTDOWN)
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown.
    
    🎓 Lifespan context manager:
    - Before yield: Startup code
    - After yield: Shutdown code
    """
    # STARTUP
    logger.info("🚀 Starting Quant Research Engine...")
    
    # Initialize database
    await init_database()
    
    # Initialize components
    generator = get_strategy_generator()
    strategies = generator.create_initial_population()
    
    simulator = get_simulator()
    simulator.initialize(strategies)
    
    engine = get_paper_trading_engine()
    # Set first strategy as champion
    if strategies:
        engine.set_champion(strategies[0].id)
    
    # Initialize market data streamer (mock mode for testing)
    app_state.streamer = get_market_streamer()
    
    # Register callbacks
    app_state.streamer.on_tick(on_tick_received)
    app_state.streamer.on_spread(on_spread_received)
    
    # Start streamer
    await app_state.streamer.connect()
    await app_state.streamer.subscribe(settings.symbol_list)
    
    app_state.is_running = True
    logger.info("✅ Quant Research Engine started")
    
    yield
    
    # SHUTDOWN
    logger.info("🛑 Shutting down...")
    app_state.is_running = False
    
    if app_state.streamer:
        await app_state.streamer.disconnect()
    
    logger.info("👋 Shutdown complete")


# =========================================================
# CALLBACKS
# =========================================================

async def on_tick_received(tick: PriceTick):
    """Process price tick updates."""
    app_state.tick_count += 1
    app_state.last_update = datetime.now()
    
    # Update regime analyzer
    regime_analyzer = get_regime_analyzer()
    regime_analyzer.add_tick(tick)


async def on_spread_received(spread: SpreadData):
    """Process spread updates."""
    # Update spread analyzer
    spread_analyzer = get_spread_analyzer()
    signal = spread_analyzer.add_spread(spread)
    
    # Update regime
    regime_analyzer = get_regime_analyzer()
    regime_analyzer.add_spread(spread)
    regime = regime_analyzer.get_regime()
    
    # Feed to simulator
    simulator = get_simulator()
    simulator.update_regime(regime)
    await simulator.on_spread_update(spread, signal)


# =========================================================
# FASTAPI APP
# =========================================================

app = FastAPI(
    title="Quant Strategy Research Engine",
    description="Self-improving trading strategy research platform",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# API ROUTES
# =========================================================

@app.get("/api/status")
async def get_status():
    """Get system status."""
    risk_manager = get_risk_manager()
    session_info = get_session_info()
    
    return {
        "system": {
            "is_running": app_state.is_running,
            "tick_count": app_state.tick_count,
            "last_update": app_state.last_update.isoformat() if app_state.last_update else None,
        },
        "market": session_info,
        "risk": risk_manager.get_status()
    }


@app.get("/api/strategies")
async def get_strategies():
    """Get all strategies with performance."""
    simulator = get_simulator()
    evaluator = get_performance_evaluator()
    
    states = simulator.get_all_states()
    ranked = evaluator.rank_strategies(states)
    
    result = []
    for dna, metrics in ranked:
        state = states.get(dna.id)
        result.append({
            "id": dna.id,
            "name": dna.name,
            "generation": dna.generation,
            "parent_id": dna.parent_id,
            "dna": {
                "min_spread_threshold": dna.min_spread_threshold,
                "stability_ticks": dna.stability_ticks,
                "position_size_pct": dna.position_size_pct,
                "preferred_session": dna.preferred_session,
            },
            "metrics": metrics.to_dict(),
            "capital": state.current_capital if state else 0,
            "trades": len(state.completed_trades) if state else 0,
        })
    
    return result


@app.get("/api/champion")
async def get_champion():
    """Get current champion strategy."""
    engine = get_paper_trading_engine()
    state = engine.get_champion_state()
    
    if not state:
        return {"champion": None}
    
    evaluator = get_performance_evaluator()
    metrics = evaluator.calculate(state)
    
    return {
        "champion": {
            "id": state.dna.id,
            "name": state.dna.name,
            "generation": state.dna.generation,
            "dna_summary": state.dna.summary(),
            "metrics": metrics.to_dict(),
        },
        "portfolio": {
            "value": engine.get_portfolio_value(),
            "pnl": engine.get_portfolio_pnl(),
            "pnl_pct": engine.get_portfolio_pnl_pct(),
        }
    }


@app.get("/api/regime")
async def get_regime():
    """Get current market regime."""
    regime_analyzer = get_regime_analyzer()
    regime = regime_analyzer.get_regime()
    
    return {
        "regime": regime.to_dict(),
        "favorable": regime_analyzer.is_favorable_for_trading()
    }


@app.get("/api/trades")
async def get_trades(limit: int = 50):
    """Get recent trades across all strategies."""
    simulator = get_simulator()
    
    all_trades = []
    for state in simulator.get_all_states().values():
        for trade in state.completed_trades[-limit:]:
            all_trades.append({
                "strategy_id": trade.strategy_id,
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "entry_price": trade.entry_price,
                "exit_price": trade.exit_price,
                "pnl": trade.pnl,
                "pnl_pct": trade.pnl_pct,
                "exit_reason": trade.exit_reason,
                "entry_time": trade.entry_time.isoformat(),
                "exit_time": trade.exit_time.isoformat(),
            })
    
    # Sort by time (newest first)
    all_trades.sort(key=lambda x: x["exit_time"], reverse=True)
    
    return all_trades[:limit]


@app.get("/api/spreads")
async def get_spreads():
    """Get current spreads for all symbols."""
    spread_analyzer = get_spread_analyzer()
    
    result = {}
    for symbol in settings.symbol_list:
        stats = spread_analyzer.get_statistics(symbol)
        signal = spread_analyzer.get_signal(symbol)
        
        result[symbol] = {
            "statistics": stats,
            "signal": str(signal) if signal else None,
            "is_actionable": signal.is_actionable if signal else False
        }
    
    return result


@app.get("/api/evolution")
async def get_evolution():
    """Get evolution history."""
    generator = get_strategy_generator()
    
    return {
        "current_generation": generator.current_generation,
        "history": [
            {
                "generation": stats.generation,
                "retired": stats.retired_count,
                "created": stats.created_count,
                "best_strategy": stats.best_strategy_id,
                "avg_performance": stats.avg_performance,
            }
            for stats in generator.evolution_history
        ]
    }


@app.post("/api/killswitch")
async def toggle_killswitch(activate: bool):
    """Toggle the kill switch."""
    risk_manager = get_risk_manager()
    
    if activate:
        risk_manager.activate_kill_switch("Manual activation via API")
    else:
        risk_manager.deactivate_kill_switch()
    
    return {"kill_switch_active": risk_manager.state.kill_switch_active}


@app.post("/api/evolve")
async def trigger_evolution():
    """Manually trigger strategy evolution."""
    simulator = get_simulator()
    generator = get_strategy_generator()
    
    # Get ranked strategies
    leaderboard = simulator.get_leaderboard()
    
    if not leaderboard:
        raise HTTPException(status_code=400, detail="No strategies to evolve")
    
    # Evolve
    new_population = generator.evolve(leaderboard)
    
    # Re-initialize simulator with new population
    simulator.initialize(new_population)
    
    # Update champion
    engine = get_paper_trading_engine()
    if new_population:
        engine.set_champion(new_population[0].id)
    
    return {
        "new_generation": generator.current_generation,
        "strategies_count": len(new_population)
    }


@app.get("/api/report")
async def generate_report():
    """
    Generate weekly report with all trades and analysis.
    
    🎓 This creates a complete documentation of:
    - All trades executed
    - Stock selection rationale
    - Strategy performance
    - Evolution history
    """
    from reports.report_generator import get_report_generator
    
    generator = get_report_generator()
    report = generator.generate()
    
    # Save report
    filepath = generator.save_report(report)
    
    return {
        "report": report,
        "saved_to": str(filepath)
    }


@app.get("/api/report/download", response_class=HTMLResponse)
async def download_report():
    """Get the latest report as downloadable markdown."""
    from reports.report_generator import get_report_generator
    
    generator = get_report_generator()
    report = generator.generate()
    
    # Return as markdown file
    from fastapi.responses import Response
    return Response(
        content=report,
        media_type="text/markdown",
        headers={"Content-Disposition": "attachment; filename=weekly_report.md"}
    )


# =========================================================
# PRINTABLE REPORT PAGE (Browser Print to PDF)
# =========================================================

@app.get("/report", response_class=HTMLResponse)
async def report_page():
    """Simple printable report page using API data."""
    from datetime import datetime
    
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>Quant Research Engine - Complete Report</title>
    <style>
        * { font-family: 'Segoe UI', Arial, sans-serif; }
        body { max-width: 1000px; margin: 0 auto; padding: 20px; background: #fff; color: #333; }
        h1 { color: #1a1a2e; border-bottom: 3px solid #4ecca3; padding-bottom: 10px; }
        h2 { color: #16213e; margin-top: 30px; border-bottom: 1px solid #ddd; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        td, th { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background: #16213e; color: white; }
        .positive { color: #27ae60; font-weight: bold; }
        .negative { color: #e74c3c; font-weight: bold; }
        .strategy-card { background: #f8f9fa; border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 15px 0; }
        .summary-box { background: #e8f5e9; border: 2px solid #4ecca3; padding: 20px; border-radius: 8px; margin: 20px 0; }
        .print-btn { background: #4ecca3; color: white; border: none; padding: 15px 30px; font-size: 18px; cursor: pointer; border-radius: 5px; margin: 10px 5px; }
        @media print { .no-print { display: none; } }
        .loading { color: #888; font-style: italic; }
    </style>
</head>
<body>
    <div class="no-print">
        <button class="print-btn" onclick="window.print()">🖨️ Print to PDF (Ctrl+P)</button>
        <a href="/" style="margin-left: 20px;">← Back to Dashboard</a>
    </div>
    
    <h1>📊 Quant Research Engine - Complete Report</h1>
    <p><b>Generated:</b> """ + datetime.now().strftime('%d %B %Y at %H:%M IST') + """</p>
    <p><b>Mode:</b> Paper Trading (No Real Money) | <b>Capital:</b> ₹10,000</p>
    
    <div class="summary-box">
        <h2 style="margin-top:0;">💰 Portfolio Summary</h2>
        <div id="portfolio-summary" class="loading">Loading...</div>
    </div>
    
    <h2>🎯 Stock Selection - NSE-BSE Arbitrage Strategy</h2>
    
    <div style="background:#fff3cd; border:1px solid #ffc107; padding:15px; border-radius:8px; margin:10px 0;">
        <h3 style="margin-top:0;">📈 Strategy Logic: Exchange Price Difference</h3>
        <p>Same stock trades at <b>slightly different prices</b> on NSE vs BSE due to:</p>
        <ul>
            <li>Different order books and liquidity</li>
            <li>Timing differences in order execution</li>
            <li>Different trader behavior on each exchange</li>
        </ul>
        <p><b>Example:</b> RELIANCE @ ₹2,450.30 on NSE, ₹2,450.70 on BSE = <b>₹0.40 spread</b></p>
        <p>If we buy on NSE and sell on BSE → <b>₹0.40 profit per share</b> (minus fees)</p>
    </div>
    
    <table>
        <tr><th>Symbol</th><th>Why This Stock for Arbitrage</th><th>Typical Spread</th></tr>
        <tr>
            <td><b>RELIANCE</b></td>
            <td>Highest volume stock - both NSE & BSE have deep liquidity, spreads appear frequently</td>
            <td>₹0.20 - ₹0.50</td>
        </tr>
        <tr>
            <td><b>TCS</b></td>
            <td>High price (₹3500+) means even small % difference = good absolute spread in rupees</td>
            <td>₹0.30 - ₹0.80</td>
        </tr>
        <tr>
            <td><b>INFY</b></td>
            <td>Tech sector has volatile intraday moves, creates temporary price mismatches</td>
            <td>₹0.15 - ₹0.40</td>
        </tr>
        <tr>
            <td><b>HDFCBANK</b></td>
            <td>Banking stocks react to news differently on each exchange, creates opportunities</td>
            <td>₹0.20 - ₹0.60</td>
        </tr>
        <tr>
            <td><b>ICICIBANK</b></td>
            <td>Second most traded bank stock, frequent NSE-BSE pricing gaps</td>
            <td>₹0.15 - ₹0.45</td>
        </tr>
    </table>
    
    <h3>How We Detect Opportunities</h3>
    <pre style="background:#f5f5f5; padding:10px; border-radius:5px;">
SPREAD = |NSE Price - BSE Price|
SPREAD_PERCENT = SPREAD / Average Price × 100

If SPREAD_PERCENT > 0.03% AND stable for 3+ ticks:
   → TRADE SIGNAL GENERATED
   → Buy on CHEAPER exchange
   → Sell on EXPENSIVE exchange
   → Lock in the difference as profit
    </pre>
    
    <h2>🧬 All Strategy Algorithms</h2>
    <div id="strategies-section" class="loading">Loading strategies...</div>
    
    <h2>📝 Trade Log</h2>
    <div id="trades-section" class="loading">Loading trades...</div>
    
    <h2>🌤️ Market Conditions</h2>
    <div id="regime-section" class="loading">Loading...</div>
    
    <hr>
    <p style="color:#888;font-size:12px;"><i>Educational purposes only. No real money traded.</i></p>
    
    <script>
        async function loadReport() {
            try {
                // Load champion/portfolio
                const champ = await fetch('/api/champion').then(r => r.json());
                if (champ.portfolio) {
                    const p = champ.portfolio;
                    document.getElementById('portfolio-summary').innerHTML = `
                        <table>
                            <tr><td><b>Invested Amount</b></td><td>₹10,000.00</td></tr>
                            <tr><td><b>Current Value</b></td><td>₹${p.value.toFixed(2)}</td></tr>
                            <tr><td><b>Total P&L</b></td><td class="${p.pnl >= 0 ? 'positive' : 'negative'}">₹${p.pnl.toFixed(2)}</td></tr>
                            <tr><td><b>Return</b></td><td class="${p.pnl_pct >= 0 ? 'positive' : 'negative'}">${p.pnl_pct.toFixed(2)}%</td></tr>
                        </table>
                    `;
                }
                
                // Load strategies
                const strategies = await fetch('/api/strategies').then(r => r.json());
                let stratHtml = '';
                strategies.forEach((s, i) => {
                    stratHtml += `
                        <div class="strategy-card">
                            <h3>${i === 0 ? '👑 ' : ''}${i+1}. ${s.name} (Gen ${s.generation})</h3>
                            <table>
                                <tr><td><b>ID:</b></td><td>${s.id}</td></tr>
                                <tr><td><b>Spread Threshold:</b></td><td>${(s.dna.min_spread_threshold * 100).toFixed(4)}%</td></tr>
                                <tr><td><b>Stability Ticks:</b></td><td>${s.dna.stability_ticks}</td></tr>
                                <tr><td><b>Position Size:</b></td><td>${s.dna.position_size_pct}%</td></tr>
                                <tr><td><b>Session:</b></td><td>${s.dna.preferred_session}</td></tr>
                            </table>
                            <h4>Performance</h4>
                            <table>
                                <tr><td><b>P&L:</b></td><td class="${s.metrics.net_pnl >= 0 ? 'positive' : 'negative'}">₹${s.metrics.net_pnl.toFixed(2)}</td></tr>
                                <tr><td><b>Sharpe:</b></td><td>${s.metrics.sharpe_ratio.toFixed(2)}</td></tr>
                                <tr><td><b>Win Rate:</b></td><td>${s.metrics.win_rate.toFixed(1)}%</td></tr>
                                <tr><td><b>Trades:</b></td><td>${s.trades}</td></tr>
                                <tr><td><b>Score:</b></td><td><b>${s.metrics.composite_score.toFixed(1)}</b></td></tr>
                            </table>
                        </div>
                    `;
                });
                document.getElementById('strategies-section').innerHTML = stratHtml || '<p>No strategies yet</p>';
                
                // Load trades
                const trades = await fetch('/api/trades?limit=30').then(r => r.json());
                if (trades.length > 0) {
                    let tradeHtml = '<table><tr><th>#</th><th>Time</th><th>Symbol</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Reason</th></tr>';
                    trades.forEach((t, i) => {
                        tradeHtml += `<tr>
                            <td>${i+1}</td>
                            <td>${new Date(t.entry_time).toLocaleString('en-IN')}</td>
                            <td>${t.symbol}</td>
                            <td>₹${t.entry_price.toFixed(2)}</td>
                            <td>₹${t.exit_price.toFixed(2)}</td>
                            <td class="${t.pnl >= 0 ? 'positive' : 'negative'}">₹${t.pnl.toFixed(2)}</td>
                            <td>${t.exit_reason}</td>
                        </tr>`;
                    });
                    tradeHtml += '</table>';
                    document.getElementById('trades-section').innerHTML = tradeHtml;
                } else {
                    document.getElementById('trades-section').innerHTML = '<p>No trades executed yet (mock mode)</p>';
                }
                
                // Load regime
                const regime = await fetch('/api/regime').then(r => r.json());
                document.getElementById('regime-section').innerHTML = `
                    <table>
                        <tr><td><b>Volatility:</b></td><td>${regime.regime.volatility}</td></tr>
                        <tr><td><b>Liquidity:</b></td><td>${regime.regime.liquidity}</td></tr>
                        <tr><td><b>Session:</b></td><td>${regime.regime.session}</td></tr>
                    </table>
                `;
                
            } catch (error) {
                console.error('Error loading report:', error);
            }
        }
        loadReport();
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)


# =========================================================
# DASHBOARD ROUTE
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard."""
    # Read dashboard HTML
    dashboard_path = os.path.join(
        os.path.dirname(__file__), 
        "..", "dashboard", "index.html"
    )
    
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r") as f:
            return HTMLResponse(content=f.read())
    
    # Fallback simple dashboard
    return HTMLResponse(content="""
<!DOCTYPE html>
<html>
<head>
    <title>Quant Research Engine</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; margin: 20px; background: #1a1a2e; color: #eee; }
        h1 { color: #4ecca3; }
        .card { background: #16213e; border-radius: 8px; padding: 15px; margin: 10px 0; }
        .metric { display: inline-block; margin: 10px 20px; }
        .metric-value { font-size: 24px; font-weight: bold; color: #4ecca3; }
        .metric-label { font-size: 12px; color: #888; }
        #strategies { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 15px; }
        .strategy { background: #1f4068; border-radius: 8px; padding: 15px; }
        .champion { border: 2px solid #ffd700; }
        .positive { color: #4ecca3; }
        .negative { color: #ff6b6b; }
        button { background: #4ecca3; color: #1a1a2e; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
        button:hover { background: #3db892; }
        #status { position: fixed; top: 10px; right: 10px; padding: 10px; border-radius: 5px; }
        .running { background: #4ecca3; color: #1a1a2e; }
        .stopped { background: #ff6b6b; color: #fff; }
    </style>
</head>
<body>
    <h1>🧬 Quant Strategy Research Engine</h1>
    <div id="status" class="running">Loading...</div>
    
    <div class="card">
        <h2>📊 System Status</h2>
        <div class="metric">
            <div class="metric-value" id="tick-count">0</div>
            <div class="metric-label">Ticks Received</div>
        </div>
        <div class="metric">
            <div class="metric-value" id="session">-</div>
            <div class="metric-label">Market Session</div>
        </div>
        <div class="metric">
            <div class="metric-value" id="regime">-</div>
            <div class="metric-label">Market Regime</div>
        </div>
    </div>
    
    <div class="card" style="border: 2px solid #4ecca3; background: linear-gradient(135deg, #16213e, #1f4068);">
        <h2>💰 Portfolio Summary</h2>
        <div class="metric">
            <div class="metric-value" style="color: #888;">₹10,000</div>
            <div class="metric-label">Invested Amount</div>
        </div>
        <div class="metric">
            <div class="metric-value" id="current-value">₹10,000</div>
            <div class="metric-label">Current Value</div>
        </div>
        <div class="metric">
            <div class="metric-value" id="total-pnl">₹0.00</div>
            <div class="metric-label">Total P&L</div>
        </div>
        <div class="metric">
            <div class="metric-value" id="return-pct">0.00%</div>
            <div class="metric-label">Return %</div>
        </div>
        <div class="metric">
            <div class="metric-value" id="total-trades">0</div>
            <div class="metric-label">Total Trades</div>
        </div>
    </div>
    
    <div class="card">
        <h2>👑 Champion Strategy</h2>
        <div id="champion">Loading...</div>
    </div>
    
    <div class="card">
        <h2>🏆 Strategy Leaderboard</h2>
        <div id="strategies">Loading...</div>
    </div>
    
    <div class="card">
        <h2>⚙️ Controls</h2>
        <button onclick="triggerEvolution()">🧬 Trigger Evolution</button>
        <button onclick="toggleKillSwitch()" id="killswitch-btn">🛑 Kill Switch</button>
        <a href="/report" target="_blank" style="display:inline-block; background: #ffd700; color: #1a1a2e; font-weight: bold; padding: 10px 20px; border-radius: 5px; text-decoration: none; margin-left: 5px;">📊 View Full Report</a>
    </div>
    
    <div class="card" style="border: 2px solid #ffd700;">
        <h2>📋 Complete Report</h2>
        <p style="color: #888; margin-bottom: 15px;">All strategies, trades, stock rationale - printable to PDF</p>
        <a href="/report" target="_blank" style="display:inline-block; background: linear-gradient(135deg, #4ecca3, #2ecc71); color: white; font-size: 18px; padding: 15px 30px; border-radius: 5px; text-decoration: none;">
            📄 Open Report Page (Use Ctrl+P for PDF)
        </a>
        <p style="color: #4ecca3; margin-top: 10px;">💡 Report page pe jaake Ctrl+P dabao to save as PDF</p>
    </div>
    
    <script>
        async function fetchData() {
            try {
                // Fetch status
                const status = await fetch('/api/status').then(r => r.json());
                document.getElementById('tick-count').textContent = status.system.tick_count;
                document.getElementById('session').textContent = status.market.session;
                document.getElementById('status').textContent = status.system.is_running ? '🟢 Running' : '🔴 Stopped';
                document.getElementById('status').className = status.system.is_running ? 'running' : 'stopped';
                
                // Fetch regime
                const regime = await fetch('/api/regime').then(r => r.json());
                document.getElementById('regime').textContent = 
                    `${regime.regime.volatility} vol | ${regime.regime.liquidity} liq`;
                
                // Fetch champion
                const champion = await fetch('/api/champion').then(r => r.json());
                if (champion.champion) {
                    const c = champion.champion;
                    const p = champion.portfolio;
                    document.getElementById('champion').innerHTML = `
                        <div class="metric">
                            <div class="metric-value">${c.name}</div>
                            <div class="metric-label">Name (Gen ${c.generation})</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value ${p.pnl >= 0 ? 'positive' : 'negative'}">
                                ₹${p.pnl.toFixed(2)}
                            </div>
                            <div class="metric-label">Portfolio P&L</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value ${p.pnl_pct >= 0 ? 'positive' : 'negative'}">
                                ${p.pnl_pct.toFixed(2)}%
                            </div>
                            <div class="metric-label">Return</div>
                        </div>
                    `;
                }
                
                // Fetch strategies
                const strategies = await fetch('/api/strategies').then(r => r.json());
                document.getElementById('strategies').innerHTML = strategies.map((s, i) => `
                    <div class="strategy ${i === 0 ? 'champion' : ''}">
                        <h3>${i + 1}. ${s.name}</h3>
                        <p>Generation: ${s.generation} | Trades: ${s.trades}</p>
                        <p class="${s.metrics.net_pnl >= 0 ? 'positive' : 'negative'}">
                            P&L: ₹${s.metrics.net_pnl.toFixed(2)} (${s.metrics.return_pct.toFixed(2)}%)
                        </p>
                        <p>Sharpe: ${s.metrics.sharpe_ratio.toFixed(2)} | Win: ${s.metrics.win_rate.toFixed(1)}%</p>
                        <p>Score: ${s.metrics.composite_score.toFixed(1)}</p>
                    </div>
                `).join('');
                
                // Update Portfolio Summary
                if (champion.portfolio) {
                    const p = champion.portfolio;
                    document.getElementById('current-value').textContent = '₹' + p.value.toFixed(2);
                    const pnlEl = document.getElementById('total-pnl');
                    pnlEl.textContent = '₹' + p.pnl.toFixed(2);
                    pnlEl.className = 'metric-value ' + (p.pnl >= 0 ? 'positive' : 'negative');
                    const retEl = document.getElementById('return-pct');
                    retEl.textContent = p.pnl_pct.toFixed(2) + '%';
                    retEl.className = 'metric-value ' + (p.pnl_pct >= 0 ? 'positive' : 'negative');
                }
                
                // Count total trades
                let totalTrades = strategies.reduce((sum, s) => sum + s.trades, 0);
                document.getElementById('total-trades').textContent = totalTrades;
                
            } catch (error) {
                console.error('Error fetching data:', error);
            }
        }
        
        async function triggerEvolution() {
            const resp = await fetch('/api/evolve', { method: 'POST' });
            const data = await resp.json();
            alert(`Evolution complete! New generation: ${data.new_generation}`);
            fetchData();
        }
        
        let killSwitchActive = false;
        async function toggleKillSwitch() {
            killSwitchActive = !killSwitchActive;
            const resp = await fetch('/api/killswitch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ activate: killSwitchActive })
            });
            const data = await resp.json();
            document.getElementById('killswitch-btn').textContent = 
                data.kill_switch_active ? '🟢 Deactivate Kill Switch' : '🛑 Kill Switch';
            fetchData();
        }
        
        
        // Initial fetch and periodic updates
        fetchData();
        setInterval(fetchData, 2000);
        
        async function downloadReport() {
            document.getElementById('report-status').textContent = '⏳ Generating report...';
            try {
                const resp = await fetch('/api/report');
                const data = await resp.json();
                
                // Create download link
                const blob = new Blob([data.report], { type: 'text/markdown' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'trading_report_' + new Date().toISOString().split('T')[0] + '.md';
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                document.getElementById('report-status').textContent = '✅ Report downloaded! Check your downloads folder.';
            } catch (error) {
                document.getElementById('report-status').textContent = '❌ Error generating report: ' + error;
            }
        }
    </script>
</body>
</html>
    """)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
