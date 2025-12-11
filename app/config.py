# File: /backend/app/config.py
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Dasan Shift Manager"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_pdTmvE0AfLk9@ep-lucky-paper-a49tdqla-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require")
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dasanchamgo")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

@lru_cache()
def get_settings() -> Settings:
    return Settings()
