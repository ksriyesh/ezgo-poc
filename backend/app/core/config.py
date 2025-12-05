from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Find .env file - check root first, then backend directory
def find_env_file() -> str:
    """Find .env file, prioritizing root directory."""
    root_env = Path(__file__).resolve().parent.parent.parent.parent / ".env"
    local_env = Path(__file__).resolve().parent.parent.parent / ".env"
    
    if root_env.exists():
        return str(root_env)
    if local_env.exists():
        return str(local_env)
    return ".env"


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
    
    model_config = SettingsConfigDict(
        env_file=find_env_file(),
        case_sensitive=True,
    )


settings = Settings()

