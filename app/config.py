from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

SERVER_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(SERVER_ROOT / ".env", override=True)


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()

def _require(name: str) -> str:
    value = _env(name)
    if not value:
        raise RuntimeError(f"{name} is not set - add it to .env")
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        self.stt_provider: str = _env("STT_PROVIDER", "deepgram")
        self.llm_provider: str = _env("LLM_PROVIDER", "gemini")
        self.tts_provider: str = _env("TTS_PROVIDER", "deepgram")

        self.deepgram_api_key: str = _require("DEEPGRAM_API_KEY")
        self.deepgram_stt_model: str = _env("DEEPGRAM_STT_MODEL") or "nova-3"
        self.deepgram_tts_model: str = _env("DEEPGRAM_TTS_MODEL") or "aura-2-thalia-en"
        self.elevenlabs_api_key: str | None = _env("ELEVENLABS_API_KEY")
        self.openai_api_key: str | None = _env("OPENAI_API_KEY")
        self.gemini_api_key: str | None = _env("GEMINI_API_KEY")
        self.gemini_model: str = _env("GEMINI_MODEL") or "gemini-2.5-flash"
        self.openai_model: str = _env("OPENAI_MODEL") or "gpt-4.1-nano-2025-04-14"

        self.cors_origins: str = _env("CORS_ORIGINS") or ""

        self.admin_email: str | None = _env("ADMIN_EMAIL")

        self.smtp_host: str | None = _env("SMTP_HOST")
        self.smtp_port: int = _env_int("SMTP_PORT", 587)
        self.smtp_user: str | None = _env("SMTP_USER")
        self.smtp_password: str | None = _env("SMTP_PASSWORD")
        self.smtp_from: str | None = _env("SMTP_FROM")

        self.google_calendar_id: str = _env("GOOGLE_CALENDAR_ID", "primary") or "primary"
        self.google_credentials_file: str | None = _env("GOOGLE_CREDENTIALS_FILE")
        self.google_credentials_json: str | None = _env("GOOGLE_CREDENTIALS_JSON")
        self.google_token_file: str | None = _env("GOOGLE_TOKEN_FILE")
        self.google_token_json: str | None = _env("GOOGLE_TOKEN_JSON")
        self.google_redirect_uri: str = (
            _env("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
            or "http://localhost:8000/auth/google/callback"
        )
        self.default_timezone: str = _env("DEFAULT_TIMEZONE", "Asia/Kolkata") or "Asia/Kolkata"

        self.mongodb_uri: str | None = _env("MONGODB_URI")
        self.mongodb_db_name: str = _env("MONGODB_DB_NAME", "voice_agent") or "voice_agent"
        self.jwt_secret_key: str = _env("JWT_SECRET_KEY", "change-this-secret") or "change-this-secret"
        self.jwt_algorithm: str = _env("JWT_ALGORITHM", "HS256") or "HS256"
        self.jwt_access_token_expire_minutes: int = _env_int("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 10080)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

settings = Settings()
