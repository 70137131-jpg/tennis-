# Dataset and model inventory — 2026-10-08

Two external CC BY 4.0 tennis datasets are registered in `data/datasets.json` and
have been downloaded to `D:\CourtsideData`: 2,000 JPEG images, four COCO annotation
files, 472 MP4 clips and four landing-point CSVs. All 2,480 source files passed
publisher SHA256 verification. Local paths and verified file inventories are
recorded in the ignored `data/local_datasets.json`; `data/download_datasets.py`
can reproduce the setup. Two experimental models have now been trained with the
original action/direction labels using `data/train_external.py`; see
[external training](../docs/external_training.md). These schemas cannot be promoted
as the app's four-stroke classifier. The running application still uses the
general pose task and movement baselines.

| Candidate | Source | License decision / use |
|---|---|---|
| Tennis Player Actions v1 | [Publisher](https://data.mendeley.com/datasets/nv3rpsxhhk/1) | CC BY 4.0. 2,000 action images and four COCO annotation files. Staged as supplementary data; continuous shot windows and volleys are missing. |
| Tennis Shot Side-View and Top-View v3 | [Publisher](https://data.mendeley.com/datasets/75m8vz7jr2/3) | CC BY 4.0. 472 video clips and four landing-point CSVs. Additional stroke labels, pose extraction, reviewed boundaries and participant provenance are required before training. |
| Own tennis recordings | Private consented local files | Primary training/evaluation source. Requires all-player processing consent and separate training consent; juniors require guardian consent and assent. None supplied yet. |
| COCO keypoints | [Official COCO terms](https://cocodataset.org/#termsofuse) | Candidate only. The site was checked, but its dynamic terms were not fully retrievable here. Image and annotation rights must be audited separately before use. Not downloaded/approved for shipped training. |
| COCO-WholeBody | [Dataset authors](https://github.com/jin-s13/COCO-WholeBody) | Candidate only; no model is trained on it by this project. Full applicable image/annotation/model terms unresolved. Excluded pending audit. |
| THETIS / F3Set / TenniSet | [Source audit](../docs/training_data_sources.md) | Research-only or unresolved commercial footage terms. Catalogued separately; not acquired for commercial training. |
| TrackNet tennis sets | [TrackNetV4 terms](https://tracknetv4.github.io/) | The new dataset requires an access request and research-only agreement. Color/motion tracking remains implemented; no TrackNet weights/data are acquired. |
| TennisCourtDetector | [Creator](https://github.com/yastrebksv/TennisCourtDetector) | Dataset license unresolved. No court data acquired; user-confirmed four-corner calibration provides the current homography. |
| MediaPipe full pose float16 v1 task | [Official model guide](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker) | SDK source is Apache-2.0. Task-specific commercial redistribution terms remain a separate release check. Download is for local evaluation; no commercial clearance inferred from the SDK license. |

Run `python data/download_model.py` for the versioned official pose task. Its
SHA256 is pinned and verified before use. `models/manifest.json` records the exact
source and digest. Weight files stay outside version control.

See [dataset setup](../docs/dataset_setup.md) for verified downloads, attribution,
external storage and the distinction between staged data and reviewed training
manifests. The current local setup uses `D:\CourtsideData` because C: lacks space.
Dataset files remain outside Git, and staging does not bypass training consent or
promotion checks.

Synthetic demo clips and test fixtures are project-generated software fixtures.
They are never admissible as real held-out tennis performance evidence. See
`docs/data.md`, `docs/training.md` and `docs/licenses.md`.
