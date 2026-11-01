from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./academicflow.db"
    frontend_url: str = "http://localhost:3000"
    redirect_uri: str = "http://localhost:3000/api/auth/callback"
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant_id: str = "organizations"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:3000/api/auth/google/callback"
    credential_key: str = ""
    cookie_secure: bool = False
    default_timezone: str = "Asia/Kolkata"
    demo_enabled: bool = True


@lru_cache
def settings():
    return Settings()
