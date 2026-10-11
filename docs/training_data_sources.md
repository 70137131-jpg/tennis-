# Online tennis training data

Sources checked on 2026-10-07. This is a shortlist for Courtside, with access and
published terms checked against dataset publishers or authors. The two CC BY
Mendeley sources are now downloaded and verified at `D:\CourtsideData`; see
`docs/dataset_setup.md` and the ignored `data/local_datasets.json` for paths and
completed inventories. The action dataset's four annotation files were inspected:
each contains 500 labeled images and 18 body keypoints. The video inventory has
236 matched camera-view pairs and 236 CSV landing-point records. Other candidates remain
catalogued sources. Experimental training on the two downloaded sources' original
label tasks is documented in [external training](external_training.md). Sizes/counts
below are publisher claims unless confirmed by a completed local inventory.

## Candidates with an explicit permissive dataset license

| Dataset | Contents and access | Fit for Courtside | Published terms |
| --- | --- | --- | --- |
| [Tennis Player Actions, v1](https://data.mendeley.com/datasets/nv3rpsxhhk/1) | 2,000 images, 500 each for forehand, backhand, serve and ready position; 18 body keypoints in COCO JSON; about 508 MB. Use the publisher's Download All control. | Supplementary pose evaluation or a separate image classifier. No volley class, continuous shot windows or contact labels. | Publisher lists CC BY 4.0. |
| [Tennis Shot Side-View and Top-View, v3](https://data.mendeley.com/datasets/75m8vz7jr2/3) | 472 clips: 236 side views and 236 top views of corresponding shots. Indoor/outdoor recordings, straight/cross-court categories, landing coordinates in four CSV files; about 2.42 GB. Use Download All. | Video-based motion and direction experiments. Requires additional four-class shot labels and pose extraction. Paired views must remain in the same split. | Publisher lists CC BY 4.0. |

[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) allows reuse and adaptation
for commercial purposes with attribution and the other license conditions.
These two sources are promising candidates for commercial training; this shortlist
does not establish that they satisfy Courtside's consent/provenance requirements.
Neither is a complete dataset for the existing four-class temporal classifier.

## Shot recognition and event detection research

**[THETIS](https://github.com/THETIS-dataset/dataset).** The authors list 55 people,
12 action types and approximately 1,980 RGB clips, alongside depth, mask and
skeleton recordings. The often quoted 8,374 count combines modalities, rather
than representing 8,374 unique RGB performances. Indoor Kinect recordings are
useful for isolated-shot experiments, with a substantial difference from phone
footage of matches. Access the
[RGB directory](https://github.com/THETIS-dataset/dataset/tree/main/VIDEO_RGB).
The [original paper](https://openaccess.thecvf.com/content_cvpr_workshops_2013/W08/html/Gourgari_THETIS_Three_Dimensional_2013_CVPR_paper.html)
offers the dataset for research; commercial training permission was not verified.

Suggested label conversion, requiring review: map service variants to serve,
forehand groundstroke variants to forehand, backhand groundstroke variants to
backhand, and both volley variants to volley. Exclude smash from the current
four-class task. Split by actor IDs, and keep all modalities/repeats of an actor
together. Contact and shot-boundary labels still need review.

**[F3Set-Tennis](https://github.com/F3Set/F3Set/tree/main/data/f3set-tennis).** The
[authors' paper](https://arxiv.org/html/2504.08222v2) reports 114 broadcast matches,
75 players, 11,584 rallies and 42,846 shots. Labels identify contact-frame events
and detailed attributes. JSON annotations and YouTube IDs are available in the
repository; footage access is separate. This is the strongest candidate here for
research on match event spotting. The paper explicitly limits intended use to
academic research. Its published split separates test videos, but Courtside also
requires player separation. Add reviewed start/end boundaries and extract poses
before any compatible temporal-classification experiment.

**[TenniSet](https://github.com/HaydenFaulkner/Tennis).** Five matches with manual
temporal events and commentary captions. The
[author's download instructions](https://github.com/HaydenFaulkner/Tennis/tree/master/data)
link to videos (11.1 GB) and annotations (9.5 MB); downloading the 217 GB frame and
flow exports is unnecessary for an initial inspection. Useful as a smaller event
localization benchmark, with a different label vocabulary. The repository's
[MIT license](https://raw.githubusercontent.com/HaydenFaulkner/Tennis/master/LICENSE)
covers software; a separate grant for the underlying broadcast footage was not
verified. Commercial dataset/model use remains unresolved.

## Ball, court and pose research

**[TrackNetV4 tennis data](https://tracknetv4.github.io/).** The new dataset covers
multiple balls, singles/doubles, nighttime footage and difficult visibility.
The authors require an access-request form and publish a research-only agreement
that prohibits commercial use and restricts sharing. Suitable for research on
ball tracking, not a source of reviewed shot-type or coaching-quality labels.
The repository's MIT software license does not override the dataset agreement.
The [official setup guide](https://github.com/TrackNetV4/TrackNetV4/blob/main/docs/DATASET.md)
also links the older TrackNet tennis dataset through an explicitly unofficial
implementation; its commercial dataset terms were not verified.

**[TennisCourtDetector](https://github.com/yastrebksv/TennisCourtDetector).** The
dataset creator lists 8,841 images at 1280 x 720 with 14 annotated court points,
covering hard, clay and grass. The README supplies a
[dataset archive link](https://drive.google.com/file/d/1lhAaeQCmk2y440PmagA0KmIVBIysVMwu/view).
Useful for court calibration experiments. The images were extracted from YouTube
highlights; no explicit dataset license was found on the reviewed repository
page. Commercial use is unresolved. Rebuild splits by source match rather than
assuming its image-level train/validation division proves generalization.

**[CalTennis](https://huggingface.co/datasets/demalenk/caltennis).** Synchronized
multi-view video, timestamps and camera calibration, with mini/mid subsets.
The publisher labels it CC BY-NC 4.0. Useful for research on multi-view pose
consistency, not a verified source of reviewed four-class shot annotations.
Do not treat it as commercially permissive training data.

## Next steps for this repository

1. Inspect the two CC BY Mendeley datasets first; retain their DOI, exact version,
   license, attribution and recording/participant documentation.
2. Use THETIS or F3Set only in an appropriately permitted research experiment.
   Keep models/evidence from restricted datasets separate from a shipped model.
3. Obtain additional consented recordings covering all four classes, especially
   volleys, from the intended phone-camera setup and diverse players. Preserve
   independent sessions/players for a frozen test set.
4. Build a reviewed importer only after resolving provenance. The existing loader
   in `src/courtside/training.py` accepts `data_origin: own-consented`, requires
   all-player processing/training consent and checks original-video hashes.
   Third-party data cannot be made compatible by falsely setting those fields.
5. Extract poses, review start/contact/end times, map supported labels, and
   evaluate complete sessions separately from manually segmented shot windows.

None of these sources, as reviewed, supplies qualified-coach judgments sufficient
to validate Courtside's technique ratings or advice.
