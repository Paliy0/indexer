"""
Application configuration using Pydantic Settings
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False
    )
    
    # Database
    database_url: str = "sqlite:///./data/sites.db"
    
    # Web Parser
    web_parser_path: str = "./web-parser/web-parser"
    
    # Server
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Meilisearch (Phase 2+)
    meilisearch_host: str = "http://127.0.0.1:7700"
    meili_master_key: str = "your-development-master-key"
    
    # Subdomain routing (Phase 3+)
    base_domain: str = ""  # e.g., "example.com" - leave empty to disable subdomain routing


@lru_cache()
def get_settings():
    """
    Cached settings instance.
    Using lru_cache ensures we only create one Settings instance.
    """
    return Settings()
