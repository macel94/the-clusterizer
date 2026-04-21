import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .database import engine, Base
from .routes import analyses

logging.basicConfig(level=logging.INFO)


def _ensure_analysis_progress_columns() -> None:
    statements = [
        "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS status_detail VARCHAR NOT NULL DEFAULT 'Queued for processing'",
        "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS progress_current INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS progress_total INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE analyses ADD COLUMN IF NOT EXISTS progress_unit VARCHAR NOT NULL DEFAULT 'steps'",
    ]
    with engine.connect() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    _ensure_analysis_progress_columns()
    yield


app = FastAPI(title="The Clusterizer API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyses.router, prefix="/api/analyses", tags=["analyses"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve built frontend (production)
_FRONTEND_DIST = "/app/frontend/dist"
if os.path.exists(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
