import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)


def _api_key(name: str) -> str:
    value = os.getenv(name, "").strip()
    if value.lower().startswith(("your_", "your-", "placeholder", "<")):
        return ""
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def _api_keys() -> tuple[str, ...]:
    values = [*os.getenv("NVIDIA_API_KEYS", "").split(","), _api_key("NVIDIA_API_KEY")]
    return tuple(
        dict.fromkeys(
            key.strip()
            for key in values
            if key.strip() and not key.strip().lower().startswith(("your_", "your-", "placeholder", "<"))
        )
    )


class Settings:
    APP_NAME = "JARVIS Personal AI Life Assistant"
    APP_VERSION = "1.0.0"
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", "8000"))
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "UTC")
    DEFAULT_CITY = os.getenv("DEFAULT_CITY", "Belagavi")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    NVIDIA_API_KEY = _api_key("NVIDIA_API_KEY")
    NVIDIA_API_KEYS = _api_keys()
    NVIDIA_VISION_API_KEY = _api_key("NVIDIA_VISION_API_KEY") or NVIDIA_API_KEY
    NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "openai/gpt-oss-20b")
    NVIDIA_FALLBACK_MODEL = os.getenv("NVIDIA_FALLBACK_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")
    NEWS_API_KEY = _api_key("NEWS_API_KEY")
    GNEWS_API_KEY = _api_key("GNEWS_API_KEY")
    GUARDIAN_API_KEY = _api_key("GUARDIAN_API_KEY")
    API_TIMEOUT_SECONDS = float(os.getenv("API_TIMEOUT_SECONDS", "15.0"))
    # Bound each model attempt so chat can quickly move to the fallback model.
    NVIDIA_TIMEOUT_SECONDS = float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "12.0"))

    @property
    def DATABASE_URL(self) -> str:
        value = os.getenv("DATABASE_URL", "sqlite:///./jarvis.db")
        if value.startswith("sqlite") and value.startswith("sqlite:///./"):
            db_path = (BASE_DIR / value.removeprefix("sqlite:///./")).resolve()
            return f"sqlite:///{db_path.as_posix()}"
        return value

    def news_enabled(self) -> bool:
        # Google News RSS is available as a keyless fallback.
        return True

    def ai_enabled(self) -> bool:
        return bool(self.NVIDIA_API_KEYS)


settings = Settings()
