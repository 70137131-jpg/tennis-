# Dataset and model inventory — 2026-10-05

No third-party tennis dataset has been downloaded or used for training. The shipped
path currently uses a downloaded general pose task and hand-written tennis baselines.

| Candidate | Source | License decision / use |
|---|---|---|
| Own tennis recordings | Private consented local files | Primary training/evaluation source. Requires all-player processing consent and separate training consent; juniors require guardian consent and assent. None supplied yet. |
| COCO keypoints | [Official COCO terms](https://cocodataset.org/#termsofuse) | Candidate only. The site was checked, but its dynamic terms were not fully retrievable here. Image and annotation rights must be audited separately before use. Not downloaded/approved for shipped training. |
| COCO-WholeBody | [Dataset authors](https://github.com/jin-s13/COCO-WholeBody) | Candidate only; no model is trained on it by this project. Full applicable image/annotation/model terms unresolved. Excluded pending audit. |
| THETIS / TenniSet | Named research candidates in PRD | Exact release/rights not verified. Neither downloaded nor approved for training or redistribution. |
| TrackNet tennis sets | Named research candidates in PRD | Exact dataset/checkpoint terms not verified. Color/motion tracking is implemented instead; no TrackNet weights/data are downloaded. |
| Court keypoint datasets | Named research candidates in PRD | No third-party court data used. User-confirmed four-corner calibration provides the current homography. |
| MediaPipe full pose float16 v1 task | [Official model guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) | SDK source is Apache-2.0. Task-specific commercial redistribution terms remain a separate release check. Download is for local evaluation; no commercial clearance inferred from the SDK license. |

Run `python data/download_model.py` for the versioned official pose task. Its
SHA256 is pinned and verified before use. `models/manifest.json` records the exact
source and digest. Weight files stay outside version control.

Synthetic demo clips and test fixtures are project-generated software fixtures.
They are never admissible as real held-out tennis performance evidence. See
`docs/data.md`, `docs/training.md` and `docs/licenses.md`.
