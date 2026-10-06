import hashlib
import json
from copy import deepcopy

import pytest
import yaml

from courtside.pipeline import ROOT
from courtside.schemas import Keypoint, PoseFrame
from courtside.training import load_dataset, train


def manifest_fixture(tmp_path, video_file, group):
    # Explicit software-only fixture. Artifacts remain in pytest's temp directory.
    frames = []
    labels = []
    for class_index, name in enumerate(["serve", "forehand", "backhand", "volley"]):
        for i in range(4):
            points = [
                Keypoint(x=100 + j + class_index * 5, y=40 + j * 4 + group, confidence=0.99)
                for j in range(17)
            ]
            points[10].x += class_index * 20
            frames.append(
                PoseFrame(
                    frame=len(frames),
                    time=class_index + i * 0.1,
                    player_id="player-near",
                    side="near",
                    keypoints=points,
                )
            )
        labels.append(
            {
                "type": name,
                "player_id": "player-near",
                "player_identity": f"person-{group}",
                "start": class_index,
                "contact": class_index + 0.1,
                "end": class_index + 0.3,
            }
        )
    poses = tmp_path / f"poses-{group}.json"
    poses.write_text(json.dumps([p.model_dump() for p in frames]))
    original = tmp_path / f"video-{group}.mp4"
    original.write_bytes(video_file.read_bytes() + bytes([group]))
    manifest = [
        {
            "session_id": f"session-{group}",
            "player_ids": [f"person-{group}"],
            "data_origin": "own-consented",
            "labels_reviewed": True,
            "video": original.name,
            "video_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
            "poses": poses.name,
            "consent": {"processing": True, "training": True, "all_players": True},
            "shots": labels,
        }
    ]
    path = tmp_path / f"manifest-{group}.json"
    path.write_text(json.dumps(manifest))
    return path, manifest


def test_training_writes_candidate_and_evaluation_without_auto_promotion(tmp_path, video_file):
    manifests = [manifest_fixture(tmp_path, video_file, i)[0] for i in range(3)]
    model = train(*manifests, tmp_path / "candidate", ROOT / "configs/training.yaml")
    assert not model["promoted"]
    assert model["held_out"]["samples"] == 4 and model["split_verified"]
    assert (tmp_path / "candidate/classifier.json").is_file()
    assert "Insufficient held-out" in (tmp_path / "candidate/evaluation.md").read_text()
    # These math fixtures do not satisfy sample-count release gates.


@pytest.mark.parametrize(
    "change,match",
    [
        ("minor", "Guardian"),
        ("hash", "SHA256"),
        ("label", "supported class"),
        ("identity", "identity"),
        ("empty", "No labeled"),
    ],
)
def test_training_manifest_rejects_invalid_evidence(tmp_path, video_file, change, match):
    path, rows = manifest_fixture(tmp_path, video_file, 0)
    rows = deepcopy(rows)
    if change == "minor":
        rows[0]["includes_minors"] = True
    elif change == "hash":
        rows[0]["video_sha256"] = "f" * 64
    elif change == "label":
        rows[0]["shots"][0]["type"] = "smash"
    elif change == "identity":
        rows[0]["shots"][0]["player_identity"] = "someone-else"
    else:
        rows[0]["shots"] = []
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match=match):
        load_dataset(path, yaml.safe_load((ROOT / "configs/training.yaml").read_text()))
