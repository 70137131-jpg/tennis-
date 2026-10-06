"""Traceable shot-phase assessment using configured 2D technique proxies."""

from typing import Literal

from courtside.feedback import target_for
from courtside.metrics import compute_metrics
from courtside.schemas import Metric, PoseFrame, Shot, TechniqueAssessment, TechniqueCheck


def shot_metrics(
    sequence: list[PoseFrame], shot: Shot, handedness="right", min_confidence=0.65
) -> list[Metric]:
    sequence = [p for p in sequence if p.player_id == shot.player_id and shot.start <= p.time <= shot.end]
    if not sequence:
        return []
    moments = {
        "preparation": shot.contact - 0.5,
        "contact": shot.contact,
        "finish": shot.contact + 0.8,
    }
    phases = {}
    missing = set()
    for phase, moment in moments.items():
        candidates = [
            p
            for p in sequence
            if (
                p.time < shot.contact
                if phase == "preparation"
                else p.time > shot.contact
                if phase == "finish"
                else True
            )
        ]
        nearest = min(candidates or sequence, key=lambda p: abs(p.time - moment))
        phases[phase] = nearest
        if not candidates or not shot.start <= moment <= shot.end or abs(nearest.time - moment) > 0.3:
            missing.add(phase)
    metrics = compute_metrics(
        phases["preparation"], phases["contact"], phases["finish"], handedness, min_confidence
    )
    for metric in metrics:
        if metric.phase in missing:
            metric.value = None
            metric.measurable = False
            metric.reason = f"No reliable {metric.phase} pose in the shot window"
    return metrics


def assess_technique(shot: Shot, rules: dict, age_group="adult", level="competitive", enabled=True):
    checks = []
    for metric in shot.metrics:
        rule = next(
            (
                r
                for r in rules["rules"]
                if r["metric"] == metric.name and r["phase"] == metric.phase and shot.type in r["shots"]
            ),
            None,
        )
        metric.target = target_for(rule, rules, age_group, level) if rule else None
        status: Literal["within_target", "below_target", "above_target", "not_measurable", "no_target"] = (
            "no_target"
        )
        reason: str | None = "No configured target for this shot type"
        if not metric.measurable or metric.value is None or metric.confidence < rules["min_confidence"]:
            status, reason = "not_measurable", metric.reason or "Low-confidence measurement"
        elif not enabled:
            reason = "Technique comparisons are disabled"
        elif metric.target:
            status = (
                "below_target"
                if metric.value < metric.target[0]
                else "above_target"
                if metric.value > metric.target[1]
                else "within_target"
            )
            reason = None
        checks.append(
            TechniqueCheck(
                metric=metric.name,
                label=metric.label,
                phase=metric.phase,
                value=metric.value if status != "not_measurable" else None,
                unit=metric.unit,
                target=metric.target if enabled else None,
                status=status,
                reason=reason,
            )
        )
    expected = sum(shot.type in r["shots"] for r in rules["rules"])
    measured = [c for c in checks if c.status in {"within_target", "below_target", "above_target"}]
    score = None
    assessment_status: Literal["provisional", "limited", "unavailable", "disabled"] = "unavailable"
    if not enabled:
        assessment_status, explanation = (
            "disabled",
            "Enable experimental coaching to compare measured technique.",
        )
    elif shot.type == "unknown" or shot.confidence < rules["min_confidence"]:
        explanation = "Shot type is uncertain; technique targets cannot be selected reliably."
    elif not expected:
        explanation = "No technique targets are configured for this shot type yet."
    elif len(measured) < max(2, expected):
        assessment_status = "limited"
        explanation = f"Only {len(measured)} of {expected} technique checks are measurable; no overall score."
    else:
        assessment_status = "provisional"
        score = round(sum(c.status == "within_target" for c in measured) / len(measured) * 100, 1)
        explanation = (
            "Percentage of measured checks within configured ranges. "
            "This does not measure ball placement, power, spin, or overall shot success."
        )
    return TechniqueAssessment(
        status=assessment_status,
        score=score,
        measured_checks=len(measured),
        expected_checks=expected,
        checks=checks,
        explanation=explanation,
        rule_version=rules["version"],
    )
