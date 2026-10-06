# Repository Guidelines

## Project Structure & Module Organization

Courtside is a local tennis coaching workspace. `src/courtside/` contains analysis, tracking, metrics, training, and CLI code; `api/` contains FastAPI endpoints and SQLite storage; `worker/` processes queued sessions. React/TypeScript code and colocated tests live in `web/src/`, with static assets in `web/public/`. Python tests live in `tests/`. Use `configs/` for YAML settings, `eval/` for evaluation, and `docs/` for architecture, deployment, and training guidance. `storage/` and `models/` hold ignored runtime data.

## Build, Test, and Development Commands

Use Python 3.11 and Node.js 22. Create and activate a virtual environment before running Python commands. Run these from the repository root:

- `python -m pip install -c requirements.lock -e ".[vision,dev]"`: install constrained Python dependencies.
- `npm ci`: install locked frontend dependencies.
- `python data/download_model.py`: download and verify the official pose model.
- `courtside serve`: start the API and embedded worker at `127.0.0.1:8000`.
- `npm run dev`: start Vite at port 5173, proxying `/api` to the backend.
- `npm run build`: type-check and build the frontend into `web/dist/`.
- `npm run check`: run frontend TypeScript checks.
- `courtside doctor`: check installation readiness.

## Coding Style & Naming Conventions

Use four-space Python indentation, `snake_case` functions/modules, and `PascalCase` classes. Follow Ruff's import ordering and configured 110-character line length; run `python -m ruff check src api worker tests eval` and `python -m mypy src/courtside api worker`.

Use two-space TypeScript indentation, single quotes, semicolons, `PascalCase` component filenames, and `camelCase` functions/variables. TypeScript uses strict checking; no frontend formatter or ESLint configuration is present.

## Testing Guidelines

Run `python -m pytest --cov --cov-report=term-missing`; Python coverage must remain at least 85%. Name tests `tests/test_*.py`. The real-model smoke test requires the downloaded pose model. Run `npm test` for Vitest and React Testing Library tests in jsdom; use `*.test.ts` or `*.test.tsx` beside frontend modules. Add regression tests for behavioral changes. CI verifies Windows and Linux.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects, such as `Fix camera cleanup on disconnect`. PRs should explain behavior changes, link relevant issues, report verification results, and include screenshots for UI changes.

## Security & Configuration

Never commit tokens, recordings, SQLite databases, or model weights. Set environment variables explicitly; the CLI does not load `.env` automatically. Require `COURTSIDE_TOKEN` for non-loopback access. Preserve processing/training consent checks, live-frame privacy, and experimental coaching labels.
