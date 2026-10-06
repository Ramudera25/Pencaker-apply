"""Background worker — memproses queue aplikasi (generate + submit)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from . import ai, db, submit

# Queue sederhana berbasis polling DB. Cukup untuk MVP single-VM.
_POLL_INTERVAL = 3.0
_thread: threading.Thread | None = None
_stop = threading.Event()


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _load_profile(profile_id: int) -> dict[str, Any]:
    rows = db.query("SELECT * FROM profiles WHERE id = ?", (profile_id,))
    return _row_to_dict(rows[0]) if rows else {}


def _load_job(job_id: int) -> dict[str, Any]:
    rows = db.query("SELECT * FROM jobs WHERE id = ?", (job_id,))
    return _row_to_dict(rows[0]) if rows else {}


def _mark(app_id: int, status: str, **fields) -> None:
    cols = ["status = ?", "updated_at = ?"] + [f"{k} = ?" for k in fields]
    vals: list[Any] = [status, db.now(), *fields.values()]
    db.execute(f"UPDATE applications SET {', '.join(cols)} WHERE id = ?", (*vals, app_id))


def _process_one(app_id: int) -> None:
    rows = db.query("SELECT * FROM applications WHERE id = ?", (app_id,))
    if not rows:
        return
    app = _row_to_dict(rows[0])
    if app["status"] not in ("queued",):
        return

    profile = _load_profile(app["profile_id"])
    job = _load_job(app["job_id"])
    if not profile or not job:
        _mark(app_id, "failed", error="Profile atau job hilang")
        return

    try:
        _mark(app_id, "generating")
        cover = ai.generate_cover_letter(profile, job)

        q_raw = job.get("questions")
        questions = json.loads(q_raw) if q_raw else []
        answers = ai.generate_answers(profile, job, questions) if questions else []

        _mark(app_id, "generated", cover_letter=cover, answers=json.dumps(answers))

        # ── Fase submit ──────────────────────────────────────────────
        if not submit.can_auto_submit(job["portal"]):
            _mark(
                app_id,
                "skipped",
                submit_log=submit.describe_submit_path(job["portal"]),
            )
            return

        if not _within_daily_limit(app["profile_id"]):
            _mark(app_id, "skipped", error="Batas harian tercapai")
            return

        # Auto-submit masih offline di MVP (browser automation opsional).
        _mark(
            app_id,
            "skipped",
            submit_log=(
                "Auto-submit browser belum diaktifkan. Surat + jawaban siap — "
                "buka detail untuk kirim manual, atau aktifkan AUTOLAMAR_BROWSER=true."
            ),
        )
    except Exception as exc:  # noqa: BLE001 - worker harus survive
        _mark(app_id, "failed", error=f"{type(exc).__name__}: {exc}")


def _within_daily_limit(profile_id: int) -> bool:
    cutoff = (datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")
    rows = db.query(
        "SELECT COUNT(*) c FROM applications WHERE profile_id = ? AND status = 'submitted' AND updated_at >= ?",
        (profile_id, cutoff),
    )
    return rows[0]["c"] < settings_max_daily()


def settings_max_daily() -> int:
    from .config import settings

    return settings.max_auto_submit_per_day


def _loop() -> None:
    while not _stop.is_set():
        try:
            queued = db.query("SELECT id FROM applications WHERE status = 'queued' ORDER BY id LIMIT 5")
            for row in queued:
                _process_one(row["id"])
        except Exception:  # noqa: BLE001
            pass
        time.sleep(_POLL_INTERVAL)


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="autolamar-worker")
    _thread.start()


def stop() -> None:
    _stop.set()
    if _thread:
        _thread.join(timeout=10)
