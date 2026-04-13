from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str

    # Už nepoužíváme po přechodu na přesnější zdroje (CFTC open data a MyFXBook)
    # nasdaq_api_key: str = ""
    # oanda_api_token: str = ""
    alpha_vantage_key: str = ""
    eodhd_api_key: str = ""
    gemini_api_key: str = ""
    myfxbook_email: str = ""
    myfxbook_password: str = ""
    cron_secret: str = "TajnySuperKlicProCloudCronUpdate!2026"
    
    # Odebráno:
    # nasdaq_api_key
    # oanda_api_token

    next_public_api_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
