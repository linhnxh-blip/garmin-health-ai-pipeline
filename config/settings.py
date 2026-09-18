import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent

# Detect .env or .env.txt in root project directory
ENV_PATH = BASE_DIR / ".env"
ENV_TXT_PATH = BASE_DIR / ".env.txt"

if not ENV_PATH.exists() and ENV_TXT_PATH.exists():
    # Sync .env.txt to .env if user saved it as .env.txt on Windows
    try:
        ENV_PATH.write_bytes(ENV_TXT_PATH.read_bytes())
        print(f"ℹ️ Automatically created `.env` from `.env.txt` at '{ENV_PATH}'.")
    except Exception as err:
        print(f"⚠️ Could not copy `.env.txt` to `.env`: {err}", file=sys.stderr)

target_env_file = ENV_PATH if ENV_PATH.exists() else (ENV_TXT_PATH if ENV_TXT_PATH.exists() else ENV_PATH)

if not target_env_file.exists():
    print(f"⚠️ Warning: `.env` file not found at '{ENV_PATH}'. Please ensure `.env` is created in root directory.", file=sys.stderr)
else:
    load_dotenv(dotenv_path=target_env_file, override=True)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(target_env_file),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    db_path: str = Field(default=str(BASE_DIR / "data" / "garmin_health.db"))
    garmin_username: str = ""
    garmin_email: str = ""
    garmin_password: str = ""
    garmin_token_dir: str = Field(default=str(BASE_DIR / "data" / ".garmin_tokens"))

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    google_keep_email: str = ""
    google_keep_app_password: str = ""
    google_keep_master_token: str = ""

    nightly_run_time: str = "23:00"

    @property
    def effective_garmin_username(self) -> str:
        """Return garmin_username or garmin_email as fallback."""
        val = (self.garmin_username or self.garmin_email or os.getenv("GARMIN_USERNAME") or os.getenv("GARMIN_EMAIL") or "").strip()
        return val

    @property
    def absolute_db_path(self) -> Path:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

settings = Settings()

# Check credentials and issue warning if missing/empty
if not settings.effective_garmin_username or not settings.garmin_password:
    print(
        f"⚠️ Warning: Garmin credentials missing or empty in .env!\n"
        f"   - GARMIN_USERNAME/GARMIN_EMAIL: '{settings.effective_garmin_username or 'EMPTY'}'\n"
        f"   - GARMIN_PASSWORD: {'***' if settings.garmin_password else 'EMPTY'}",
        file=sys.stderr
    )
