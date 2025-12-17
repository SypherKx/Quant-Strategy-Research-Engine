"""
Configuration Management
========================

🎓 WHAT IS THIS FILE?
This file loads all settings from environment variables (.env file)
and provides type-safe access to configuration throughout the app.

🎓 WHY USE PYDANTIC SETTINGS?
- Automatic type conversion (string "100" → int 100)
- Validation (catches wrong values early)
- Default values if not specified
- Single source of truth for all config

🎓 HOW IT WORKS:
1. You create a .env file with your settings
2. This file reads that .env file
3. All other code imports 'settings' from here
4. If a required setting is missing → clear error message

Example usage in other files:
    from config import settings
    print(settings.INITIAL_CAPITAL)  # → 100000.0
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os

class Settings(BaseSettings):
    """
    All application settings in one place.
    
    🎓 Each setting has:
    - Type annotation (str, int, float, etc.)
    - Default value (if optional)
    - Description in comments
    """
    
    # =========================================================
    # UPSTOX API CREDENTIALS
    # =========================================================
    # These are required - the app won't work without them
    
    UPSTOX_API_KEY: str = Field(
        default="",
        description="Your Upstox API Key (Client ID)"
    )
    UPSTOX_API_SECRET: str = Field(
        default="",
        description="Your Upstox API Secret"
    )
    UPSTOX_TOTP_SECRET: str = Field(
        default="",
        description="TOTP secret for automated login"
    )
    UPSTOX_REDIRECT_URI: str = Field(
        default="http://localhost:8000/callback",
        description="OAuth redirect URI (must match Upstox app settings)"
    )
    
    # =========================================================
    # TRADING CONFIGURATION
    # =========================================================
    
    # Symbols to track - these will be monitored on both NSE and BSE
    SYMBOLS: str = Field(
        default="RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK",
        description="Comma-separated list of symbols to track"
    )
    
    @property
    def symbol_list(self) -> List[str]:
        """Convert comma-separated string to list."""
        return [s.strip() for s in self.SYMBOLS.split(",")]
    
    # =========================================================
    # STRATEGY EVOLUTION SETTINGS
    # =========================================================
    
    INITIAL_POPULATION_SIZE: int = Field(
        default=8,
        ge=3,  # minimum 3 strategies
        le=20, # maximum 20 strategies
        description="Number of strategies to run in parallel"
    )
    
    EVOLUTION_INTERVAL_HOURS: int = Field(
        default=24,
        ge=1,
        description="Hours between evolution cycles"
    )
    
    RETIRE_BOTTOM_PERCENT: float = Field(
        default=0.25,
        ge=0.1,
        le=0.5,
        description="Percentage of worst strategies to retire"
    )
    
    MUTATION_RATE: float = Field(
        default=0.3,
        ge=0.1,
        le=0.8,
        description="Probability of mutation in surviving strategies"
    )
    
    # =========================================================
    # RISK MANAGEMENT (SACRED - NEVER WEAKEN THESE)
    # =========================================================
    
    INITIAL_CAPITAL: float = Field(
        default=10000.0,  # ₹10,000 - Changed per user request
        ge=10000.0,
        description="Starting virtual capital in INR"
    )
    
    MAX_DAILY_LOSS_PERCENT: float = Field(
        default=2.0,
        ge=0.5,
        le=5.0,
        description="Maximum daily loss before trading stops"
    )
    
    MAX_TRADES_PER_DAY: int = Field(
        default=50,
        ge=10,
        le=200,
        description="Maximum number of trades per day"
    )
    
    MAX_POSITION_SIZE_PERCENT: float = Field(
        default=10.0,
        ge=1.0,
        le=25.0,
        description="Maximum percentage of capital per position"
    )
    
    # =========================================================
    # MARKET HOURS (IST)
    # =========================================================
    
    MARKET_OPEN_HOUR: int = Field(default=9)
    MARKET_OPEN_MINUTE: int = Field(default=15)
    MARKET_CLOSE_HOUR: int = Field(default=15)
    MARKET_CLOSE_MINUTE: int = Field(default=30)
    
    # =========================================================
    # DATABASE
    # =========================================================
    
    DATABASE_URL: str = Field(
        default="sqlite:///./quant_engine.db",
        description="Database connection string"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Ignore extra env vars


# Create a singleton instance
# 🎓 WHY SINGLETON?
# We only need ONE settings object for the entire app.
# This is created when the module is imported.
settings = Settings()


# =========================================================
# VALIDATION ON STARTUP
# =========================================================

def validate_settings() -> bool:
    """
    Check if critical settings are configured.
    
    🎓 WHY VALIDATE?
    Better to fail fast with clear error message than
    to fail later with cryptic API errors.
    """
    errors = []
    
    if not settings.UPSTOX_API_KEY or settings.UPSTOX_API_KEY == "your_api_key_here":
        errors.append("UPSTOX_API_KEY is not set")
    
    if not settings.UPSTOX_API_SECRET or settings.UPSTOX_API_SECRET == "your_api_secret_here":
        errors.append("UPSTOX_API_SECRET is not set")
    
    if errors:
        print("⚠️  Configuration Errors:")
        for error in errors:
            print(f"   - {error}")
        print("\n📝 Please copy .env.example to .env and fill in your credentials")
        return False
    
    return True


if __name__ == "__main__":
    # Test configuration loading
    print("🔧 Configuration loaded successfully!")
    print(f"   Symbols: {settings.symbol_list}")
    print(f"   Initial Capital: ₹{settings.INITIAL_CAPITAL:,.2f}")
    print(f"   Population Size: {settings.INITIAL_POPULATION_SIZE}")
    print(f"   Max Daily Loss: {settings.MAX_DAILY_LOSS_PERCENT}%")
    print()
    validate_settings()
