"""
Algvex Web Configuration
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "Algvex"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = "change-this-in-production-use-secrets"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: str = "https://algvex.com/api/auth/callback/google"

    # Admin emails allowed to login
    ADMIN_EMAILS: list[str] = []

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./algvex.db"

    # AItrader paths
    AITRADER_PATH: Path = Path("/home/linuxuser/nautilus_AItrader")
    AITRADER_CONFIG_PATH: Path = Path("/home/linuxuser/nautilus_AItrader/configs/strategy_config.yaml")
    AITRADER_ENV_PATH: Path = Path.home() / ".env.aitrader"
    AITRADER_SERVICE_NAME: str = "nautilus-trader"

    # Binance API (read from AItrader env)
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_API_SECRET: Optional[str] = None

    # CORS
    CORS_ORIGINS: list[str] = [
        "https://algvex.com",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()


def load_aitrader_env():
    """Load Binance API keys from AItrader environment file"""
    env_path = settings.AITRADER_ENV_PATH
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Strip inline comments
                    if "#" in value and not value.startswith('"'):
                        value = value.split("#")[0].strip()
                    value = value.strip().strip('"').strip("'")

                    if key == "BINANCE_API_KEY":
                        settings.BINANCE_API_KEY = value
                    elif key == "BINANCE_API_SECRET":
                        settings.BINANCE_API_SECRET = value
