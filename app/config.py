"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import BASE_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Telegram ---
    bot_token: str = ""
    admin_ids: str = ""

    # --- Runtime ---
    tz: str = "Europe/Kyiv"
    data_dir: Path = BASE_DIR / "data"
    db_path: Path = BASE_DIR / "data" / "vibeparser.db"
    log_level: str = "INFO"

    # --- Polling ---
    poll_interval: int = Field(default=75, ge=20, le=3600)
    http_timeout: float = Field(default=25.0, ge=5, le=120)
    max_pages: int = Field(default=2, ge=1, le=5)

    # --- Notifications ---
    screenshot_mode: str = "card"  # card | page
    startup_message: bool = False

    # --- Sources ---
    freelancehunt_token: str = ""
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # --- Currency rates to UAH (used only for filtering) ---
    rate_usd_uah: float = 42.0
    rate_eur_uah: float = 45.5
    rate_gbp_uah: float = 53.0
    rate_pln_uah: float = 10.5
    rate_cad_uah: float = 31.0
    rate_rub_uah: float = 0.45

    @field_validator("screenshot_mode")
    @classmethod
    def _validate_screenshot_mode(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"card", "page"}:
            raise ValueError("SCREENSHOT_MODE must be 'card' or 'page'")
        return value

    @field_validator("data_dir", "db_path", mode="after")
    @classmethod
    def _resolve_paths(cls, value: Path) -> Path:
        """Resolve relative paths against the app folder, not the shell CWD.

        This keeps ``data/`` next to the .exe even when the app is launched
        from a shortcut or another working directory.
        """
        return value if value.is_absolute() else (BASE_DIR / value).resolve()

    @property
    def has_valid_bot_token(self) -> bool:
        """Reject empty and example tokens from .env.example."""
        token = self.bot_token.strip()
        return bool(re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{20,}", token))

    @property
    def admin_id_list(self) -> list[int]:
        result: list[int] = []
        for raw in self.admin_ids.replace(";", ",").split(","):
            raw = raw.strip()
            if not raw:
                continue
            try:
                result.append(int(raw))
            except ValueError:
                continue
        return result

    @property
    def currency_rates(self) -> dict[str, float]:
        return {
            "UAH": 1.0,
            "USD": self.rate_usd_uah,
            "EUR": self.rate_eur_uah,
            "GBP": self.rate_gbp_uah,
            "PLN": self.rate_pln_uah,
            "CAD": self.rate_cad_uah,
            "RUB": self.rate_rub_uah,
        }

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "resumes").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "previews").mkdir(parents=True, exist_ok=True)
