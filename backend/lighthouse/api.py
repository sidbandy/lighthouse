"""FastAPI application.

Thin transport layer: routers translate HTTP to service calls and back, and
hold no business logic of their own.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.router import router as corpus_router
from .discover.router import router as discover_router
from .ingest.router import router as ingest_router
from .network.router import router as network_router
from .track.router import router as track_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="Lighthouse",
    description="A command center for the software engineering internship and new-grad search.",
    version="0.1.0",
)

# Single-user and local-only for now, so the Vite dev server is the only origin
# that needs to reach the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(corpus_router)
app.include_router(discover_router)
app.include_router(ingest_router)
app.include_router(network_router)
app.include_router(track_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
