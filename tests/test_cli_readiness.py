import json
import sys

import pytest

from courtside.cli import main
from courtside.pipeline import ROOT
from courtside.readiness import installation_status


@pytest.mark.parametrize("command", [["--help"], ["--version"], ["train", "--help"], ["stream", "--help"]])
def test_help_and_version(command, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["courtside", *command])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0 and "courtside" in capsys.readouterr().out


def test_remote_serve_requires_long_token(monkeypatch):
    monkeypatch.setenv("COURTSIDE_AUTH_MODE", "local")
    monkeypatch.delenv("COURTSIDE_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["courtside", "serve", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_local_serve_calls_uvicorn(monkeypatch):
    calls = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "argv", ["courtside", "serve", "--port", "8765"])
    main()
    assert calls[0][1]["host"] == "127.0.0.1" and calls[0][1]["port"] == 8765


def test_doctor_reports_prerequisites_and_preserves_release_gates(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["courtside", "doctor"])
    main()
    value = json.loads(capsys.readouterr().out)
    assert value["local_ready"] and not value["commercial_release_ready"]
    assert not value["coach_rules_validated"]


def test_missing_installation_and_remote_token_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("COURTSIDE_AUTH_MODE", "local")
    monkeypatch.delenv("COURTSIDE_MODEL", raising=False)
    monkeypatch.setenv("COURTSIDE_HOST", "0.0.0.0")
    monkeypatch.delenv("COURTSIDE_TOKEN", raising=False)
    result = installation_status(tmp_path)
    assert not result["local_ready"]
    assert any("token" in error for error in result["errors"])
    assert any("Pose model missing" in error for error in result["errors"])


def test_cli_bad_input_and_training_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["courtside", "analyze", str(tmp_path / "bad.mp4")])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "courtside",
            "train",
            "--train",
            "missing.json",
            "--validation",
            "missing.json",
            "--test",
            "missing.json",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1


def test_cli_analysis_court_and_stream_forward_options(tmp_path, monkeypatch, capsys):
    import courtside.pipeline
    import courtside.stream
    from courtside.schemas import Report, VideoInfo

    calls = []

    def fake_analyze(video, output, options, progress):
        calls.append(options)
        progress(100, "Complete")
        return Report(
            feedback_rules_version="test",
            video=VideoInfo(width=320, height=240, fps=30, frames=90, duration=3),
            shots=[],
        )

    monkeypatch.setattr(courtside.pipeline, "analyze", fake_analyze)
    court = tmp_path / "court.json"
    court.write_text("[[0,0],[1,0],[1,1],[0,1]]")
    monkeypatch.setattr(sys, "argv", ["courtside", "analyze", "test.mp4", "--court", str(court), "--no-blur"])
    main()
    assert not calls[0]["blur_faces"] and calls[0]["court_corners"][2] == [1, 1]
    monkeypatch.setattr(courtside.stream, "simulate", lambda *args: calls.append(args))
    monkeypatch.setattr(sys, "argv", ["courtside", "stream", "test.mp4"])
    main()
    assert calls[-1][2:] == (6.0, 10.0)


def test_cli_cleanup(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("COURTSIDE_STORAGE", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["courtside", "cleanup"])
    main()
    assert "Deleted 0" in capsys.readouterr().out


def test_pose_model_hash_verification(tmp_path, monkeypatch):
    model = tmp_path / "pose_landmarker_full.task"
    model.write_bytes(b"corrupt model")
    monkeypatch.setenv("COURTSIDE_MODEL", str(model))
    assert any("SHA256" in error for error in installation_status(ROOT)["errors"])
