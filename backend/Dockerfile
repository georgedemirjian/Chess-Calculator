# Backend image for any Docker host (Render, Fly.io, Cloud Run, etc).
# Build context: this directory (backend/). On Render set Root Directory = backend.

FROM python:3.11-slim

# Stockfish ships in Debian's main repo; install once at build time.
# /usr/games/stockfish is the binary path the apt package uses.
RUN apt-get update \
    && apt-get install -y --no-install-recommends stockfish \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps in their own layer so source changes don't bust the cache.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app (including ml/elo_model.joblib — required at startup).
COPY . .

# Override defaults from .env so the container doesn't depend on a .env file.
# FRONTEND_ORIGIN is overridden per environment in the host's dashboard.
ENV STOCKFISH_PATH=/usr/games/stockfish \
    PORT=8000

EXPOSE 8000

# Render injects $PORT — bind to it. Locally falls back to 8000.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
