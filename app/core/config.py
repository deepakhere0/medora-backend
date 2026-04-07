from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    APP_NAME: str = "Medora"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    DATABASE_URL: str
    DIRECT_URL: str | None = None

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    SUPABASE_URL: str
    SUPABASE_KEY: str
    SUPABASE_BUCKET: str = "medical-reports"

    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    GOOGLE_CLIENT_ID: str = ""



settings = Settings()
