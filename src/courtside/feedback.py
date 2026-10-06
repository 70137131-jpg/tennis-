"""Pure, versioned and confidence-gated coaching rules."""

import math
from copy import deepcopy
from pathlib import Path

import yaml

from courtside.schemas import Metric, Tip


def load_rules(path: Path) -> dict:
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or not isinstance(rules.get("version"), str) or not rules["version"]:
        raise ValueError("Rules need a version")
    if type(rules.get("coach_validated")) is not bool:
        raise ValueError("coach_validated must be a boolean")
    confidence = rules.get("min_confidence")
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or not 0 < confidence <= 1
    ):
        raise ValueError("Rules need a finite confidence threshold")
    for name in ["max_tips_per_shot", "max_tips_per_session"]:
        if type(rules.get(name)) is not int or not 0 <= rules[name] <= 100:
            raise ValueError(f"Invalid {name}")

    def check_range(target):
        if (
            not isinstance(target, list)
            or len(target) != 2
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in target)
            or target[0] > target[1]
        ):
            raise ValueError("Rule targets must be finite ordered ranges")

    entries = rules.get("rules")
    if not isinstance(entries, list):
        raise ValueError("Rules must be a list")
    seen = set()
    for rule in rules.get("rules", []):
        if (
            not isinstance(rule, dict)
            or not isinstance(rule.get("metric"), str)
            or rule.get("phase") not in {"preparation", "contact", "finish"}
            or not isinstance(rule.get("shots"), list)
            or not rule["shots"]
        ):
            raise ValueError("Each rule needs a metric, phase and supported shot types")
        check_range(rule.get("target"))
        if any(
            not isinstance(rule.get(name), str) or not rule[name].strip()
            for name in ["metric", "title", "explanation"]
        ):
            raise ValueError("Rules need nonempty metric, title and explanation strings")
        joints = rule.get("joints", [])
        if not isinstance(joints, list) or any(type(j) is not int or not 0 <= j < 17 for j in joints):
            raise ValueError("Rule joints must be COCO keypoint indices")
        for shot_type in rule["shots"]:
            key = (rule["metric"], rule["phase"], shot_type)
            if shot_type not in {"serve", "forehand", "backhand", "volley"} or key in seen:
                raise ValueError("Rules must have unique targets for each shot and phase")
            seen.add(key)
        if type(rule.get("severity")) is not int or not 1 <= rule["severity"] <= 3:
            raise ValueError("Rule severity must be between 1 and 3")
    profiles = rules.get("profiles", {})
    adjustments = rules.get("level_adjustments", {})
    if not isinstance(profiles, dict) or not isinstance(adjustments, dict):
        raise ValueError("Rule profiles and adjustments must be mappings")
    for profile in profiles.values():
        if not isinstance(profile, dict):
            raise ValueError("Rule profiles must contain target mappings")
        for target in profile.values():
            check_range(target)
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in adjustments.values()):
        raise ValueError("Level tolerances must be finite and nonnegative")
    return rules


def target_for(rule: dict, config: dict, age_group: str, level: str) -> list[float]:
    target = config.get("profiles", {}).get(age_group, {}).get(rule["metric"], rule["target"])
    tolerance = (
        config.get("level_adjustments", {}).get(level, 0)
        if rule["metric"] in {"knee_angle", "elbow_extension"}
        else 0
    )
    return [target[0] - tolerance, target[1] + tolerance]


def apply_rules(
    metrics: list[Metric], shot_type: str, config: dict, age_group="adult", level="competitive"
) -> list[Tip]:
    if not config.get("coach_validated", False):
        return []
    tips = []
    for rule in config.get("rules", []):
        metric = next((m for m in metrics if m.name == rule["metric"] and m.phase == rule["phase"]), None)
        if shot_type not in rule["shots"] or metric is None:
            continue
        if not metric.measurable or metric.value is None or metric.confidence < config["min_confidence"]:
            continue
        target = target_for(rule, config, age_group, level)
        if target[0] <= metric.value <= target[1]:
            continue
        tips.append(
            Tip(
                id=f"{metric.name}-{metric.phase}",
                metric=metric.name,
                value=metric.value,
                target=target,
                severity=rule["severity"],
                title=rule["title"],
                explanation=rule["explanation"],
                joints=deepcopy(rule.get("joints", [])),
                rule_version=config["version"],
            )
        )
    return sorted(tips, key=lambda tip: -tip.severity)[: config.get("max_tips_per_shot", 3)]


def summarize_tips(tips: list[Tip], config: dict) -> list[Tip]:
    unique: dict[str, Tip] = {}
    for tip in sorted(tips, key=lambda t: -t.severity):
        unique.setdefault(tip.metric, tip)
    return list(unique.values())[: config.get("max_tips_per_session", 5)]
