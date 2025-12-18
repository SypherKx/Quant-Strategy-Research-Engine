# Quant Strategy Research Engine
# =================================
# A self-improving trading strategy research platform
#
# 🎓 WHAT IS THIS?
# This system runs multiple trading strategies in parallel,
# evaluates their performance, evolves the best ones, and
# provides a dashboard for monitoring.
#
# 🎓 HOW TO RUN:
# 1. Copy .env.example to .env
# 2. Fill in your Angel One SmartAPI credentials
# 3. Install dependencies: pip install -r requirements.txt
# 4. Run: python run.py
# 5. Open http://localhost:8000 in browser

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings, validate_settings
from core.logger import logger


def print_banner():
    """Print startup banner."""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🧬 QUANT STRATEGY RESEARCH ENGINE                         ║
║                                                              ║
║   A Self-Improving Trading Research Platform                ║
║                                                              ║
║   ⚠️  PAPER TRADING ONLY - NO REAL MONEY                    ║
║   📚 Built for Learning                                      ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def check_requirements():
    """Check if all requirements are met."""
    errors = []
    
    # Check Python version
    if sys.version_info < (3, 9):
        errors.append(f"Python 3.9+ required (you have {sys.version})")
    
    # Check required packages
    required_packages = [
        'fastapi', 'uvicorn', 'aiosqlite', 'numpy', 
        'pydantic', 'websockets', 'httpx'
    ]
    
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            errors.append(f"Missing package: {package}")
    
    if errors:
        print("❌ Requirements not met:")
        for error in errors:
            print(f"   • {error}")
        print("\n📦 Run: pip install -r requirements.txt")
        return False
    
    return True


def main():
    """Main entry point."""
    print_banner()
    
    # Check requirements
    print("🔍 Checking requirements...")
    if not check_requirements():
        sys.exit(1)
    print("✅ Requirements OK")
    
    # Validate settings
    print("\n🔧 Validating configuration...")
    config_valid = validate_settings()
    
    if not config_valid:
        print("\n⚠️  Running in MOCK MODE (no real API connection)")
        print("   This is fine for testing and learning!")
    else:
        print("✅ Configuration valid")
    
    # Print summary
    print("\n📋 Configuration Summary:")
    print(f"   Symbols: {settings.symbol_list}")
    print(f"   Initial Capital: ₹{settings.INITIAL_CAPITAL:,.2f}")
    print(f"   Population Size: {settings.INITIAL_POPULATION_SIZE}")
    print(f"   Max Daily Loss: {settings.MAX_DAILY_LOSS_PERCENT}%")
    print(f"   Max Trades/Day: {settings.MAX_TRADES_PER_DAY}")
    
    # Start server
    print("\n🚀 Starting server...")
    print("   Dashboard: http://localhost:8000")
    print("   API Docs:  http://localhost:8000/docs")
    print("\n   Press Ctrl+C to stop\n")
    
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )


if __name__ == "__main__":
    main()
