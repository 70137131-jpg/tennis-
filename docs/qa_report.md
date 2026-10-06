# QA report

## Pipeline hardening — 2026-10-06

- All 147 Python tests and 30 frontend tests passed. Ruff, mypy, frontend type
  checks, the production build, and the change whitespace check passed.
- The eight changed detection/classification/assessment/configuration modules
  have 94.03% combined statement coverage. Assessment and runtime configuration
  validation have 100% coverage.
- Reproduced nine failures before fixing them: low-confidence feet affecting
  volley labels, unreliable ball evidence raising confidence, chronological
  limits selecting the wrong player, duplicate metric evidence inflating scores,
  missing contact still leaving measurements available, repeated sliding-window
  swings being accepted, and closed analyzers still accepting frames.
- Further regressions cover track reacquisition/teleports, discontinuous temporal
  classifier input, internal camera gaps, finite configuration/rule validation,
  corrupt official model weights, startup failure before native model allocation,
  and frame/pose memory cleanup when native close fails.
- Full repository coverage is 74.79%; the 85% gate remains failing because of
  existing uncovered account/gateway/release code and partially covered storage
  operations. No exclusions or threshold reductions were introduced.
- Native pose smoke tests passed. Physical camera trials, real tennis accuracy,
  and coach agreement remain unverified.

## Live shot and technique update — 2026-10-06

- All 106 Python tests and 30 frontend tests passed. Ruff, mypy, and the frontend
  production build passed.
- The 38 focused shot/assessment/live/pipeline tests passed. Statement coverage
  for `shots.py` and `assessment.py` is 100%; combined coverage with `live.py` is
  96.03%.
- Regressions cover near/far camera orientation, handedness, body translation,
  scale changes, small wrist jitter, uncertain shot labels, calibrated overheads,
  phase selection, clipped/occluded phases, applicable targets, disabled previews,
  and incomplete evidence that must not produce an overall score.
- Full repository coverage is 73.55%, so the configured 85% coverage gate fails.
  Existing `api/accounts.py`, `api/gateway.py`, and `src/courtside/release.py` have
  no test coverage, and storage operations have partial coverage. The coverage
  policy remains enforced.
- Actual MediaPipe inference still passes the no-person smoke test. Camera UI
  tests use simulated hardware; no physical camera trial, real tennis accuracy
  evaluation, or coach validation was performed in this update.

See `docs/shot_analysis.md` for the first camera trial and scoring boundaries.

## Previous verification — 2026-10-05

Verified locally on Windows, Python 3.11, Node 22. These are engineering checks;
synthetic fixtures do not establish tennis accuracy or coach agreement.

| Check | Result |
|---|---|
| Python unit/integration tests | 86 passed |
| Python statement coverage | 94.51%; enforced minimum 85% |
| Metrics, court geometry, schemas, SQLite store | 100% statement coverage |
| Live analysis engine | 93% statement coverage |
| Live WebSocket API | 86% statement coverage |
| Frontend API/component/camera tests | 19 passed |
| Python lint and typing | Ruff and mypy passed |
| Frontend build/type checking | Passed |
| Clean environment dependency install/check | Installed from project; `pip check` passed; exact set locked |
| Official pose task | SHA256 verified; real inference smoke passed |
| WebSocket/model integration | 20 synthetic 320×240 JPEG frames passed; no fabricated people/shots |
| Local round-trip benchmark | Mean 13.9 ms, p95 14.9 ms; person-free low-resolution fixture only |
| npm dependency audit | 0 reported vulnerabilities after test-runner update |
| Installation doctor / readiness | Local prerequisites pass; commercial release remains unverified |
| Docker Compose configuration | Validated with a disposable configuration token |
| Docker build / hosted CI | Not run: Docker daemon stopped; no Git remote configured |

The Python suite covers upload offsets/chunk limits, corruption/consent validation,
remote/token/Origin access, signed media/ranges/allowlists, review upserts,
settings, deletion, worker completion/failure/retry/cancellation/restart, retention,
pose/ball/court utilities, wrist peaks and shot types, confidence-gated metrics and
rules, overlay encoding/clips, classifier fitting, split leakage, manifest consent,
model promotion, CLI commands, installation readiness and simulated windows.

Live-specific checks cover JPEG dimensions/byte bounds, monotonic timestamps,
camera resize/history reset, bounded buffers, measured suggestions, unscored
low-confidence/no-player input, actual MediaPipe inference, initial socket auth,
junior consent, single-live-session exclusion, stop cleanup and oversized frames.
Disconnect races during error reporting and socket closing release the session;
optional trained classification selects the applicable coaching targets.
Frontend tests cover camera start/frame transport/stop, denied permission, insecure
contexts, offline state, junior consent controls and stable media URLs during
polling. They mock camera hardware; no physical camera was enabled during QA.

Browser checks: dashboard/library/report navigation, search and shot filters,
synthetic H.264 clip decode, no browser console errors, Live Court desktop layout,
390×844 mobile layout without horizontal overflow, mobile drawer, secure camera
setup/experimental preview controls and the camera-off state. The final live UI
screenshot is in `test-results/live-court.jpg`.

Known test warning: the current Starlette version deprecates its httpx TestClient
adapter; the suite passes. Migrate to its replacement when stabilizing the next
dependency upgrade. No warning is suppressed to claim a clean run.

Outstanding: real tennis/phone camera field test; pose/ball/tracking/contact/F1
benchmarks; coach-reviewed target ranges and ratings; IP/RTSP ingestion; Docker
runtime; HTTPS target-host setup; backup restore; academy pilot and commercial
release checks. See `eval/status.md` and `docs/known_issues.md`.
