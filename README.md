<div align="center">

<img src="frontend/public/favicon.png" alt="Elo Heaven logo" width="96" />

# Elo Heaven

**Paste a chess game. Get every move graded by Stockfish and an Elo estimate for both players.**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-38B2AC?logo=tailwindcss&logoColor=white)
![Stockfish](https://img.shields.io/badge/Engine-Stockfish-4B8B3B)
![XGBoost](https://img.shields.io/badge/ML-XGBoost-EB5E28)

### [🚀 Live demo → elo-heaven-chess.vercel.app](https://elo-heaven-chess.vercel.app/)

</div>


---

## What it does

- **Evaluates every move with Stockfish.** Each position is scored from White's point of view, and mate scores are normalized to ±10,000 cp.
- **Labels each move** as Best, Excellent, Good, Inaccuracy, Mistake, Blunder or Forced, based on how much **win probability** it gave up. It doesn't use raw centipawn loss for this, the same approach Lichess and Chess.com take.
- **Estimates each player's Elo from that one game** with an XGBoost model trained on about 43k Lichess games.
- **Shows the game interactively:** a board with the engine's best move drawn as an arrow, an eval bar, an evaluation graph, a move list with color-coded labels, and a per-player summary (ACPL, accuracy, label counts).
- **Includes five famous games, already analyzed:** Spassky–Fischer 1972, Kasparov–Topalov 1999, Botvinnik–Capablanca 1938, Gelfand–Nakamura 2010 and Aronian–Carlsen 2017. They load right away, with no wait for the engine.
- Light and dark themes, board flip, and move sounds.

## How it works

```
PGN ──► parse ──► Stockfish eval ──► classify ──► Elo model ──► React UI
        python-chess   per position     by WP loss    XGBoost       Recharts + react-chessboard
```

### Move classification

Win probability is a sigmoid of the engine eval, so it flattens out in positions that are already decided. Going from +12 to +9 barely matters. Going from +0.5 to −2 can lose the game. Grading moves by WP loss reflects that difference:

| Label | Win-probability loss |
|---|---|
| 🟢 **Best** | Engine's top move, < 2% |
| 🟢 **Excellent** | < 2% |
| 🟢 **Good** | < 5% |
| 🟡 **Inaccuracy** | < 10% |
| 🟠 **Mistake** | < 20% |
| 🔴 **Blunder** | ≥ 20% |
| ⚪ **Forced** | Only one legal move |

### Elo estimation

The model gets a short list of per-player features built from the classifications: average WP loss, effective ACPL, the rate of each move label, and the number of moves analyzed. It never sees raw evaluations.

| | |
|---|---|
| Training data | 42,727 player-games from Lichess, sampled evenly across Elo ranges |
| Split | 80 / 20, split **by player** (no player appears in both train and test) |
| Model | XGBoost (beat Ridge and Random Forest in testing) |
| Test MAE | ~307 Elo |
| R² | 0.59 |
| Within ±200 Elo | 40% |

One game is a noisy sample of a player's strength, so read the estimate as a rough performance rating, not a measurement. The analysis depth the model was trained at is saved inside the model file, and the backend runs Stockfish at that same depth. Features computed at any other depth would throw the predictions off.

## Project structure

```
├── backend/               FastAPI app
│   ├── main.py            Startup: one Stockfish process + ML model, loaded once
│   ├── routers/           HTTP layer (validation, response shaping)
│   ├── services/          PGN parsing, Stockfish, classification, ML inference
│   ├── models/            Pydantic schemas
│   ├── ml/                Trained model file (elo_model.joblib)
│   └── scripts/           Offline pre-analysis of the example games
├── frontend/              React + Vite + TypeScript + Tailwind
│   └── src/
│       ├── api/           All network calls
│       ├── components/    Board, eval bar/graph, move list, summary, …
│       └── lib/           Shared types and helpers
└── training/              Offline ML pipeline (collect → extract → split → train)
```

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 20+
- [Stockfish](https://stockfishchess.org/download/): `brew install stockfish` on macOS, `apt install stockfish` on Debian/Ubuntu

### Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cp backend/.env.example backend/.env   # set STOCKFISH_PATH
cd backend
uvicorn main:app --reload --port 8000
```

Interactive API docs are at <http://localhost:8000/docs>.

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The frontend calls `http://localhost:8000/api` by default. To use a different backend, set `VITE_API_BASE` (see `frontend/.env.example`).

### Configuration

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `STOCKFISH_PATH` | `backend/.env` | `/usr/local/bin/stockfish` | Path to the engine binary |
| `STOCKFISH_DEPTH` | `backend/.env` | `18` | Search depth (ignored when the ML model is loaded; the model's training depth is used instead) |
| `FRONTEND_ORIGIN` | `backend/.env` | `http://localhost:5173` | Allowed CORS origins, comma-separated |
| `VITE_API_BASE` | `frontend/.env.local` | `http://localhost:8000/api` | Backend URL |

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/analyze` | Analyze a game. Body: `{ "pgn": "..." }` |

```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"pgn": "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *"}'
```

The response includes game metadata and, for every move, the SAN/UCI, the FENs before and after the move, evals before and after, centipawn loss, win-probability loss, the classification and the engine's best reply. It ends with per-player ACPL, average WP loss and the Elo estimate. Invalid PGNs return `422` with a readable `detail` message.

## Training the model

The trained model is already committed to `backend/ml/`. To build a new one:

```bash
cd training
pip install -r requirements.txt

python collect_data.py --months 2024-01 --per-player-cap 10   # stream Lichess games, sampled evenly across Elo ranges
python extract_features.py                                     # run Stockfish, write data/features.csv
python split_dataset.py                                        # split into train/test by player
python train.py                                                # compare models, save the best one to backend/ml/
```

Training and inference use the same feature-extraction function, so the features the model sees in production are computed exactly as they were in training.

After changing the model or the response schema, regenerate the example games:

```bash
cd backend && python scripts/generate_examples.py
```

## Deployment

- **Backend:** `backend/Dockerfile` installs Stockfish from apt and starts uvicorn on `$PORT`. It runs on Render, Fly.io, Cloud Run and similar hosts. Set the root directory to `backend/` and set `FRONTEND_ORIGIN` to your frontend URL.
- **Frontend:** a static Vite build that works on Vercel or Netlify. Set `VITE_API_BASE` to your backend URL with `/api` on the end.

## Roadmap

- [x] PGN parsing and move metadata
- [x] Stockfish evaluation and move classification
- [x] Elo estimation from a single game
- [x] React frontend (board, eval graph, move list, summary)
- [ ] Import games by Chess.com username
- [ ] AI coaching insights

## Acknowledgements

- [Stockfish](https://stockfishchess.org/), the engine behind every evaluation
- [python-chess](https://python-chess.readthedocs.io/) for PGN parsing and board logic
- [Lichess open database](https://database.lichess.org/), where the training games come from
- [react-chessboard](https://github.com/Clariity/react-chessboard) and [Recharts](https://recharts.org/)
