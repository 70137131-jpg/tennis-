"""Compute only independently labeled pose, ball, tracking and coach metrics."""

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np


def measure(data: dict) -> dict:
    result = {}
    if data.get("pose"):
        threshold = data["pose_threshold_torso_fraction"]
        if threshold <= 0:
            raise ValueError("Pose threshold must be positive")
        hits, total, errors = 0, 0, []
        for item in data["pose"]:
            scale = item["torso_px"]
            if scale <= 0:
                raise ValueError("Reference torso size must be positive")
            for expected, actual in zip(item["expected"], item["predicted"]):
                if expected is None:
                    continue
                total += 1
                if actual is not None:
                    error = float(np.linalg.norm(np.array(expected) - actual) / scale)
                    errors.append(error)
                    hits += error <= threshold
        result["pose"] = {
            "pck": hits / total if total else None,
            "labeled_keypoints": total,
            "mean_normalized_error": float(np.mean(errors)) if errors else None,
        }
    if data.get("ball"):
        threshold = data["ball_threshold_px"]
        if threshold <= 0:
            raise ValueError("Ball threshold must be positive")
        tp, fp, fn = 0, 0, 0
        visible, matched = [], []
        for item in data["ball"]:
            expected, actual = item["expected"], item["predicted"]
            hit = (
                expected is not None
                and actual is not None
                and np.linalg.norm(np.array(expected) - actual) <= threshold
            )
            tp += int(hit)
            fp += int(actual is not None and not hit)
            fn += int(expected is not None and not hit)
            visible.append(expected is not None)
            matched.append(bool(hit))
        pairs = [i for i in range(1, len(visible)) if visible[i] and visible[i - 1]]
        result["ball"] = {
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "trajectory_continuity": sum(matched[i] and matched[i - 1] for i in pairs) / len(pairs)
            if pairs
            else None,
        }
    if data.get("tracking"):
        last, switches, correct = {}, 0, 0
        for item in sorted(data["tracking"], key=lambda value: (value["session_id"], value["time"])):
            key = (item["session_id"], item["person_id"])
            track = item.get("track_id")
            if track is not None:
                switches += int(key in last and last[key] != track)
                last[key] = track
            correct += item["expected_side"] == item.get("predicted_side")
        result["tracking"] = {
            "id_switches": switches,
            "near_far_accuracy": correct / len(data["tracking"]),
            "observations": len(data["tracking"]),
        }
    if data.get("coach_reviews"):
        counts = Counter(item["rating"] for item in data["coach_reviews"])
        if set(counts) - {"correct", "incorrect", "unhelpful"}:
            raise ValueError("Unsupported coach review rating")
        result["coach"] = {"agreement": counts["correct"] / sum(counts.values()), "counts": dict(counts)}
    if data.get("system"):
        completed = [item["processing_seconds"] for item in data["system"] if item["status"] == "completed"]
        result["system"] = {
            "failure_rate": sum(item["status"] == "failed" for item in data["system"]) / len(data["system"]),
            "mean_processing_seconds": float(np.mean(completed)) if completed else None,
        }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("labels", type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval/measurements.md"))
    args = parser.parse_args()
    results = measure(json.loads(args.labels.read_text()))
    lines = ["# Independent labeled measurements", "", "Missing label groups are not measured.", ""]
    for name, value in results.items():
        lines.extend([f"## {name.capitalize()}", "", "```json", json.dumps(value, indent=2), "```", ""])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(args.out)
