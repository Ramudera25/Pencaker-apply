# AutoLamar — Pencari Kerja Apply Instan bantu AI

Website yang bantu melamar kerja otomatis: cari lowongan Kalibrr (Indonesia),
generate surat lamaran pakai AI per lowongan, lalu siap untuk dikirim.

## Stack

- **Backend:** FastAPI + Uvicorn
- **DB:** SQLite (`autolamar.db`)
- **AI:** proxy LiteLLM (model cadangan: cohere/gemini/llm7/zai/ollama)
- **Lowongan:** Kalibrr (endpoint JSON publik, tanpa login)

## Struktur

```
app/
  main.py      # FastAPI app + startup
  routes.py    # semua route web
  config.py    # Settings (LLM endpoint, model)
  ai.py        # generate surat + jawaban screening + parse CV
  db.py        # helper SQLite
  portals.py   # scraper portal lowongan (Kalibrr)
  worker.py    # background worker (queue lamaran)
  submit.py    # auto-submit browser automation (opsional)
  keys.py      # resolve master key LiteLLM dari .env
  templates/   # Jinja2 (dashboard, profile, search, application)
start.sh       # launcher
```

## Cara jalan

```bash
python -m venv venv && source venv/bin/activate
pip install fastapi uvicorn jinja2 python-multipart httpx beautifulsoup4
./start.sh
```

Buka `http://127.0.0.1:8010`.

## Konfigurasi LLM

Endpoint default: `http://127.0.0.1:4000/v1` (proxy LiteLLM lokal).
Master key dibaca otomatis dari `.env` (variabel `LITELLM_MASTER_KEY`).
Bisa di-override lewat env var:

```
AUTOLAMAR_LLM_BASE_URL=http://127.0.0.1:4000/v1
AUTOLAMAR_LLM_MODEL=cadangan-cohere
AUTOLAMAR_LLM_KEY=<master key>
AUTOLAMAR_LLM_MODELS=cadangan-gemini,cadangan-llm7,cadangan-zai,cadangan-ollama
AUTOLAMAR_BROWSER=false   # set true untuk auto-submit browser
```

## Catatan

- `.gitignore` mengecualikan `.env`, `*.db`, `*.log`, dan `venv/` — tidak ada
  secret atau data pribadi yang ter-commit.
- Mode default adalah **hybrid**: AI buatkan surat + jawaban screening,
  pengirimannya manual. Auto-submit browser bisa diaktifkan tapi portal
  lowongan umumnya butuh login manual pertama.
