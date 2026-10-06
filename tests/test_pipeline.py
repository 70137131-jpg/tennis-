from courtside.pipeline import analyze
from courtside.schemas import Report


def test_full_pipeline_with_real_model_handles_no_player(video_file, tmp_path):
    # A synthetic court/ball clip must never produce fabricated human measurements.
    import os

    import pytest

    from courtside.pipeline import ROOT

    if (
        not __import__("pathlib")
        .Path(os.environ.get("COURTSIDE_MODEL", ROOT / "models/pose_landmarker_full.task"))
        .exists()
    ):
        pytest.skip("Official pose model not present; download for the real inference smoke test")
    progress = []
    report = analyze(
        video_file, tmp_path / "report", progress=lambda percent, stage: progress.append(percent)
    )
    assert report.shots == [] and report.summary_tips == []
    assert (tmp_path / "report/annotated.mp4").stat().st_size > 100
    assert (tmp_path / "report/poses.json").exists()
    assert Report.model_validate_json((tmp_path / "report/report.json").read_text()).schema_version == "1.0.0"
    assert progress[-1] == 100


def test_rendering_measured_shots_and_clips(video_file, tmp_path, monkeypatch):
    import math

    import yaml

    import courtside.pipeline as pipeline
    from courtside.schemas import Keypoint

    class Estimator:
        def __init__(self, path):
            pass

        def detect(self, image, timestamp):
            points = [Keypoint(x=150, y=40, confidence=0.99) for _ in range(17)]
            for index, xy in {
                5: (100, 80),
                6: (180, 80),
                7: (90, 110),
                8: (200, 110),
                9: (80, 140),
                10: (220 + 70 * math.sin(timestamp / 90), 120),
                11: (110, 150),
                12: (170, 150),
                13: (110, 190),
                14: (170, 190),
                15: (120, 220),
                16: (180, 220),
            }.items():
                points[index] = Keypoint(x=xy[0], y=xy[1], confidence=0.99)
            return [points]

        def close(self):
            pass

    rules = yaml.safe_load((pipeline.ROOT / "configs/feedback_rules.yaml").read_text())
    rules["coach_validated"] = True
    monkeypatch.setattr(pipeline, "PoseEstimator", Estimator)
    monkeypatch.setattr(pipeline, "load_rules", lambda path: rules)
    report = analyze(
        video_file,
        tmp_path / "measured",
        {
            "court_corners": [[0.2, 0.1], [0.8, 0.1], [0.9, 0.9], [0.1, 0.9]],
            "analysis_fps": 15,
            "max_width": 320,
        },
    )
    assert report.shots and report.players and report.coach_validated
    assert report.pipeline_version == "baseline-3"
    assert all(shot.technique is not None for shot in report.shots)
    assert any(shot.metrics for shot in report.shots)
    assert all((tmp_path / "measured" / shot.clip).stat().st_size > 100 for shot in report.shots)
    # Unit fixture exercises output plumbing, never reports tennis accuracy.
