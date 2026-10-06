"""Validate runtime limits before allocating native inference resources."""

import math


def validate_runtime_config(config: dict, live: dict | None = None):
    def number(values, name, minimum=0, maximum=math.inf, integer=False):
        value = values.get(name)
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not minimum <= value <= maximum
            or integer
            and type(value) is not int
        ):
            raise ValueError(f"Invalid {name} configuration")

    for name in [
        "analysis_fps",
        "wrist_speed_threshold",
        "max_wrist_speed",
        "min_swing_displacement",
        "ball_contact_radius_torso",
        "volley_max_swing_displacement",
        "min_shot_gap_seconds",
        "max_track_gap_seconds",
        "max_ball_gap_seconds",
        "max_duration_seconds",
    ]:
        number(config, name, 0.001)
    for name in ["min_keypoint_confidence", "smoothing_alpha", "stroke_side_margin"]:
        number(config, name, 0.001, 1)
    number(config, "max_width", 2, 8192, integer=True)
    number(config, "max_shots", 1, 100000, integer=True)
    number(config, "clip_before_seconds", 0.5)
    number(config, "clip_after_seconds", 0.8)
    if config["max_wrist_speed"] <= config["wrist_speed_threshold"]:
        raise ValueError("Maximum wrist speed must exceed the shot threshold")
    for name in ["ball_hsv_lower", "ball_hsv_upper"]:
        values = config.get(name)
        if (
            not isinstance(values, list)
            or len(values) != 3
            or any(type(value) is not int or not 0 <= value <= 255 for value in values)
        ):
            raise ValueError(f"Invalid {name} configuration")
    if any(a > b for a, b in zip(config["ball_hsv_lower"], config["ball_hsv_upper"])):
        raise ValueError("Ball HSV limits must be ordered")
    if live is not None:
        for name in [
            "max_width",
            "max_frame_bytes",
            "max_frame_pixels",
            "max_buffer_poses",
            "max_pending_shots",
        ]:
            number(live, name, 2, integer=True)
        for name in ["target_fps", "history_seconds", "idle_timeout_seconds", "live_budget_ms"]:
            number(live, name, 0.001)
        window = config["clip_before_seconds"] + config["clip_after_seconds"]
        if (
            live["history_seconds"] < window + 0.3
            or live["max_buffer_poses"] < math.ceil(window * live["target_fps"] * 2) + 4
        ):
            raise ValueError("Live history must retain a complete two-player shot window")
