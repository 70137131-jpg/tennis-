import pytest

from courtside.court import CourtCalibration
from courtside.schemas import Keypoint
from courtside.vision import PlayerTracker, interpolate_ball


def detection(x, y):
    return [Keypoint(x=x, y=y, confidence=0.99) for _ in range(17)]


def test_tracking_survives_detector_order_changes():
    tracker = PlayerTracker(alpha=1)
    first = tracker.update([detection(100, 300), detection(100, 100)], 0, 0)
    second = tracker.update([detection(101, 101), detection(101, 301)], 1, 0.067)
    assert first[0].player_id == second[1].player_id == "player-near"
    assert second[0].player_id == "player-far"
    assert tracker.update([], 2, 0.1) == []


def test_ball_interpolation_is_bounded_and_never_extrapolates():
    a = {"time": 0.1, "x": 10, "y": 20, "confidence": 0.9, "interpolated": False}
    b = {"time": 0.3, "x": 30, "y": 40, "confidence": 0.8, "interpolated": False}
    output = interpolate_ball([None, a, None, b, None], [0, 0.1, 0.2, 0.3, 0.4], 0.21)
    assert output[0] is None and output[-1] is None
    assert output[2]["x"] == pytest.approx(20)
    assert output[2]["confidence"] < 0.8 and output[2]["interpolated"]
    assert interpolate_ball([a, None, b], [0.1, 0.2, 0.3], 0.1)[1] is None


def test_homography_maps_singles_corners():
    court = CourtCalibration([[0.2, 0.1], [0.8, 0.1], [0.9, 0.9], [0.1, 0.9]], 1000, 1000)
    assert court.position(200, 100) == pytest.approx([0, 0], abs=0.01)
    assert court.position(900, 900) == pytest.approx([8.23, 23.77], abs=0.01)


@pytest.mark.parametrize(
    "corners", [[[0, 0]] * 4, [[0, 0], [1, 1], [1, 0], [0, 1]], [[0, 0], [1, 0], [2, 1], [0, 1]]]
)
def test_invalid_court_geometry_rejected(corners):
    with pytest.raises(ValueError):
        CourtCalibration(corners, 1000, 1000)
