"""Pure, versioned and confidence-gated coaching rules."""

from copy import deepcopy
from pathlib import Path

import yaml

from courtside.schemas import Metric, Tip


def load_rules(path: Path) -> dict:
    rules = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or not rules.get("version"):
        raise ValueError("Rules need a version")
    for rule in rules.get("rules", []):
        target = rule["target"]
        if len(target) != 2 or target[0] > target[1]:
            raise ValueError("Rule targets must be ordered ranges")
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
