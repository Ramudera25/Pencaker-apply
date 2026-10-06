"""Auto-submit engine via browser automation.

Implementasi menggunakan browser_harness (bawaan Hermes) alih-alih Playwright terpisah
agar tidak butuh install dependency tambahan dan memakai browser yang sudah ter-login
kalau session-nya dipersist.

Untuk MVP: class ini menyediakan struktur + deteksi form. Auto-submit penuh ke portal
spesifik butuh selector per-portal yang harus di-update mengikuti perubahan UI portal.
"""
from __future__ import annotations

import json
from typing import Any


class AutoSubmitError(Exception):
    """Gagal auto-submit (captcha, login wall, selector berubah)."""


# Selector form umum (best-effort) untuk career page / ATS populer di Indonesia
COMMON_SELECTORS = {
    "name": ["input[name='name']", "input[name='fullname']", "input[placeholder*='Nama' i]"],
    "email": ["input[type='email']", "input[name='email']"],
    "phone": ["input[type='tel']", "input[name='phone']", "input[placeholder*='HP' i]"],
    "cover_letter": [
        "textarea[name='cover_letter']",
        "textarea[name='message']",
        "textarea[placeholder*='cover' i]",
        "textarea[placeholder*='surat' i]",
    ],
    "submit": [
        "button[type='submit']",
        "button:has-text('Apply')",
        "button:has-text('Kirim')",
        "button:has-text('Submit')",
    ],
}


def build_fill_plan(profile: dict[str, Any], cover_letter: str, answers: list[dict[str, str]]) -> dict[str, str]:
    """Rencana pengisian form: field -> nilai.

    Dipakai browser worker untuk mengisi form career page/ATS generik.
    """
    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = json.loads(skills)

    plan = {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "phone": profile.get("phone", ""),
        "cover_letter": cover_letter,
    }

    # Pertanyaan screening (Kalibrr/Glints/ATS) biasanya berupa textarea/select
    for i, qa in enumerate(answers):
        plan[f"question_{i}"] = qa.get("answer", "")

    return {k: v for k, v in plan.items() if v}


def humanize_delay_ms() -> int:
    """Jeda random antar field agar tidak terdeteksi bot (300-900ms)."""
    import random

    return random.randint(300, 900)


# ──────────────────────────────────────────────────────────────────────
# Registry strategi submit per-portal
# ──────────────────────────────────────────────────────────────────────
def can_auto_submit(portal: str) -> bool:
    """Portal mana yang auto-submit didukung untuk MVP ini.

    JobStreet & LinkedIn anti-bot ekstrem + wajib login; auto-submit ke sana hampir
    pasti berakhir captcha/blokir, jadi tidak diaktifkan demi keandalan.
    """
    return portal in {"kalibrr", "direct", "glints"}


def describe_submit_path(portal: str) -> str:
    return {
        "kalibrr": "Browser: buka job URL -> isi cover letter + jawaban -> klik Apply (perlu login Kalibrr).",
        "glints": "Browser: buka job URL -> isi form apply -> submit (perlu login Glints).",
        "direct": "Browser: buka career page -> deteksi form umum -> isi -> kirim.",
        "jobstreet": "Tidak didukung: Akamai Bot Manager. Pakai mode hybrid (AI generate, kirim manual).",
        "linkedin": "Tidak didukung: login wall + anti-bot. Pakai mode hybrid (AI generate, kirim manual).",
    }.get(portal, "Tidak ada strategi submit.")
