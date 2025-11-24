from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "ezGO POC Backend"
    VERSION: str = "0.1.0"
    
    # Database Configuration
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ezgo-poc"
    
    # Security (for future use)
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    
    # Mapbox Configuration
    MAPBOX_ACCESS_TOKEN: str = ""
    
    # H3 Configuration
    DEFAULT_H3_RESOLUTION: int = 9
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

