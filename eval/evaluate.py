"""Evaluate real held-out session predictions; no synthetic accuracy claims."""

import argparse
import json
from collections import Counter
from pathlib import Path

TYPES = ["serve", "forehand", "backhand", "volley"]


def evaluate(manifest, tolerance=0.2):
    labels, predictions = Counter(), Counter()
    matrix = {t: Counter() for t in TYPES}
    errors, missed, false, matched, correct = [], 0, 0, 0, Counter()
    for session in manifest:
        report = json.loads(Path(session["report"]).read_text())
        if report.get("is_demo"):
            raise ValueError("Synthetic demo reports cannot be used for held-out accuracy evaluation")
        expected = session["shots"]
        actual = report["shots"]
        used = set()
        for shot in actual:
            predictions[shot["type"]] += 1
        for label in expected:
            labels[label["type"]] += 1
            candidates = [
                (abs(p["contact"] - label["contact"]), i, p)
                for i, p in enumerate(actual)
                if i not in used and p["player_id"] == label["player_id"]
            ]
            closest = min(candidates, key=lambda row: row[0]) if candidates else None
            if not closest or closest[0] > tolerance:
                missed += 1
                continue
            error, index, prediction = closest
            used.add(index)
            errors.append(error)
            matched += 1
            if label["type"] in matrix:
                matrix[label["type"]][prediction["type"]] += 1
            if label["type"] == prediction["type"]:
                correct[label["type"]] += 1
        false += len(actual) - len(used)
    lines = [
        "# Held-out evaluation",
        "",
        f"Sessions: {len(manifest)}. Matched contacts: {matched}. Missed shots: {missed}. False shots: {false}.",
        "",
        "| Shot type | Precision | Recall | F1 | Support |",
        "|---|---:|---:|---:|---:|",
    ]
    f1s = []
    for t in TYPES:
        precision = correct[t] / predictions[t] if predictions[t] else 0
        recall = correct[t] / labels[t] if labels[t] else 0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
        if labels[t]:
            f1s.append(f1)
        lines.append(f"| {t} | {precision:.3f} | {recall:.3f} | {f1:.3f} | {labels[t]} |")
    lines += [
        "",
        f"Macro F1 across represented classes: {sum(f1s) / len(f1s):.3f}"
        if f1s
        else "Macro F1: not measurable (no labeled shots).",
        f"Mean matched contact error: {sum(errors) / len(errors):.3f}s"
        if errors
        else "Contact error: not measurable.",
        "",
        "## Confusion matrix",
        "",
        "| Actual / predicted | " + " | ".join(TYPES) + " |",
        "|---|" + "---:|" * len(TYPES),
    ]
    for t in TYPES:
        lines.append("| " + t + " | " + " | ".join(str(matrix[t][p]) for p in TYPES) + " |")
    lines += [
        "",
        "Pose PCK/OKS, tracking ID switches, ball precision/recall and coach agreement require their own hand-corrected labels. They are not inferred from shot labels.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest",
        type=Path,
        help="JSON array: session_id, player_id, report path, shots[{type,contact,player_id}]",
    )
    parser.add_argument("--out", type=Path, default=Path("eval/held_out.md"))
    parser.add_argument("--tolerance", type=float, default=0.2)
    parser.add_argument("--train-manifest", type=Path)
    args = parser.parse_args()
    held = json.loads(args.manifest.read_text())
    if args.train_manifest:
        training = json.loads(args.train_manifest.read_text())
        for key in ["session_id", "player_id"]:
            overlap = {s[key] for s in training} & {s[key] for s in held}
            if overlap:
                raise SystemExit(f"Leakage: train and evaluation share {key}: {sorted(overlap)}")
    args.out.write_text(evaluate(held, args.tolerance), encoding="utf-8")
    print(args.out)
