"""Ambil LITELLM_MASTER_KEY untuk proxy LiteLLM di port 4000."""
from __future__ import annotations

import os
from pathlib import Path

# .env litellm asli sudah terhapus bersama foldernya; backup tarball masih ada.
_LITELLM_ENVS = [
    Path("/home/agentuser/.litellm/.env"),
    Path("/tmp/.litellm/.env"),
]


def _from_litellm_env() -> str | None:
    """Baca LITELLM_MASTER_KEY dari .env litellm."""
    for path in _LITELLM_ENVS:
        if path.exists():
            for line in path.read_text().splitlines():
                if line.startswith("LITELLM_MASTER_KEY="):
                    return line.split("=", 1)[1].strip()
    return None


def resolve_llm_key() -> str:
    """Urutan: env eksplisit > .env litellm (master key).

    CATATAN PENTING: JANGAN pakai CUSTOM_API_KEY dari ~/.hermes/.env — itu adalah
    key 9Router (port 20128), bukan master key LiteLLM (port 4000). Proxy LiteLLM
    menolaknya dengan "Invalid API key" / "No connected db".
    """
    key = os.getenv("AUTOLAMAR_LLM_KEY")
    if key:
        return key
    key = _from_litellm_env()
    if key:
        return key
    return "sk-anything"
