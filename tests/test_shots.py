from copy import deepcopy

import pytest
import yaml

from courtside.pipeline import ROOT
from courtside.schemas import Keypoint, PoseFrame
from courtside.shots import segment_shots


def moving_poses(hand="right", raised=False):
    result = []
    for index, x in enumerate([110, 120, 210, 220, 225]):
        points = [Keypoint(x=100, y=80, confidence=0.99) for _ in range(17)]
        points[5].x = points[11].x = 80
        points[6].x = points[12].x = 120
        for joint in [11, 12]:
            points[joint].y = 160
        points[9 if hand == "left" else 10].x = x
        points[9 if hand == "left" else 10].y = 20 if raised else 100
        result.append(
            PoseFrame(frame=index, time=index * 0.1, player_id="player-near", side="near", keypoints=points)
        )
    return result


@pytest.fixture
def config():
    return yaml.safe_load((ROOT / "configs/pipeline.yaml").read_text())


@pytest.mark.parametrize("raised,expected", [(True, "serve"), (False, "forehand")])
def test_wrist_peak_contact_classification_and_bounded_clips(config, raised, expected):
    shots = segment_shots(moving_poses(raised=raised), 0.5, config)
    assert len(shots) == 1
    assert shots[0].contact == pytest.approx(0.2)
    assert shots[0].type == expected and shots[0].end == 0.5 and shots[0].start == 0


def test_dominant_hand_backhand_volley_and_ball_confirmation(config):
    poses = moving_poses("left")
    assert segment_shots(poses, 0.5, config, "left")[0].type == "backhand"

    class Court:
        def position(self, x, y):
            return [4, 12]

    balls = [{"time": 0.2, "x": 210, "y": 100, "confidence": 0.9}]
    shot = segment_shots(moving_poses(), 0.5, config, calibration=Court(), balls=balls)[0]
    assert shot.type == "volley" and shot.confidence == 0.88 and shot.court_position == [4, 12]


def test_no_shots_from_low_confidence_static_or_sparse_poses(config):
    poses = moving_poses()
    for p in poses:
        p.keypoints[10].confidence = 0.1
    assert segment_shots(poses, 0.5, config) == []
    assert segment_shots([moving_poses()[0]] * 5, 0.5, config) == []
    poses = moving_poses()
    for p in poses:
        p.time *= 5
    assert segment_shots(poses, 3, config) == []


def test_max_shots_applies_across_both_players(config):
    first = moving_poses()
    second = deepcopy(first)
    for p in second:
        p.player_id = "player-far"
        p.side = "far"
    assert len(segment_shots(first + second, 0.5, {**config, "max_shots": 1})) == 1


@pytest.mark.parametrize("hand,expected", [("right", "forehand"), ("left", "backhand")])
@pytest.mark.parametrize("mirrored", [False, True])
def test_stroke_side_uses_anatomical_orientation(config, hand, expected, mirrored):
    poses = moving_poses(hand)
    if mirrored:
        for pose in poses:
            pose.side = "far"
            for point in pose.keypoints:
                point.x = 320 - point.x
    shot = segment_shots(poses, 0.5, config, hand)[0]
    assert shot.type == expected
    assert shot.classification_source == "heuristic" and shot.classification_evidence


@pytest.mark.parametrize("motion", ["translation", "scale", "small_wrist_jitter"])
def test_body_translation_zoom_and_small_jitter_do_not_become_shots(config, motion):
    poses = [moving_poses()[0].model_copy(deep=True) for _ in range(5)]
    for index, (pose, amount) in enumerate(zip(poses, [0, 10, 100, 110, 115])):
        pose.time = index * 0.1
        if motion == "translation":
            for point in pose.keypoints:
                point.x += amount
        elif motion == "scale":
            for point in pose.keypoints:
                point.x *= 1 + amount / 100
                point.y *= 1 + amount / 100
        else:
            pose.keypoints[10].x = [110, 110, 125, 125, 125][index]
    assert segment_shots(poses, 0.5, config) == []


def test_ambiguous_wrist_side_is_unknown_and_occluded_head_is_not_a_serve(config):
    poses = moving_poses()
    for pose, x in zip(poses, [70, 75, 101, 105, 106]):
        pose.keypoints[10].x = x
    assert segment_shots(poses, 0.5, config)[0].type == "unknown"
    poses = moving_poses(raised=True)
    for pose in poses:
        pose.keypoints[0].confidence = 0.1
    assert segment_shots(poses, 0.5, config)[0].type == "forehand"


def test_ball_proximity_is_scale_invariant_and_long_net_swings_are_not_forced_volleys(config):
    class Court:
        def position(self, x, y):
            return [4, 12]

    poses = moving_poses()
    balls = [{"time": 0.2, "x": 280, "y": 100, "confidence": 0.9}]
    original = segment_shots(poses, 0.5, config, calibration=Court(), balls=balls)[0]
    for pose in poses:
        for point in pose.keypoints:
            point.x *= 3
            point.y *= 3
    balls[0]["x"] *= 3
    balls[0]["y"] *= 3
    scaled = segment_shots(poses, 0.5, config, calibration=Court(), balls=balls)[0]
    assert original.type == scaled.type == "volley" and original.confidence == scaled.confidence == 0.88
    assert (
        segment_shots(poses, 0.5, {**config, "volley_max_swing_displacement": 0.5}, calibration=Court())[
            0
        ].type
        == "forehand"
    )


def test_overhead_swing_near_net_is_not_labeled_as_serve(config):
    class Court:
        def position(self, x, y):
            return [4, 12]

    shot = segment_shots(moving_poses(raised=True), 0.5, config, calibration=Court())[0]
    assert shot.type == "unknown" and "possible smash" in shot.classification_evidence[-1]


def test_collapsed_torso_geometry_does_not_produce_shot(config):
    poses = moving_poses()
    for pose in poses:
        for joint in [5, 6, 11, 12]:
            pose.keypoints[joint].x = 100
            pose.keypoints[joint].y = 100
    assert segment_shots(poses, 0.5, config) == []


def test_low_confidence_feet_do_not_select_geometry_based_volley(config):
    class Court:
        def position(self, x, y):
            return [4, 12]

    poses = moving_poses()
    for pose in poses:
        pose.keypoints[15].confidence = 0.1
    candidate = segment_shots(poses, 0.5, config, calibration=Court())[0]
    assert candidate.type == "forehand" and candidate.court_position is None


@pytest.mark.parametrize(
    "ball",
    [
        {"time": 0.2, "x": 210, "y": 100, "confidence": 0.1},
        {"time": 0.2, "x": 210, "y": 100, "confidence": 0.9, "interpolated": True},
        {"time": 0.2, "x": float("nan"), "y": 100, "confidence": 0.9},
        {"time": 0.2, "x": 210, "y": 100},
    ],
)
def test_unreliable_ball_evidence_cannot_raise_confidence(config, ball):
    assert segment_shots(moving_poses(), 0.5, config, balls=[ball])[0].confidence == 0.78


def test_global_limit_keeps_earliest_contact_across_players(config):
    near = moving_poses()
    for pose in near:
        pose.time += 0.4
    far = moving_poses()
    for pose in far:
        pose.player_id = "player-far"
        pose.side = "far"
        pose.time += 1
    # Player IDs sort far before near, but the earlier near swing must win.
    shots = segment_shots(near + far, 2, {**config, "max_shots": 1})
    assert len(shots) == 1 and shots[0].player_id == "player-near"
