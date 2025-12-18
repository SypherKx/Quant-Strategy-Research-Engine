"""
Angel One SmartAPI Authentication Module
=========================================

🎓 WHAT IS THIS FILE?
This file handles authentication with Angel One SmartAPI.
It manages:
- Session generation with TOTP
- JWT token management
- Feed token for WebSocket

🎓 HOW ANGEL ONE AUTHENTICATION WORKS:

1. GENERATE SESSION:
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │ Client Code  │ ──► │ PIN + TOTP   │ ──► │ JWT Token    │
   │ API Key      │     │ Validation   │     │ + Feed Token │
   └──────────────┘     └──────────────┘     └──────────────┘

2. USE TOKENS:
   - JWT Token: For REST API calls
   - Feed Token: For WebSocket market data
   - Refresh Token: To regenerate JWT

🎓 SECURITY NOTE:
Your API Key and TOTP secret are sensitive. Keep them in .env file.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from core.logger import logger

# Token storage file (local, not shared)
TOKEN_FILE = Path(__file__).parent.parent / ".access_token"


class AngelOneAuth:
    """
    Handles Angel One SmartAPI authentication.
    
    🎓 USAGE:
    auth = AngelOneAuth()
    await auth.generate_session()
    token = auth.get_access_token()
    feed_token = auth.get_feed_token()
    """
    
    def __init__(self):
        self.api_key = settings.ANGELONE_API_KEY
        self.client_code = settings.ANGELONE_CLIENT_CODE
        self.pin = settings.ANGELONE_PIN
        self.totp_secret = settings.ANGELONE_TOTP_SECRET
        
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._feed_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        
        self._smart_api = None
    
    def _initialize_smart_api(self):
        """Initialize SmartAPI object."""
        if self._smart_api is None:
            try:
                from SmartApi import SmartConnect
                self._smart_api = SmartConnect(api_key=self.api_key)
                logger.info("✅ SmartAPI initialized")
            except ImportError:
                logger.error("❌ smartapi-python not installed. Run: pip install smartapi-python")
                raise
    
    @property
    def is_token_valid(self) -> bool:
        """
        Check if current token is valid.
        
        🎓 Tokens are generally valid for the trading day.
        We consider token invalid 30 minutes before expiry.
        """
        if not self._access_token or not self._token_expiry:
            return False
        
        return datetime.now() < self._token_expiry - timedelta(minutes=30)
    
    def generate_totp(self) -> str:
        """
        Generate current TOTP code.
        
        🎓 TOTP = Time-based One-Time Password
        It generates a 6-digit code that changes every 30 seconds.
        
        Returns:
            6-digit TOTP code
        """
        if not self.totp_secret:
            raise ValueError("TOTP secret not configured")
        
        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()
    
    async def generate_session(self) -> bool:
        """
        Generate a new session with Angel One.
        
        🎓 This is the main login function.
        It uses Client Code, PIN, and TOTP to authenticate.
        
        Returns:
            True if successful, False otherwise
        """
        logger.info("🔑 Generating Angel One session...")
        
        try:
            self._initialize_smart_api()
            
            # Generate TOTP
            totp = self.generate_totp()
            logger.debug(f"Generated TOTP: {totp[:2]}****")
            
            # Generate session
            data = self._smart_api.generateSession(
                clientCode=self.client_code,
                password=self.pin,
                totp=totp
            )
            
            if data.get('status') == False:
                logger.error(f"Session generation failed: {data.get('message', 'Unknown error')}")
                return False
            
            # Extract tokens
            self._access_token = data['data']['jwtToken']
            self._refresh_token = data['data']['refreshToken']
            
            # Get feed token for WebSocket
            self._feed_token = self._smart_api.getfeedToken()
            
            # Set expiry to end of trading day (3:30 PM) + buffer
            today = datetime.now().date()
            self._token_expiry = datetime.combine(
                today,
                datetime.strptime("15:30", "%H:%M").time()
            )
            
            # If past 3:30 PM, set to next day
            if datetime.now() > self._token_expiry:
                self._token_expiry += timedelta(days=1)
            
            # Save token
            self._save_token()
            
            logger.info("✅ Angel One session generated successfully")
            logger.info(f"   Feed Token: {self._feed_token[:20] if self._feed_token else 'N/A'}...")
            
            return True
            
        except Exception as e:
            logger.error(f"Session generation failed: {e}")
            return False
    
    async def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        🎓 This is the main function you should use.
        
        Returns:
            Valid access token
        """
        if self.is_token_valid:
            return self._access_token
        
        # Try to load from file
        if self._load_token():
            return self._access_token
        
        # Need fresh session
        success = await self.generate_session()
        if not success:
            raise Exception("Failed to generate Angel One session")
        
        return self._access_token
    
    def get_feed_token(self) -> str:
        """Get the feed token for WebSocket connection."""
        if not self._feed_token:
            raise ValueError("No feed token available. Call generate_session() first.")
        return self._feed_token
    
    def get_smart_api(self):
        """Get the SmartAPI object for API calls."""
        if not self._smart_api:
            self._initialize_smart_api()
        return self._smart_api
    
    def _save_token(self):
        """Save token to file for persistence."""
        if self._access_token:
            data = {
                "access_token": self._access_token,
                "refresh_token": self._refresh_token,
                "feed_token": self._feed_token,
                "expiry": self._token_expiry.isoformat() if self._token_expiry else None,
                "saved_at": datetime.now().isoformat()
            }
            TOKEN_FILE.write_text(json.dumps(data))
            logger.debug("Token saved to file")
    
    def _load_token(self) -> bool:
        """Load token from file if valid."""
        if not TOKEN_FILE.exists():
            return False
        
        try:
            data = json.loads(TOKEN_FILE.read_text())
            expiry = datetime.fromisoformat(data["expiry"])
            
            # Check if still valid
            if datetime.now() < expiry - timedelta(minutes=30):
                self._access_token = data["access_token"]
                self._refresh_token = data.get("refresh_token")
                self._feed_token = data.get("feed_token")
                self._token_expiry = expiry
                
                # Re-initialize SmartAPI with token
                self._initialize_smart_api()
                if self._access_token:
                    self._smart_api.setAccessToken(self._access_token)
                
                logger.info("✅ Loaded saved access token")
                return True
            else:
                logger.info("Saved token expired, need new one")
                return False
                
        except Exception as e:
            logger.warning(f"Could not load saved token: {e}")
            return False
    
    def get_api_headers(self) -> dict:
        """
        Get headers for API requests.
        
        Returns:
            Dict with Authorization and other required headers
        """
        if not self._access_token:
            raise ValueError("No access token available. Call get_access_token() first.")
        
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-PrivateKey": self.api_key,
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-UserType": "USER"
        }


# =========================================================
# MOCK AUTH FOR TESTING WITHOUT REAL CREDENTIALS
# =========================================================

class MockAngelOneAuth:
    """
    Mock authentication for testing without real API credentials.
    
    🎓 WHY A MOCK?
    During development and testing, you may not have:
    - Angel One account yet
    - API credentials set up
    - Working TOTP configuration
    
    This mock lets you test the rest of the system!
    """
    
    def __init__(self):
        self._access_token = "mock_token_for_testing"
        self._feed_token = "mock_feed_token"
        logger.info("🔧 Using MOCK authentication (no real API calls)")
    
    @property
    def is_token_valid(self) -> bool:
        return True
    
    async def generate_session(self) -> bool:
        return True
    
    async def get_access_token(self) -> str:
        return self._access_token
    
    def get_feed_token(self) -> str:
        return self._feed_token
    
    def get_smart_api(self):
        return None
    
    def get_api_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }


def get_auth_client():
    """
    Factory function to get appropriate auth client.
    
    🎓 Returns MockAngelOneAuth if credentials are not configured,
    otherwise returns real AngelOneAuth.
    """
    if not settings.ANGELONE_API_KEY or settings.ANGELONE_API_KEY == "your_api_key_here":
        logger.warning("Angel One credentials not configured, using mock auth")
        return MockAngelOneAuth()
    
    return AngelOneAuth()


# =========================================================
# MAIN - Test authentication
# =========================================================

if __name__ == "__main__":
    async def main():
        print("🔧 Testing Angel One authentication...")
        print()
        
        auth = get_auth_client()
        
        if isinstance(auth, MockAngelOneAuth):
            print("⚠️  Using MOCK authentication")
            print("   To use real auth, configure these in .env:")
            print("   - ANGELONE_API_KEY")
            print("   - ANGELONE_CLIENT_CODE")
            print("   - ANGELONE_PIN")
            print("   - ANGELONE_TOTP_SECRET")
            print()
        
        token = await auth.get_access_token()
        print(f"✅ Access token: {token[:20]}...")
        
        feed_token = auth.get_feed_token()
        print(f"✅ Feed token: {feed_token[:20]}...")
        
        headers = auth.get_api_headers()
        print(f"✅ API headers ready: {list(headers.keys())}")
    
    asyncio.run(main())
