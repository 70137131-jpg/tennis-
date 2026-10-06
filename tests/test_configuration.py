from copy import deepcopy

import pytest
import yaml

from courtside.configuration import validate_runtime_config
from courtside.feedback import load_rules
from courtside.pipeline import ROOT
from courtside.vision import PoseEstimator


@pytest.fixture
def configs():
    return (
        yaml.safe_load((ROOT / "configs/pipeline.yaml").read_text()),
        yaml.safe_load((ROOT / "configs/live.yaml").read_text()),
    )


@pytest.mark.parametrize(
    "name,value",
    [
        ("analysis_fps", 0),
        ("max_width", True),
        ("max_shots", -1),
        ("min_keypoint_confidence", float("nan")),
        ("clip_before_seconds", 0.1),
        ("max_wrist_speed", 0.5),
        ("ball_hsv_lower", [20, 50]),
        ("ball_hsv_upper", [1, 1, 1]),
        ("ball_hsv_lower", [True, 1, 1]),
    ],
)
def test_invalid_analysis_limits_fail_before_inference(configs, name, value):
    pipeline, live = configs
    pipeline[name] = value
    with pytest.raises(ValueError):
        validate_runtime_config(pipeline, live)


@pytest.mark.parametrize(
    "name,value",
    [("max_pending_shots", 0), ("max_buffer_poses", 4), ("history_seconds", 1), ("target_fps", float("inf"))],
)
def test_invalid_live_limits_cannot_starve_shot_history(configs, name, value):
    pipeline, live = configs
    live[name] = value
    with pytest.raises(ValueError):
        validate_runtime_config(pipeline, live)


@pytest.mark.parametrize(
    "change", ["string_approval", "nan_target", "bad_profile", "duplicate", "negative_tolerance"]
)
def test_invalid_rule_configuration_cannot_enable_or_inflate_feedback(tmp_path, change):
    rules = deepcopy(load_rules(ROOT / "configs/feedback_rules.yaml"))
    if change == "string_approval":
        rules["coach_validated"] = "false"
    elif change == "nan_target":
        rules["rules"][0]["target"] = [float("nan"), 180]
    elif change == "bad_profile":
        rules["profiles"]["adult"]["knee_angle"] = [180, 90]
    elif change == "duplicate":
        rules["rules"].append(deepcopy(rules["rules"][0]))
    else:
        rules["level_adjustments"]["beginner"] = -10
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(rules))
    with pytest.raises(ValueError):
        load_rules(path)


def test_corrupt_official_weights_are_rejected_before_native_loading(tmp_path):
    model = tmp_path / "pose_landmarker_full.task"
    model.write_bytes(b"damaged model")
    with pytest.raises(RuntimeError, match="SHA256"):
        PoseEstimator(model)


@pytest.mark.parametrize("fault", ["epoch", "duplicate_time", "gap"])
def test_temporal_classifier_rejects_discontinuous_or_repeated_frames(fault):
    from courtside.classifier import pose_features
    from courtside.schemas import Keypoint, PoseFrame

    frames = [
        PoseFrame(
            frame=i,
            time=i * 0.1,
            player_id="p",
            side="near",
            keypoints=[Keypoint(x=1, y=1, confidence=0.9) for _ in range(17)],
        )
        for i in range(3)
    ]
    if fault == "epoch":
        frames[2].track_epoch = 1
    elif fault == "duplicate_time":
        frames[2].time = frames[1].time
    else:
        frames[2].time = 1
    with pytest.raises(ValueError, match="continuous player track"):
        pose_features(frames)
