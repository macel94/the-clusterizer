import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .database import engine, Base
from .routes import analyses

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="The Clusterizer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)


app.include_router(analyses.router, prefix="/api/analyses", tags=["analyses"])


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve built frontend (production)
_FRONTEND_DIST = "/app/frontend/dist"
if os.path.exists(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
