import pytest
from pydantic import ValidationError

from courtside.metrics import angle, compute_metrics
from courtside.schemas import Keypoint, Metric, PoseFrame, Shot


def point(x, y, confidence=0.99):
    return Keypoint(x=x, y=y, confidence=confidence)


def pose():
    points = [point(0, 0) for _ in range(17)]
    for i, xy in {
        5: (10, 10),
        6: (30, 10),
        7: (10, 20),
        8: (40, 10),
        9: (20, 20),
        10: (50, 10),
        11: (10, 30),
        12: (30, 30),
        13: (10, 40),
        14: (30, 40),
        15: (20, 40),
        16: (40, 40),
    }.items():
        points[i] = point(*xy)
    return PoseFrame(frame=0, time=0, player_id="player-near", side="near", keypoints=points)


def test_angle_and_degenerate_geometry():
    assert angle(point(1, 0), point(0, 0), point(0, 1)) == 90
    assert angle(point(-1, 0), point(0, 0), point(1, 0)) == 180
    assert angle(point(0, 0), point(0, 0), point(1, 0)) is None


def test_key_frames_handedness_and_scale_invariance():
    p = pose()
    right = compute_metrics(p, p, p, "right")
    left = compute_metrics(p, p, p, "left")
    assert right[0].value == 90 and right[1].value == 180
    assert left[1].value == 90
    scaled = p.model_copy(deep=True)
    for keypoint in scaled.keypoints:
        keypoint.x *= 3
        keypoint.y *= 3
    assert [m.value for m in compute_metrics(scaled, scaled, scaled)] == [m.value for m in right]


def test_confidence_gate_and_unsupported_metrics():
    p = pose()
    p.keypoints[8].confidence = 0.1
    metrics = compute_metrics(p, p, p)
    assert not metrics[1].measurable and metrics[1].value is None
    assert all(
        not m.measurable for m in metrics if m.name in {"racket_path", "weight_transfer", "contact_in_front"}
    )


def test_report_schema_rejects_invalid_evidence():
    with pytest.raises(ValidationError):
        Metric(name="x", label="X", phase="contact", value=None, unit="", confidence=0.9, measurable=True)
    with pytest.raises(ValidationError):
        Metric(name="x", label="X", phase="contact", value=20, unit="", confidence=0.9, measurable=False)
    with pytest.raises(ValidationError):
        Shot(id="1", player_id="p", type="serve", start=2, contact=1, end=3, confidence=0.8)
    with pytest.raises(ValidationError):
        Keypoint(x=0, y=0, confidence=2)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_keypoints_are_rejected(value):
    with pytest.raises(ValidationError):
        Keypoint(x=value, y=0, confidence=0.9)
