import json

import numpy as np
import pytest
import yaml

from courtside.classifier import (
    CLASSES,
    FEATURE_COUNT,
    ShotClassifier,
    classification_scores,
    fingerprint,
    fit,
    pose_features,
    probabilities,
    promotion_failures,
)
from courtside.pipeline import ROOT
from courtside.schemas import Keypoint, PoseFrame
from courtside.training import load_dataset, promote, verify_splits


@pytest.fixture
def training_config():
    return yaml.safe_load((ROOT / "configs/training.yaml").read_text())


def sequence():
    points = [Keypoint(x=10 + i, y=20 + i * 2, confidence=0.99) for i in range(17)]
    return [
        PoseFrame(frame=i, time=i / 15, player_id="player-near", side="near", keypoints=points)
        for i in range(5)
    ]


def test_temporal_features_are_translation_and_scale_invariant():
    poses = sequence()
    features = pose_features(poses)
    moved = [p.model_copy(deep=True) for p in poses]
    for pose in moved:
        for point in pose.keypoints:
            point.x = point.x * 2 + 200
            point.y = point.y * 2 + 300
    assert features.shape == (FEATURE_COUNT,)
    np.testing.assert_allclose(features, pose_features(moved))
    poses[0].keypoints[9].confidence = 0.1
    with pytest.raises(ValueError, match="confident"):
        pose_features(poses[:3])


def test_softmax_learns_separable_unit_fixture_reproducibly(training_config):
    # Pure math fixture, never recorded as real tennis performance.
    x = np.repeat(np.eye(4), 5, axis=0)
    labels = np.repeat(np.arange(4), 5)
    first = fit(x, labels, x, labels, training_config)
    second = fit(x, labels, x, labels, training_config)
    assert first == second
    assert classification_scores(labels, probabilities(x, first).argmax(1))["macro_f1"] == 1
    assert probabilities(x, first).sum(1) == pytest.approx(np.ones(len(x)))
    with pytest.raises(ValueError, match="all four"):
        fit(x[:5], labels[:5], x, labels, training_config)


def model_fixture():
    model = {
        "data_origin": "own-consented",
        "split_verified": True,
        "classes": CLASSES,
        "feature_version": "pose-window-v1",
        "mean": [0.0] * FEATURE_COUNT,
        "scale": [1.0] * FEATURE_COUNT,
        "weights": np.zeros((FEATURE_COUNT, 4)).tolist(),
        "bias": [4.0, 0.0, 0.0, 0.0],
        "held_out": {
            "macro_f1": 0.9,
            "classes": [{"class": name, "support": 20, "f1": 0.9} for name in CLASSES],
        },
        "promoted": False,
    }
    model["sha256"] = fingerprint(model)
    return model


def test_promotion_rejects_missing_classes_fake_origin_and_tampering(training_config, tmp_path):
    model = model_fixture()
    assert not promotion_failures(model, training_config)
    model["held_out"]["classes"][0]["support"] = 0
    assert promotion_failures(model, training_config)
    model = model_fixture()
    model["data_origin"] = "demo"
    model["sha256"] = fingerprint(model)
    assert any("real footage" in reason for reason in promotion_failures(model, training_config))
    source = tmp_path / "candidate.json"
    source.write_text(json.dumps(model))
    with pytest.raises(ValueError, match="blocked"):
        promote(source, tmp_path / "active.json", ROOT / "configs/training.yaml")


def test_promoted_inference_suppresses_uncertain_windows(training_config, tmp_path):
    source = tmp_path / "candidate.json"
    source.write_text(json.dumps(model_fixture()))
    target = tmp_path / "active.json"
    promote(source, target, ROOT / "configs/training.yaml")
    classifier = ShotClassifier(target, training_config)
    assert classifier.predict(sequence())[0] == "serve"
    assert classifier.predict([]) == ("unknown", 0.0)
    model = json.loads(target.read_text())
    model["bias"] = [0, 0, 0, 0]
    model["sha256"] = fingerprint(model)
    target.write_text(json.dumps(model))
    classifier = ShotClassifier(target, training_config)
    assert classifier.predict(sequence()) == ("unknown", 0.25)
    model["weights"][0][0] = 10
    target.write_text(json.dumps(model))
    with pytest.raises(ValueError, match="promotion"):
        ShotClassifier(target, training_config)


@pytest.mark.parametrize("key", ["session_id", "video_sha256", "pose_sha256", "player_ids"])
def test_split_leakage_is_rejected(key):
    left = {"session_id": "a", "video_sha256": "a", "pose_sha256": "a", "player_ids": ["alice"]}
    right = {"session_id": "b", "video_sha256": "b", "pose_sha256": "b", "player_ids": ["bob"]}
    right[key] = left[key]
    with pytest.raises(ValueError, match="leakage"):
        verify_splits([[left], [right]])


def test_manifest_requires_real_consent_and_review(tmp_path, training_config):
    path = tmp_path / "labels.json"
    path.write_text('[{"data_origin":"demo","is_demo":true}]')
    with pytest.raises(ValueError, match="real"):
        load_dataset(path, training_config)
    path.write_text(
        json.dumps(
            [
                {
                    "data_origin": "own-consented",
                    "labels_reviewed": True,
                    "session_id": "a",
                    "player_ids": ["a"],
                    "video_sha256": "a" * 64,
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="consent"):
        load_dataset(path, training_config)
