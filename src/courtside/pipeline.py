import json
import os
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from courtside.assessment import assess_technique, shot_metrics
from courtside.court import CourtCalibration, line_candidates
from courtside.feedback import apply_rules, load_rules, summarize_tips
from courtside.schemas import PoseFrame, Report
from courtside.shots import segment_shots
from courtside.video import encode_video, inspect_video
from courtside.vision import CONNECTIONS, BallTracker, PlayerTracker, PoseEstimator, interpolate_ball

ROOT = Path(__file__).resolve().parents[2]


def analyze(video: Path, output: Path, options=None, progress=None) -> Report:
    options = options or {}
    progress = progress or (lambda percent, stage: None)
    started = time.perf_counter()
    config = yaml.safe_load((ROOT / "configs/pipeline.yaml").read_text())
    for key in ["analysis_fps", "max_width"]:
        if key in options:
            config[key] = options[key]
    rules = load_rules(ROOT / "configs/feedback_rules.yaml")
    info = inspect_video(video, config["max_duration_seconds"])
    output.mkdir(parents=True, exist_ok=True)
    progress(3, "Reading video")
    model = Path(os.environ.get("COURTSIDE_MODEL", str(ROOT / "models/pose_landmarker_full.task")))
    estimator = PoseEstimator(model)
    scale = min(1.0, config["max_width"] / info.width)
    width, height = int(info.width * scale) // 2 * 2, int(info.height * scale) // 2 * 2
    calibration = (
        CourtCalibration(options["court_corners"], width, height) if options.get("court_corners") else None
    )
    tracker = PlayerTracker(config["smoothing_alpha"], config["max_track_gap_seconds"])
    ball_tracker = BallTracker(config)
    cap = cv2.VideoCapture(str(video))
    stride = max(1, round(info.fps / config["analysis_fps"]))
    poses, balls, times = [], [], []
    suggestions = []
    try:
        frame_index = 0
        while True:
            ok, image = cap.read()
            if not ok:
                break
            if frame_index % stride == 0:
                image = cv2.resize(image, (width, height))
                stamp = frame_index / info.fps
                if frame_index == 0:
                    cv2.imwrite(str(output / "poster.jpg"), image)
                    suggestions = line_candidates(image)
                detections = estimator.detect(image, int(round(stamp * 1000)))
                poses.extend(tracker.update(detections, frame_index, stamp, calibration))
                balls.append(ball_tracker.update(image, stamp))
                times.append(stamp)
                progress(5 + int(frame_index / info.frames * 52), "Tracking players & ball")
            frame_index += 1
    finally:
        cap.release()
        estimator.close()
    balls = interpolate_ball(balls, times, config["max_ball_gap_seconds"])
    (output / "poses.json").write_text(json.dumps([p.model_dump() for p in poses]), encoding="utf-8")
    (output / "ball.json").write_text(json.dumps(balls), encoding="utf-8")
    (output / "court.json").write_text(
        json.dumps(
            {
                "corners": options.get("court_corners"),
                "line_candidates": suggestions,
                "confirmed": bool(calibration),
            }
        )
    )
    progress(59, "Finding shot boundaries")
    shots = segment_shots(
        poses, info.duration, config, options.get("handedness", "right"), calibration, balls
    )
    classifier_path = os.environ.get("COURTSIDE_CLASSIFIER")
    if classifier_path:
        from courtside.classifier import ShotClassifier

        training_config = yaml.safe_load((ROOT / "configs/training.yaml").read_text())
        classifier = ShotClassifier(Path(classifier_path), training_config)
        for shot in shots:
            sequence = [
                p for p in poses if p.player_id == shot.player_id and shot.start <= p.time <= shot.end
            ]
            shot.type, probability = classifier.predict(sequence)
            shot.confidence = min(shot.confidence, probability)
            shot.classification_source = "trained"
            shot.classification_evidence = ["Promoted temporal pose classifier"]
    for shot in shots:
        sequence = [p for p in poses if p.player_id == shot.player_id]

        shot.metrics = shot_metrics(
            sequence,
            shot,
            options.get("handedness", "right"),
            config["min_keypoint_confidence"],
        )
        shot.technique = assess_technique(
            shot, rules, options.get("age_group", "adult"), options.get("level", "competitive"),
            rules["coach_validated"]
        )
        shot.tips = apply_rules(
            shot.metrics,
            shot.type,
            rules,
            options.get("age_group", "adult"),
            options.get("level", "competitive"),
        )
    progress(65, "Rendering skeleton overlays")
    indexed: dict[int, list[PoseFrame]] = {}
    for pose in poses:
        indexed.setdefault(pose.frame, []).append(pose)
    ball_by_frame = {round(t * info.fps): b for t, b in zip(times, balls) if b}
    raw = output / "overlay.avi"
    cap = cv2.VideoCapture(str(video))
    writer = cv2.VideoWriter(str(raw), cv2.VideoWriter.fourcc(*"MJPG"), info.fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError("Could not open video writer")
    last_poses, trail = [], []
    try:
        index = 0
        while True:
            ok, image = cap.read()
            if not ok:
                break
            image = cv2.resize(image, (width, height))
            stamp = index / info.fps
            if index in indexed:
                last_poses = indexed[index]
            active = next((s for s in shots if abs(s.contact - stamp) <= 0.15), None)
            for pose in last_poses:
                if stamp - pose.time > 0.2:
                    continue
                points = pose.keypoints
                if options.get("blur_faces", True):
                    visible_face = [p for p in points[:5] if p.confidence >= 0.5]
                    if visible_face:
                        center_x = int(np.mean([p.x for p in visible_face]))
                        center_y = int(np.mean([p.y for p in visible_face]))
                        radius = max(15, int(abs(points[5].x - points[6].x) * 0.35))
                        x0, y0 = max(0, center_x - radius), max(0, center_y - radius)
                        x1, y1 = min(width, center_x + radius), min(height, center_y + radius)
                        if x1 > x0 and y1 > y0:
                            image[y0:y1, x0:x1] = cv2.GaussianBlur(image[y0:y1, x0:x1], (31, 31), 0)
                highlighted = (
                    {joint for tip in active.tips for joint in tip.joints}
                    if active and active.player_id == pose.player_id
                    else set()
                )
                for a, b in CONNECTIONS:
                    if min(points[a].confidence, points[b].confidence) >= config["min_keypoint_confidence"]:
                        cv2.line(
                            image,
                            (int(points[a].x), int(points[a].y)),
                            (int(points[b].x), int(points[b].y)),
                            (118, 231, 199),
                            2,
                            cv2.LINE_AA,
                        )
                for joint, point in enumerate(points):
                    if point.confidence >= config["min_keypoint_confidence"]:
                        cv2.circle(
                            image,
                            (int(point.x), int(point.y)),
                            4,
                            (60, 155, 255) if joint in highlighted else (165, 242, 220),
                            -1,
                            cv2.LINE_AA,
                        )
            ball = ball_by_frame.get(index)
            if ball:
                trail.append((int(ball["x"]), int(ball["y"])))
                trail = trail[-8:]
            elif index % stride == 0:
                trail = []
            for trail_start, trail_end in zip(trail, trail[1:]):
                cv2.line(image, trail_start, trail_end, (65, 232, 224), 2)
            if active:
                cv2.rectangle(image, (14, 14), (325, 56), (35, 63, 48), -1)
                cv2.putText(
                    image,
                    f"CONTACT | {active.type.upper()}",
                    (24, 42),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (197, 239, 200),
                    2,
                )
            writer.write(image)
            index += 1
            if index % max(1, int(info.fps * 2)) == 0:
                progress(65 + int(index / info.frames * 17), "Rendering skeleton overlays")
    finally:
        cap.release()
        writer.release()
    progress(83, "Encoding browser-friendly video")
    encode_video(raw, output / "annotated.mp4")
    raw.unlink(missing_ok=True)
    for index, shot in enumerate(shots):
        shot.clip = f"{shot.id}.mp4"
        encode_video(output / "annotated.mp4", output / shot.clip, shot.start, shot.end - shot.start)
        progress(85 + int((index + 1) / max(1, len(shots)) * 13), "Creating shot clips")
    warnings = list(info.warnings)
    warnings.append(
        "Shot boundaries require validation on held-out tennis footage."
        if classifier_path
        else "Heuristic shot labels and contact timestamps require validation on held-out tennis footage."
    )
    if not calibration:
        warnings.append(
            "Court is not calibrated. Court positions and geometry-based volley labels are unavailable."
        )
    if not rules["coach_validated"]:
        warnings.append(
            "Coaching thresholds await qualified-coach approval; measured metrics are available, real tips are disabled."
        )
    if not poses:
        warnings.append("No confident players detected. Try a closer, clearer fixed-camera recording.")
    if not shots:
        warnings.append("No confident shot candidates detected. No technique findings are inferred.")
    report = Report(
        pipeline_version=config["version"],
        feedback_rules_version=rules["version"],
        coach_validated=rules["coach_validated"],
        video=info,
        shots=shots,
        summary_tips=summarize_tips([tip for shot in shots for tip in shot.tips], rules),
        players=[
            {"id": player, "side": player.removeprefix("player-")}
            for player in sorted({p.player_id for p in poses})
        ],
        warnings=warnings,
        diagnostics={
            "processing_seconds": round(time.perf_counter() - started, 2),
            "analyzed_frames": len(times),
            "pose_frames": len(poses),
            "ball_detection_rate": round(
                sum(b is not None and not b["interpolated"] for b in balls) / max(1, len(balls)), 3
            ),
            "backhand_style": options.get("backhand_style", "two-handed"),
            "model": model.name,
            "classifier": Path(classifier_path).name if classifier_path else "heuristic",
        },
    )
    (output / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    progress(100, "Complete")
    return report
