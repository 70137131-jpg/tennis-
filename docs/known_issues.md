# Known limitations

- No real labeled tennis set was provided. Macro-F1, contact error, ball recall,
  player ID switches, robustness and GPU speed targets are unmeasured.
- Default shot labels are heuristics. Raised-wrist motion can resemble a serve;
  wrist peaks do not establish racket/ball contact. Stable IDs are positional
  near/far slots and may change through long occlusion or player end changes.
- Ball tracking is an HSV/motion baseline and may mistake clothing or markings
  for a ball. Interpolation fills short gaps only. Court lines are suggestions;
  calibration is manual, with no trained court keypoint detector.
- Backhand style is recorded; there are no independently validated one-hand and
  two-hand models or style-specific metrics. Left/right handedness affects metrics.
- The pretrained pose model is general-purpose and CPU-based here. No local-GPU
  or ten-minute 1080p performance claim has been established.
- Rear-camera 2D geometry cannot reliably measure racket path, contact in front
  or true weight transfer. These metrics are explicitly not measurable.
- Offline coaching tips are disabled until qualified-coach rule approval. Live
  experimental previews can be explicitly enabled and are labeled provisional. Configured
  ranges shown with measurements are hypotheses, not validated coaching targets.
- Face blurring depends on detected pose/face points and can miss undetected
  people. Originals and initial posters remain private but are not anonymized.
- Access is one shared token; player/coach/admin accounts and multi-academy
  tenancy are not implemented. No cloud job service or cloud storage is configured.
- Webcam/phone camera streaming is implemented. Tennis-specific latency and accuracy
  on a real camera/phone remain unvalidated. Direct IP/RTSP capture is not implemented.
  Simulated-live file windows remain available for benchmarking.
- Container recipes are unbuilt because the Docker daemon is not running. Model-weight redistribution,
  FFmpeg/libx264 distribution, target-country legal review, HTTPS on a target host,
  restore drills and the academy pilot remain release prerequisites.
- Long clips consume disk space for an intermediate MJPEG overlay. Check storage
  before processing hour-long sessions. Audio is intentionally omitted from outputs.
