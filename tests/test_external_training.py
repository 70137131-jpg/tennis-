import hashlib
import json

import numpy as np
import pytest
import yaml

from courtside.classifier import probabilities, promotion_failures
from data.train_external import (
    ROOT,
    fit_baseline,
    image_features,
    image_split,
    motion_crop,
    remove_exact_overlap,
    scores,
    summarize_video,
    verified_source,
    video_identity,
    write_experiment,
)


@pytest.fixture
def config():
    return yaml.safe_load((ROOT / "configs/external_training.yaml").read_text())


def keypoints():
    points = np.array([[10 + i, 20 + i * 2, 2] for i in range(18)], dtype=float)
    points[11:13, 1] += 10
    return points


def test_image_features_preserve_coco_visibility_and_normalize_position():
    points = keypoints()
    points[1, 2] = 1  # Occluded but labeled; it must not be treated as missing.
    points[2, 2] = 0
    first = image_features(points.reshape(-1).tolist())
    moved = points.copy()
    moved[:, :2] = moved[:, :2] * 3 + 200
    np.testing.assert_allclose(first, image_features(moved.reshape(-1).tolist()))
    assert first.shape == (51,)
    assert first[34 + 1] == 1 and first[34 + 2] == 0
    points[5, 2] = 0
    with pytest.raises(ValueError, match="Shoulder"):
        image_features(points.reshape(-1).tolist())


def test_temporal_features_have_finite_expected_schema_and_reject_missing_poses(config):
    poses = [keypoints()[:17].copy() for _ in range(4)]
    for i, pose in enumerate(poses):
        pose[9, 0] += i
        pose[:, 2] = 0.9
    features = summarize_video(poses, 1.7, config)
    assert features.shape == (175,) and np.isfinite(features).all()
    with pytest.raises(ValueError, match="Not enough"):
        summarize_video([], 1.7, config)


def test_motion_crop_is_label_independent_and_handles_static_background():
    first = np.zeros((100, 120, 3), dtype=np.uint8)
    second = first.copy()
    first[30:60, 20:40] = 200
    second[30:60, 40:60] = 200
    crop = motion_crop([first, second])
    assert crop is not None
    left, top, right, bottom = crop
    assert 0 <= left <= 20 and top <= 30 and 60 <= right <= 120 and 60 <= bottom <= 100
    assert motion_crop([first, first]) is None


def test_splits_purge_boundary_images_and_keep_camera_pairs_together(config):
    assert [image_split(i, config) for i in (299, 300, 319, 320, 399, 400, 419, 420)] == [
        "train", "purged", "purged", "validation", "validation", "purged", "purged", "test"]
    for number, split in ((70, "train"), (71, "purged"), (79, "purged"), (80, "validation")):
        side = video_identity(f"Indoor Field/Cross-court Shot/Side-View/ICS{number:02d}.mp4", config)
        top = video_identity(f"Indoor Field/Cross-court Shot/Top-View/ICT{number:02d}.mp4", config)
        assert side["group"] == top["group"] and side["split"] == top["split"] == split
    assert video_identity("Outdoor Field/Straight Shot/Side-View/OSS01.mp4", config)["split"] == "test"
    with pytest.raises(ValueError, match="direction"):
        video_identity("Indoor Field/Volley/Side-View/ICS01.mp4", config)


def test_content_duplicates_are_removed_and_pair_leakage_is_rejected():
    def row(group, split, digest, features):
        return {"group": group, "split": split, "sha256": digest, "features": features}

    rows = [row("a", "train", "first", [1]), row("b", "validation", "first", [2]),
            row("c", "test", "third", [1]), row("d", "test", "fourth", [4])]
    rejected = []
    assert len(remove_exact_overlap(rows, rejected)) == 2
    assert len(rejected) == 2
    with pytest.raises(ValueError, match="leak"):
        remove_exact_overlap([row("pair", "train", "first", [1]), row("pair", "test", "second", [2])], [])


def test_source_hashes_are_rechecked_before_training(tmp_path):
    dataset = tmp_path / "source"
    contents = dataset / "contents"
    contents.mkdir(parents=True)
    path = contents / "sample.json"
    path.write_bytes(b"{}")
    digest = hashlib.sha256(b"{}").hexdigest()
    inventory = {"license": "CC BY 4.0", "files_verified": True, "file_count": 1}
    (dataset / "inventory.json").write_text(json.dumps(inventory))
    (dataset / "source_files.json").write_text(json.dumps([{"path": path.name, "size_bytes": 2, "sha256": digest}]))
    assert verified_source(tmp_path, "source")[1]["hashes"][path.name] == digest
    path.write_bytes(b"[]")
    with pytest.raises(ValueError, match="checksum"):
        verified_source(tmp_path, "source")
    inventory["license"] = "research-only"
    (dataset / "inventory.json").write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="CC BY"):
        verified_source(tmp_path, "source")


def fixture_records():
    # Pure software fixture for the optimizer and artifact format, not tennis evidence.
    return [{"class": label, "split": split, "features": [float(i == j) for j in range(2)],
             "path": f"{split}-{label}", "group": f"{split}-{label}", "sha256": f"{split}-{label}"}
            for split in ("train", "validation", "test") for i, label in enumerate(("a", "b"))]


def test_optimizer_uses_training_statistics_and_supports_original_class_schema(config):
    rows = fixture_records()
    config = {**config, "epochs": 15}
    model = fit_baseline(rows, ["a", "b"], config)
    assert model == fit_baseline(rows, ["a", "b"], config)
    assert model["classes"] == ["a", "b"] and model["metrics"]["test"]["accuracy"] == 1
    assert probabilities(np.eye(2), model).sum(1) == pytest.approx(np.ones(2))
    first_weights = model["weights"]
    changed_test = [{**r, "features": [100, 100]} if r["split"] == "test" else r for r in rows]
    assert fit_baseline(changed_test, ["a", "b"], config)["weights"] == first_weights
    with pytest.raises(ValueError, match="Every class"):
        fit_baseline(rows[:1], ["a", "b"], config)


def test_evaluation_uses_supplied_classes_and_zero_support_is_visible():
    result = scores(np.array([0, 0]), np.array([0, 1]), ["ready_position", "serve"])
    assert result["accuracy"] == 0.5 and result["confusion_matrix"] == [[1, 1], [0, 0]]
    assert result["classes"][1]["support"] == 0 and result["classes"][1]["f1"] == 0


def test_external_artifact_cannot_pass_existing_app_promotion(tmp_path, config):
    rows = fixture_records()
    # Distinct inputs keep the artifact test from being filtered as exact duplicates.
    for i, row in enumerate(rows):
        row["features"] = [1.0, float(i)]
    source = {"inventory": {"source": "local-software-fixture"}, "hashes": {}}
    model = write_experiment("image_actions", rows, [], ["a", "b"], {**config, "epochs": 2}, source, tmp_path, "Fixture only")
    app_config = yaml.safe_load((ROOT / "configs/training.yaml").read_text())
    assert model["data_origin"] == "external-cc-by" and model["promoted"] is False
    assert model["player_split_verified"] is False
    assert any("Consented" in reason for reason in promotion_failures(model, app_config))
    assert (tmp_path / "image_actions_model.json").exists() and (tmp_path / "image_actions_evaluation.md").exists()
