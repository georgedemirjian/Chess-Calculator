# Chess Analyzer — CLAUDE.md

Working guide for Claude Code. Read this before touching any file.

---

## Project Purpose

A full-stack chess game analyzer that accepts a PGN, evaluates every move with
Stockfish, classifies move quality, computes centipawn loss statistics, and
uses a trained ML model to estimate the player's Elo performance from a single
game. The goal is a clean, maintainable tool — not a production SaaS platform.

**Planned feature sequence (do not skip ahead):**
1. PGN parsing + move metadata ✅
2. Stockfish evaluation + move classification 🔜
3. Elo estimation via scikit-learn ML 🔜
4. React frontend (eval graph, move list, summary) 🔜
5. Chess.com username game import 🔜
6. AI coaching insights 🔜

---

## Architecture Overview

```
chess-calculator/
├── backend/          FastAPI — all server-side logic
│   ├── main.py       App entry point, CORS, lifespan hooks
│   ├── config.py     All env var reads in one place
│   ├── routers/      HTTP layer only — validation + response shaping
│   ├── services/     Business logic — parsing, Stockfish, ML, classification
│   └── models/       Pydantic schemas shared by routers and services
├── frontend/         React + Vite (not yet scaffolded)
└── .venv/            Python virtual environment (project root, not inside backend/)
```

The backend follows a strict **three-layer rule**:

```
routers/ → services/ → models/
```

- Routers know nothing about chess or Stockfish. They validate input, call a
  service function, and shape the response.
- Services contain all logic. They do not import from `routers/`.
- Models (`schemas.py`) are shared types. They do not import from either layer.

No layer skips another. Routers never call `chess.pgn` directly.
Services never call `HTTPException`.

---

## Folder Structure Philosophy

**Backend:** One file per concern. If a service file exceeds ~150 lines, split
it. The current services are:

| File | Responsibility |
|---|---|
| `pgn_parser.py` | PGN → structured move dicts. No Stockfish dependency. |
| `stockfish_service.py` | Engine lifecycle + position evaluation. |
| `classifier.py` | Centipawn loss → move label + ACPL computation. |
| `ml_service.py` | Feature extraction + Elo prediction. *(planned)* |

When adding ML: create `backend/services/ml_service.py` and
`backend/ml/` for model artifacts (`.joblib` files, feature lists).
Do **not** put model files inside `services/`.

**Frontend:** One component per UI concern. Shared utilities go in `src/lib/`.
API calls go in `src/api/` — never inline fetch calls inside components.

---

## Running the Project

```bash
# Backend
source .venv/bin/activate        # virtual env lives at project root
cd backend
uvicorn main:app --reload --port 8000

# Frontend (once scaffolded)
cd frontend
npm run dev                       # Vite dev server on port 5173
```

Environment: copy `backend/.env.example` to `backend/.env` and fill in
`STOCKFISH_PATH`. All other settings have sensible defaults.

---

## Backend Conventions

### General
- Python 3.11+. Use built-in type hints (`list[str]`, `dict[str, int]`), not
  `typing.List` / `typing.Dict` — except where Pydantic forces it.
- All environment variables are read **only** in `config.py`. Services import
  from `config`, never from `os` directly.
- Module-level docstrings on every service file explaining its single
  responsibility and what it does NOT do.

### Pydantic schemas
- `Optional[X] = None` for fields that are not yet populated (e.g., eval fields
  before Stockfish runs). Never use sentinel values like `-1` or `""`.
- Validate at the boundary (`AnalyzeRequest`) — not inside services.
- `field_validator` for non-trivial input rules; keep validators small.

### Services
- Pure functions preferred over classes. Use a class only when shared state
  is genuinely needed (e.g., `StockfishService` holds an open engine process).
- Raise `ValueError` with human-readable messages. The router converts these
  to `HTTPException(status_code=422)`. Services never raise HTTP exceptions.
- Functions that extract data from a board state must be called **before**
  `board.push(move)` — document this constraint with a comment when it applies.

### Stockfish integration
- One engine process, opened at app startup in `main.py`'s `lifespan` context
  manager, closed on shutdown. Never open a subprocess per request.
- Stockfish calls are synchronous/blocking. Always run them inside
  `asyncio.get_event_loop().run_in_executor(None, fn, args)` to avoid
  blocking FastAPI's event loop.
- Store all centipawn evaluations from **White's perspective** (positive =
  White better, negative = Black better). Normalize mate scores to ±10 000 cp.
- Analysis depth is controlled by `STOCKFISH_DEPTH` in `.env` (default: 18).

### ML pipeline
- Feature extraction lives in `ml_service.py`, not in the router or classifier.
- Trained model artifacts (`.joblib`) go in `backend/ml/`. Load them once at
  startup, not on every request.
- The ML model is trained offline; do not retrain in the request path.
- Features should be computable from move classifications and centipawn loss
  alone — do not leak raw evals into the model without feature engineering.

---

## Frontend Conventions

*(Frontend is not yet scaffolded. Apply these rules when it is created.)*

### Component structure
- One component per file. Keep components under ~100 lines; split if larger.
- No inline API calls. All `fetch` / `axios` calls belong in `src/api/`.
- Lift state to the nearest common ancestor — no global state library unless
  the component tree genuinely demands it.
- Props typed with TypeScript interfaces (use Vite's TS template from the start).

### State
- `App.jsx` (or `App.tsx`) owns top-level state: `pgn`, `result`, `loading`, `error`.
- Components receive data as props and emit events via callbacks — they do not
  fetch their own data.

### API layer (`src/api/analyze.js`)
- One function per API endpoint. Returns the parsed JSON or throws an `Error`
  with the server's `detail` message.
- Never expose raw `Response` objects to components.

### Evaluation graph
- Use **Recharts** (small bundle, React-native API, no config overhead).
- Cap Y-axis display at ±1 000 cp even when mate scores (±10 000) are present.
- Always render from White's perspective; label the axis clearly.

---

## API Design Conventions

- All routes are prefixed `/api/`. No unversioned top-level routes.
- HTTP status codes:
  - `200` — success
  - `422` — user-supplied data is invalid (bad PGN, empty input)
  - `500` — unexpected server error (engine crash, model load failure)
- Response bodies always return JSON. Error responses use FastAPI's default
  `{ "detail": "..." }` shape — do not invent custom error envelopes.
- Do not add query parameters for things that belong in the request body.
- `GET /api/health` — health check; extend it later to verify engine status.

**Current endpoints:**

| Method | Path | Status |
|---|---|---|
| GET | `/api/health` | ✅ |
| POST | `/api/analyze` | Partial — parsing done, evals pending |

---

## Error Handling Philosophy

- **Validate at boundaries, trust internals.** `AnalyzeRequest` validates the
  raw PGN string. Once inside `pgn_parser.parse()`, trust that the input is a
  non-empty string — do not re-validate.
- **Fail loudly with context.** A `ValueError` like `"Illegal move at ply 7
  (Nxf3): move not in legal moves"` is far more useful than `"Parse error"`.
- **Do not swallow exceptions.** If Stockfish crashes, propagate the error — do
  not return zeroed-out data silently.
- **Do not add fallbacks for impossible states.** If `board.piece_at()` returns
  `None` on a move that python-chess declared legal, that is a library bug —
  guard it with a comment explaining why the guard exists, not silently.

---

## Code Quality Standards

- **Comments explain WHY, not WHAT.** A comment on `board.san(move)` should
  say "must be called before push — SAN requires the pre-move position", not
  "generates the SAN string".
- **No multi-paragraph docstrings.** Module-level docstrings: 2–4 sentences.
  Function docstrings: one sentence + `Args:` / `Raises:` blocks only when
  non-obvious. Skip docstrings on trivial functions.
- **No dead code.** Remove placeholder `pass` bodies as soon as they are
  implemented. Do not leave `# TODO` comments for known upcoming work — track
  that in conversation instead.
- **No premature abstraction.** Three similar blocks is not a reason to extract
  a helper. Extract when there are four or more, or when the duplication
  genuinely hides intent.
- **Imports:** stdlib → third-party → local, separated by blank lines.
  No wildcard imports.

---

## Modularity Requirements

- A new developer should be able to understand any single service file without
  reading the others. Each file is a complete, self-contained unit of logic.
- If implementing a new feature requires changes in more than three files, stop
  and reconsider the design before writing code.
- The ML pipeline should be removable without touching the PGN parser or
  Stockfish service. The Stockfish service should be removable without touching
  the ML pipeline. These are separate concerns.
- Do not put two distinct responsibilities in one file. `classifier.py` classifies
  moves. When ML feature extraction is added, it goes in `ml_service.py`.

---

## Performance Considerations

- Stockfish is the bottleneck. For a 40-move game at depth 18,
  expect 4–12 seconds of analysis time. That is acceptable for an MVP.
- Do not add caching, background task queues, or async job systems unless the
  user asks. `run_in_executor` is sufficient.
- The ML model must load once at startup and be reused across requests.
  Model loading at request time is not acceptable.
- Frontend: do not load Stockfish in the browser. All analysis happens server-side.

---

## Styling and UI Guidelines

*(Apply when frontend is scaffolded.)*

- Use **Tailwind CSS** for styling — no CSS-in-JS, no custom CSS files unless
  absolutely necessary.
- Dark theme by default — a dark board and dark background are standard for
  chess UIs.
- Move classification badges use consistent colors:
  - Best / Excellent → green
  - Inaccuracy → yellow
  - Mistake → orange
  - Blunder → red
- Keep the layout simple: PGN input → analysis view. No tabs, no modal stacks,
  no sidebars until the feature set genuinely demands them.
- The evaluation graph and move list should be the primary visual elements —
  not decorative chrome.

---

## Things to Avoid

| Avoid | Reason |
|---|---|
| Redis, Celery, task queues | Not needed at this scale; `run_in_executor` is enough |
| Database / ORM | No persistence required in MVP |
| Authentication / user accounts | Out of scope until explicitly requested |
| Multiple PGN games in one request | Parse only the first game from each PGN string |
| Opening a new Stockfish process per request | Too slow; use the lifespan singleton |
| Calling `board.push()` before `board.san()` | SAN requires the pre-move position |
| Storing evals from the moving player's POV in the API response | Always store as White's POV in the response; convert internally for cp_loss |
| Feature flags, backwards-compat shims | Just change the code |
| Global exception handlers that swallow errors | Errors should surface with full context |
| Rewriting working files when adding a feature | Make targeted edits; preserve existing patterns |

---

## Git Workflow

- One commit per logical unit of work (e.g., "implement Stockfish service",
  not "wip" or "fix stuff").
- Commit messages: imperative mood, present tense ("add StockfishService",
  not "added" or "adds").
- Main branch only for this project at MVP stage. Branch when features become
  large enough to warrant isolation.
- Do not commit `.env` (it is gitignored). `.env.example` is committed and
  kept up to date whenever a new env var is added.

---

## Incremental Development Philosophy

Build in the order the pipeline flows:

```
PGN input → parse → evaluate → classify → predict → display
```

Do not start the frontend until the backend API returns real Stockfish data.
Do not start the ML model until there is a dataset of real game analyses to
train on. Do not add Chess.com import until PGN paste works end-to-end.

Each step should be testable in isolation before the next begins:
- PGN parser: test with a known game, verify move metadata
- Stockfish service: test with a known FEN, verify eval value
- Classifier: test with known cp_loss values, verify label output
- ML model: test with a known feature vector, verify predicted Elo is plausible
- Frontend: test with the real API running locally, not a mock

When making changes:
- Edit only the files the task requires. Do not refactor adjacent code unless
  it directly blocks the current task.
- If a change to a service requires updating the schema or router, update all
  three together in the same edit session.
- Leave `# 🔜 next step` markers in routers to indicate where the next pipeline
  stage hooks in — remove them once implemented.
