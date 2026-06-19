"""FastAPI application factory for the Control Room."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from viral_editor.api.routes import jobs as jobs_routes
from viral_editor.api.schemas import HealthResponse
from viral_editor.api.store import JobStore

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Viral Editor Control Room",
        description="Local API for the retention video editor UI.",
        version="0.1.0",
    )

    app.state.job_store = JobStore()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            "http://127.0.0.1:8765",
            "http://localhost:8765",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            ffmpeg_available=shutil.which("ffmpeg") is not None
            and shutil.which("ffprobe") is not None,
        )

    app.include_router(jobs_routes.router, prefix="/api")

    if WEB_DIST.is_dir():
        app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
    else:

        @app.get("/")
        def ui_placeholder() -> JSONResponse:
            return JSONResponse(
                {
                    "message": "Control Room UI not built yet.",
                    "hint": "Run `npm install && npm run build` in web/, or `npm run dev` for development.",
                    "api": "/api/health",
                }
            )

    return app
