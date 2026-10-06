"""A reproducible NumPy temporal-feature baseline; no pretrained tennis accuracy claims."""

import hashlib
import json
from pathlib import Path
from typing import cast

import numpy as np

from courtside.schemas import PoseFrame, ShotType

CLASSES = ["serve", "forehand", "backhand", "volley"]
FEATURE_VERSION = "pose-window-v1"
FEATURE_COUNT = 17 * 2 * 5


def pose_features(sequence: list[PoseFrame], confidence=0.65, min_frames=3) -> np.ndarray:
    ordered = sorted(sequence, key=lambda p: p.time)
    if len({(p.player_id, p.track_epoch) for p in ordered}) != 1 or any(
        not 0 < b.time - a.time <= 0.3 + 1e-6 for a, b in zip(ordered, ordered[1:])
    ):
        raise ValueError("Classification requires one continuous player track")
    usable = []
    for pose in ordered:
        points = pose.keypoints
        if min(points[i].confidence for i in [5, 6, 9, 10, 11, 12]) < confidence:
            continue
        xy = np.array([[p.x, p.y] for p in points], dtype=float)
        origin = (xy[11] + xy[12]) / 2
        scale = np.linalg.norm((xy[5] + xy[6]) / 2 - origin)
        if scale < 1 or not np.isfinite(xy).all():
            continue
        normalized = (xy - origin) / scale
        normalized[[p.confidence < confidence for p in points]] = 0
        usable.append(normalized.reshape(-1))
    if len(usable) < min_frames:
        raise ValueError("Not enough confident pose frames for classification")
    array = np.array(usable)
    return np.concatenate(
        [array.mean(0), array.std(0), array.min(0), array.max(0), np.abs(np.diff(array, axis=0)).mean(0)]
    )


def probabilities(features: np.ndarray, model: dict) -> np.ndarray:
    standardized = (features - np.array(model["mean"])) / np.array(model["scale"])
    logits = standardized @ np.array(model["weights"]) + np.array(model["bias"])
    exp = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
    return exp / exp.sum(axis=-1, keepdims=True)


def classification_scores(labels: np.ndarray, predictions: np.ndarray) -> dict:
    matrix = np.zeros((len(CLASSES), len(CLASSES)), dtype=int)
    for expected, actual in zip(labels, predictions):
        matrix[int(expected), int(actual)] += 1
    rows = []
    for index, name in enumerate(CLASSES):
        support = int(matrix[index].sum())
        guessed = int(matrix[:, index].sum())
        correct = int(matrix[index, index])
        precision, recall = correct / max(1, guessed), correct / max(1, support)
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({"class": name, "support": support, "precision": precision, "recall": recall, "f1": f1})
    return {
        "macro_f1": float(np.mean([row["f1"] for row in rows])),
        "classes": rows,
        "confusion_matrix": matrix.tolist(),
        "samples": int(len(labels)),
    }


def fit(
    train_x: np.ndarray, train_y: np.ndarray, validation_x: np.ndarray, validation_y: np.ndarray, config: dict
) -> dict:
    if set(train_y.tolist()) != set(range(len(CLASSES))):
        raise ValueError("Training requires examples of all four shot classes")
    if not len(validation_y) or not np.isfinite(train_x).all() or not np.isfinite(validation_x).all():
        raise ValueError("Finite features and nonempty validation data are required")
    mean, scale = train_x.mean(0), np.maximum(train_x.std(0), 0.01)
    x = (train_x - mean) / scale
    rng = np.random.default_rng(config["seed"])
    weights = rng.normal(0, 0.001, (train_x.shape[1], len(CLASSES)))
    bias = np.zeros(len(CLASSES))
    targets = np.eye(len(CLASSES))[train_y]
    best_score, best = -1.0, None
    for epoch in range(config["epochs"]):
        logits = x @ weights + bias
        exp = np.exp(logits - logits.max(1, keepdims=True))
        gradient = (exp / exp.sum(1, keepdims=True) - targets) / len(x)
        weights -= config["learning_rate"] * (x.T @ gradient + config["l2"] * weights)
        bias -= config["learning_rate"] * gradient.sum(0)
        candidate = {
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "weights": weights.tolist(),
            "bias": bias.tolist(),
            "epoch": epoch + 1,
        }
        score = classification_scores(validation_y, probabilities(validation_x, candidate).argmax(1))[
            "macro_f1"
        ]
        if score > best_score:
            best_score, best = score, candidate
    if best is None:
        raise ValueError("Training epochs must be positive")
    return {**best, "validation_macro_f1": best_score, "feature_version": FEATURE_VERSION, "classes": CLASSES}


def fingerprint(model: dict) -> str:
    content = {k: v for k, v in model.items() if k not in {"sha256", "promoted"}}
    return hashlib.sha256(json.dumps(content, sort_keys=True, allow_nan=False).encode()).hexdigest()


def promotion_failures(model: dict, config: dict) -> list[str]:
    failures = []
    if model.get("data_origin") != "own-consented" or not model.get("split_verified"):
        failures.append("Consented real footage and disjoint session/player/content splits are required")
    scores = model.get("held_out", {})
    if scores.get("macro_f1", 0) < config["promotion_macro_f1"]:
        failures.append("Held-out macro F1 is below the configured target")
    rows = {row["class"]: row for row in scores.get("classes", [])}
    for name in CLASSES:
        row = rows.get(name, {})
        if row.get("support", 0) < config["promotion_min_samples_per_class"]:
            failures.append(f"Insufficient held-out {name} examples")
        if row.get("f1", 0) < config["promotion_min_f1_per_class"]:
            failures.append(f"Held-out {name} F1 is below the configured target")
    if model.get("sha256") != fingerprint(model):
        failures.append("Model fingerprint does not match its contents")
    return failures


class ShotClassifier:
    def __init__(self, path: Path, config: dict):
        self.model = json.loads(path.read_text(encoding="utf-8"))
        self.config = config
        if not self.model.get("promoted") or promotion_failures(self.model, config):
            raise ValueError("Classifier must pass promotion checks before use")
        if self.model.get("feature_version") != FEATURE_VERSION or self.model.get("classes") != CLASSES:
            raise ValueError("Unsupported classifier feature schema")
        expected_shapes = {
            "mean": (FEATURE_COUNT,),
            "scale": (FEATURE_COUNT,),
            "weights": (FEATURE_COUNT, 4),
            "bias": (4,),
        }
        for key, shape in expected_shapes.items():
            value = np.array(self.model[key])
            if value.shape != shape or not np.isfinite(value).all():
                raise ValueError("Invalid classifier parameter dimensions or values")
        if np.any(np.array(self.model["scale"]) <= 0):
            raise ValueError("Classifier scales must be positive")

    def predict(self, sequence: list[PoseFrame]) -> tuple[ShotType, float]:
        try:
            features = pose_features(
                sequence, self.config["min_keypoint_confidence"], self.config["min_frames"]
            )
        except ValueError:
            return "unknown", 0.0
        scores = probabilities(features, self.model)
        index = int(scores.argmax())
        confidence = float(scores[index])
        return (
            cast(ShotType, CLASSES[index]) if confidence >= self.config["min_probability"] else "unknown",
            confidence,
        )
