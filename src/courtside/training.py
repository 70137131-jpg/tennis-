"""Train on manually labeled, separately consented pose exports, with frozen holdout."""

import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import yaml

from courtside.classifier import (
    CLASSES,
    classification_scores,
    fingerprint,
    fit,
    pose_features,
    probabilities,
    promotion_failures,
)
from courtside.schemas import PoseFrame


def load_dataset(path: Path, config: dict) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    sessions = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("Manifest must contain labeled real sessions")
    x, y, identities = [], [], []
    for session in sessions:
        if (
            session.get("data_origin") != "own-consented"
            or session.get("is_demo")
            or not session.get("labels_reviewed")
        ):
            raise ValueError("Only reviewed labels on real, own-consented footage may be used")
        if not all(session.get(key) for key in ["session_id", "player_ids", "video_sha256"]):
            raise ValueError("Session identity, every player's identity and video SHA256 are required")
        digest = session["video_sha256"]
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("video_sha256 must be a lowercase SHA256 digest of the original video")
        consent = session.get("consent", {})
        if not all(consent.get(key) for key in ["processing", "training", "all_players"]):
            raise ValueError("Separate processing and training consent for all recorded players is required")
        if session.get("includes_minors") and not all(consent.get(k) for k in ["guardian", "assent"]):
            raise ValueError("Guardian consent and junior assent are required")
        video_path = (path.parent / session["video"]).resolve()
        with video_path.open("rb") as video_file:
            actual_digest = hashlib.file_digest(video_file, "sha256").hexdigest()
        if actual_digest != digest:
            raise ValueError("Original video SHA256 does not match the training manifest")
        pose_path = (path.parent / session["poses"]).resolve()
        poses = [PoseFrame.model_validate(p) for p in json.loads(pose_path.read_text(encoding="utf-8"))]
        # Also catch aliases of the same exported poses across splits.
        pose_digest = hashlib.sha256(pose_path.read_bytes()).hexdigest()
        identities.append({**session, "pose_sha256": pose_digest})
        for shot in session["shots"]:
            if shot["type"] not in CLASSES or not 0 <= shot["start"] <= shot["contact"] <= shot["end"]:
                raise ValueError("Labels require a supported class and ordered shot times")
            if shot["player_identity"] not in session["player_ids"]:
                raise ValueError("Labeled player's identity must be declared in player_ids")
            sequence = [
                p
                for p in poses
                if p.player_id == shot["player_id"] and shot["start"] <= p.time <= shot["end"]
            ]
            x.append(pose_features(sequence, config["min_keypoint_confidence"], config["min_frames"]))
            y.append(CLASSES.index(shot["type"]))
    if not x:
        raise ValueError("No labeled shot windows found")
    return np.array(x), np.array(y), identities


def verify_splits(groups: list[list[dict]]) -> None:
    for left, right in itertools.combinations(groups, 2):
        for key in ["session_id", "video_sha256", "pose_sha256"]:
            overlap = {s[key] for s in left} & {s[key] for s in right}
            if overlap:
                raise ValueError(f"Train/validation/test leakage in {key}")
        if {p for s in left for p in s["player_ids"]} & {p for s in right for p in s["player_ids"]}:
            raise ValueError("Train/validation/test leakage in player identities")


def train(
    train_manifest: Path, validation_manifest: Path, test_manifest: Path, output: Path, config_path: Path
) -> dict:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    train_x, train_y, training = load_dataset(train_manifest, config)
    val_x, val_y, validation = load_dataset(validation_manifest, config)
    test_x, test_y, testing = load_dataset(test_manifest, config)
    verify_splits([training, validation, testing])
    model = fit(train_x, train_y, val_x, val_y, config)
    model.update(
        {
            "data_origin": "own-consented",
            "split_verified": True,
            "training_config": config,
            "held_out": classification_scores(test_y, probabilities(test_x, model).argmax(1)),
            "provenance": {
                "train": [{k: s[k] for k in ["session_id", "video_sha256", "pose_sha256"]} for s in training],
                "validation": [
                    {k: s[k] for k in ["session_id", "video_sha256", "pose_sha256"]} for s in validation
                ],
                "test": [{k: s[k] for k in ["session_id", "video_sha256", "pose_sha256"]} for s in testing],
            },
            "promoted": False,
        }
    )
    model["sha256"] = fingerprint(model)
    output.mkdir(parents=True, exist_ok=True)
    (output / "classifier.json").write_text(json.dumps(model, indent=2, allow_nan=False), encoding="utf-8")
    failures = promotion_failures(model, config)
    lines = [
        "# Shot classifier held-out evaluation",
        "",
        "Ground-truth shot windows only; segmentation, pose and ball accuracy are evaluated separately.",
        "",
        f"Macro F1: {model['held_out']['macro_f1']:.3f}",
        "",
        "| Class | Support | F1 |",
        "|---|---:|---:|",
    ]
    lines += [
        f"| {row['class']} | {row['support']} | {row['f1']:.3f} |" for row in model["held_out"]["classes"]
    ]
    lines += [
        "",
        "Promotion checks: " + ("passed" if not failures else "; ".join(failures)),
        "",
        "A passing classifier does not establish clinical, coaching, ball-tracking or end-to-end performance.",
    ]
    (output / "evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return model


def promote(source: Path, target: Path, config_path: Path) -> None:
    model = json.loads(source.read_text(encoding="utf-8"))
    failures = promotion_failures(model, yaml.safe_load(config_path.read_text(encoding="utf-8")))
    if failures:
        raise ValueError("Promotion blocked: " + "; ".join(failures))
    model["promoted"] = True
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(model, indent=2, allow_nan=False), encoding="utf-8")
