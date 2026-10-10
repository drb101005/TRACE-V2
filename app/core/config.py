from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "AI-Run Statutory Revenue Audit Engine"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"
    DATABASE_URL: str = "sqlite:///./revenue_audit.db"
    JWT_SECRET_KEY: str = "replace-this-in-env"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    MAX_UPLOAD_MB: int = 25
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")
    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]

settings = Settings()
