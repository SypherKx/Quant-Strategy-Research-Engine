"""
Data Layer Module
==================

This module handles all market data related functionality:
- Angel One SmartAPI authentication
- WebSocket market data streaming
- Instrument discovery and mapping
"""

from data.angelone_auth import get_auth_client, AngelOneAuth, MockAngelOneAuth
from data.websocket_streamer import (
    get_market_streamer,
    MarketDataStreamer,
    MockMarketDataStreamer,
    PriceTick,
    SpreadData
)
from data.instruments import get_instrument_manager, InstrumentManager, Instrument

__all__ = [
    # Auth
    'get_auth_client',
    'AngelOneAuth',
    'MockAngelOneAuth',
    
    # Streamer
    'get_market_streamer',
    'MarketDataStreamer',
    'MockMarketDataStreamer',
    'PriceTick',
    'SpreadData',
    
    # Instruments
    'get_instrument_manager',
    'InstrumentManager',
    'Instrument',
]
