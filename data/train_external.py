"""Train experimental baselines with the published labels of staged CC BY datasets.

These schemas are separate from the consented four-stroke Courtside classifier.
No participant consent, independent player split or production eligibility is inferred.
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import yaml

from courtside.classifier import fingerprint, probabilities
from courtside.vision import COCO_FROM_MEDIAPIPE

ROOT = Path(__file__).resolve().parents[1]
IMAGE_CLASSES = ["backhand", "forehand", "ready_position", "serve"]
VIDEO_CLASSES = ["cross_court", "straight"]
FEATURE_VERSION = "external-pose-baselines-v1"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_source(root: Path, name: str) -> tuple[Path, dict]:
    directory = root / name
    inventory = json.loads((directory / "inventory.json").read_text(encoding="utf-8"))
    if inventory.get("license") != "CC BY 4.0" or not inventory.get("files_verified"):
        raise ValueError("A verified CC BY source inventory is required")
    # This experiment uses the downloader's per-file provenance, rather than a ZIP.
    records = json.loads((directory / "source_files.json").read_text(encoding="utf-8"))
    contents = (directory / "contents").resolve()
    hashes = {}
    for record in records:
        path = (contents / record["path"]).resolve()
        if not path.is_relative_to(contents) or not path.is_file():
            raise ValueError("Source file is missing or outside its dataset")
        if path.stat().st_size != record["size_bytes"] or sha256(path) != record["sha256"]:
            raise ValueError(f"Source checksum changed: {record['path']}")
        hashes[record["path"]] = record["sha256"]
    if len(hashes) != inventory["file_count"] or len(hashes) != len(records):
        raise ValueError("Source inventory counts differ")
    print(f"Reverified {len(hashes)} source files: {name}", flush=True)
    return contents, {"inventory": inventory, "hashes": hashes}


def normalized_pose(points: np.ndarray, confidence: float) -> tuple[np.ndarray, np.ndarray, float]:
    if points.shape != (17, 3) or not np.isfinite(points).all():
        raise ValueError("Expected 17 finite COCO keypoints")
    visible = points[:, 2] >= confidence
    if not visible[[5, 6, 11, 12]].all():
        raise ValueError("Shoulder and hip keypoints are required")
    origin = points[[11, 12], :2].mean(0)
    scale = float(np.linalg.norm(points[[5, 6], :2].mean(0) - origin))
    if scale < 1e-6:
        raise ValueError("Degenerate torso scale")
    xy = (points[:, :2] - origin) / scale
    xy[~visible] = 0
    return xy, origin, scale


def image_features(keypoints: list) -> np.ndarray:
    points = np.asarray(keypoints, dtype=float).reshape(18, 3)[:17]
    # COCO visibility 1 means labeled but occluded, 2 means visible; neither is a probability.
    points[:, 2] = (points[:, 2] > 0).astype(float)
    xy, _, _ = normalized_pose(points, 0.5)
    return np.concatenate([xy.reshape(-1), points[:, 2]])


def image_split(index: int, config: dict) -> str:
    if index < config["image_train_end"]:
        return "train"
    if config["image_validation_start"] <= index < config["image_validation_end"]:
        return "validation"
    if index >= config["image_test_start"]:
        return "test"
    return "purged"


def image_records(contents: Path, source: dict, config: dict) -> tuple[list[dict], list[dict]]:
    records, rejected = [], []
    required_joints = ["nose", "left_eye", "right_eye", "left_ear", "right_ear", "left_shoulder",
                       "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist",
                       "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle", "neck"]
    for label in IMAGE_CLASSES:
        annotation_path = contents / "annotations" / f"{label}.json"
        document = json.loads(annotation_path.read_text(encoding="utf-8"))
        categories = document["categories"]
        if len(categories) != 1 or categories[0]["name"].lower() != label or categories[0]["keypoints"] != required_joints:
            raise ValueError("Unexpected action category or keypoint ordering")
        annotations = {a["image_id"]: a for a in document["annotations"]}
        if len(annotations) != len(document["annotations"]):
            raise ValueError("Multiple annotations per image are unsupported")
        images = sorted(document["images"], key=lambda image: image["file_name"])
        for index, image in enumerate(images):
            path = (annotation_path.parent / image["path"]).resolve()
            if not path.is_relative_to(contents):
                raise ValueError("Annotation references a file outside the dataset")
            relative = path.relative_to(contents).as_posix()
            record = {"path": relative, "class": label, "group": relative, "split": image_split(index, config),
                      "sha256": source["hashes"][relative], "source_index": index}
            if record["split"] == "purged":
                rejected.append({**record, "reason": "Gap between filename blocks"})
                continue
            try:
                annotation = annotations[image["id"]]
                if annotation["category_id"] != categories[0]["id"]:
                    raise ValueError("Annotation category mismatch")
                record["features"] = image_features(annotation["keypoints"]).tolist()
                records.append(record)
            except ValueError as exc:
                rejected.append({**record, "reason": str(exc)})
    return records, rejected


def video_identity(relative: str, config: dict) -> dict:
    path = Path(relative)
    if len(path.parts) != 4 or path.parts[0] not in {"Indoor Field", "Outdoor Field"}:
        raise ValueError("Unexpected video location")
    label = {"Cross-court Shot": "cross_court", "Straight Shot": "straight"}.get(path.parts[1])
    if label is None or path.parts[2] not in {"Side-View", "Top-View"}:
        raise ValueError("Unexpected shot direction or camera view")
    index = int(path.stem[3:]) - 1
    if path.parts[0] == "Outdoor Field":
        split = "test"
    elif index < config["video_train_pairs"]:
        split = "train"
    elif index >= config["video_validation_start"]:
        split = "validation"
    else:
        split = "purged"
    return {"path": relative, "class": label, "view": path.parts[2], "location": path.parts[0],
            "group": f"{path.parts[0]}/{path.parts[1]}/{index + 1}", "split": split}


def summarize_video(poses: list[np.ndarray], duration: float, config: dict) -> np.ndarray:
    normalized, origins, scales = [], [], []
    for points in poses:
        try:
            xy, origin, scale = normalized_pose(points, config["pose_confidence"])
        except ValueError:
            continue
        normalized.append(xy.reshape(-1))
        origins.append(origin)
        scales.append(scale)
    if len(normalized) < config["min_pose_frames"]:
        raise ValueError("Not enough confident pose samples")
    array = np.asarray(normalized)
    centers = np.asarray(origins) / np.mean(scales)
    return np.concatenate([array.mean(0), array.std(0), array.min(0), array.max(0),
                           np.abs(np.diff(array, axis=0)).mean(0), centers[-1] - centers[0],
                           np.ptp(centers, axis=0), [duration]])


def motion_crop(frames: list[np.ndarray]) -> tuple[int, int, int, int] | None:
    """Locate the largest moving foreground region without consulting shot labels."""
    gray = np.asarray([cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) for frame in frames])
    mask = (np.ptp(gray, axis=0) > 25).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((11, 11), np.uint8))
    _, _, components, _ = cv2.connectedComponentsWithStats(mask)
    if len(components) < 2:
        return None
    x, y, width, height, area = max(components[1:], key=lambda row: row[cv2.CC_STAT_AREA])
    frame_height, frame_width = frames[0].shape[:2]
    if not 0.0005 * frame_width * frame_height <= area <= 0.4 * frame_width * frame_height:
        return None
    padding = max(24, round(max(width, height) * 0.3))
    left, top = max(0, int(x) - padding), max(0, int(y) - padding)
    right, bottom = min(frame_width, int(x + width) + padding), min(frame_height, int(y + height) + padding)
    return left, top, right, bottom


def extract_video(path: Path, detector, mp, config: dict) -> tuple[np.ndarray, dict]:
    capture = cv2.VideoCapture(str(path))
    try:
        count, fps = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), capture.get(cv2.CAP_PROP_FPS)
        if not capture.isOpened() or count < 2 or not np.isfinite(fps) or fps <= 0:
            raise ValueError("Video metadata is invalid")
        indices = np.unique(np.linspace(0, count - 1, config["video_sample_frames"], dtype=int))
        frames = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                raise ValueError("A sampled video frame failed to decode")
            height, width = frame.shape[:2]
            if width > 960:
                frame = cv2.resize(frame, (960, round(height * 960 / width)))
            frames.append(frame)
        crop = motion_crop(frames)
        poses, cropped_frames = [], 0
        for frame in frames:
            candidates = []
            regions = [(0, 0, frame.shape[1], frame.shape[0])]
            if crop:
                regions.append(crop)
            for region_index, (left, top, right, bottom) in enumerate(regions):
                region = np.ascontiguousarray(frame[top:bottom, left:right])
                height, width = region.shape[:2]
                result = detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(region, cv2.COLOR_BGR2RGB)))
                for pose in result.pose_landmarks:
                    points = np.asarray([[pose[i].x * width + left, pose[i].y * height + top,
                                          min(pose[i].visibility, pose[i].presence)] for i in COCO_FROM_MEDIAPIPE], dtype=float)
                    try:
                        normalized_pose(points, config["pose_confidence"])
                    except ValueError:
                        continue
                    candidates.append(points)
                if candidates:
                    cropped_frames += int(region_index > 0)
                    break
            if candidates:
                # Dominant torso is a heuristic; this does not attest a stable player identity.
                poses.append(max(candidates, key=lambda p: np.linalg.norm(p[[5, 6], :2].mean(0) - p[[11, 12], :2].mean(0))))
        return summarize_video(poses, count / fps, config), {"sampled_frames": len(frames), "detected_frames": len(poses),
                                                           "cropped_frames": cropped_frames, "duration": count / fps}
    finally:
        capture.release()


def video_records(contents: Path, source: dict, config: dict, pose_model: Path, output: Path) -> tuple[list[dict], list[dict]]:
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    matplotlib_cache = output / "matplotlib_cache"
    matplotlib_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(matplotlib_cache.resolve()))
    import mediapipe as mp

    from courtside.readiness import OFFICIAL_POSE_SHA256

    pose_hash = sha256(pose_model)
    if pose_hash != OFFICIAL_POSE_SHA256:
        raise ValueError("The pinned official pose model is required")
    signature = fingerprint({"feature_version": FEATURE_VERSION, "model": pose_hash,
                             "crop": "motion-foreground-fallback-v1",
                             "samples": config["video_sample_frames"], "confidence": config["pose_confidence"],
                             "min_frames": config["min_pose_frames"], "mediapipe": mp.__version__})
    source["pose_model_sha256"] = pose_hash
    source["mediapipe_version"] = mp.__version__
    source["crop"] = "motion-foreground-fallback-v1"
    cache = output / "pose_feature_cache"
    cache.mkdir(parents=True, exist_ok=True)
    detector = mp.tasks.vision.PoseLandmarker.create_from_options(mp.tasks.vision.PoseLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(pose_model)),
        running_mode=mp.tasks.vision.RunningMode.IMAGE, num_poses=2,
        min_pose_detection_confidence=0.5, min_pose_presence_confidence=0.5))
    records, rejected = [], []
    videos = sorted(relative for relative in source["hashes"] if relative.endswith(".mp4"))
    try:
        for index, relative in enumerate(videos, 1):
            record = {**video_identity(relative, config), "sha256": source["hashes"][relative]}
            if record["split"] == "purged":
                rejected.append({**record, "reason": "Gap between indoor clip blocks"})
                continue
            cache_path = cache / f"{record['sha256']}.json"
            cached = json.loads(cache_path.read_text()) if cache_path.exists() else {}
            if cached.get("signature") != signature or cached.get("sha256") != fingerprint(cached):
                try:
                    features, details = extract_video(contents / relative, detector, mp, config)
                    cached = {"signature": signature, "features": features.tolist(), "details": details}
                except ValueError as exc:
                    cached = {"signature": signature, "error": str(exc)}
                cached["sha256"] = fingerprint(cached)
                cache_path.write_text(json.dumps(cached, allow_nan=False), encoding="utf-8")
            if "error" in cached:
                rejected.append({**record, "reason": cached["error"]})
            else:
                features = np.asarray(cached["features"])
                if features.shape != (175,) or not np.isfinite(features).all():
                    raise ValueError("Cached pose features are invalid")
                records.append({**record, "features": cached["features"], **cached["details"]})
            if index % 10 == 0 or index == len(videos):
                print(f"Video features: {index}/{len(videos)}, usable={len(records)}, excluded={len(rejected)}", flush=True)
    finally:
        detector.close()
    return records, rejected


def remove_exact_overlap(records: list[dict], rejected: list[dict]) -> list[dict]:
    seen = set()
    accepted = []
    for split in ("train", "validation", "test"):
        for record in records:
            if record["split"] != split:
                continue
            feature_hash = fingerprint({"features": record["features"]})
            if record["sha256"] in seen or feature_hash in seen:
                rejected.append({**{k: v for k, v in record.items() if k != "features"}, "reason": "Exact content or feature duplicate"})
            else:
                seen.update([record["sha256"], feature_hash])
                accepted.append(record)
    groups = [{record["group"] for record in accepted if record["split"] == split} for split in ("train", "validation", "test")]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i)):
        raise ValueError("Paired video groups leak across splits")
    return accepted


def scores(labels: np.ndarray, predicted: np.ndarray, classes: list[str]) -> dict:
    matrix = np.zeros((len(classes), len(classes)), dtype=int)
    for label, prediction in zip(labels, predicted):
        matrix[int(label), int(prediction)] += 1
    rows = []
    for index, name in enumerate(classes):
        support, guessed, correct = int(matrix[index].sum()), int(matrix[:, index].sum()), int(matrix[index, index])
        precision, recall = correct / max(guessed, 1), correct / max(support, 1)
        rows.append({"class": name, "support": support, "precision": precision, "recall": recall,
                     "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0})
    return {"samples": int(len(labels)), "accuracy": float(np.trace(matrix) / max(len(labels), 1)),
            "macro_f1": float(np.mean([row["f1"] for row in rows])), "classes": rows, "confusion_matrix": matrix.tolist()}


def fit_baseline(records: list[dict], classes: list[str], config: dict) -> dict:
    splits = {}
    for split in ("train", "validation", "test"):
        rows = [record for record in records if record["split"] == split]
        x = np.asarray([record["features"] for record in rows], dtype=float)
        y = np.asarray([classes.index(record["class"]) for record in rows])
        if not len(rows) or set(y.tolist()) != set(range(len(classes))) or not np.isfinite(x).all():
            raise ValueError(f"Every class and finite features are required in {split}")
        splits[split] = (x, y)
    train_x, train_y = splits["train"]
    mean, scale = train_x.mean(0), np.maximum(train_x.std(0), 0.01)
    x = (train_x - mean) / scale
    weights = np.random.default_rng(config["seed"]).normal(0, 0.001, (x.shape[1], len(classes)))
    bias = np.zeros(len(classes))
    targets = np.eye(len(classes))[train_y]
    best_score, best = -1.0, None
    for epoch in range(config["epochs"]):
        logits = x @ weights + bias
        exp = np.exp(logits - logits.max(1, keepdims=True))
        gradient = (exp / exp.sum(1, keepdims=True) - targets) / len(x)
        weights -= config["learning_rate"] * (x.T @ gradient + config["l2"] * weights)
        bias -= config["learning_rate"] * gradient.sum(0)
        candidate = {"mean": mean.tolist(), "scale": scale.tolist(), "weights": weights.tolist(),
                     "bias": bias.tolist(), "epoch": epoch + 1}
        val_x, val_y = splits["validation"]
        score = scores(val_y, probabilities(val_x, candidate).argmax(1), classes)["macro_f1"]
        if score > best_score:
            best_score, best = score, candidate
    if best is None:
        raise ValueError("Positive training epochs are required")
    majority = int(np.bincount(train_y, minlength=len(classes)).argmax())
    return {**best, "classes": classes,
            "metrics": {split: scores(y, probabilities(features, best).argmax(1), classes) for split, (features, y) in splits.items()},
            "majority_test": scores(splits["test"][1], np.full(len(splits["test"][1]), majority), classes)}


def write_experiment(name: str, records: list[dict], rejected: list[dict], classes: list[str], config: dict,
                     source: dict, output: Path, protocol: str) -> dict:
    records = remove_exact_overlap(records, rejected)
    model = fit_baseline(records, classes, config)
    model.update({"task": name, "feature_version": FEATURE_VERSION + ":" + name, "data_origin": "external-cc-by",
                  "experimental": True, "promoted": False, "player_split_verified": False,
                  "training_config": config, "source": source["inventory"]["source"], "license": "CC BY 4.0",
                  "provenance": {"doi": source["inventory"].get("doi"), "publisher_hash_index_sha256": fingerprint(source["hashes"]),
                                 "annotation_sha256": {path: digest for path, digest in source["hashes"].items() if path.endswith(".json")},
                                 "pose_model_sha256": source.get("pose_model_sha256"), "mediapipe_version": source.get("mediapipe_version"),
                                 "crop": source.get("crop"),
                                 "numpy_version": np.__version__, "opencv_version": cv2.__version__},
                  "split_protocol": protocol, "excluded": dict(Counter(row["reason"] for row in rejected))})
    if name == "video_direction":
        model["test_by_view"] = {}
        for view in ("Side-View", "Top-View"):
            subset = [row for row in records if row["split"] == "test" and row["view"] == view]
            if subset:
                x = np.asarray([row["features"] for row in subset])
                y = np.asarray([classes.index(row["class"]) for row in subset])
                model["test_by_view"][view] = scores(y, probabilities(x, model).argmax(1), classes)
    model["sha256"] = fingerprint(model)
    (output / f"{name}_model.json").write_text(json.dumps(model, indent=2, allow_nan=False), encoding="utf-8")
    manifest = {"protocol": protocol, "player_split_verified": False,
                "included": [{k: v for k, v in row.items() if k != "features"} for row in records], "excluded": rejected}
    (output / f"{name}_split.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    np.savez_compressed(output / f"{name}_features.npz", features=np.asarray([row["features"] for row in records]),
                        labels=np.asarray([classes.index(row["class"]) for row in records]),
                        splits=np.asarray([row["split"] for row in records]))
    held_out = model["metrics"]["test"]
    lines = [f"# Experimental {name.replace('_', ' ')} baseline", "", f"Source: {model['source']}",
             "License: CC BY 4.0; preserve the accompanying source attribution.", "", protocol, "",
             "Player/session separation is unverified. No participant-consent attestation is inferred.",
             "This model is not eligible for Courtside promotion or production coaching.", "",
             "Image actions use publisher-annotated keypoints, not automatic image recognition.",
             "Video direction uses sampled MediaPipe poses with a dominant-person heuristic, not reviewed stroke windows.", "",
             "| Split | Samples | Accuracy | Macro F1 |", "| --- | ---: | ---: | ---: |"]
    lines += [f"| {split} | {metric['samples']} | {metric['accuracy']:.3f} | {metric['macro_f1']:.3f} |" for split, metric in model["metrics"].items()]
    lines += ["", f"Majority-class test accuracy: {model['majority_test']['accuracy']:.3f}.", "",
              "| Test class | Support | Precision | Recall | F1 |", "| --- | ---: | ---: | ---: | ---: |"]
    lines += [f"| {row['class']} | {row['support']} | {row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |" for row in held_out["classes"]]
    lines += ["", f"Excluded records: {len(rejected)}. Details are in the split manifest.",
              "Exact file/feature duplicates were removed; near-duplicate images and repeated players may remain.",
              "The frozen test split was scored after validation selected the checkpoint."]
    (output / f"{name}_evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Trained {name}: test accuracy={held_out['accuracy']:.3f}, macro F1={held_out['macro_f1']:.3f}, n={held_out['samples']}", flush=True)
    return model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "models/external-baselines")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/external_training.yaml")
    parser.add_argument("--pose-model", type=Path, default=ROOT / "models/pose_landmarker_full.task")
    parser.add_argument("--task", choices=["all", "image_actions", "video_direction"], default="all")
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    tasks = [("image_actions", "tennis-player-actions", IMAGE_CLASSES), ("video_direction", "tennis-paired-views", VIDEO_CLASSES)]
    try:
        for task, dataset, classes in tasks:
            if args.task not in {"all", task}:
                continue
            contents, source = verified_source(args.data_root, dataset)
            if task == "image_actions":
                records, rejected = image_records(contents, source, config)
                protocol = (f"Per-category ordered filename blocks (zero-based): [0, {config['image_train_end']}) train, "
                            f"[{config['image_validation_start']}, {config['image_validation_end']}) validation, "
                            f"[{config['image_test_start']}, end) test; intervening images purged.")
            else:
                records, rejected = video_records(contents, source, config, args.pose_model, args.out)
                protocol = (f"Indoor pairs 1-{config['video_train_pairs']} train, "
                            f"{config['video_validation_start'] + 1}-99 validation, intervening pairs purged; "
                            "all outdoor pairs test. Both camera views stay together.")
            write_experiment(task, records, rejected, classes, config, source, args.out, protocol)
            attribution = (args.data_root / dataset / "ATTRIBUTION.txt").read_text(encoding="utf-8")
            (args.out / f"{task}_ATTRIBUTION.txt").write_text(attribution + "\nDerived artifact: experimental pose-feature softmax classifier.\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"External training failed: {exc}\n")


if __name__ == "__main__":
    main()
