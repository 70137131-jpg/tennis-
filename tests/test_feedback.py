from copy import deepcopy

import pytest

from courtside.feedback import apply_rules, load_rules, summarize_tips
from courtside.pipeline import ROOT
from courtside.schemas import Metric


@pytest.fixture
def rules():
    return {**load_rules(ROOT / "configs/feedback_rules.yaml"), "coach_validated": True}


def metric(value=175, confidence=0.95, measurable=True):
    return Metric(
        name="knee_angle",
        label="Knee bend",
        phase="preparation",
        value=value,
        unit="°",
        confidence=confidence,
        measurable=measurable,
    )


def test_every_tip_has_traceable_evidence(rules):
    tips = apply_rules([metric()], "forehand", rules)
    assert len(tips) == 1
    assert tips[0].value == 175 and tips[0].target == [105, 160]
    assert tips[0].rule_version == rules["version"] and tips[0].metric == "knee_angle"


@pytest.mark.parametrize(
    "value,confidence,measurable", [(175, 0.2, True), (None, 0.9, False), (140, 0.9, True)]
)
def test_uncertain_or_in_range_measurements_never_emit_tips(rules, value, confidence, measurable):
    assert apply_rules([metric(value, confidence, measurable)], "forehand", rules) == []


def test_unvalidated_rules_are_silent():
    assert apply_rules([metric()], "forehand", load_rules(ROOT / "configs/feedback_rules.yaml")) == []


def test_age_level_ranges_and_pure_function(rules):
    before = deepcopy(rules)
    assert apply_rules([metric(165)], "forehand", rules, "adult", "beginner") == []
    assert len(apply_rules([metric(165)], "forehand", rules, "adult", "competitive")) == 1
    assert rules == before


def test_summary_deduplicates_and_caps(rules):
    tips = apply_rules([metric()], "forehand", rules)
    assert len(summarize_tips(tips * 20, rules)) == 1
    assert apply_rules([metric()], "volley", rules) == []


def test_severity_ranking_and_limit(rules):
    values = [
        metric(),
        Metric(
            name="elbow_extension",
            label="Arm",
            phase="contact",
            value=120,
            unit="°",
            confidence=0.95,
            measurable=True,
        ),
    ]
    tips = apply_rules(values, "serve", {**rules, "max_tips_per_shot": 1})
    assert tips[0].metric == "elbow_extension"
