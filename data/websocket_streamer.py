"""
WebSocket Market Data Streamer (Angel One SmartAPI)
====================================================

🎓 WHAT IS THIS FILE?
This file handles real-time market data streaming from Angel One.
It connects to Angel One WebSocket and receives live price updates.

🎓 WHY WEBSOCKET INSTEAD OF REST?

REST API:
┌──────────┐  Request   ┌──────────┐
│  Client  │ ────────►  │  Server  │
│          │ ◄────────  │          │
└──────────┘  Response  └──────────┘
(Must ask every time, adds latency)

WebSocket:
┌──────────┐  Connect   ┌──────────┐
│  Client  │ ═════════  │  Server  │
│          │ ◄═════════ │          │
└──────────┘  Real-time └──────────┘
            (Server pushes instantly)

🎓 ANGEL ONE WEBSOCKET MODES:
- Mode 1 (LTP): Last Traded Price only (minimal, fast)
- Mode 2 (Quote): LTP + OHLC + Volume
- Mode 3 (Snap Quote): Full depth data

🎓 EXCHANGE TYPES:
- 1: NSE
- 2: NFO
- 3: BSE
- 5: MCX

🎓 MESSAGE FORMAT (from Angel One WebSocket V2):
Binary data that gets decoded to:
{
    "token": "3045",           # Instrument token
    "exchange_type": 1,        # 1=NSE, 3=BSE
    "ltp": 245050,            # LTP in paise (divide by 100)
    "open": 244500,
    "high": 246000,
    "low": 244000,
    "close": 245000,
    "volume": 1234567
}
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Callable
import asyncio
import json
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger
from data.angelone_auth import get_auth_client


# =========================================================
# DATA STRUCTURES
# =========================================================

@dataclass
class PriceTick:
    """
    A single price update from the market.
    
    🎓 This is the basic unit of market data.
    Every time a trade happens, we get a tick.
    """
    symbol: str
    exchange: str  # "NSE" or "BSE"
    ltp: float     # Last Traded Price
    timestamp: datetime
    volume: int = 0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    change: float = 0.0
    change_pct: float = 0.0
    
    def __post_init__(self):
        """Calculate derived fields."""
        if self.prev_close and self.prev_close > 0:
            self.change = self.ltp - self.prev_close
            self.change_pct = (self.change / self.prev_close) * 100


@dataclass
class SpreadData:
    """
    Price spread between NSE and BSE for a symbol.
    
    🎓 This is the core of arbitrage opportunity detection!
    
    Example:
    - RELIANCE on NSE: ₹2450.00
    - RELIANCE on BSE: ₹2451.50
    - Spread: ₹1.50 (BSE higher)
    - If spread > transaction costs → Arbitrage opportunity!
    """
    symbol: str
    nse_price: float
    bse_price: float
    timestamp: datetime
    nse_volume: int = 0
    bse_volume: int = 0
    
    @property
    def spread(self) -> float:
        """Absolute spread in rupees."""
        return abs(self.nse_price - self.bse_price)
    
    @property
    def spread_pct(self) -> float:
        """Spread as percentage of average price."""
        avg_price = (self.nse_price + self.bse_price) / 2
        if avg_price == 0:
            return 0
        return (self.spread / avg_price) * 100
    
    @property
    def direction(self) -> str:
        """Which exchange is higher."""
        if self.nse_price > self.bse_price:
            return "NSE_HIGH"
        elif self.bse_price > self.nse_price:
            return "BSE_HIGH"
        return "EQUAL"


# =========================================================
# ANGEL ONE WEBSOCKET STREAMER
# =========================================================

class MarketDataStreamer:
    """
    Real-time market data streamer using Angel One WebSocket V2.
    
    🎓 USAGE:
    streamer = MarketDataStreamer()
    
    # Add callbacks for price updates
    streamer.on_tick(my_price_handler)
    streamer.on_spread(my_spread_handler)
    
    # Connect and subscribe
    await streamer.connect()
    streamer.subscribe(["RELIANCE", "TCS", "INFY"])
    
    # When done
    await streamer.disconnect()
    """
    
    # Exchange type mappings for Angel One
    EXCHANGE_NSE = 1
    EXCHANGE_BSE = 3
    
    # Subscription modes
    MODE_LTP = 1
    MODE_QUOTE = 2
    MODE_SNAP_QUOTE = 3
    
    def __init__(self):
        self.auth = get_auth_client()
        
        # Callbacks
        self._tick_callbacks: List[Callable[[PriceTick], None]] = []
        self._spread_callbacks: List[Callable[[SpreadData], None]] = []
        
        # Price cache for spread calculation
        self._prices: Dict[str, Dict[str, PriceTick]] = {}  # {symbol: {exchange: tick}}
        
        # WebSocket client
        self._ws = None
        self._connected = False
        self._running = False
        
        # Instrument token mapping
        self._token_to_symbol: Dict[str, tuple] = {}  # {token: (symbol, exchange)}
        self._symbol_to_token: Dict[tuple, str] = {}  # {(symbol, exchange): token}
    
    def on_tick(self, callback: Callable[[PriceTick], None]):
        """
        Register callback for price tick updates.
        
        🎓 Your callback will be called every time a price updates.
        Keep it fast - don't do heavy processing in the callback!
        """
        self._tick_callbacks.append(callback)
    
    def on_spread(self, callback: Callable[[SpreadData], None]):
        """
        Register callback for spread updates.
        
        🎓 Called when we have prices from both exchanges for a symbol.
        """
        self._spread_callbacks.append(callback)
    
    async def connect(self):
        """
        Connect to Angel One WebSocket.
        
        🎓 This establishes the WebSocket connection and starts
        receiving market data.
        """
        logger.info("🔌 Connecting to Angel One WebSocket...")
        
        try:
            # First ensure we have a valid session
            await self.auth.get_access_token()
            
            # Get feed token
            feed_token = self.auth.get_feed_token()
            
            # Initialize WebSocket V2
            from SmartApi.smartWebSocketV2 import SmartWebSocketV2
            
            self._ws = SmartWebSocketV2(
                auth_token=self.auth._access_token,
                api_key=settings.ANGELONE_API_KEY,
                client_code=settings.ANGELONE_CLIENT_CODE,
                feed_token=feed_token
            )
            
            # Set up callbacks
            self._ws.on_open = self._on_ws_open
            self._ws.on_data = self._on_ws_data
            self._ws.on_error = self._on_ws_error
            self._ws.on_close = self._on_ws_close
            
            # Connect in background thread (SmartWebSocketV2 is blocking)
            self._running = True
            asyncio.get_event_loop().run_in_executor(None, self._ws.connect)
            
            logger.info("✅ WebSocket connection initiated")
            
        except ImportError:
            logger.error("❌ smartapi-python not installed")
            logger.info("🔧 Starting mock data streamer instead")
            self._start_mock_mode()
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            logger.info("🔧 Starting mock data streamer instead")
            self._start_mock_mode()
    
    async def disconnect(self):
        """Disconnect from WebSocket."""
        logger.info("🔌 Disconnecting from WebSocket...")
        self._running = False
        
        if self._ws:
            try:
                self._ws.close_connection()
            except:
                pass
        
        self._connected = False
        logger.info("✅ Disconnected")
    
    def subscribe(self, symbols: List[str]):
        """
        Subscribe to market data for given symbols.
        
        🎓 Args:
            symbols: List of stock symbols (e.g., ['RELIANCE', 'TCS'])
        
        The system will automatically subscribe to both NSE and BSE
        for each symbol to calculate spreads.
        """
        logger.info(f"📡 Subscribing to {len(symbols)} symbols...")
        
        if self._ws and self._connected:
            # Build token list for both exchanges
            token_list = []
            
            for symbol in symbols:
                # NSE subscription
                nse_token = self._get_token(symbol, "NSE")
                if nse_token:
                    token_list.append({
                        "exchangeType": self.EXCHANGE_NSE,
                        "tokens": [nse_token]
                    })
                    self._token_to_symbol[nse_token] = (symbol, "NSE")
                    self._symbol_to_token[(symbol, "NSE")] = nse_token
                
                # BSE subscription
                bse_token = self._get_token(symbol, "BSE")
                if bse_token:
                    token_list.append({
                        "exchangeType": self.EXCHANGE_BSE,
                        "tokens": [bse_token]
                    })
                    self._token_to_symbol[bse_token] = (symbol, "BSE")
                    self._symbol_to_token[(symbol, "BSE")] = bse_token
            
            if token_list:
                correlation_id = "quant_engine"
                self._ws.subscribe(correlation_id, self.MODE_QUOTE, token_list)
                logger.info(f"✅ Subscribed to {len(token_list)} token streams")
        else:
            logger.warning("WebSocket not connected, using mock data")
    
    def _get_token(self, symbol: str, exchange: str) -> Optional[str]:
        """Get instrument token for symbol on exchange."""
        # Use common large-cap tokens (you should load these from instruments API)
        token_map = {
            ("RELIANCE", "NSE"): "2885",
            ("RELIANCE", "BSE"): "500325",
            ("TCS", "NSE"): "11536",
            ("TCS", "BSE"): "532540",
            ("INFY", "NSE"): "1594",
            ("INFY", "BSE"): "500209",
            ("HDFCBANK", "NSE"): "1333",
            ("HDFCBANK", "BSE"): "500180",
            ("ICICIBANK", "NSE"): "4963",
            ("ICICIBANK", "BSE"): "532174",
            ("SBIN", "NSE"): "3045",
            ("SBIN", "BSE"): "500112",
            ("HINDUNILVR", "NSE"): "1394",
            ("HINDUNILVR", "BSE"): "500696",
            ("ITC", "NSE"): "1660",
            ("ITC", "BSE"): "500875",
            ("BHARTIARTL", "NSE"): "10604",
            ("BHARTIARTL", "BSE"): "532454",
            ("KOTAKBANK", "NSE"): "1922",
            ("KOTAKBANK", "BSE"): "500247",
        }
        return token_map.get((symbol.upper(), exchange.upper()))
    
    def _on_ws_open(self, wsapp):
        """WebSocket open callback."""
        logger.info("✅ WebSocket connected")
        self._connected = True
    
    def _on_ws_data(self, wsapp, message):
        """WebSocket data callback."""
        try:
            self._process_message(message)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def _on_ws_error(self, wsapp, error):
        """WebSocket error callback."""
        logger.error(f"WebSocket error: {error}")
    
    def _on_ws_close(self, wsapp):
        """WebSocket close callback."""
        logger.info("WebSocket closed")
        self._connected = False
    
    def _process_message(self, message: dict):
        """
        Process a WebSocket message.
        
        🎓 Angel One WebSocket V2 sends data in a specific format.
        We extract price data and create PriceTick objects.
        """
        if not message:
            return
        
        try:
            # Extract data from message
            token = str(message.get("token", ""))
            exchange_type = message.get("exchange_type", 1)
            
            # Look up symbol
            symbol_info = self._token_to_symbol.get(token)
            if not symbol_info:
                return
            
            symbol, exchange = symbol_info
            
            # Price values are in paise, convert to rupees
            ltp = message.get("ltp", 0) / 100.0
            open_price = message.get("open", 0) / 100.0
            high = message.get("high", 0) / 100.0
            low = message.get("low", 0) / 100.0
            close = message.get("close", 0) / 100.0
            volume = message.get("volume", 0)
            
            # Create tick
            tick = PriceTick(
                symbol=symbol,
                exchange=exchange,
                ltp=ltp,
                timestamp=datetime.now(),
                volume=volume,
                open=open_price,
                high=high,
                low=low,
                prev_close=close
            )
            
            # Store in cache
            if symbol not in self._prices:
                self._prices[symbol] = {}
            self._prices[symbol][exchange] = tick
            
            # Notify tick callbacks
            for callback in self._tick_callbacks:
                try:
                    callback(tick)
                except Exception as e:
                    logger.error(f"Tick callback error: {e}")
            
            # Check for spread
            self._check_spread(symbol)
            
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    def _check_spread(self, symbol: str):
        """Check if we have both NSE and BSE prices, then notify spread callbacks."""
        if symbol not in self._prices:
            return
        
        prices = self._prices[symbol]
        if "NSE" not in prices or "BSE" not in prices:
            return
        
        nse_tick = prices["NSE"]
        bse_tick = prices["BSE"]
        
        # Ensure prices are fresh (within 5 seconds)
        now = datetime.now()
        if (now - nse_tick.timestamp).seconds > 5 or (now - bse_tick.timestamp).seconds > 5:
            return
        
        # Create spread data
        spread = SpreadData(
            symbol=symbol,
            nse_price=nse_tick.ltp,
            bse_price=bse_tick.ltp,
            timestamp=now,
            nse_volume=nse_tick.volume,
            bse_volume=bse_tick.volume
        )
        
        # Notify callbacks
        for callback in self._spread_callbacks:
            try:
                callback(spread)
            except Exception as e:
                logger.error(f"Spread callback error: {e}")
    
    def get_latest_price(self, symbol: str, exchange: str) -> Optional[PriceTick]:
        """Get the latest price for a symbol on an exchange."""
        return self._prices.get(symbol, {}).get(exchange)
    
    def get_spread(self, symbol: str) -> Optional[SpreadData]:
        """Get current spread for a symbol."""
        if symbol not in self._prices:
            return None
        
        prices = self._prices[symbol]
        if "NSE" not in prices or "BSE" not in prices:
            return None
        
        return SpreadData(
            symbol=symbol,
            nse_price=prices["NSE"].ltp,
            bse_price=prices["BSE"].ltp,
            timestamp=datetime.now(),
            nse_volume=prices["NSE"].volume,
            bse_volume=prices["BSE"].volume
        )
    
    def _start_mock_mode(self):
        """Start mock data mode for testing."""
        logger.info("🔧 Starting MOCK data streamer")
        self._running = True
        asyncio.create_task(self._mock_data_loop())
    
    async def _mock_data_loop(self):
        """Generate mock market data for testing."""
        import random
        
        # Base prices for mock data
        base_prices = {
            "RELIANCE": 2450.0,
            "TCS": 3800.0,
            "INFY": 1550.0,
            "HDFCBANK": 1650.0,
            "ICICIBANK": 1050.0,
        }
        
        while self._running:
            for symbol, base_price in base_prices.items():
                # Generate slightly different prices for NSE and BSE
                nse_variation = random.uniform(-0.5, 0.5)
                bse_variation = random.uniform(-0.5, 0.5)
                
                # Add some spread
                spread_amount = random.uniform(0.1, 1.0)
                
                nse_price = base_price + nse_variation
                bse_price = base_price + bse_variation + spread_amount
                
                # Sometimes flip which is higher
                if random.random() > 0.5:
                    nse_price, bse_price = bse_price, nse_price
                
                now = datetime.now()
                
                # Create NSE tick
                nse_tick = PriceTick(
                    symbol=symbol,
                    exchange="NSE",
                    ltp=round(nse_price, 2),
                    timestamp=now,
                    volume=random.randint(10000, 100000),
                    prev_close=base_price
                )
                
                # Create BSE tick
                bse_tick = PriceTick(
                    symbol=symbol,
                    exchange="BSE",
                    ltp=round(bse_price, 2),
                    timestamp=now,
                    volume=random.randint(5000, 50000),
                    prev_close=base_price
                )
                
                # Store in cache
                if symbol not in self._prices:
                    self._prices[symbol] = {}
                self._prices[symbol]["NSE"] = nse_tick
                self._prices[symbol]["BSE"] = bse_tick
                
                # Notify callbacks
                for callback in self._tick_callbacks:
                    try:
                        callback(nse_tick)
                        callback(bse_tick)
                    except Exception as e:
                        logger.error(f"Mock tick callback error: {e}")
                
                # Create and notify spread
                spread = SpreadData(
                    symbol=symbol,
                    nse_price=nse_tick.ltp,
                    bse_price=bse_tick.ltp,
                    timestamp=now,
                    nse_volume=nse_tick.volume,
                    bse_volume=bse_tick.volume
                )
                
                for callback in self._spread_callbacks:
                    try:
                        callback(spread)
                    except Exception as e:
                        logger.error(f"Mock spread callback error: {e}")
            
            # Sleep before next update
            await asyncio.sleep(1)


# =========================================================
# MOCK STREAMER FOR TESTING
# =========================================================

class MockMarketDataStreamer(MarketDataStreamer):
    """
    Mock market data streamer for testing without real API.
    
    🎓 Generates realistic-looking fake market data
    for testing the strategy logic.
    """
    
    def __init__(self):
        super().__init__()
        logger.info("🔧 Using MOCK market data streamer")
    
    async def connect(self):
        """Start mock data generation."""
        logger.info("🔌 Starting mock data stream...")
        self._running = True
        await self._mock_data_loop()
    
    async def disconnect(self):
        """Stop mock data generation."""
        self._running = False
        logger.info("✅ Mock data stream stopped")
    
    def subscribe(self, symbols: List[str]):
        """Mock subscription (no-op, generates all data anyway)."""
        logger.info(f"📡 Mock subscribed to {len(symbols)} symbols")


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_streamer: Optional[MarketDataStreamer] = None


def get_market_streamer() -> MarketDataStreamer:
    """Get or create the singleton market data streamer."""
    global _streamer
    
    if _streamer is None:
        # Check if we have real credentials
        if not settings.ANGELONE_API_KEY or settings.ANGELONE_API_KEY == "your_api_key_here":
            _streamer = MockMarketDataStreamer()
        else:
            _streamer = MarketDataStreamer()
    
    return _streamer


# =========================================================
# MAIN - Test streamer
# =========================================================

if __name__ == "__main__":
    async def main():
        print("🔧 Testing market data streamer...")
        print()
        
        streamer = get_market_streamer()
        
        # Add test callbacks
        def on_tick(tick: PriceTick):
            print(f"📊 {tick.symbol} {tick.exchange}: ₹{tick.ltp:.2f}")
        
        def on_spread(spread: SpreadData):
            print(f"📈 {spread.symbol} Spread: ₹{spread.spread:.2f} ({spread.spread_pct:.3f}%) - {spread.direction}")
        
        streamer.on_tick(on_tick)
        streamer.on_spread(on_spread)
        
        # Connect
        await streamer.connect()
        
        # Subscribe to symbols
        streamer.subscribe(settings.symbol_list)
        
        # Run for 30 seconds
        print("\n⏳ Running for 30 seconds...\n")
        await asyncio.sleep(30)
        
        # Disconnect
        await streamer.disconnect()
        print("\n✅ Test complete!")
    
    asyncio.run(main())
