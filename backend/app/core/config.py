from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str
    API_V1_STR: str
    SECRET_KEY: str
    DATABASE_URL: str
    GOOGLE_CLOUD_PROJECT: str
    GOOGLE_CLOUD_STORAGE_BUCKET: str
    EMAIL_SUBMISSION_ADDRESS: str
    SENTRY_DSN: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

def get_settings() -> Settings:
    return Settings()