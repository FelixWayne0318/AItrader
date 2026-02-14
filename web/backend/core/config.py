"""
AlgVex Web Configuration
"""
import os
import warnings
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


def _detect_aitrader_path() -> str:
    """Auto-detect AItrader project root path"""
    # 1. Environment variable takes priority
    env_path = os.getenv("AITRADER_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    # 2. Detect relative to this file (web/backend/core/config.py -> project root)
    this_file = Path(__file__).resolve()
    project_root = this_file.parent.parent.parent.parent  # core -> backend -> web -> AItrader
    if (project_root / "main_live.py").exists():
        return str(project_root)

    # 3. Common server path
    server_path = Path("/home/linuxuser/nautilus_AItrader")
    if server_path.exists():
        return str(server_path)

    # 4. Fallback
    return str(project_root)


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "AlgVex"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-in-production-use-secrets")
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

    # AItrader paths (auto-detected)
    AITRADER_PATH: Path = Path(_detect_aitrader_path())

    @property
    def aitrader_config_path(self) -> Path:
        """Derive config path from AITRADER_PATH"""
        return self.AITRADER_PATH / "configs" / "base.yaml"

    AITRADER_ENV_PATH: Path = Path.home() / ".env.aitrader"
    AITRADER_SERVICE_NAME: str = "nautilus-trader"

    # Binance API (read from AItrader env)
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_API_SECRET: Optional[str] = None

    # CORS
    CORS_ORIGINS: list[str] = [
        "https://algvex.com",
        "http://algvex.com",
        "https://www.algvex.com",
        "http://www.algvex.com",
        "http://139.180.157.152:3000",
        "http://139.180.157.152",
        "https://139.180.157.152:3000",
        "https://139.180.157.152",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

# Validate SECRET_KEY: only crash if .env file exists (production) but SECRET_KEY is default
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists() and not settings.DEBUG:
    if settings.SECRET_KEY == "change-this-in-production-use-secrets":
        raise ValueError(
            "SECURITY ERROR: Default SECRET_KEY detected in production!\n"
            "   Set a secure SECRET_KEY in your .env file:\n"
            "   SECRET_KEY=$(openssl rand -hex 32)"
        )
elif not _env_file.exists() and settings.SECRET_KEY == "change-this-in-production-use-secrets":
    # No .env file = development/first-run mode, just warn
    warnings.warn(
        "Using default SECRET_KEY. Create web/backend/.env with a secure SECRET_KEY for production.",
        stacklevel=2,
    )


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
