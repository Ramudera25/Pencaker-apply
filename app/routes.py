"""FastAPI routes untuk AutoLamar."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import ai, db, portals, submit
from .config import TEMPLATES_DIR, settings

router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _load_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value or []


# ──────────────────────────────────────────────────────────────────────
# Dashboard
# ──────────────────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    profiles = [dict(r) for r in db.query("SELECT * FROM profiles ORDER BY id DESC")]
    apps = [
        dict(r)
        for r in db.query(
            "SELECT a.*, j.title, j.company, j.portal, j.url FROM applications a "
            "JOIN jobs j ON j.id = a.job_id ORDER BY a.updated_at DESC LIMIT 50"
        )
    ]
    counts = {
        "total": len(apps),
        "generated": sum(1 for a in apps if a["status"] in ("generated", "submitted")),
        "submitted": sum(1 for a in apps if a["status"] == "submitted"),
        "queued": sum(1 for a in apps if a["status"] == "queued"),
        "skipped": sum(1 for a in apps if a["status"] == "skipped"),
        "failed": sum(1 for a in apps if a["status"] == "failed"),
    }
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "profiles": profiles,
            "applications": apps,
            "counts": counts,
            "auto_submit": settings.auto_submit,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Profile
# ──────────────────────────────────────────────────────────────────────
@router.get("/profile/new", response_class=HTMLResponse)
async def profile_form(request: Request):
    return templates.TemplateResponse(request=request, name="profile_form.html", context={})


@router.post("/profile/new")
async def profile_create(
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(""),
    target_role: str = Form(...),
    headline: str = Form(""),
    summary: str = Form(""),
    skills: str = Form(""),           # dipisah koma
    cv_text: str = Form(""),
):
    skills_list = [s.strip() for s in skills.split(",") if s.strip()]
    pid = db.execute(
        """INSERT INTO profiles (name, email, phone, target_role, headline, summary,
           skills, experience, education, cv_text, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name,
            email,
            phone,
            target_role,
            headline,
            summary,
            db._json_dumps(skills_list) if hasattr(db, "_json_dumps") else json.dumps(skills_list),
            "[]",
            "[]",
            cv_text,
            db.now(),
            db.now(),
        ),
    )
    return RedirectResponse(url=f"/?profile={pid}", status_code=303)


@router.post("/profile/parse")
async def profile_parse(cv_text: str = Form(...)):
    """AI ekstrak profile dari CV mentah."""
    try:
        parsed = ai.parse_cv(cv_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return parsed


@router.get("/profile/{pid}/edit", response_class=HTMLResponse)
async def profile_edit_form(request: Request, pid: int):
    rows = db.query("SELECT * FROM profiles WHERE id = ?", (pid,))
    if not rows:
        raise HTTPException(status_code=404, detail="Profile tidak ditemukan")
    return templates.TemplateResponse(request=request, name="profile_form.html", context={"p": dict(rows[0])})


# ──────────────────────────────────────────────────────────────────────
# Cari lowongan
# ──────────────────────────────────────────────────────────────────────
@router.get("/search", response_class=HTMLResponse)
async def search_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={"results": None, "portal": "all", "q": ""},
    )


@router.post("/search", response_class=HTMLResponse)
async def search_do(
    request: Request,
    keyword: str = Form(...),
    portal: str = Form("kalibrr"),
    limit: int = Form(15),
):
    fn = portals.PORTALS.get(portal)
    if fn is None:
        raise HTTPException(status_code=400, detail="Portal tidak dikenal")
    results = fn(keyword, limit)
    errors = [r for r in results if "error" in r]
    jobs = [r for r in results if "error" not in r]

    # Simpan hasil ke DB (skip duplikat)
    saved = 0
    for j in jobs:
        try:
            db.execute(
                """INSERT OR IGNORE INTO jobs (portal, company, title, url, location, salary,
                   description, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    j["portal"],
                    j["company"],
                    j["title"],
                    j["url"],
                    j.get("location"),
                    j.get("salary"),
                    j.get("description"),
                    db.now(),
                ),
            )
            saved += 1
        except Exception:  # noqa: BLE001
            continue

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "results": jobs,
            "errors": errors,
            "portal": portal,
            "q": keyword,
            "saved": saved,
        },
    )


# ──────────────────────────────────────────────────────────────────────
# Lamar (generate surat + antrian)
# ──────────────────────────────────────────────────────────────────────
@router.post("/apply")
async def apply(job_id: int = Form(...), profile_id: int = Form(...)):
    rows = db.query("SELECT id FROM applications WHERE profile_id = ? AND job_id = ?", (profile_id, job_id))
    if rows:
        app_id = rows[0]["id"]
        db.execute("UPDATE applications SET status='queued', updated_at=? WHERE id=?", (db.now(), app_id))
    else:
        app_id = db.execute(
            """INSERT INTO applications (profile_id, job_id, status, created_at, updated_at)
               VALUES (?,?, 'queued', ?, ?)""",
            (profile_id, job_id, db.now(), db.now()),
        )
    return RedirectResponse(url=f"/application/{app_id}", status_code=303)


@router.get("/application/{app_id}", response_class=HTMLResponse)
async def application_detail(request: Request, app_id: int):
    rows = db.query(
        "SELECT a.*, j.title, j.company, j.portal, j.url FROM applications a "
        "JOIN jobs j ON j.id = a.job_id WHERE a.id = ?",
        (app_id,),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Aplikasi tidak ditemukan")
    app = dict(rows[0])
    return templates.TemplateResponse(
        request=request,
        name="application.html",
        context={
            "app": app,
            "answers": _load_json(app.get("answers")),
            "can_auto": submit.can_auto_submit(app["portal"]),
            "submit_hint": submit.describe_submit_path(app["portal"]),
        },
    )


@router.post("/application/{app_id}/regenerate")
async def regenerate(app_id: int):
    """Buat ulang surat lamaran (misal user edit profile)."""
    db.execute("UPDATE applications SET status='queued', updated_at=? WHERE id=?", (db.now(), app_id))
    return RedirectResponse(url=f"/application/{app_id}", status_code=303)


# ──────────────────────────────────────────────────────────────────────
# API JSON (untuk integrasi/cron)
# ──────────────────────────────────────────────────────────────────────
@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_base": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "auto_submit": settings.auto_submit,
    }


@router.post("/api/apply/bulk")
async def apply_bulk(job_ids: list[int] = Form(...), profile_id: int = Form(...)):
    """Antrikan banyak lowongan sekaligus."""
    queued: list[int] = []
    for jid in job_ids:
        rows = db.query("SELECT id FROM applications WHERE profile_id = ? AND job_id = ?", (profile_id, jid))
        if rows:
            app_id = rows[0]["id"]
            db.execute("UPDATE applications SET status='queued', updated_at=? WHERE id=?", (db.now(), app_id))
        else:
            app_id = db.execute(
                """INSERT INTO applications (profile_id, job_id, status, created_at, updated_at)
                   VALUES (?,?, 'queued', ?, ?)""",
                (profile_id, jid, db.now(), db.now()),
            )
        queued.append(app_id)
    return {"queued": queued, "count": len(queued)}
