import os
from dotenv import load_dotenv

load_dotenv()

# Path to the Stockfish binary — must be set in .env before running analysis.
STOCKFISH_PATH: str = os.getenv("STOCKFISH_PATH", "/usr/local/bin/stockfish")

# Depth passed to Stockfish's `go depth` command for each position.
STOCKFISH_DEPTH: int = int(os.getenv("STOCKFISH_DEPTH", "18"))

# Allowed CORS origin (the Vite frontend dev server).
FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
