import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    APP_NAME: str = "VERITY Module 1 Backend"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@127.0.0.1:5432/verity_db"
    )
    AI_ENABLED: bool = os.getenv("AI_ENABLED", "true").lower() in ("true", "1", "t")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENGINE_VERSION: str = "1.0.0"

settings = Settings()
