# Courtside

A private, local tennis live-coaching workspace with a mobile React interface,
FastAPI API, SQLite job queue, MediaPipe pose baseline, annotated H.264 clips,
traceable metrics, court calibration, session history and coach reviews. Live camera
frames are analyzed over WebSocket for player skeletons, ball candidates and
experimental per-shot ratings/suggestions; no recording is required.

**Status:** working local evaluation MVP. The supplied demo is synthetic. Tennis
classification/segmentation accuracy, coach agreement and academy readiness have
not been established on real sessions. Real coaching tips stay disabled until a
qualified coach approves the rule configuration for offline reports. Live Court
offers an explicitly labeled experimental preview of measured ratings/suggestions.

## Run on Windows

Use Python 3.11 and Node.js 22. Run from this folder:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -c requirements.lock -e '.[vision,dev]'
npm ci --cache .npm-cache
python data\download_model.py
npm run build
.venv\Scripts\courtside.exe doctor
.venv\Scripts\courtside.exe serve
```

Open [Live Court](http://127.0.0.1:8000/#live), choose your webcam/phone camera,
confirm processing permission and click **Start live feed**. The browser asks for
camera permission. Camera frames are not recorded or saved. Live experimental
coaching is explicitly labeled and can be disabled in the camera setup.

See `docs/shot_analysis.md` for shot-type evidence, phase-based technique checks,
scoring limits, and the first live camera trial.

For archived recordings, switch **Demo workspace** to **Your
sessions** to upload your recordings. Settings accepts the optional workspace
access token. The server starts its local worker automatically.

This project's clean verification environment is `.qa-venv`; it can run the same
commands by replacing `.venv` with `.qa-venv`. A fresh virtual environment avoids
conflicting global OpenCV installations.

On Linux/macOS, substitute `.venv/bin/python` and `.venv/bin/courtside`.
Environment variables in `.env.example` are documentation: the local CLI does
not automatically load a `.env` file. Set them in the shell before starting.

## Analyze without the web app

```powershell
.venv\Scripts\courtside.exe analyze session.mp4 --out out\session
.venv\Scripts\courtside.exe stream session.mp4 --out out\stream
```

`analyze` writes `report.json`, `poses.json`, `ball.json`, `court.json`,
`annotated.mp4`, a poster and one clip for every detected shot candidate. Use
`--handedness left`, `--backhand-style one-handed` and `--court corners.json`
when appropriate. Court corners are normalized and ordered far-left, far-right,
near-right, near-left. `stream` is a simulated-live file benchmark, not a live
camera service.

## Verify

```powershell
.venv\Scripts\python.exe -m pytest --cov --cov-report=term-missing
.venv\Scripts\python.exe -m ruff check src api worker tests eval
.venv\Scripts\python.exe -m mypy src/courtside api worker
npm test
npm run build
```

Python coverage has an 85% minimum. Synthetic demo generation is excluded;
inference, rendering, API, worker, training and CLI code are included. The real
pose-model smoke test requires the downloaded official model. CI downloads and
verifies it. See `docs/qa_report.md` for measured results and browser checks.

## Training and deployment

The current pose model is a general pretrained model; the default tennis labels
are wrist-motion heuristics. A NumPy temporal-feature classifier can be trained
on your separately consented, manually reviewed data. Train/validation/test
splits must be disjoint by session, every player, original-video hash and pose
export hash. All four classes and minimum held-out support are required before
promotion. See `docs/training.md`.

Local/LAN deployment, Docker configuration, HTTPS, storage, restart and backup
instructions are in `docs/deployment.md`. Docker recipes are provided; the image
has not been built here because the Docker daemon is not running. No cloud resources were
created and no hosting subscription is required for local use.

See `docs/architecture.md`, `docs/camera_setup.md`, `docs/known_issues.md`,
`docs/licenses.md`, `data/README.md` and `eval/status.md` for boundaries and
outstanding empirical phase gates.
