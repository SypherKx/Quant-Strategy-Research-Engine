"""
Instrument Discovery Module
===========================

🎓 WHAT IS THIS FILE?
This file handles mapping between stock symbols and exchange-specific
identifiers (instrument keys, ISINs, tokens).

🎓 WHY IS THIS NEEDED?

Stock exchanges don't just use "RELIANCE" as identifier.
They use complex codes:
- NSE: Instrument Token (numeric ID)
- BSE: Scrip Code (numeric)
- Both: ISIN (International Securities ID)

Example for RELIANCE:
┌──────────┬─────────────────┬─────────────────────┐
│ Exchange │ Identifier      │ Example             │
├──────────┼─────────────────┼─────────────────────┤
│ Symbol   │ Trading Symbol  │ RELIANCE            │
│ ISIN     │ Unique ID       │ INE002A01018        │
│ NSE      │ Instrument Key  │ NSE_EQ|INE002A01018 │
│ BSE      │ Instrument Key  │ BSE_EQ|INE002A01018 │
│ BSE      │ Scrip Code      │ 500325              │
└──────────┴─────────────────┴─────────────────────┘

🎓 ISIN EXPLAINED:
ISIN = International Securities Identification Number
- Globally unique identifier for securities
- Format: 2-letter country + 9 alphanumeric + 1 check digit
- India: Starts with "IN"
- Example: INE002A01018 (Reliance Industries)

We use ISIN as the primary identifier because:
1. Same across NSE and BSE
2. Never changes (unlike trading symbols)
3. Required for regulatory compliance
"""

import httpx
import json
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
import asyncio
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger
from data.upstox_auth import get_auth_client


# Cache file for instruments (refreshed daily)
CACHE_FILE = Path(__file__).parent.parent / ".instruments_cache.json"


@dataclass
class Instrument:
    """
    Represents a tradeable instrument.
    
    🎓 Contains all identifiers needed to:
    - Subscribe to market data
    - Place orders
    - Track positions
    """
    symbol: str           # Trading symbol (RELIANCE)
    name: str            # Full name (Reliance Industries Limited)
    isin: str            # ISIN (INE002A01018)
    exchange: str        # NSE or BSE
    instrument_key: str  # For WebSocket subscription
    token: str           # Exchange token
    lot_size: int = 1    # Minimum trade quantity
    tick_size: float = 0.05  # Minimum price movement
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "isin": self.isin,
            "exchange": self.exchange,
            "instrument_key": self.instrument_key,
            "token": self.token,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Instrument':
        return cls(**data)


class InstrumentManager:
    """
    Manages instrument discovery and caching.
    
    🎓 USAGE:
    manager = InstrumentManager()
    await manager.initialize()
    
    # Get instrument for a symbol
    reliance_nse = manager.get("RELIANCE", "NSE")
    reliance_bse = manager.get("RELIANCE", "BSE")
    
    # Get instrument keys for WebSocket
    keys = manager.get_instrument_keys(["RELIANCE", "TCS"])
    """
    
    # Upstox instruments API
    INSTRUMENTS_URL = "https://api.upstox.com/v2/instruments"
    
    def __init__(self):
        self.auth = get_auth_client()
        
        # Instruments indexed by (symbol, exchange)
        self._instruments: Dict[tuple, Instrument] = {}
        
        # ISIN to instruments mapping
        self._by_isin: Dict[str, Dict[str, Instrument]] = {}
        
        self._initialized = False
    
    async def initialize(self):
        """
        Initialize by loading or fetching instruments.
        
        🎓 Tries to load from cache first.
        If cache is stale (>1 day), fetches fresh data.
        """
        if self._initialized:
            return
        
        # Try loading from cache
        if self._load_cache():
            self._initialized = True
            logger.info(f"✅ Loaded {len(self._instruments)} instruments from cache")
            return
        
        # Fetch fresh data
        await self._fetch_instruments()
        self._initialized = True
    
    def get(self, symbol: str, exchange: str) -> Optional[Instrument]:
        """Get instrument by symbol and exchange."""
        return self._instruments.get((symbol.upper(), exchange.upper()))
    
    def get_by_isin(self, isin: str) -> Dict[str, Instrument]:
        """Get all instruments for an ISIN (both NSE and BSE)."""
        return self._by_isin.get(isin.upper(), {})
    
    def get_instrument_keys(self, symbols: List[str]) -> List[str]:
        """
        Get instrument keys for WebSocket subscription.
        
        🎓 Returns keys for both NSE and BSE for each symbol.
        """
        keys = []
        for symbol in symbols:
            for exchange in ["NSE", "BSE"]:
                instrument = self.get(symbol, exchange)
                if instrument:
                    keys.append(instrument.instrument_key)
        return keys
    
    def get_all_symbols(self) -> List[str]:
        """Get list of all known symbols."""
        symbols = set()
        for (symbol, _) in self._instruments.keys():
            symbols.add(symbol)
        return sorted(symbols)
    
    async def _fetch_instruments(self):
        """
        Fetch instruments from Upstox API.
        
        🎓 This downloads the full instrument list from Upstox.
        Takes a few seconds but only done once per day.
        """
        logger.info("📥 Fetching instruments from Upstox...")
        
        try:
            # For equity, we need NSE and BSE segments
            for segment in ["NSE_EQ", "BSE_EQ"]:
                await self._fetch_segment(segment)
            
            # Save to cache
            self._save_cache()
            
            logger.info(f"✅ Fetched {len(self._instruments)} instruments")
            
        except Exception as e:
            logger.error(f"Failed to fetch instruments: {e}")
            # Fall back to hardcoded common instruments
            self._load_fallback()
    
    async def _fetch_segment(self, segment: str):
        """Fetch instruments for a specific segment."""
        try:
            token = await self.auth.get_access_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.INSTRUMENTS_URL,
                    params={"instrument_type": segment},
                    headers=self.auth.get_api_headers(),
                    timeout=30
                )
                
                if response.status_code != 200:
                    logger.warning(f"Failed to fetch {segment}: {response.status_code}")
                    return
                
                data = response.json()
                
                for item in data.get("data", []):
                    instrument = Instrument(
                        symbol=item.get("trading_symbol", ""),
                        name=item.get("name", ""),
                        isin=item.get("isin", ""),
                        exchange="NSE" if "NSE" in segment else "BSE",
                        instrument_key=item.get("instrument_key", ""),
                        token=item.get("instrument_token", ""),
                        lot_size=item.get("lot_size", 1),
                        tick_size=item.get("tick_size", 0.05)
                    )
                    
                    key = (instrument.symbol, instrument.exchange)
                    self._instruments[key] = instrument
                    
                    if instrument.isin:
                        if instrument.isin not in self._by_isin:
                            self._by_isin[instrument.isin] = {}
                        self._by_isin[instrument.isin][instrument.exchange] = instrument
                        
        except Exception as e:
            logger.error(f"Error fetching segment {segment}: {e}")
    
    def _load_fallback(self):
        """
        Load hardcoded fallback instruments.
        
        🎓 Used when API is unavailable.
        Contains common large-cap stocks.
        """
        logger.warning("Using fallback instrument list")
        
        fallback_data = [
            ("RELIANCE", "Reliance Industries", "INE002A01018"),
            ("TCS", "Tata Consultancy Services", "INE467B01029"),
            ("INFY", "Infosys Limited", "INE009A01021"),
            ("HDFCBANK", "HDFC Bank Limited", "INE040A01034"),
            ("ICICIBANK", "ICICI Bank Limited", "INE090A01021"),
            ("HINDUNILVR", "Hindustan Unilever", "INE030A01027"),
            ("ITC", "ITC Limited", "INE154A01025"),
            ("SBIN", "State Bank of India", "INE062A01020"),
            ("BHARTIARTL", "Bharti Airtel", "INE397D01024"),
            ("KOTAKBANK", "Kotak Mahindra Bank", "INE237A01028"),
        ]
        
        for symbol, name, isin in fallback_data:
            for exchange in ["NSE", "BSE"]:
                instrument = Instrument(
                    symbol=symbol,
                    name=name,
                    isin=isin,
                    exchange=exchange,
                    instrument_key=f"{exchange}_EQ|{isin}",
                    token=f"{exchange}_{symbol}",
                )
                
                key = (symbol, exchange)
                self._instruments[key] = instrument
                
                if isin not in self._by_isin:
                    self._by_isin[isin] = {}
                self._by_isin[isin][exchange] = instrument
    
    def _save_cache(self):
        """Save instruments to cache file."""
        cache_data = {
            "date": date.today().isoformat(),
            "instruments": [inst.to_dict() for inst in self._instruments.values()]
        }
        CACHE_FILE.write_text(json.dumps(cache_data, indent=2))
        logger.debug(f"Saved {len(self._instruments)} instruments to cache")
    
    def _load_cache(self) -> bool:
        """
        Load instruments from cache.
        
        Returns True if cache is valid and loaded.
        """
        if not CACHE_FILE.exists():
            return False
        
        try:
            cache_data = json.loads(CACHE_FILE.read_text())
            cache_date = date.fromisoformat(cache_data["date"])
            
            # Cache valid for 1 day
            if (date.today() - cache_date).days > 1:
                logger.info("Cache is stale, will refresh")
                return False
            
            for item in cache_data["instruments"]:
                instrument = Instrument.from_dict(item)
                key = (instrument.symbol, instrument.exchange)
                self._instruments[key] = instrument
                
                if instrument.isin:
                    if instrument.isin not in self._by_isin:
                        self._by_isin[instrument.isin] = {}
                    self._by_isin[instrument.isin][instrument.exchange] = instrument
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return False


# =========================================================
# SINGLETON INSTANCE
# =========================================================

_instrument_manager: Optional[InstrumentManager] = None


async def get_instrument_manager() -> InstrumentManager:
    """Get or create the singleton instrument manager."""
    global _instrument_manager
    
    if _instrument_manager is None:
        _instrument_manager = InstrumentManager()
        await _instrument_manager.initialize()
    
    return _instrument_manager


# =========================================================
# MAIN - Test instruments
# =========================================================

if __name__ == "__main__":
    async def main():
        print("🔧 Testing instrument manager...")
        print()
        
        manager = await get_instrument_manager()
        
        # Test getting instruments
        for symbol in settings.symbol_list[:3]:
            print(f"\n📊 {symbol}:")
            for exchange in ["NSE", "BSE"]:
                inst = manager.get(symbol, exchange)
                if inst:
                    print(f"   {exchange}: {inst.instrument_key}")
                    print(f"         ISIN: {inst.isin}")
                else:
                    print(f"   {exchange}: Not found")
        
        # Get instrument keys for subscription
        print("\n🔑 Instrument Keys for WebSocket:")
        keys = manager.get_instrument_keys(settings.symbol_list[:3])
        for key in keys:
            print(f"   {key}")
    
    asyncio.run(main())
