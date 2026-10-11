# Staging external tennis datasets

The versioned inventory is `data/datasets.json`. Both enabled Mendeley datasets
were downloaded to `D:\CourtsideData` on 2026-10-07. Their publisher metadata
explicitly lists CC BY 4.0:

| Local ID | Publisher version | Verified local contents |
| --- | --- | --- |
| `tennis-player-actions` | [nv3rpsxhhk v1](https://data.mendeley.com/datasets/nv3rpsxhhk/1) | 2,000 JPEG images and four COCO annotation JSON files |
| `tennis-paired-views` | [75m8vz7jr2 v3](https://data.mendeley.com/datasets/75m8vz7jr2/3) | 472 MP4 clips and four landing-point CSV files |

The first dataset contains forehand, backhand, serve and ready-position images.
The second records shot direction and paired camera views. Neither includes a
complete reviewed four-class temporal classification training set.

All 2,480 source files passed their publisher SHA256 checks, totaling
3,130,399,074 bytes (2.92 GiB). The action annotations contain 500 images per
category and 18 keypoints. The video inventory contains 236 matching side/top
view pairs and 236 landing-point records across four CSVs. Corresponding clip
IDs match in each direction/location group. One clip from each camera view was
decoded successfully at 1920 by 1080 and approximately 59.94 frames per second;
the remaining clips were checked for file integrity, not decoded end to end.

## Download and verify

Activate a Python 3.11 environment. No new dependencies are required by the
downloader. Choose a drive with at least 7 GB free for both ZIPs and extraction;
individual-file mode needs approximately 3 GB plus free-space headroom.

```powershell
& .\.qa-venv\Scripts\Activate.ps1
python data/download_datasets.py --root 'D:\CourtsideData'
```

The downloader checks publisher identity, version and license before fetching
data. It verifies a pinned publisher SHA256 for each ZIP. If the cached ZIP returns
403 or 404, it falls back to the official versioned file inventory and verifies
every individual file against its publisher SHA256. ZIP extraction rejects paths
outside the destination, symbolic links and case-insensitive path collisions.
Partial transfers can resume. Existing files must pass verification before reuse.

Mendeley's cached ZIPs returned 403 during setup on 2026-10-07. To use the working
individual-file route directly:

```powershell
python data/download_datasets.py --root 'D:\CourtsideData' --mode files
```

Select one dataset with `--dataset tennis-player-actions` or
`--dataset tennis-paired-views`. Acquisition uses six concurrent file transfers;
it does not start training or change any classifier or consent configuration.

## Local files and attribution

Each staged dataset has:

```text
<data root>/<dataset ID>/
    ATTRIBUTION.txt       # Authors, DOI, version and license URL
    publisher.json       # Publisher's versioned metadata and license statement
    source_files.json    # Paths, sizes and SHA256s in individual-file mode
    archive.zip          # Present only when the cached ZIP is available
    contents/            # Original dataset files
    inventory.json       # Actual local file counts and verification method
```

`data/local_datasets.json` records the local paths and is ignored by Git. Raw
recordings, original images, annotations and the generated inventories stay in
the selected data directory. The publisher files remain unmodified. Preserve
`ATTRIBUTION.txt` and the CC BY attribution requirements when reusing the data.

THETIS, F3Set-Tennis, TrackNetV4 and TennisCourtDetector are catalogued separately
in `data/datasets.json`; the downloader does not acquire them. Their research-only
or unresolved terms are documented in `docs/training_data_sources.md`.

## Prepare reviewed training data

The staged inventories explicitly set `training_ready: false`. They do not
invent all-player training consent or label-review attestations. The existing
`courtside train` loader still requires own-consented video recordings, original
hashes, reviewed start/contact/end labels and independent sessions/players.

For action images, inspect the COCO annotations as a pose evaluation resource;
still images do not supply continuous movement windows and ready position is not
the current classifier's volley class. For paired videos, extract poses and
review the actual stroke type and boundaries. Keep corresponding Side-View and
Top-View clips in the same split, and obtain stable session/player identities and
participant provenance before assigning training splits. Do not randomly split
adjacent images or paired views across training and evaluation.

See `docs/training.md` for the existing training manifest and promotion checks.

For experiments with the original public action/direction labels, use the separate
`data/train_external.py` workflow in [external training](external_training.md).
It does not convert these sources into consented app-training manifests.
