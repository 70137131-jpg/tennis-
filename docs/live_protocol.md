# Live camera protocol

WebSocket endpoint: `/api/live`. Exactly one session is active per workspace.
The Origin and remote-access checks apply to the handshake. Start with JSON:

```json
{"type":"start","token":"PRIVATE_WORKSPACE_TOKEN_IF_CONFIGURED","options":{"processing_consent":true,"handedness":"right","age_group":"adult","level":"competitive","experimental_feedback":true}}
```

The server replies `{"type":"ready","target_fps":12,"max_width":960}` after
loading the pose model. Then send binary JPEG frames, waiting for each `frame`
response before sending the next. The token is not put in query strings or logs.
Frame byte/dimension/history limits live in `configs/live.yaml`.

Each result includes source dimensions, server-relative timestamp, current player
poses (17 COCO points), ball candidate/trail, shot counts, the latest completed
shot with measured metrics/tips/rating, mean target-match rating and processing
milliseconds. `reduce_workload` asks the browser to lower capture resolution.
Resizing resets geometric history so old coordinates do not contaminate metrics.

Frame responses identify `pipeline_version` (currently `baseline-2`).
Completed shots also include `classification_source` (`heuristic` or `trained`),
`classification_evidence` (observed movement cues), and `technique` with `status`,
`score`, `measured_checks`, `expected_checks`, `checks`, `explanation`, and
`rule_version`. Check statuses are `within_target`, `below_target`, `above_target`,
`not_measurable`, or `no_target`. Technique status is `provisional`, `limited`,
`unavailable`, or `disabled`. `rating` mirrors `technique.score`; only scored shots
contribute to `session_rating`. Unknown shot types and insufficient applicable
measurements are unscored. Detection confidence is not calibrated accuracy.

Send the text `stop` to get `{"type":"stopped"}` and release the model. Closing
the socket also releases it. Invalid input/consent, model failures or idle timeouts
return `{"type":"error","message":"..."}` and close. The browser camera closes
on stop, error, timeout and page unmount.

For juniors, include `guardian_consent`, `guardian_name` and `player_assent`.
For court calibration, include four normalized `court_corners` in far-left,
far-right, near-right, near-left order. Frames and history are in memory only.

No training data is collected by this endpoint. Live ratings/suggestions are
experimental unless rules are coach-approved. Tips require real measured,
confidence-gated metrics; no poses or reliable phases means no score/tip.
