"""
WebSocket Market Data Streamer
==============================

🎓 WHAT IS THIS FILE?
This file handles real-time market data streaming from Upstox.
It connects to Upstox WebSocket and receives live price updates.

🎓 WHY WEBSOCKET INSTEAD OF REST?

REST API (old way):
┌────────────┐      ┌────────────┐
│ Your App   │ ───► │ Upstox API │  Request
│            │ ◄─── │            │  Response
└────────────┘      └────────────┘
(Repeat every second... wasteful!)

WebSocket (modern way):
┌────────────┐      ┌────────────┐
│ Your App   │ ═════│ Upstox WS  │  Persistent connection
│            │ ◄════│ Server     │  Data pushed instantly
└────────────┘      └────────────┘
(One connection, infinite updates!)

🎓 WEBSOCKET BENEFITS:
1. SPEED: Data arrives in milliseconds, not seconds
2. EFFICIENCY: No repeated request overhead
3. REAL-TIME: Get every tick as it happens
4. LESS LOAD: Upstox doesn't rate-limit WebSocket

🎓 DATA MODES:
- ltpc: Last Traded Price + Change (minimal, fast)
- full: Full depth, OHLC, volume (detailed, more data)

We use 'full' mode to get complete market picture.

🎓 MESSAGE FORMAT (from Upstox):
{
    "feeds": {
        "NSE_EQ|INE002A01018": {  // RELIANCE NSE
            "ff": {  // Full Feed
                "ltpc": {
                    "ltp": 2450.50,      // Last traded price
                    "ltt": "1702809045", // Last trade time (unix)
                    "cp": 2445.00        // Previous close
                },
                "marketOHLC": {
                    "ohlc": [{"open": 2448, "high": 2455, "low": 2440, "close": 2450}]
                }
            }
        }
    }
}
"""

import asyncio
import json
import websockets
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger
from data.upstox_auth import get_auth_client


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
    exchange: str           # 'NSE' or 'BSE'
    ltp: float             # Last Traded Price
    timestamp: datetime
    volume: int = 0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    prev_close: float = 0.0
    change: float = 0.0    # LTP - Prev Close
    change_pct: float = 0.0  # Change as percentage
    
    def __post_init__(self):
        """Calculate derived fields."""
        if self.prev_close > 0:
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
    - Spread: ₹1.50 (0.06%)
    
    If spread is large enough to cover transaction costs,
    it's a potential trading opportunity!
    """
    symbol: str
    nse_price: float
    bse_price: float
    timestamp: datetime
    
    @property
    def spread(self) -> float:
        """Absolute spread in rupees."""
        return abs(self.nse_price - self.bse_price)
    
    @property
    def spread_pct(self) -> float:
        """Spread as percentage of average price."""
        avg_price = (self.nse_price + self.bse_price) / 2
        if avg_price > 0:
            return (self.spread / avg_price) * 100
        return 0.0
    
    @property
    def direction(self) -> str:
        """Which exchange is higher."""
        if self.nse_price > self.bse_price:
            return "NSE>BSE"
        elif self.bse_price > self.nse_price:
            return "BSE>NSE"
        return "EQUAL"


# =========================================================
# WEBSOCKET STREAMER
# =========================================================

class MarketDataStreamer:
    """
    Real-time market data streamer using Upstox WebSocket.
    
    🎓 USAGE:
    streamer = MarketDataStreamer()
    
    # Add callbacks for price updates
    streamer.on_tick(my_price_handler)
    streamer.on_spread(my_spread_handler)
    
    # Start streaming
    await streamer.connect()
    await streamer.subscribe(['RELIANCE', 'TCS'])
    
    # Stop streaming
    await streamer.disconnect()
    """
    
    # Upstox WebSocket endpoint
    WS_URL = "wss://api.upstox.com/v2/feed/market-data-feed"
    
    def __init__(self):
        self.auth = get_auth_client()
        self._websocket = None
        self._is_connected = False
        self._subscribed_symbols: List[str] = []
        
        # Latest prices for each symbol+exchange
        self._latest_prices: Dict[str, Dict[str, PriceTick]] = defaultdict(dict)
        
        # Callbacks
        self._tick_callbacks: List[Callable[[PriceTick], None]] = []
        self._spread_callbacks: List[Callable[[SpreadData], None]] = []
        
        # Receive task
        self._receive_task: Optional[asyncio.Task] = None
    
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
        Connect to Upstox WebSocket.
        
        🎓 This establishes the WebSocket connection and starts
        receiving market data.
        """
        if self._is_connected:
            logger.warning("Already connected to WebSocket")
            return
        
        try:
            token = await self.auth.get_access_token()
            
            # Connect with auth header
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json"
            }
            
            self._websocket = await websockets.connect(
                self.WS_URL,
                extra_headers=headers,
                ping_interval=30,
                ping_timeout=10
            )
            
            self._is_connected = True
            logger.info("✅ Connected to Upstox WebSocket")
            
            # Start receive loop
            self._receive_task = asyncio.create_task(self._receive_loop())
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from WebSocket."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        
        self._is_connected = False
        logger.info("Disconnected from WebSocket")
    
    async def subscribe(self, symbols: List[str]):
        """
        Subscribe to market data for given symbols.
        
        🎓 Args:
            symbols: List of stock symbols (e.g., ['RELIANCE', 'TCS'])
        
        The system will automatically subscribe to both NSE and BSE
        for each symbol to calculate spreads.
        """
        if not self._is_connected:
            raise RuntimeError("Not connected. Call connect() first.")
        
        # Build instrument keys for both exchanges
        # Format: NSE_EQ|ISIN or NSE_EQ|SYMBOL
        instrument_keys = []
        for symbol in symbols:
            # We need instrument tokens from instruments module
            # For now, use symbol directly
            instrument_keys.append(f"NSE_EQ|{symbol}")
            instrument_keys.append(f"BSE_EQ|{symbol}")
        
        # Subscribe message
        subscribe_msg = {
            "guid": "subscribe_1",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": instrument_keys
            }
        }
        
        await self._websocket.send(json.dumps(subscribe_msg))
        self._subscribed_symbols.extend(symbols)
        
        logger.info(f"Subscribed to {len(symbols)} symbols: {symbols}")
    
    async def _receive_loop(self):
        """
        Main loop that receives and processes messages.
        
        🎓 This runs continuously in the background,
        processing every message from WebSocket.
        """
        try:
            async for message in self._websocket:
                await self._process_message(message)
        except websockets.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self._is_connected = False
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            self._is_connected = False
    
    async def _process_message(self, message: str):
        """
        Process a WebSocket message.
        
        🎓 Messages are JSON with nested structure.
        We extract price data and create PriceTick objects.
        """
        try:
            data = json.loads(message)
            
            # Check if it's a feed message
            if "feeds" not in data:
                return
            
            feeds = data["feeds"]
            
            for instrument_key, feed_data in feeds.items():
                # Parse instrument key (e.g., "NSE_EQ|INE002A01018")
                parts = instrument_key.split("|")
                if len(parts) != 2:
                    continue
                
                exchange_segment = parts[0]  # "NSE_EQ" or "BSE_EQ"
                identifier = parts[1]  # ISIN or symbol
                
                # Determine exchange
                if "NSE" in exchange_segment:
                    exchange = "NSE"
                elif "BSE" in exchange_segment:
                    exchange = "BSE"
                else:
                    continue
                
                # Extract price data
                ff = feed_data.get("ff", {})
                ltpc = ff.get("ltpc", {})
                ohlc_data = ff.get("marketOHLC", {}).get("ohlc", [{}])[0] if ff.get("marketOHLC") else {}
                
                if not ltpc.get("ltp"):
                    continue
                
                # Create PriceTick
                tick = PriceTick(
                    symbol=identifier,  # Will need to map to symbol
                    exchange=exchange,
                    ltp=float(ltpc.get("ltp", 0)),
                    timestamp=datetime.now(),
                    prev_close=float(ltpc.get("cp", 0)),
                    open=float(ohlc_data.get("open", 0)),
                    high=float(ohlc_data.get("high", 0)),
                    low=float(ohlc_data.get("low", 0)),
                    volume=int(ff.get("marketLevel", {}).get("tbq", 0))
                )
                
                # Store latest price
                self._latest_prices[tick.symbol][tick.exchange] = tick
                
                # Notify tick callbacks
                for callback in self._tick_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(tick)
                        else:
                            callback(tick)
                    except Exception as e:
                        logger.error(f"Error in tick callback: {e}")
                
                # Check if we have both NSE and BSE prices for spread
                symbol_prices = self._latest_prices[tick.symbol]
                if "NSE" in symbol_prices and "BSE" in symbol_prices:
                    nse_tick = symbol_prices["NSE"]
                    bse_tick = symbol_prices["BSE"]
                    
                    # Only calculate if both are recent (within 5 seconds)
                    if abs((nse_tick.timestamp - bse_tick.timestamp).total_seconds()) < 5:
                        spread = SpreadData(
                            symbol=tick.symbol,
                            nse_price=nse_tick.ltp,
                            bse_price=bse_tick.ltp,
                            timestamp=datetime.now()
                        )
                        
                        # Notify spread callbacks
                        for callback in self._spread_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(spread)
                                else:
                                    callback(spread)
                            except Exception as e:
                                logger.error(f"Error in spread callback: {e}")
        
        except json.JSONDecodeError:
            logger.warning("Received non-JSON message")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    def get_latest_price(self, symbol: str, exchange: str) -> Optional[PriceTick]:
        """Get the latest price for a symbol on an exchange."""
        return self._latest_prices.get(symbol, {}).get(exchange)
    
    def get_spread(self, symbol: str) -> Optional[SpreadData]:
        """Get current spread for a symbol."""
        prices = self._latest_prices.get(symbol, {})
        if "NSE" in prices and "BSE" in prices:
            return SpreadData(
                symbol=symbol,
                nse_price=prices["NSE"].ltp,
                bse_price=prices["BSE"].ltp,
                timestamp=datetime.now()
            )
        return None


# =========================================================
# MOCK STREAMER FOR TESTING
# =========================================================

class MockMarketDataStreamer:
    """
    Mock streamer that generates fake market data.
    
    🎓 WHY MOCK?
    - Testing without real API connection
    - Development when markets are closed
    - Unit testing strategies
    """
    
    def __init__(self):
        self._is_connected = False
        self._tick_callbacks = []
        self._spread_callbacks = []
        self._generate_task = None
        self._latest_prices = defaultdict(dict)
        
        logger.info("🔧 Using MOCK market data streamer")
    
    def on_tick(self, callback):
        self._tick_callbacks.append(callback)
    
    def on_spread(self, callback):
        self._spread_callbacks.append(callback)
    
    async def connect(self):
        self._is_connected = True
        self._generate_task = asyncio.create_task(self._generate_loop())
        logger.info("✅ Mock streamer connected")
    
    async def disconnect(self):
        if self._generate_task:
            self._generate_task.cancel()
        self._is_connected = False
        logger.info("Mock streamer disconnected")
    
    async def subscribe(self, symbols: List[str]):
        self._symbols = symbols
        logger.info(f"Mock subscribed to: {symbols}")
    
    async def _generate_loop(self):
        """Generate fake price data."""
        import random
        
        # Base prices for mock symbols
        base_prices = {
            "RELIANCE": 2450.0,
            "TCS": 3800.0,
            "INFY": 1500.0,
            "HDFCBANK": 1650.0,
            "ICICIBANK": 1050.0,
        }
        
        while self._is_connected:
            try:
                for symbol in getattr(self, '_symbols', settings.symbol_list):
                    base = base_prices.get(symbol, 1000.0)
                    
                    for exchange in ["NSE", "BSE"]:
                        # Random price movement
                        noise = random.gauss(0, base * 0.001)  # 0.1% std dev
                        
                        # BSE slightly different from NSE
                        if exchange == "BSE":
                            noise += random.gauss(0, base * 0.0005)
                        
                        price = base + noise
                        
                        tick = PriceTick(
                            symbol=symbol,
                            exchange=exchange,
                            ltp=round(price, 2),
                            timestamp=datetime.now(),
                            prev_close=base,
                            volume=random.randint(1000, 10000)
                        )
                        
                        self._latest_prices[symbol][exchange] = tick
                        
                        for callback in self._tick_callbacks:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(tick)
                            else:
                                callback(tick)
                    
                    # Generate spread
                    nse = self._latest_prices[symbol]["NSE"]
                    bse = self._latest_prices[symbol]["BSE"]
                    
                    spread = SpreadData(
                        symbol=symbol,
                        nse_price=nse.ltp,
                        bse_price=bse.ltp,
                        timestamp=datetime.now()
                    )
                    
                    for callback in self._spread_callbacks:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(spread)
                        else:
                            callback(spread)
                
                await asyncio.sleep(1)  # Update every second
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in mock generator: {e}")
                await asyncio.sleep(1)
    
    def get_latest_price(self, symbol: str, exchange: str) -> Optional[PriceTick]:
        return self._latest_prices.get(symbol, {}).get(exchange)
    
    def get_spread(self, symbol: str) -> Optional[SpreadData]:
        prices = self._latest_prices.get(symbol, {})
        if "NSE" in prices and "BSE" in prices:
            return SpreadData(
                symbol=symbol,
                nse_price=prices["NSE"].ltp,
                bse_price=prices["BSE"].ltp,
                timestamp=datetime.now()
            )
        return None


def get_streamer(use_mock: bool = False) -> MarketDataStreamer:
    """
    Factory function to get appropriate streamer.
    
    🎓 Returns MockMarketDataStreamer if:
    - use_mock=True
    - Credentials not configured
    """
    if use_mock or not settings.UPSTOX_API_KEY or settings.UPSTOX_API_KEY == "your_api_key_here":
        return MockMarketDataStreamer()
    return MarketDataStreamer()


# =========================================================
# MAIN - Test streaming
# =========================================================

if __name__ == "__main__":
    async def main():
        print("🔧 Testing market data streamer...")
        print()
        
        # Use mock for testing
        streamer = get_streamer(use_mock=True)
        
        # Track ticks received
        tick_count = 0
        
        def on_tick(tick: PriceTick):
            nonlocal tick_count
            tick_count += 1
            print(f"📊 {tick.exchange:3} {tick.symbol:10} ₹{tick.ltp:,.2f} ({tick.change_pct:+.2f}%)")
        
        def on_spread(spread: SpreadData):
            print(f"   ↔️  Spread: ₹{spread.spread:.2f} ({spread.spread_pct:.4f}%) [{spread.direction}]")
        
        streamer.on_tick(on_tick)
        streamer.on_spread(on_spread)
        
        await streamer.connect()
        await streamer.subscribe(['RELIANCE', 'TCS'])
        
        # Run for 10 seconds
        print("\n⏳ Streaming for 10 seconds...\n")
        await asyncio.sleep(10)
        
        await streamer.disconnect()
        print(f"\n✅ Received {tick_count} ticks")
    
    asyncio.run(main())
