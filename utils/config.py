"""
Configuration Manager
Load karta hai .env file se settings
"""
import os
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class Config:
    # Bybit API
    BYBIT_API_KEY: str = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET: str = os.getenv("BYBIT_API_SECRET", "")
    BYBIT_TESTNET: bool = os.getenv("BYBIT_TESTNET", "True").lower() == "true"
    BYBIT_BASE_URL: str = (
        "https://api-testnet.bybit.com" if BYBIT_TESTNET else "https://api.bybit.com"
    )
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Trading Settings
    DEFAULT_LEVERAGE: int = int(os.getenv("DEFAULT_LEVERAGE", "10"))
    DEFAULT_RISK_PERCENT: float = float(os.getenv("DEFAULT_RISK_PERCENT", "1.0"))
    MAX_POSITION_SIZE: float = float(os.getenv("MAX_POSITION_SIZE", "1000"))
    PYRAMID_STEPS: int = int(os.getenv("PYRAMID_STEPS", "7"))
    
    # Risk Management
    MAX_DAILY_LOSS: float = float(os.getenv("MAX_DAILY_LOSS", "500"))
    MAX_OPEN_POSITIONS: int = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
    TRAILING_STOP_PERCENT: float = float(os.getenv("TRAILING_STOP_PERCENT", "2.0"))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "trading_bot.log")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configurations"""
        required = [
            cls.BYBIT_API_KEY,
            cls.BYBIT_API_SECRET,
            cls.TELEGRAM_BOT_TOKEN,
            cls.TELEGRAM_CHAT_ID
        ]
        return all(required)
    
    @classmethod
    def get_bybit_headers(cls, timestamp: str, signature: str) -> dict:
        """Generate Bybit API headers"""
        return {
            "X-BAPI-API-KEY": cls.BYBIT_API_KEY,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": "5000",
            "Content-Type": "application/json"
        }