"""
Chess Analyzer API — entry point.

Start the server:
    uvicorn main:app --reload --port 8000

The app is structured in three layers:
    routers/    HTTP layer — request validation, response shaping
    services/   Business logic — PGN parsing, Stockfish, classification
    models/     Pydantic schemas — shared types used by both layers
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import FRONTEND_ORIGIN
from routers import analysis
from services.stockfish_service import StockfishService


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = StockfishService()
    engine.open()
    app.state.stockfish = engine
    yield
    engine.close()


app = FastAPI(
    title="Chess Analyzer API",
    version="0.1.0",
    description="Analyze chess games from PGN using Stockfish.",
    lifespan=lifespan,
)

# Allow the Vite dev server to reach this API without CORS errors.
# In production, replace FRONTEND_ORIGIN with your deployed frontend URL.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health_check() -> dict:
    """Confirm the API is reachable. Extend this to check engine status later."""
    return {"status": "ok"}
