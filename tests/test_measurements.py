from eval.measurements import measure


def test_independent_pose_ball_tracking_and_coach_labels():
    result = measure(
        {
            "pose_threshold_torso_fraction": 0.1,
            "ball_threshold_px": 5,
            "pose": [{"torso_px": 100, "expected": [[0, 0], [10, 10]], "predicted": [[1, 1], None]}],
            "ball": [
                {"expected": [10, 10], "predicted": [11, 11]},
                {"expected": [20, 20], "predicted": None},
                {"expected": None, "predicted": [30, 30]},
            ],
            "tracking": [
                {
                    "session_id": "s",
                    "time": 0,
                    "person_id": "p",
                    "track_id": "a",
                    "expected_side": "near",
                    "predicted_side": "near",
                },
                {
                    "session_id": "s",
                    "time": 1,
                    "person_id": "p",
                    "track_id": "b",
                    "expected_side": "near",
                    "predicted_side": "far",
                },
            ],
            "coach_reviews": [{"rating": "correct"}, {"rating": "incorrect"}],
            "system": [{"status": "completed", "processing_seconds": 3}, {"status": "failed"}],
        }
    )
    assert result["pose"]["pck"] == 0.5
    assert result["ball"]["precision"] == 0.5 and result["ball"]["recall"] == 0.5
    assert result["ball"]["trajectory_continuity"] == 0
    assert result["tracking"]["id_switches"] == 1 and result["tracking"]["near_far_accuracy"] == 0.5
    assert result["coach"]["agreement"] == 0.5 and result["system"]["failure_rate"] == 0.5
    assert measure({}) == {}
