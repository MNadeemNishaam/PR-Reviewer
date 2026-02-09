import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # GitHub App Configuration
    github_app_id: str
    github_app_private_key: str  # PEM format, can be multiline
    github_webhook_secret: str
    
    # LLM API Keys
    openai_api_key: str
    anthropic_api_key: str
    
    # Database Configuration
    database_url: str  # PostgreSQL connection string (Supabase)
    
    # Redis Configuration
    redis_url: str  # Upstash Redis connection string
    
    # Application Configuration
    environment: str = "development"
    log_level: str = "INFO"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Worker Configuration
    worker_poll_interval: int = 5  # seconds
    max_retries: int = 3
    retry_delay: int = 5  # seconds
    
    # Rate Limiting
    github_rate_limit_per_minute: int = 30
    openai_rate_limit_per_minute: int = 60
    anthropic_rate_limit_per_minute: int = 50
    
    # LLM Model Configuration
    scout_model: str = "gpt-4o-mini"
    guardian_model: str = "claude-3-5-sonnet-20241022"
    architect_model: str = "gpt-4o"
    stylist_model: str = "gpt-4o-mini"
    synthesizer_model: str = "gpt-4o"
    
    # Diff Processing
    max_diff_size: int = 100000  # characters
    max_file_size: int = 50000  # characters per file
    
    def get_github_private_key(self) -> str:
        """Get the GitHub private key, handling multiline format."""
        # Handle both single-line (with \n) and multiline formats
        if "\\n" in self.github_app_private_key:
            return self.github_app_private_key.replace("\\n", "\n")
        return self.github_app_private_key
    
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"


# Global settings instance
settings = Settings()

