"""Release gates are explicit evidence checks, never synthetic accuracy claims."""

import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import yaml

from courtside.classifier import CLASSES, promotion_failures


def training_readiness(root):
    config = yaml.safe_load((root / "configs/training.yaml").read_text())
    reports, groups, errors = {}, [], []
    for split in ["train", "validation", "test"]:
        path = root / f"data/labels/{split}.json"
        if not path.is_file():
            reports[split] = {
                "ready": False,
                "sessions": 0,
                "shots": 0,
                "classes": {},
                "message": "Real labeled manifest required",
            }
            errors.append(f"Missing {split} manifest")
            continue
        try:
            from courtside.training import load_dataset

            x, labels, identities = load_dataset(path, config)
            counts = Counter(CLASSES[i] for i in labels)
            if set(counts) != set(CLASSES):
                raise ValueError("Every split must include all four shot classes")
            if split == "test" and min(counts.values()) < config["promotion_min_samples_per_class"]:
                raise ValueError("Held-out support is below the promotion minimum")
            groups.append(identities)
            reports[split] = {
                "ready": True,
                "sessions": len(identities),
                "shots": len(x),
                "classes": dict(counts),
            }
        except (ValueError, KeyError, OSError, TypeError) as exc:
            errors.append(f"{split}: {exc}")
            reports[split] = {"ready": False, "message": str(exc)}
    if len(groups) == 3:
        from courtside.training import verify_splits

        try:
            verify_splits(groups)
        except ValueError as exc:
            errors.append(str(exc))
    return {"ready": not errors, "splits": reports, "errors": errors, "training_started": False}


def coach_approval(root):
    rules_path = root / "configs/feedback_rules.yaml"
    rules = yaml.safe_load(rules_path.read_text())
    path = root / "eval/evidence/coach-approval.json"
    if not path.is_file():
        return False, "Qualified coach approval and rated sample required"
    try:
        proof = json.loads(path.read_text())
        approved = all(
            [
                bool(proof.get("coach_name")),
                bool(proof.get("reviewed_at")),
                proof.get("rules_sha256") == hashlib.sha256(rules_path.read_bytes()).hexdigest(),
                proof.get("rule_version") == rules["version"],
                proof.get("sample_count", 0) >= 100,
                proof.get("agreement", 0) >= 0.85,
                proof.get("real_footage") is True,
                rules["coach_validated"] is True,
            ]
        )
        return approved, "Exact rules and coach review sample must pass"
    except (ValueError, TypeError):
        return False, "Invalid coach approval evidence"


def release_status(root: Path):
    config = yaml.safe_load((root / "configs/training.yaml").read_text())
    candidate = Path(os.environ.get("COURTSIDE_CLASSIFIER", root / "models/shot-classifier.json"))
    model_ready, model_message = False, "No promoted tennis classifier; default labels use heuristics"
    if candidate.is_file():
        try:
            model = json.loads(candidate.read_text())
            from courtside.classifier import ShotClassifier

            ShotClassifier(candidate, config)
            model_ready = not promotion_failures(model, config)
            model_message = f"Held-out window classifier macro F1: {model['held_out']['macro_f1']:.3f}"
        except (ValueError, KeyError, TypeError):
            model_message = "Classifier artifact failed promotion or schema checks"
    approved, reason = coach_approval(root)
    gates = [
        {
            "id": "classifier",
            "label": "Trained tennis classifier",
            "passed": model_ready,
            "detail": model_message,
        },
        {"id": "coach", "label": "Coach-approved ratings", "passed": approved, "detail": reason},
    ]
    definitions: dict[str, tuple[str, dict[str, float], dict[str, float]]] = {
        "court-benchmark": (
            "Independent court benchmark",
            {"shot_macro_f1": 0.85, "ball_precision": 0.9, "ball_recall": 0.85},
            {"contact_p95_seconds": 0.2},
        ),
        "live-trial": (
            "Real camera endurance trial",
            {"duration_seconds": 3600},
            {"overlay_p95_ms": 250, "feedback_p95_seconds": 5, "memory_growth_mb": 100},
        ),
        "deployment": (
            "Deployment and recovery",
            {"container_build_passed": 1, "ci_passed": 1, "https_passed": 1, "restore_passed": 1},
            {},
        ),
        "academy-pilot": ("Academy pilot", {"sessions": 20, "coach_agreement": 0.85}, {}),
        "commercial-review": (
            "Model, data and country review",
            {"licenses_reviewed": 1, "privacy_reviewed": 1},
            {},
        ),
    }
    for key, (label, lower, upper) in definitions.items():
        path = root / f"eval/evidence/{key}.json"
        passed = False
        detail = "Evidence not supplied"
        if path.is_file():
            try:
                evidence = json.loads(path.read_text())
                values = evidence["metrics"]
                passed = bool(
                    evidence.get("reviewed_by")
                    and evidence.get("reviewed_at")
                    and evidence.get("real_evidence") is True
                    and evidence.get("source_sha256")
                )
                passed &= all(
                    isinstance(values.get(k), (int, float)) and values[k] >= v for k, v in lower.items()
                )
                passed &= all(
                    isinstance(values.get(k), (int, float)) and 0 <= values[k] <= v for k, v in upper.items()
                )
                detail = (
                    "Reviewed evidence meets configured pilot targets"
                    if passed
                    else "Evidence is incomplete or below pilot targets"
                )
            except (ValueError, KeyError, TypeError):
                detail = "Invalid evidence document"
        gates.append({"id": key, "label": label, "passed": bool(passed), "detail": detail})
    return {
        "release_ready": all(g["passed"] for g in gates),
        "gates": gates,
        "training": training_readiness(root),
        "targets_are_proposed": True,
    }
