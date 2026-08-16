"""
Central application configuration.

This module defines ALL configuration using Pydantic Settings.
Automatically reads the .env file and validates types.

Usage:
    from app.config import get_settings
    settings = get_settings()
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration.
    
    Each attribute = an environment variable.
    Default values are used if not in .env.
    """
    
    # Configuration for reading .env
    model_config = SettingsConfigDict(
        env_file=".env",           # File to read
        env_file_encoding="utf-8", # Encoding
        case_sensitive=False,      # Case insensitive
        extra="ignore",            # Ignore unknown variables (no failure)
    )

    # =========================================================================
    # APP - General configuration
    # =========================================================================
    APP_NAME: str = "Career Fit Intelligence API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False                    # True = docs enabled, verbose logs
    API_PREFIX: str = "/v1"                # Prefix for all routes: /v1/analyze, /v1/health

    # =========================================================================
    # DATABASE - PostgreSQL with pgvector
    # =========================================================================
    # We use full DATABASE_URL (simpler than separate parts)
    # Format: postgresql+asyncpg://user:pass@host:port/dbname
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@db:5432/career_fit"
    
    # Connection pool (asyncpg)
    DATABASE_POOL_SIZE: int = 10           # Permanent connections
    DATABASE_MAX_OVERFLOW: int = 20        # Extra connections under load

    # =========================================================================
    # FREEHIRE - Job listings data source
    # =========================================================================
    FREEHIRE_BASE_URL: str = "https://freehire.me/api/v1"
    FREEHIRE_TIMEOUT: float = 30.0         # Seconds for HTTP timeout
    FREEHIRE_PAGE_SIZE: int = 100          # Jobs per page in API
    INGESTION_BATCH_SIZE: int = 500        # Jobs to process per batch
    INGESTION_DAILY_HOUR: int = 3          # UTC hour for daily ingestion (3 AM)

    # =========================================================================
    # LLM - Groq (OpenAI-compatible) for CV extraction and normalization
    # =========================================================================
    # Get your free key at: https://console.groq.com
    LLM_PROVIDER: str = "groq"             # groq, openai, anthropic, local
    LLM_API_KEY: str = ""                  # Required in .env
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "llama-3.1-70b-versatile"
    LLM_TEMPERATURE: float = 0.1           # Low = more deterministic
    LLM_MAX_TOKENS: int = 4000
    LLM_TIMEOUT: float = 60.0

    # =========================================================================
    # EMBEDDINGS - Local (sentence-transformers), no API key
    # =========================================================================
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DEVICE: str = "cpu"          # cpu, cuda, mps

    # =========================================================================
    # ML - Paths to trained models
    # =========================================================================
    SALARY_MODEL_PATH: str = "/app/models/salary_model.pkl"
    MATCH_MODEL_PATH: str = "/app/models/match_model.pkl"

    # =========================================================================
    # REDIS - For future cache / queues
    # =========================================================================
    REDIS_URL: str = "redis://redis:6379/0"

    # =========================================================================
    # LOGGING
    # =========================================================================
    LOG_LEVEL: str = "INFO"                # DEBUG, INFO, WARNING, ERROR
    LOG_FORMAT: str = "json"               # json or console

    # =========================================================================
    # ANALYSIS - Default configuration
    # =========================================================================
    DEFAULT_ANALYSIS_LEVEL: str = "full"   # basic, standard, full
    MAX_CONCURRENT_ANALYSES: int = 5       # Limit of concurrent analyses


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns the singleton Settings instance.
    
    @lru_cache ensures that:
    1. .env is read ONCE on first call
    2. Same instance is reused throughout the app
    3. Tests can call cache_clear() to reload
    
    Returns:
        Settings: Validated and typed configuration
    """
    return Settings()


# Global instance for direct use (optional, prefer get_settings())
settings = get_settings()