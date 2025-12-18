"""
Instrument Discovery Module (Angel One SmartAPI)
=================================================

🎓 WHAT IS THIS FILE?
This file handles mapping between stock symbols and exchange-specific
identifiers (instrument tokens).

🎓 WHY IS THIS NEEDED?

Stock exchanges don't just use "RELIANCE" as identifier.
They use token codes:
- NSE: Numeric token (e.g., 2885 for RELIANCE)
- BSE: Scrip code (e.g., 500325 for RELIANCE)

Example for RELIANCE:
┌──────────┬─────────────────┬─────────────────────┐
│ Exchange │ Identifier      │ Example             │
├──────────┼─────────────────┼─────────────────────┤
│ Symbol   │ Trading Symbol  │ RELIANCE-EQ         │
│ NSE      │ Token           │ 2885                │
│ BSE      │ Scrip Code      │ 500325              │
│ ISIN     │ Unique ID       │ INE002A01018        │
└──────────┴─────────────────┴─────────────────────┘

🎓 ANGEL ONE TOKEN FORMAT:
For WebSocket subscription:
- exchangeType: 1 (NSE), 3 (BSE)
- token: Numeric token as string

For REST API:
- exchange: "NSE" or "BSE"
- symboltoken: Numeric token as string
- tradingsymbol: "RELIANCE-EQ"
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
from data.angelone_auth import get_auth_client


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
    token: str           # Exchange token (2885 for NSE, 500325 for BSE)
    trading_symbol: str  # Full trading symbol (RELIANCE-EQ)
    lot_size: int = 1    # Minimum trade quantity
    tick_size: float = 0.05  # Minimum price movement
    instrument_type: str = "EQ"  # EQ, FUT, OPT, etc.
    
    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "isin": self.isin,
            "exchange": self.exchange,
            "token": self.token,
            "trading_symbol": self.trading_symbol,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size,
            "instrument_type": self.instrument_type
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
    
    # Get tokens for WebSocket subscription
    tokens = manager.get_tokens(["RELIANCE", "TCS"])
    """
    
    def __init__(self):
        self.auth = get_auth_client()
        
        # Instruments indexed by (symbol, exchange)
        self._instruments: Dict[tuple, Instrument] = {}
        
        # Token to instrument mapping
        self._by_token: Dict[str, Dict[str, Instrument]] = {}  # {token: {exchange: instrument}}
        
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
        
        # Fetch fresh data or use fallback
        await self._fetch_instruments()
        self._initialized = True
    
    def get(self, symbol: str, exchange: str) -> Optional[Instrument]:
        """Get instrument by symbol and exchange."""
        return self._instruments.get((symbol.upper(), exchange.upper()))
    
    def get_by_token(self, token: str, exchange: str) -> Optional[Instrument]:
        """Get instrument by token."""
        return self._by_token.get(token, {}).get(exchange.upper())
    
    def get_tokens(self, symbols: List[str]) -> Dict[str, Dict[str, str]]:
        """
        Get tokens for WebSocket subscription.
        
        🎓 Returns dict like:
        {
            "RELIANCE": {"NSE": "2885", "BSE": "500325"},
            "TCS": {"NSE": "11536", "BSE": "532540"}
        }
        """
        result = {}
        for symbol in symbols:
            result[symbol] = {}
            for exchange in ["NSE", "BSE"]:
                instrument = self.get(symbol, exchange)
                if instrument:
                    result[symbol][exchange] = instrument.token
        return result
    
    def get_subscription_list(self, symbols: List[str]) -> List[dict]:
        """
        Get token list formatted for Angel One WebSocket subscription.
        
        🎓 Returns list like:
        [
            {"exchangeType": 1, "tokens": ["2885", "11536"]},  # NSE
            {"exchangeType": 3, "tokens": ["500325", "532540"]}  # BSE
        ]
        """
        nse_tokens = []
        bse_tokens = []
        
        for symbol in symbols:
            nse_inst = self.get(symbol, "NSE")
            bse_inst = self.get(symbol, "BSE")
            
            if nse_inst:
                nse_tokens.append(nse_inst.token)
            if bse_inst:
                bse_tokens.append(bse_inst.token)
        
        result = []
        if nse_tokens:
            result.append({"exchangeType": 1, "tokens": nse_tokens})
        if bse_tokens:
            result.append({"exchangeType": 3, "tokens": bse_tokens})
        
        return result
    
    def get_all_symbols(self) -> List[str]:
        """Get list of all known symbols."""
        symbols = set()
        for (symbol, _) in self._instruments.keys():
            symbols.add(symbol)
        return sorted(symbols)
    
    async def _fetch_instruments(self):
        """
        Fetch instruments from Angel One API.
        
        🎓 Angel One provides instrument master files.
        For simplicity, we use a fallback list of common stocks.
        """
        logger.info("📥 Loading instruments...")
        
        try:
            # Try to get from API if authenticated
            smart_api = self.auth.get_smart_api()
            if smart_api:
                # Angel One has searchScrip API
                for symbol in settings.symbol_list:
                    try:
                        response = smart_api.searchScrip(exchange="NSE", searchscrip=symbol)
                        if response.get('status') and response.get('data'):
                            for item in response['data']:
                                instrument = Instrument(
                                    symbol=symbol,
                                    name=item.get('tradingsymbol', ''),
                                    isin='',
                                    exchange='NSE',
                                    token=item.get('symboltoken', ''),
                                    trading_symbol=item.get('tradingsymbol', ''),
                                )
                                key = (symbol, 'NSE')
                                self._instruments[key] = instrument
                    except Exception as e:
                        logger.debug(f"Could not fetch {symbol}: {e}")
                
                self._save_cache()
                logger.info(f"✅ Fetched {len(self._instruments)} instruments from API")
                
        except Exception as e:
            logger.warning(f"Failed to fetch instruments: {e}")
        
        # Always ensure fallback is loaded
        if len(self._instruments) < len(settings.symbol_list):
            self._load_fallback()
    
    def _load_fallback(self):
        """
        Load hardcoded fallback instruments.
        
        🎓 Used when API is unavailable.
        Contains common large-cap stocks with their tokens.
        """
        logger.info("Using fallback instrument list")
        
        # Common large-cap stocks with their NSE and BSE tokens
        fallback_data = [
            ("RELIANCE", "Reliance Industries", "INE002A01018", "2885", "500325"),
            ("TCS", "Tata Consultancy Services", "INE467B01029", "11536", "532540"),
            ("INFY", "Infosys Limited", "INE009A01021", "1594", "500209"),
            ("HDFCBANK", "HDFC Bank Limited", "INE040A01034", "1333", "500180"),
            ("ICICIBANK", "ICICI Bank Limited", "INE090A01021", "4963", "532174"),
            ("HINDUNILVR", "Hindustan Unilever", "INE030A01027", "1394", "500696"),
            ("ITC", "ITC Limited", "INE154A01025", "1660", "500875"),
            ("SBIN", "State Bank of India", "INE062A01020", "3045", "500112"),
            ("BHARTIARTL", "Bharti Airtel", "INE397D01024", "10604", "532454"),
            ("KOTAKBANK", "Kotak Mahindra Bank", "INE237A01028", "1922", "500247"),
            ("LT", "Larsen & Toubro", "INE018A01030", "11483", "500510"),
            ("WIPRO", "Wipro Limited", "INE075A01022", "3787", "507685"),
            ("AXISBANK", "Axis Bank Limited", "INE238A01034", "5900", "532215"),
            ("MARUTI", "Maruti Suzuki India", "INE585B01010", "10999", "532500"),
            ("SUNPHARMA", "Sun Pharma Industries", "INE044A01036", "3351", "524715"),
        ]
        
        for symbol, name, isin, nse_token, bse_token in fallback_data:
            # NSE instrument
            nse_instrument = Instrument(
                symbol=symbol,
                name=name,
                isin=isin,
                exchange="NSE",
                token=nse_token,
                trading_symbol=f"{symbol}-EQ",
            )
            key = (symbol, "NSE")
            self._instruments[key] = nse_instrument
            
            if nse_token not in self._by_token:
                self._by_token[nse_token] = {}
            self._by_token[nse_token]["NSE"] = nse_instrument
            
            # BSE instrument
            bse_instrument = Instrument(
                symbol=symbol,
                name=name,
                isin=isin,
                exchange="BSE",
                token=bse_token,
                trading_symbol=symbol,
            )
            key = (symbol, "BSE")
            self._instruments[key] = bse_instrument
            
            if bse_token not in self._by_token:
                self._by_token[bse_token] = {}
            self._by_token[bse_token]["BSE"] = bse_instrument
        
        logger.info(f"✅ Loaded {len(self._instruments)} instruments from fallback")
    
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
                
                if instrument.token not in self._by_token:
                    self._by_token[instrument.token] = {}
                self._by_token[instrument.token][instrument.exchange] = instrument
            
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
                    print(f"   {exchange}: Token={inst.token}, Symbol={inst.trading_symbol}")
                else:
                    print(f"   {exchange}: Not found")
        
        # Get subscription list
        print("\n🔑 WebSocket Subscription Format:")
        sub_list = manager.get_subscription_list(settings.symbol_list[:3])
        for item in sub_list:
            exchange_name = "NSE" if item["exchangeType"] == 1 else "BSE"
            print(f"   {exchange_name}: {item['tokens']}")
    
    asyncio.run(main())
