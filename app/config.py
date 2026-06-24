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
        raise RuntimeError(f"{name} is not set — add it to .env")
    return value


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

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
