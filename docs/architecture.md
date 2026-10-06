# Architecture

The React app consumes versioned report JSON. FastAPI validates uploads and
stores options/consent, metadata, status and reports in SQLite. Original videos
and derived artifacts live under the private `COURTSIDE_STORAGE` directory.
SQLite WAL and `BEGIN IMMEDIATE` protect upload offsets and job claims.

One embedded worker claims queued jobs. A server restart requeues interrupted
jobs. Deleting a session cancels analysis at the next progress update and removes
its originals, clips, metrics and reviews. Cleanup runs hourly and on CLI request;
partial uploads expire after 24 hours. Processing jobs are excluded from retention.

The standalone `courtside analyze` pipeline reads a fixed-camera file, samples
poses, smooths/tracks up to two people, tracks color/motion ball candidates,
interpolates short gaps, proposes wrist-speed contacts, measures supported 2D
metrics and renders overlays. Court calibration requires four manually confirmed
corners. Optional promoted classifier inference replaces heuristic shot types;
it does not replace segmentation, pose estimation or ball tracking.

Rules are a pure `metrics + YAML config -> tips` function. Every emitted tip
stores its metric, value, target and rule version. Confidence gating suppresses
uncertain measurements. `coach_validated: false` suppresses all real tips.

The access model is one private workspace, not multi-tenant accounts. Localhost
can run without a token. Remote clients require a token. Media has one-hour HMAC
links, asset allowlists, private cache headers and browser range support. CORS and
Origin checks reject unconfigured sites. API errors avoid exposing server traces.

Live Court captures a webcam/phone video track without audio and sends one bounded
JPEG frame at a time over an authenticated WebSocket. Stateful inference runs off
the API event loop, returns poses/ball/metrics and never writes frames to disk.
The browser renders overlays on the camera preview and waits for acknowledgements
before capturing the next frame. A six-second bounded pose history supports
follow-through measurements. Preview rules are explicitly experimental when
`coach_validated` is false. Slow capture reduces resolution and resets coordinate
history; lost connections stop the camera.

Run exactly one API process/worker per storage directory. Distributed queues,
multi-tenant roles, automatic court keypoints, trained ball detection, GPU
processing, IP/RTSP capture and real-field live validation are future work.
