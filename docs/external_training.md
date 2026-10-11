# Experimental training on the external tennis datasets

`data/train_external.py` trains two separate NumPy softmax baselines using the
published labels in the downloaded CC BY 4.0 datasets. These experiments have
different classes and features from the app's four-stroke temporal classifier.
They do not change `courtside train`, consent checks, promotion checks or the
active model configuration.

## Completed local run — 2026-10-08

Both experiments completed under `models/external-baselines/`. Saved features
reproduce every reported train/validation/test score, model fingerprints verify,
and group/file hashes do not overlap across splits. The app rejects both artifacts
for active inference.

| Task | Train / validation / test samples | Test accuracy | Test macro F1 | Majority test accuracy |
| --- | --- | ---: | ---: | ---: |
| Annotated image actions | 1,199 / 320 / 320 | 85.625% | 0.85255 | 25.0% |
| Video shot direction | 280 / 80 / 75 | 54.667% | 0.46697 | 53.333% |

The image experiment excluded 160 split-gap images and one annotation missing
required shoulder/hip joints. It uses ground-truth keypoints and does not measure
automatic image recognition; all-player/session separation remains unverified.

The video experiment excluded 36 split-gap clips and one outdoor top-view clip
(`OST09.mp4`) with inadequate confident pose samples. Its 75 test clips represent
38 paired shots with one unavailable view. Validation accuracy was 92.5%, but the
outdoor test accuracy is barely above the majority baseline. Straight-shot recall
is only 17.1%; this model does not generalize reliably to the outdoor set. No
feature, threshold or checkpoint was tuned in response to those test scores.

## Run and reproduce

Use the existing Python 3.11 environment with the vision extra installed:

```powershell
& .\.qa-venv\Scripts\Activate.ps1
python data/train_external.py --data-root D:\CourtsideData --out models/external-baselines
```

Select a task with `--task image_actions` or `--task video_direction`. The seed,
optimizer parameters, split boundaries and pose-sampling settings are versioned
in `configs/external_training.yaml`. No additional packages or remote services
are required. The original dataset files remain unmodified.

Training rechecks every original file against the publisher SHA256 index before
reading labels or using cached features. It requires the individual-file staging
inventory (`source_files.json`) produced by `data/download_datasets.py --mode files`.
Video pose extraction also verifies the
official MediaPipe model digest. It caches features under the output directory,
using the source video hash, model hash, extraction settings and MediaPipe version.
Cache records carry their own fingerprint. Changing extraction settings invalidates
the cached features. The optimizer standardizes features using training data only
and selects its checkpoint by validation macro F1; test data does not select weights.

## Tasks and evaluation splits

| Task | Published labels | Input features | Evaluation protocol |
| --- | --- | --- | --- |
| Image actions | Backhand, forehand, ready position, serve | Publisher-annotated COCO body keypoints, normalized by hip center and torso scale, plus labeled-point masks | Within each category: images 1-300 train, 321-400 validation, 421-500 test. Images 301-320 and 401-420 are purged. |
| Video direction | Cross-court, straight | Summary of 16 uniformly sampled MediaPipe poses, normalized body motion, hip displacement/range and clip duration | Indoor shot pairs 1-70 train and 80-99 validation; pairs 71-79 are purged. All outdoor shot pairs are test. Corresponding camera views stay together. |

The image task classifies **annotated poses**. Its scores do not measure automatic
image recognition or MediaPipe pose accuracy. Ready position remains its original
label; it is never relabeled as volley.

Video extraction uses a stateless image-mode pose detector and selects the largest
confident torso. If full-frame detection fails, it tries a crop around the largest
moving foreground region, computed without labels. This is a dominant-person
heuristic, not verified player tracking. The original labels describe direction;
the experiment does not infer forehand/backhand/serve/volley or contact times.
The CSV landing-point distances are retained as source records and are not used
as inputs to predict their related shot-direction labels.

Exact file or feature duplicates are removed. Missing core joints, inadequate pose
samples and split gaps are recorded as exclusions. Near-duplicate image frames and
repeated players may remain across splits. Filename order does not establish
distinct recording sessions. Holding out outdoor videos measures a change in
location/camera conditions; it does not establish an independent player split.

## Artifacts

The ignored `models/external-baselines/` directory contains, for each task:

- `<task>_model.json`: classes, standardized-feature parameters, validation-selected
  weights, scores, source provenance, configuration and model fingerprint.
- `<task>_evaluation.md`: split sizes, accuracy, macro F1, per-class scores,
  majority-class comparison and limitations.
- `<task>_split.json`: source paths/hashes, paired-view groups, split assignments
  and exclusions.
- `<task>_features.npz`: the features, labels and split assignments used by the run.
- `<task>_ATTRIBUTION.txt`: source authors, version, DOI, CC BY license and description
  of the derived artifact.

Model files declare `data_origin: external-cc-by`, `experimental: true`,
`player_split_verified: false` and `promoted: false`. The existing app promotion
and inference checks reject these artifacts. They do not attest processing or
training consent for recorded participants and do not establish production
coaching performance. Neither experiment trains a pose detector or ball tracker.

For the production-candidate four-stroke workflow, use the separately consented,
reviewed and independent session/player manifests described in `docs/training.md`.
The external dataset inventories remain `training_ready: false` for that workflow.
