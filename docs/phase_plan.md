# Implementation decisions and phase gates

Ali authorized the wisest defaults on 2026-10-05 and requested continuous implementation.
Defaults: fixed baseline footage; selectable left/right handedness and one/two-handed backhand;
React + Vite; FastAPI; SQLite durable queue; private local filesystem; token access;
local CPU MediaPipe baseline with optional external model; no third-party training datasets.

Phase 0: scaffold, CLI, licenses, camera guidance, CI.
Phase 1: MediaPipe multipose, temporal smoothing, wrist contact baseline, annotated video,
versioned JSON. Phase 2: manually calibrated homography, geometry-based IDs, color/motion
ball tracker and short-gap interpolation. Phase 3: confidence-gated 2D metrics, pure YAML
feedback engine, clips. Phase 4: upload, durable jobs, reports, history, consent and deletion.
Phase 5: bounded simulated-live windows and latency diagnostics.
Phase 6: coach corrections, progress and retention controls; academy pilot remains external.

Engineering checks can be verified on synthetic clips. Empirical phase gates cannot pass
without Ali's held-out tennis recordings, a qualified coach and a pilot academy. These are
tracked explicitly, without invented F1, latency, coach agreement or deployment claims.
The app is a local evaluation MVP, not a coach-validated commercial release.

2026-10-05 scope update: Ali requested live camera coaching as the primary flow.
Live Court now captures webcam/phone frames, sends them over an authenticated
WebSocket, tracks poses/ball candidates in memory and returns per-shot measured
ratings/suggestions. Preview rules are explicitly experimental and optional.
Offline uploads are secondary. Real-camera/tennis accuracy and target-device
latency gates remain pending; synthetic WebSocket checks are recorded separately.
