# Training and model promotion

The bundled MediaPipe task is a general pretrained pose model. Tennis shot labels
default to a wrist-motion heuristic. No tennis-specific classifier has been trained
on real footage in this workspace.

The implemented baseline summarizes a confident pose window into translation/scale
normalized temporal features and fits a four-class softmax classifier using NumPy.
It is deterministic with the seed and hyperparameters in `configs/training.yaml`.
Validation selects a checkpoint; a separate frozen test split supplies held-out
scores. This trains shot classification only, not pose, ball detection or segmentation.

First obtain processing consent and **separate training consent** for all people
recorded. Include guardian consent and junior assent when relevant. Analyze each
recording to get `poses.json`; manually annotate its shot boundaries and types.
Use stable pseudonymous person IDs across every session. Do not split a single
recording or player between train, validation and test.

Create three private JSON manifests. Paths resolve relative to each manifest:

```json
[
  {
    "session_id": "session-001",
    "player_ids": ["person-001", "person-002"],
    "data_origin": "own-consented",
    "labels_reviewed": true,
    "includes_minors": false,
    "video": "../raw/session-001.mp4",
    "video_sha256": "REPLACE_WITH_64_CHARACTER_LOWERCASE_SHA256",
    "poses": "../exports/session-001/poses.json",
    "consent": {"processing": true, "training": true, "all_players": true},
    "shots": [
      {"type": "forehand", "player_id": "player-near", "player_identity": "person-001", "start": 1.2, "contact": 2.4, "end": 3.9}
    ]
  }
]
```

Use `Get-FileHash -Algorithm SHA256 video.mp4` and lowercase the result. For minors,
add `guardian: true` and `assent: true` inside consent. Keep the actual consent
record privately; boolean fields are attestations, not a substitute for that record.
Declare **every** player in the recording, including unlabeled partners.

```powershell
.venv\Scripts\courtside.exe train --train data\labels\train.json --validation data\labels\validation.json --test data\labels\test.json --out models\shot-baseline
.venv\Scripts\courtside.exe promote models\shot-baseline\classifier.json
$env:COURTSIDE_CLASSIFIER = 'models/shot-classifier.json'
.venv\Scripts\courtside.exe serve
```

The loader verifies original-file hashes and rejects demo data, missing consent,
unreviewed/unsupported labels and inadequate pose windows. Splits are checked by
session, every person, original hash and pose-export hash. Promotion requires
macro-F1 ≥0.85, each class F1 ≥0.70 and at least 20 held-out examples per class by
default. Targets are adjustable in the versioned config. A fingerprint detects
accidental edits to parameters/evidence. Promotion never occurs automatically.

Inspect `classifier.json` and `evaluation.md` after each run. Do not repeatedly
tune against the frozen test set. Change model/rule versions and keep experiment
logs. Compare any future architecture with this baseline using the same independent
evaluation protocol. Classification of labeled windows does not establish contact,
ball, tracking, coaching or live-camera accuracy.
