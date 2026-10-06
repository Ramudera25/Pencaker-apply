"""Entry point AutoLamar — FastAPI + Uvicorn."""
from __future__ import annotations

import uvicorn
from fastapi import FastAPI

from . import db, worker
from .config import settings
from .keys import resolve_llm_key
from .routes import router

# Resolve LLM key dari .env litellm (proxy memerlukan master key)
settings.llm_api_key = resolve_llm_key()

app = FastAPI(title="AutoLamar", description="Auto-lamar kerja dibantu AI", version="0.1.0")

app.include_router(router)
db.init_db()
worker.start()


def main() -> None:
    uvicorn.run(
        "autolamar.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
