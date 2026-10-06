import pytest

from courtside.assessment import assess_technique, shot_metrics
from courtside.feedback import load_rules
from courtside.pipeline import ROOT
from courtside.schemas import Keypoint, Metric, PoseFrame, Shot


def shot(shot_type="forehand"):
    return Shot(
        id="s1",
        player_id="player-near",
        type=shot_type,
        start=0,
        contact=1,
        end=2,
        confidence=0.78,
        metrics=[
            Metric(
                name="knee_angle",
                label="Knee bend",
                phase="preparation",
                value=140,
                unit="°",
                confidence=0.99,
                measurable=True,
            ),
            Metric(
                name="finish_height",
                label="Finish height",
                phase="finish",
                value=0.4,
                unit="× torso",
                confidence=0.99,
                measurable=True,
            ),
            Metric(
                name="elbow_extension",
                label="Arm extension",
                phase="contact",
                value=170,
                unit="°",
                confidence=0.99,
                measurable=True,
            ),
        ],
    )


@pytest.fixture
def rules():
    return load_rules(ROOT / "configs/feedback_rules.yaml")


def test_assessment_explains_phase_targets_and_excludes_inapplicable_rules(rules):
    candidate = shot()
    assessment = assess_technique(candidate, rules)
    assert assessment.score == 50 and assessment.status == "provisional"
    assert assessment.measured_checks == assessment.expected_checks == 2
    assert [check.status for check in assessment.checks] == ["within_target", "below_target", "no_target"]
    assert candidate.metrics[2].target is None
    assert assessment.rule_version == rules["version"]
    assert "ball placement" in assessment.explanation
    serve = assess_technique(shot("serve"), rules)
    assert serve.score == 100 and serve.checks[1].status == "no_target"


@pytest.mark.parametrize("missing", ["occluded", "low_confidence", "absent"])
def test_one_good_check_cannot_produce_a_perfect_score(rules, missing):
    candidate = shot()
    if missing == "occluded":
        candidate.metrics[1].measurable = False
        candidate.metrics[1].value = None
        candidate.metrics[1].reason = "Occluded finish"
    elif missing == "low_confidence":
        candidate.metrics[1].confidence = 0.1
    else:
        del candidate.metrics[1]
    assessment = assess_technique(candidate, rules)
    assert assessment.score is None and assessment.status == "limited"
    assert assessment.measured_checks == 1 and assessment.expected_checks == 2
    assert "no overall score" in assessment.explanation


@pytest.mark.parametrize("shot_type", ["unknown", "volley"])
def test_unsupported_or_uncertain_shots_are_unscored(rules, shot_type):
    assessment = assess_technique(shot(shot_type), rules)
    assert assessment.score is None and assessment.status == "unavailable"


def test_disabled_preview_and_low_detection_confidence_are_unscored(rules):
    candidate = shot()
    disabled = assess_technique(candidate, rules, enabled=False)
    assert disabled.status == "disabled" and disabled.score is None
    assert all(check.target is None and check.status == "no_target" for check in disabled.checks)
    candidate.confidence = 0.4
    assert assess_technique(candidate, rules).score is None


def pose(time, knee_y=40):
    points = [Keypoint(x=10, y=10, confidence=0.99) for _ in range(17)]
    for index, (x, y) in {
        5: (10, 10),
        6: (30, 10),
        8: (40, 10),
        10: (50, 10),
        11: (10, 30),
        12: (30, 30),
        13: (10, knee_y),
        14: (30, knee_y),
        15: (20, 40),
        16: (40, 40),
    }.items():
        points[index] = Keypoint(x=x, y=y, confidence=0.99)
    return PoseFrame(
        frame=round(time * 10), time=time, player_id="player-near", side="near", keypoints=points
    )


def test_phases_use_pre_contact_and_post_contact_frames_and_reject_stale_poses():
    candidate = shot()
    metrics = shot_metrics([pose(0.5), pose(1, knee_y=30), pose(1.8)], candidate)
    assert metrics[0].value == 90  # Preparation knee, not the degenerate contact knee.
    assert metrics[1].value == 180
    missing = shot_metrics([pose(1)], candidate)
    assert missing[0].value is None and missing[2].value is None
    assert "preparation" in missing[0].reason and "finish" in missing[2].reason
    stale = shot_metrics([pose(0.5), pose(1.8)], candidate)
    assert not stale[1].measurable and "contact" in stale[1].reason
    assert shot_metrics([], candidate) == []


def test_clipped_preparation_is_not_replaced_with_a_mid_swing_pose():
    candidate = shot()
    candidate.contact = 0.2
    metrics = shot_metrics([pose(0), pose(0.2), pose(1)], candidate)
    assert not metrics[0].measurable and "preparation" in metrics[0].reason
    assert metrics[1].measurable and metrics[2].measurable
