# Evaluation status — 2026-10-05

Software checks use synthetic fixtures and one official pose-model no-person
inference smoke test. They measure code behavior, not tennis accuracy.

| PRD gate | Status | Evidence needed |
|---|---|---|
| CLI, scaffold, camera guidance, audit | Implemented locally | Camera/real sample selection remains open |
| Pose + offline candidates/video | Implemented baseline | Held-out pose labels, shot F1 and contact errors |
| Two players, ball and court | Implemented baseline/manual calibration | Rally/match clips, ID switches, ball labels |
| Metrics and coaching | Metrics implemented; real tips disabled | Qualified coach approval and rated tip sample |
| Upload-to-report local web MVP | Implemented and QA tested | Phone-device field test; hosted deployment if needed |
| Near real time | Browser camera/WebSocket implemented; synthetic transport tested | Tennis camera and phone trials, target-device latency/accuracy |
| Academy readiness | Consent, reviews, retention, trends implemented | Roles/tenancy, legal review, pilot and go/no-go |

Use `python eval/evaluate.py data/labels/held-out-reports.json --out
eval/held_out.md --train-manifest data/labels/train.json` for report-level shot
classification and contact matching. Demo reports are rejected. Supply independent
pose, ball, tracking and coach-review labels to `eval/measurements.py`; missing
labels produce no invented metrics. Classifier-on-labeled-window scores from
`courtside train` are separate from this end-to-end evaluation.
