# Changelog

## Unreleased

- Hardened tracking continuity, live peak deduplication, configuration validation,
  model integrity checks, geometry/ball confidence gates, unique metric evidence,
  and resource cleanup. Pipeline version is now `baseline-3`.

- Live shot candidates use torso-relative wrist motion, anatomical shoulder
  orientation, scale-aware ball proximity, and explicit unknown classifications.
- Shot evidence and phase-based technique checks explain detection confidence,
  applicable target ranges, and missing measurements. Incomplete evidence does
  not produce an overall score; experimental preview controls remain respected.
- Shared live/uploaded phase measurements reject stale and clipped phases and
  select only targets applicable to the identified shot type. Pipeline version
  was advanced to `baseline-2`; coaching target ranges remain unchanged and unvalidated.

## 0.1.0 — 2026-10-05

- Live Court is the main entry point: webcam/phone capture, authenticated
  WebSocket inference, live skeleton/ball overlay, bounded history, per-shot
  target-match ratings, measured experimental suggestions and optional spoken tips.
- Adaptive capture, connection watchdog, stop/unmount camera cleanup, junior
  consent and optional live court calibration; frames are never saved.
- Live CPU/model transport smoke test and camera lifecycle/WebSocket tests.
- Stable signed media URLs during polling prevent archived clips restarting.

- React dashboard, session library, shot reports, progress, coaching notes,
  settings, accessible dialogs and a labeled synthetic demo workspace.
- Resumable 4 MB uploads, explicit processing/junior consent, durable SQLite
  queue, local worker, failed-job retry, artifact deletion and retention cleanup.
- Two-pose MediaPipe inference, temporal tracking/smoothing, manual court
  homography, HSV/motion ball baseline, short-gap interpolation and wrist-based
  shot candidates. H.264 full-session and per-shot skeleton overlays.
- Confidence-gated 2D metrics and versioned YAML rules. Real tips disabled
  until coach validation. Private signed media URLs and optional workspace token.
- Trainable temporal-feature shot classifier with consent/provenance checks,
  three disjoint splits, deterministic fitting, held-out report, per-class
  promotion gates and opt-in pipeline inference.
- Model SHA256 verification, installation doctor/readiness endpoint, locked
  dependencies, CI, Docker recipes and reproducible setup/training documentation.
- Expanded Python unit/integration coverage and React component/API tests.
- Fixed total shot limits across both players and rejected nonfinite schema values.

Real tennis benchmarks, coach review, live-device trials, hosted deployment and
an academy pilot remain outstanding; synthetic checks do not establish accuracy.
