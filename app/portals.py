"""Job parsers/scrapers untuk berbagai portal.

Catatan penting: portal lowongan (Kalibrr, Glints, JobStreet, LinkedIn) adalah situs
dinamis dengan anti-bot. Modul ini diprioritkan untuk:
  1. Endpoint publik/API internal yang stable (Kalibrr punya GraphQL publik)
  2. Fallback ke browser automation saat mode browser diaktifkan

Setiap parser mengembalikan list of job dict dengan field seragam:
  {portal, company, title, url, location, salary, description}
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

TIMEOUT = 30.0


def _norm(text: str | None) -> str | None:
    return text.strip() if isinstance(text, str) else None


# ──────────────────────────────────────────────────────────────────────
# Kalibrr — endpoint JSON publik (ditemukan dengan inspeksi client bundle).
# Domain .id untuk lowongan Indonesia, .com untuk Filipina/internasional.
# ──────────────────────────────────────────────────────────────────────
KALIBRR_BASE = "https://www.kalibrr.id"
KALIBRR_SEARCH = f"{KALIBRR_BASE}/api/job_board/search"


def search_kalibrr(keyword: str, limit: int = 20, country: str | None = None) -> list[dict[str, Any]]:
    """Cari lowongan di Kalibrr via endpoint JSON publik (tanpa login).

    Domain .id sudah mengembalikan lowongan Indonesia secara default. Parameter
    country JANGAN dikirim — saat diuji, country=ID malah mengosongkan hasil.
    """
    params = {"text": keyword, "limit": limit}
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(KALIBRR_SEARCH, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return [{"error": f"kalibrr: {exc}"}]

    jobs: list[dict[str, Any]] = []
    for node in data.get("jobs", [])[:limit]:
        loc = node.get("google_location") or {}
        addr = loc.get("address_components") or {}
        company = node.get("company") or {}
        jobs.append(
            {
                "portal": "kalibrr",
                "title": _norm(node.get("name")) or "?",
                "company": _norm(node.get("company_name")) or _norm(company.get("name")) or "?",
                "url": f"{KALIBRR_BASE}/c/{company.get('code', '')}/j/{node.get('id', '')}/{node.get('slug', '')}",
                "location": _norm(addr.get("city")) or _norm(addr.get("country")),
                "salary": _format_salary_kalibrr(node),
                "description": _strip_html(_norm(node.get("description")) or ""),
            }
        )
    return jobs


def _format_salary_kalibrr(node: dict) -> str | None:
    cur = node.get("salary_currency") or "IDR"
    lo, hi = node.get("base_salary"), node.get("maximum_salary")
    if lo is None and hi is None:
        return None
    if lo is None:
        return f"{cur} up to {hi:,.0f}"
    if hi is None:
        return f"{cur} {lo:,.0f}"
    return f"{cur} {lo:,.0f} - {hi:,.0f}"


def _strip_html(text: str) -> str:
    """Buang tag HTML dari deskripsi lowongan (Kalibrr mengembalikan HTML)."""
    return re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").strip()


# ──────────────────────────────────────────────────────────────────────
# Glints — situs dinamis, scrape HTML dasar (rapuh). Browser mode preferred.
# ──────────────────────────────────────────────────────────────────────
def search_glints(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    """Glints V4 adalah SPA berat. Tanpa browser, coba endpoint JSON mereka."""
    url = "https://api-2.glints.com/api/v4/search/jobs"
    params = {"search": keyword, "limit": limit, "country": "ID"}
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return [{"error": f"glints: {exc}"}]

    jobs: list[dict[str, Any]] = []
    items = data.get("data", {}).get("jobs", [])
    if isinstance(items, dict):  # struktur {jobs: {...}} di beberapa versi
        items = items.get("jobs", [])
    for node in items[:limit]:
        try:
            company = node.get("company") or {}
            jobs.append(
                {
                    "portal": "glints",
                    "title": _norm(node.get("title")) or "?",
                    "company": _norm(company.get("name")) or "?",
                    "url": f"https://glints.com/id/opportunities/jobs/{node.get('id','')}",
                    "location": _norm(node.get("locationName") or node.get("city")),
                    "salary": _norm(node.get("salaryRangeName")),
                    "description": _norm(node.get("jobDescription")) or "",
                }
            )
        except AttributeError:
            continue
    return jobs


# ──────────────────────────────────────────────────────────────────────
# JobStreet / LinkedIn — anti-bot ketat. HTTP murni hampir pasti diblokir.
# ──────────────────────────────────────────────────────────────────────
def search_jobstreet(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    """JobStreet memakai Akamai Bot Manager. Tanpa browser, return info saja."""
    return [
        {
            "error": (
                "jobstreet: membutuhkan browser automation (anti-bot Akamai). "
                "Aktifkan AUTOLAMAR_BROWSER=true dan login dulu."
            )
        }
    ]


def search_linkedin(keyword: str, limit: int = 20) -> list[dict[str, Any]]:
    """LinkedIn wall login + anti-bot. Return info saja tanpa browser."""
    return [
        {
            "error": (
                "linkedin: membutuhkan browser automation + login. "
                "Aktifkan AUTOLAMAR_BROWSER=true dan login dulu."
            )
        }
    ]


# ──────────────────────────────────────────────────────────────────────
# Direct company career pages — generic form detector (browser mode)
# ──────────────────────────────────────────────────────────────────────
def submit_to_career_page(url: str, profile: dict[str, Any], cover_letter: str) -> dict[str, Any]:
    """Buka career page, deteksi form, isi otomatis. Butuh browser mode."""
    return {
        "error": (
            "career page: browser automation belum diaktifkan. "
            "Set AUTOLAMAR_BROWSER=true untuk fitur ini."
        )
    }


PORTALS = {
    "kalibrr": search_kalibrr,
    "glints": search_glints,
    "jobstreet": search_jobstreet,
    "linkedin": search_linkedin,
}
