"""Konfigurasi aplikasi AutoLamar."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DB_PATH = PROJECT_ROOT / "autolamar.db"
TEMPLATES_DIR = BASE_DIR / "templates"


@dataclass
class Settings:
    # AI endpoint: proxy LiteLLM di port 4000 (milik user). Port 20128 adalah
    # 9Router (validasi key via HMAC, hanya dipakai Hermes internal).
    llm_base_url: str = os.getenv("AUTOLAMAR_LLM_BASE_URL", "http://127.0.0.1:4000/v1")
    # Model cadangan langsung (model "utama" upstream-nya sedang unreachable,
    # tunggu timeout 120s di router).
    llm_model: str = os.getenv("AUTOLAMAR_LLM_MODEL", "cadangan-cohere")
    llm_api_key: str = ""  # di-resolve saat startup oleh app.keys.resolve_llm_key()
    # Auto-submit. Kalau False, surat dibuat tapi tidak dikirim (mode hybrid: review dulu)
    auto_submit: bool = os.getenv("AUTOLAMAR_AUTO_SUBMIT", "false").lower() in ("1", "true", "yes")
    # Berapa banyak lamaran yang boleh dikirim otomatis per hari (anti-spam / ToS)
    max_auto_submit_per_day: int = int(os.getenv("AUTOLAMAR_MAX_DAILY", "25"))
    # Server
    host: str = os.getenv("AUTOLAMAR_HOST", "127.0.0.1")
    port: int = int(os.getenv("AUTOLAMAR_PORT", "8010"))
    # Browser automation (untuk auto-submit ke portal)
    browser_enabled: bool = os.getenv("AUTOLAMAR_BROWSER", "false").lower() in ("1", "true", "yes")


settings = Settings()

# Auto-resolve key saat modul config dipakai pertama kali (untuk script CLI/Cron)
if not settings.llm_api_key:
    from .keys import resolve_llm_key  # noqa: E402

    settings.llm_api_key = resolve_llm_key()
