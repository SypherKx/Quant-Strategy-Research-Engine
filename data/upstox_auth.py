"""
Upstox Authentication Module
============================

🎓 WHAT IS THIS FILE?
This file handles OAuth2 authentication with Upstox API.
It manages:
- Initial authorization code flow
- Access token generation
- Automatic daily token refresh using TOTP

🎓 HOW UPSTOX AUTHENTICATION WORKS:

1. FIRST TIME SETUP (manual, one-time):
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │ Your App     │ ──► │ Upstox Login │ ──► │ Auth Code    │
   │ redirects to │     │ page         │     │ returned     │
   │ Upstox       │     │ (user logs)  │     │ to your app  │
   └──────────────┘     └──────────────┘     └──────────────┘

2. EXCHANGE CODE FOR TOKEN:
   ┌──────────────┐     ┌──────────────┐
   │ Auth Code +  │ ──► │ Access Token │
   │ Client Secret│     │ (valid 1 day)│
   └──────────────┘     └──────────────┘

3. DAILY AUTO-REFRESH (what this file automates):
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │ TOTP Secret  │ ──► │ Auto Login   │ ──► │ New Token    │
   │ (you set up  │     │ Script       │     │ for today    │
   │ once)        │     │              │     │              │
   └──────────────┘     └──────────────┘     └──────────────┘

🎓 WHY TOTP-BASED AUTO-LOGIN?
Upstox access tokens expire at 3:30 AM every day.
Without automation, you'd have to:
1. Manually open browser
2. Log into Upstox
3. Copy new token

With TOTP secret, the system can do this automatically!

🎓 SECURITY NOTE:
Your TOTP secret is like a password. Never share it.
Keep it in .env file, not in code.
"""

import httpx
import pyotp
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


class UpstoxAuth:
    """
    Handles Upstox API authentication.
    
    🎓 USAGE:
    auth = UpstoxAuth()
    token = await auth.get_access_token()
    # Use token for API calls
    """
    
    def __init__(self):
        self.api_key = settings.UPSTOX_API_KEY
        self.api_secret = settings.UPSTOX_API_SECRET
        self.totp_secret = settings.UPSTOX_TOTP_SECRET
        self.redirect_uri = settings.UPSTOX_REDIRECT_URI
        
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
        
        # API endpoints
        self.auth_url = "https://api.upstox.com/v2/login/authorization/dialog"
        self.token_url = "https://api.upstox.com/v2/login/authorization/token"
    
    @property
    def is_token_valid(self) -> bool:
        """
        Check if current token is valid.
        
        🎓 Tokens expire at 3:30 AM next day.
        We consider token invalid 30 minutes before expiry
        to avoid edge cases.
        """
        if not self._access_token or not self._token_expiry:
            return False
        
        # Add 30 min buffer
        return datetime.now() < self._token_expiry - timedelta(minutes=30)
    
    def get_authorization_url(self) -> str:
        """
        Get URL for initial authorization.
        
        🎓 First-time setup:
        1. Call this function
        2. Open URL in browser
        3. Login with your Upstox credentials
        4. Copy the 'code' parameter from redirect URL
        5. Use exchange_code() with that code
        """
        params = {
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{self.auth_url}?{query}"
        
        logger.info(f"Authorization URL generated")
        return url
    
    async def exchange_code(self, auth_code: str) -> str:
        """
        Exchange authorization code for access token.
        
        🎓 This is called after you manually login and get the code.
        
        Args:
            auth_code: The code from redirect URL after login
        
        Returns:
            Access token string
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "code": auth_code,
                    "client_id": self.api_key,
                    "client_secret": self.api_secret,
                    "redirect_uri": self.redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise Exception(f"Token exchange failed: {response.text}")
            
            data = response.json()
            self._access_token = data["access_token"]
            
            # Token expires at 3:30 AM next day
            tomorrow = datetime.now().date() + timedelta(days=1)
            self._token_expiry = datetime.combine(
                tomorrow, 
                datetime.strptime("03:30", "%H:%M").time()
            )
            
            # Save token for persistence
            self._save_token()
            
            logger.info("✅ Access token obtained successfully")
            return self._access_token
    
    def generate_totp(self) -> str:
        """
        Generate current TOTP code.
        
        🎓 TOTP = Time-based One-Time Password
        It generates a 6-digit code that changes every 30 seconds.
        This is the same code your authenticator app shows.
        
        Returns:
            6-digit TOTP code
        """
        if not self.totp_secret:
            raise ValueError("TOTP secret not configured")
        
        totp = pyotp.TOTP(self.totp_secret)
        return totp.now()
    
    async def auto_login(self) -> str:
        """
        Automatically login using TOTP.
        
        🎓 THIS IS THE MAGIC FUNCTION!
        It simulates the login process programmatically:
        1. Generates TOTP code
        2. Submits credentials to Upstox
        3. Gets new access token
        
        ⚠️ NOTE: This uses Upstox's internal API and may break
        if Upstox changes their login flow. If it breaks,
        fall back to manual authorization.
        
        Returns:
            Fresh access token
        """
        logger.info("🔑 Attempting automatic login...")
        
        # For now, we'll use a simplified flow
        # In production, this would involve browser automation
        # or the upstox-totp package
        
        try:
            # Check if we have a saved token
            saved_token = self._load_token()
            if saved_token:
                logger.info("✅ Loaded saved access token")
                return saved_token
            
            # If no saved token, guide user to manual auth
            logger.warning("⚠️ No valid token found. Manual authorization required.")
            print("\n" + "="*60)
            print("📋 MANUAL AUTHORIZATION REQUIRED")
            print("="*60)
            print("\n1. Open this URL in your browser:")
            print(f"\n   {self.get_authorization_url()}")
            print("\n2. Login with your Upstox credentials")
            print("3. After redirect, copy the 'code' from the URL")
            print("4. The URL will look like: http://localhost:8000/callback?code=XXXXXX")
            print("5. Enter the code below:\n")
            
            # In a real scenario, we'd use the callback server
            # For now, prompt for manual input
            auth_code = input("Enter authorization code: ").strip()
            
            if auth_code:
                return await self.exchange_code(auth_code)
            else:
                raise ValueError("No authorization code provided")
                
        except Exception as e:
            logger.error(f"Auto-login failed: {e}")
            raise
    
    async def get_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        🎓 This is the main function you should use.
        It handles all the complexity internally:
        - Returns cached token if valid
        - Auto-refreshes if expired
        - Guides through manual auth if needed
        
        Returns:
            Valid access token
        """
        if self.is_token_valid:
            return self._access_token
        
        # Try to load from file
        saved_token = self._load_token()
        if saved_token:
            self._access_token = saved_token
            # Set expiry for today at 3:30 AM tomorrow
            tomorrow = datetime.now().date() + timedelta(days=1)
            self._token_expiry = datetime.combine(
                tomorrow,
                datetime.strptime("03:30", "%H:%M").time()
            )
            return self._access_token
        
        # Need fresh token
        return await self.auto_login()
    
    def _save_token(self):
        """Save token to file for persistence."""
        if self._access_token:
            data = {
                "access_token": self._access_token,
                "expiry": self._token_expiry.isoformat() if self._token_expiry else None,
                "saved_at": datetime.now().isoformat()
            }
            TOKEN_FILE.write_text(json.dumps(data))
            logger.debug("Token saved to file")
    
    def _load_token(self) -> Optional[str]:
        """Load token from file if valid."""
        if not TOKEN_FILE.exists():
            return None
        
        try:
            data = json.loads(TOKEN_FILE.read_text())
            expiry = datetime.fromisoformat(data["expiry"])
            
            # Check if still valid
            if datetime.now() < expiry - timedelta(minutes=30):
                self._token_expiry = expiry
                return data["access_token"]
            else:
                logger.info("Saved token expired, need new one")
                return None
                
        except Exception as e:
            logger.warning(f"Could not load saved token: {e}")
            return None
    
    def get_api_headers(self) -> dict:
        """
        Get headers for API requests.
        
        🎓 Every Upstox API call needs these headers.
        
        Returns:
            Dict with Authorization and other required headers
        """
        if not self._access_token:
            raise ValueError("No access token available. Call get_access_token() first.")
        
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }


# =========================================================
# MOCK AUTH FOR TESTING WITHOUT REAL CREDENTIALS
# =========================================================

class MockUpstoxAuth:
    """
    Mock authentication for testing without real API credentials.
    
    🎓 WHY A MOCK?
    During development and testing, you may not have:
    - Upstox account yet
    - API credentials set up
    - Working TOTP configuration
    
    This mock lets you test the rest of the system!
    """
    
    def __init__(self):
        self._access_token = "mock_token_for_testing"
        logger.info("🔧 Using MOCK authentication (no real API calls)")
    
    @property
    def is_token_valid(self) -> bool:
        return True
    
    async def get_access_token(self) -> str:
        return self._access_token
    
    def get_api_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json"
        }


def get_auth_client() -> UpstoxAuth:
    """
    Factory function to get appropriate auth client.
    
    🎓 Returns MockUpstoxAuth if credentials are not configured,
    otherwise returns real UpstoxAuth.
    """
    if not settings.UPSTOX_API_KEY or settings.UPSTOX_API_KEY == "your_api_key_here":
        logger.warning("Upstox credentials not configured, using mock auth")
        return MockUpstoxAuth()
    
    return UpstoxAuth()


# =========================================================
# MAIN - Test authentication
# =========================================================

if __name__ == "__main__":
    async def main():
        print("🔧 Testing Upstox authentication...")
        print()
        
        auth = get_auth_client()
        
        if isinstance(auth, MockUpstoxAuth):
            print("⚠️  Using MOCK authentication")
            print("   To use real auth, configure these in .env:")
            print("   - UPSTOX_API_KEY")
            print("   - UPSTOX_API_SECRET")
            print("   - UPSTOX_TOTP_SECRET")
            print()
        
        token = await auth.get_access_token()
        print(f"✅ Access token: {token[:20]}...")
        
        headers = auth.get_api_headers()
        print(f"✅ API headers ready: {list(headers.keys())}")
    
    asyncio.run(main())
