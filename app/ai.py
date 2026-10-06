"""AI engine — generate surat lamaran + jawaban pertanyaan via LiteLLM proxy."""
from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
import time

from .config import settings
from .db import now

MODEL = settings.llm_model
BASE = settings.llm_base_url
KEY = settings.llm_api_key
TIMEOUT = 90.0

# Urutan model cadangan untuk failover internal. Proxy LiteLLM di port 4000 punya
# model cadangan sendiri (gemini, cohere, llm7, zai, ollama). Catatan: openrouter
# & minimax sudah kehabisan kredit (402), jadi tidak dimasukkan.
FAILOVER_MODELS = [
    m.strip()
    for m in os.getenv(
        "AUTOLAMAR_LLM_MODELS",
        "cadangan-gemini,cadangan-llm7,cadangan-zai,cadangan-ollama",
    ).split(",")
    if m.strip()
]


def _chat(messages: list[dict], temperature: float = 0.7) -> str:
    """Panggil endpoint chat/completions di proxy LiteLLM dengan failover otomatis.

    Mencoba setiap model di urutan FAILOVER_MODELS sampai ada yang berhasil.
    Status 429/500/502/503/529 dianggap sementara dan di-retry dengan backoff
    sebelum lanjut ke model berikutnya (rate limit tier gratis sering terjadi).
    """
    payload_base = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1200,
    }
    headers = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
    errors: list[str] = []
    with httpx.Client(timeout=TIMEOUT) as client:
        for model in [MODEL, *FAILOVER_MODELS]:
            payload = {**payload_base, "model": model}
            for attempt in range(2):
                try:
                    resp = client.post(f"{BASE}/chat/completions", json=payload, headers=headers)
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"].strip()
                except httpx.HTTPStatusError as exc:
                    code = exc.response.status_code
                    detail = exc.response.text[:200]
                    errors.append(f"{model}: {code} {detail}")
                    if code in (429, 500, 502, 503, 529) and attempt == 0:
                        time.sleep(2.0)
                        continue
                    break  # model ini gagal, coba model berikutnya
    raise RuntimeError("Semua model gagal: " + " | ".join(errors[-4:]))


def _strip_markdown_fences(text: str) -> str:
    """Model kadang balas dalam ```json ... ```. Ambil isinya."""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


# ──────────────────────────────────────────────────────────────────────
# Fitur 1: Generate surat lamaran
# ──────────────────────────────────────────────────────────────────────
CL_SYSTEM = """Kamu adalah asisten HRD senior dan penulis surat lamaran kerja dalam Bahasa Indonesia.
Tugasmu: menulis surat lamaran yang profesional, spesifik, dan TIDAK generik.

Aturan wajib:
- Bahasa Indonesia formal, sopan, tidak kaku seperti template.
- Wajib menyebutkan: posisi yang dilamar, nama perusahaan, dan minimal 2-3 pencapaian/skill
  kandidat yang RELEVAN dengan deskripsi lowongan.
- JANGAN gunakan kalimat klise kosong seperti "Saya adalah orang yang tekun" tanpa bukti.
- Maksimal 3 paragraf + penutup singkat. Total maksimal ~250 kata.
- JANGAN ada placeholder [Nama Perusahaan] — harus sudah terisi.
- Balas HANYA isi surat lamaran, tanpa judul "Surat Lamaran" atau penjelasan."""


def generate_cover_letter(
    profile: dict[str, Any],
    job: dict[str, Any],
) -> str:
    """Buat surat lamaran untuk satu lowongan."""
    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = json.loads(skills)
    experience = profile.get("experience") or []
    if isinstance(experience, str):
        experience = json.loads(experience)

    user = (
        f"DATA KANDIDAT\n"
        f"Nama: {profile['name']}\n"
        f"Posisi yang dituju: {job['title']}\n"
        f"Perusahaan: {job['company']}\n"
        f"Headline: {profile.get('headline', '-')}\n"
        f"Ringkasan: {profile.get('summary', '-')}\n"
        f"Skills: {', '.join(skills)}\n"
        f"\nPENGALAMAN\n"
    )
    for exp in experience[:4]:
        user += f"- {exp.get('role')} @ {exp.get('company')} ({exp.get('duration', '-')}): {exp.get('description', '')}\n"
    user += f"\nDESKRIPSI LOWONGAN\n{job.get('description', '')[:2000]}\n"
    user += "\nTulis surat lamarannya sekarang."

    return _chat(
        [
            {"role": "system", "content": CL_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.75,
    )


# ──────────────────────────────────────────────────────────────────────
# Fitur 2: Generate jawaban pertanyaan screening
# ──────────────────────────────────────────────────────────────────────
QA_SYSTEM = """Kamu asisten pelamar kerja. Jawab pertanyaan screening rekrutmen dengan jujur,
profesional, dan persuasif dalam Bahasa Indonesia.

Aturan:
- Jawab sesuai data kandidat yang diberikan. Kalau tidak ada info di data, jawab dengan
  pilihan yang paling profesional dan masuk akal, jangan mengarang pengalaman fiktif.
- Pertanyaan teknis dijawab ringkas tapi tepat.
- Pertanyaan "kenapa ingin bekerja di sini" harus spesifik ke perusahaan/posisi.
- Untuk pertanyaan gaji, berikan ekspektasi range wajar dalam Rupiah jika tak ada data.
- Output WAJIB JSON murni: {"answers": [{"question": "...", "answer": "..."}]}
  Tanpa teks lain, tanpa penjelasan."""


def generate_answers(
    profile: dict[str, Any],
    job: dict[str, Any],
    questions: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Jawab pertanyaan screening portal (Kalibrr/Glints sering pakai)."""
    if not questions:
        return []
    skills = profile.get("skills") or []
    if isinstance(skills, str):
        skills = json.loads(skills)

    qlist = "\n".join(f"{i+1}. {q['question']}" for i, q in enumerate(questions))
    user = (
        f"KANDIDAT: {profile['name']} | Target: {profile.get('target_role', job['title'])}\n"
        f"Skills: {', '.join(skills)}\n"
        f"Ringkasan: {profile.get('summary', '-')}\n"
        f"\nLOWONGAN: {job['title']} @ {job['company']}\n"
        f"{job.get('description', '')[:1500]}\n"
        f"\nPERTANYAAN:\n{qlist}\n"
        f"\nJawab semua dalam JSON."
    )
    raw = _chat(
        [
            {"role": "system", "content": QA_SYSTEM},
            {"role": "user", "content": user},
        ],
        temperature=0.5,
    )
    try:
        data = json.loads(_strip_markdown_fences(raw))
        return data.get("answers", [])
    except json.JSONDecodeError:
        # Fallback: balas apa adanya untuk pertanyaan pertama, sisanya kosong
        return [{"question": q["question"], "answer": raw[:500]} for q in questions[:1]]


# ──────────────────────────────────────────────────────────────────────
# Fitur 3: Ekstrak profile dari CV mentah (onboarding cepat)
# ──────────────────────────────────────────────────────────────────────
PARSE_SYSTEM = """Ekstrak data dari CV/keterangan kandidat menjadi JSON terstruktur.
Output WAJIB JSON murni dengan format:
{"name": "...", "email": "...", "phone": "...", "target_role": "...",
 "headline": "...", "summary": "...",
 "skills": ["...", "..."],
 "experience": [{"company": "...", "role": "...", "duration": "...", "description": "..."}],
 "education": [{"school": "...", "degree": "...", "year": "..."}]}
Jangan ada teks di luar JSON."""


def parse_cv(raw_cv: str) -> dict[str, Any]:
    """Ubah teks CV jadi profile terstruktur."""
    raw = _chat(
        [
            {"role": "system", "content": PARSE_SYSTEM},
            {"role": "user", "content": f"CV:\n{raw_cv[:6000]}"},
        ],
        temperature=0.2,
    )
    try:
        return json.loads(_strip_markdown_fences(raw))
    except json.JSONDecodeError:
        raise ValueError("AI tidak mengembalikan JSON valid. Coba lagi.")


__all__ = ["generate_cover_letter", "generate_answers", "parse_cv"]
