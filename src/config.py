"""
Application configuration using Pydantic Settings.
Loads configuration from environment variables and .env file.
"""
import importlib
import os
from typing import Optional, Protocol, Type

from dotenv import load_dotenv


class SettingsProtocol(Protocol):
    """Typed settings interface for consumers."""

    mongodb_uri: str
    mongodb_database_source: str
    mongodb_collection_occupations: str
    mongodb_database_target: str
    openai_api_key: Optional[str]
    openai_model_mini: str
    openai_model_full: str
    data_dir: str
    log_level: str
    ai_max_retries: int
    ai_rate_limit_delay: float
    ai_temperature_creative: float
    ai_temperature_factual: float


_HAS_PYDANTIC_SETTINGS = False
_HAS_PYDANTIC = False

PydanticSettingsBase: type = object
SettingsConfigDict: type = dict
PydanticBase: type = object

try:
    pydantic_settings = importlib.import_module("pydantic_settings")
    PydanticSettingsBase = getattr(pydantic_settings, "BaseSettings", object)
    SettingsConfigDict = getattr(pydantic_settings, "SettingsConfigDict", dict)
    _HAS_PYDANTIC_SETTINGS = True
except ImportError:
    _HAS_PYDANTIC_SETTINGS = False

if not _HAS_PYDANTIC_SETTINGS:
    try:
        pydantic = importlib.import_module("pydantic")
        PydanticBase = getattr(pydantic, "BaseSettings", object)
        _HAS_PYDANTIC = True
    except ImportError:
        _HAS_PYDANTIC = False


SettingsClass: Type[SettingsProtocol]

if _HAS_PYDANTIC_SETTINGS:

    class _SettingsPydanticSettings(PydanticSettingsBase):
        """Application settings loaded from environment variables."""

        # MongoDB Configuration
        mongodb_uri: str = "mongodb://localhost:27017"

        # Source Database (read-only, existing scraper DB)
        mongodb_database_source: str = "CV_DATA"
        mongodb_collection_occupations: str = "cv_berufsberatung"

        # Target Database (read/write, new app DB)
        mongodb_database_target: str = "swiss_cv_generator"

        # OpenAI Configuration
        openai_api_key: Optional[str] = None
        openai_model_mini: str = "gpt-3.5-turbo"
        openai_model_full: str = "gpt-4"

        # Application Configuration
        data_dir: str = "data"
        log_level: str = "INFO"

        # AI Configuration
        ai_max_retries: int = 5
        ai_rate_limit_delay: float = 1.0
        ai_temperature_creative: float = 0.8
        ai_temperature_factual: float = 0.3

        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )

    SettingsClass = _SettingsPydanticSettings
elif _HAS_PYDANTIC:

    class _SettingsPydantic(PydanticBase):
        """Application settings loaded from environment variables."""

        # MongoDB Configuration
        mongodb_uri: str = "mongodb://localhost:27017"

        # Source Database (read-only, existing scraper DB)
        mongodb_database_source: str = "CV_DATA"
        mongodb_collection_occupations: str = "cv_berufsberatung"

        # Target Database (read/write, new app DB)
        mongodb_database_target: str = "swiss_cv_generator"

        # OpenAI Configuration
        openai_api_key: Optional[str] = None
        openai_model_mini: str = "gpt-3.5-turbo"
        openai_model_full: str = "gpt-4"

        # Application Configuration
        data_dir: str = "data"
        log_level: str = "INFO"

        # AI Configuration
        ai_max_retries: int = 5
        ai_rate_limit_delay: float = 1.0
        ai_temperature_creative: float = 0.8
        ai_temperature_factual: float = 0.3

        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
            case_sensitive = False
            extra = "ignore"

    SettingsClass = _SettingsPydantic
else:

    class _SettingsEnv:
        """Application settings loaded from environment variables."""

        def __init__(self) -> None:
            load_dotenv()

            # MongoDB Configuration
            self.mongodb_uri = os.getenv(
                "MONGODB_URI", "mongodb://localhost:27017")

            # Source Database (read-only, existing scraper DB)
            self.mongodb_database_source = os.getenv(
                "MONGODB_DATABASE_SOURCE", "CV_DATA"
            )
            self.mongodb_collection_occupations = os.getenv(
                "MONGODB_COLLECTION_OCCUPATIONS", "cv_berufsberatung"
            )

            # Target Database (read/write, new app DB)
            self.mongodb_database_target = os.getenv(
                "MONGODB_DATABASE_TARGET", "swiss_cv_generator"
            )

            # OpenAI Configuration
            self.openai_api_key = os.getenv("OPENAI_API_KEY")
            self.openai_model_mini = os.getenv(
                "OPENAI_MODEL_MINI", "gpt-3.5-turbo")
            self.openai_model_full = os.getenv("OPENAI_MODEL_FULL", "gpt-4")

            # Application Configuration
            self.data_dir = os.getenv("DATA_DIR", "data")
            self.log_level = os.getenv("LOG_LEVEL", "INFO")

            # AI Configuration
            self.ai_max_retries = int(os.getenv("AI_MAX_RETRIES", "5"))
            self.ai_rate_limit_delay = float(
                os.getenv("AI_RATE_LIMIT_DELAY", "1.0"))
            self.ai_temperature_creative = float(
                os.getenv("AI_TEMPERATURE_CREATIVE", "0.8")
            )
            self.ai_temperature_factual = float(
                os.getenv("AI_TEMPERATURE_FACTUAL", "0.3")
            )

    SettingsClass = _SettingsEnv

Settings: Type[SettingsProtocol] = SettingsClass


# Singleton settings instance
_settings: Optional[SettingsProtocol] = None


def get_settings() -> SettingsProtocol:
    """
    Get the singleton settings instance.

    Returns:
        Settings instance loaded from environment variables and .env file.
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# Export singleton as 'settings'
settings = get_settings()
