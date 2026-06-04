import os
from dotenv import load_dotenv

load_dotenv()

# Path to the Stockfish binary — must be set in .env before running analysis.
STOCKFISH_PATH: str = os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish")

# Depth passed to Stockfish's `go depth` command for each position.
STOCKFISH_DEPTH: int = int(os.getenv("STOCKFISH_DEPTH", "18"))

# Allowed CORS origins (the Vite frontend, possibly multiple). Comma-separated
# list — e.g. "http://localhost:5173,https://elo-heaven.vercel.app" — so dev
# and production can share one config.
FRONTEND_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
    if o.strip()
]
