# 🧬 Quant Strategy Research Engine

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Angel One](https://img.shields.io/badge/Angel%20One-SmartAPI-FF6B35?style=for-the-badge)
![WebSocket](https://img.shields.io/badge/WebSocket-Real--time-4A90D9?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

### **A Self-Evolving Algorithmic Trading Research Platform**

*8 parallel strategies compete • Genetic evolution • NSE-BSE arbitrage detection*

[Live Demo](https://quant-strategy-research-engine.onrender.com) • [Features](#-key-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start)

---

</div>

## 🎯 What Is This?

A **quantitative research engine** that:

1. **Runs 8 trading strategies simultaneously** - each with unique genetic parameters
2. **Monitors NSE-BSE price spreads** in real-time via WebSocket
3. **Evolves strategies** using genetic algorithms - weak strategies die, strong ones mutate & reproduce
4. **Implements strict risk management** - daily loss caps, position limits, kill switch
5. **Paper trades only** - no real money, pure research & learning

```
┌─────────────────────────────────────────────────────────────────────┐
│                    QUANT RESEARCH ENGINE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐              │
│   │Strategy │  │Strategy │  │Strategy │  │Strategy │   ...x8      │
│   │   A     │  │   B     │  │   C     │  │   D     │              │
│   └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘              │
│        │            │            │            │                    │
│        └────────────┴────────────┴────────────┘                    │
│                          │                                          │
│                    ┌─────▼─────┐                                   │
│                    │ EVOLUTION │ ← Genetic Algorithm               │
│                    │  ENGINE   │   (Select, Mutate, Crossover)     │
│                    └─────┬─────┘                                   │
│                          │                                          │
│              ┌───────────┼───────────┐                             │
│              ▼           ▼           ▼                             │
│         ┌────────┐  ┌────────┐  ┌────────┐                        │
│         │RETIRE  │  │CHAMPION│  │ MUTATE │                        │
│         │Bottom  │  │ Wins   │  │Winners │                        │
│         │ 25%    │  │        │  │        │                        │
│         └────────┘  └────────┘  └────────┘                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 💰 The Arbitrage Opportunity

Same stock trades at **slightly different prices** on NSE vs BSE:

```
┌─────────────────────────────────────────────────────────────────────┐
│  RELIANCE                                                           │
│  ──────────                                                         │
│  NSE Price: ₹2,850.30                                              │
│  BSE Price: ₹2,850.75                                              │
│                    ↓                                                │
│            Spread = ₹0.45/share                                    │
│                    ↓                                                │
│  Buy 100 on NSE  = ₹2,85,030                                       │
│  Sell 100 on BSE = ₹2,85,075                                       │
│                    ↓                                                │
│            Profit = ₹45 (minus fees)                               │
│                                                                     │
│  This happens MULTIPLE times per day across 30+ stocks!            │
└─────────────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔄 **Real-time WebSocket** | Angel One SmartAPI WebSocket V2 for live NSE-BSE data |
| 🧬 **Genetic Evolution** | Strategies evolve through selection, mutation & crossover |
| 🏆 **Champion-Challenger** | Best strategy handles "real" portfolio, others compete |
| 📊 **30+ Stocks** | Tracking large-caps across IT, Banking, FMCG, Energy, Metals |
| 🛡️ **Risk Management** | Kill switch, daily loss caps, position limits |
| 📈 **Live Dashboard** | Real-time monitoring with strategy leaderboard |
| 📄 **Printable Reports** | Complete trade logs, strategy DNA, performance analysis |

---

## 🏗️ Architecture

```
├── run.py                      # Entry point
├── config.py                   # Settings & environment
│
├── data/                       # Market Data Layer
│   ├── angelone_auth.py       # Angel One OAuth + TOTP
│   ├── websocket_streamer.py  # Real-time WebSocket V2
│   └── instruments.py         # NSE/BSE token mapping
│
├── analysis/                   # Analysis Layer
│   ├── regime_analyzer.py     # Market regime detection
│   └── spread_analyzer.py     # NSE-BSE spread calculation
│
├── strategies/                 # Strategy Engine
│   ├── strategy_dna.py        # Genetic parameters
│   ├── generator.py           # Population creation
│   ├── simulator.py           # Parallel execution
│   └── paper_trader.py        # Champion management
│
├── evolution/                  # Evolution Engine
│   └── evaluator.py           # Sharpe, Sortino, Drawdown
│
├── risk/                       # Risk Management
│   └── risk_manager.py        # Kill switch, limits
│
└── api/                        # API & Dashboard
    └── main.py                # FastAPI + WebSocket
```

---

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/SypherKx/Quant-Strategy-Research-Engine.git
cd Quant-Strategy-Research-Engine

# Install
pip install -r requirements.txt

# Configure (copy and edit .env)
cp .env.example .env

# Run
python run.py

# Open Dashboard
# http://localhost:8000
```

---

## 🔑 Angel One SmartAPI Setup

1. Create account at [Angel One](https://www.angelone.in/)
2. Register at [SmartAPI Portal](https://smartapi.angelone.in/)
3. Create app (FREE) and get credentials
4. Add to `.env`:

```env
ANGELONE_API_KEY=your_api_key
ANGELONE_CLIENT_CODE=your_client_code
ANGELONE_PIN=your_pin
ANGELONE_TOTP_SECRET=your_totp_secret
```

**Without credentials, runs in Mock Mode with simulated data.**

---

## 🧬 Strategy DNA

Each strategy has genetic parameters that can mutate:

```python
{
    "min_spread_threshold": 0.03,  # Minimum % spread to trade
    "stability_ticks": 3,          # Ticks spread must be stable
    "position_size_pct": 5.0,      # % of capital per trade
    "take_profit_pct": 0.05,       # Exit at this profit %
    "stop_loss_pct": 0.02,         # Exit at this loss %
    "preferred_session": "mid",     # morning/mid/closing
}
```

---

## 📊 Performance Metrics

| Metric | Description |
|--------|-------------|
| **Sharpe Ratio** | Risk-adjusted returns (>1 good, >2 excellent) |
| **Sortino Ratio** | Like Sharpe but only penalizes downside |
| **Max Drawdown** | Worst peak-to-trough decline |
| **Win Rate** | % of profitable trades |
| **Composite Score** | Weighted combination for ranking |

---

## 🛡️ Risk Management

```
┌─────────────────────────────────────────────────────────────────┐
│                     RISK HIERARCHY                              │
├─────────────────────────────────────────────────────────────────┤
│  Level 1: KILL SWITCH                                          │
│           Extreme volatility / API failure → STOP EVERYTHING   │
├─────────────────────────────────────────────────────────────────┤
│  Level 2: DAILY LOSS CAP                                       │
│           Daily loss > X% → No more trades today               │
├─────────────────────────────────────────────────────────────────┤
│  Level 3: POSITION LIMITS                                      │
│           Single position > X% → Reduce size                   │
├─────────────────────────────────────────────────────────────────┤
│  Level 4: TRADE FREQUENCY                                      │
│           > N trades/day → Stop trading                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📸 Screenshots

### Dashboard
*Real-time monitoring with strategy leaderboard, portfolio value, and controls*

### Report Page
*Complete analysis with all strategy DNA, trades, and performance metrics*

---

## 🔗 Tech Stack

- **Backend:** Python 3.11+, FastAPI, asyncio
- **Market Data:** Angel One SmartAPI WebSocket V2
- **Database:** SQLite (async)
- **Frontend:** Vanilla HTML/CSS/JS (no framework bloat)
- **Deployment:** Render.com (FREE tier)

---

## ⚠️ Disclaimer

> This project is for **educational and research purposes only**.
> - No real money is traded
> - Past performance doesn't guarantee future results
> - Real arbitrage requires sub-millisecond execution
> - Actual trading involves fees, slippage, execution risk

---

## 📜 License

MIT License - Use freely for learning and research.

---

<div align="center">

**Built for learning - every decision explained, every trade documented.**

⭐ Star this repo if you find it useful!

Made with 🧬 by a quant enthusiast

</div>
