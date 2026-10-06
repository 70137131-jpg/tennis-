from courtside.stream import adaptive_settings


def test_slow_windows_reduce_work_and_stop_at_floor():
    assert adaptive_settings(11, 10, 1280, 15) == (960, 7)
    assert adaptive_settings(5, 10, 1280, 15) == (1280, 15)
    assert adaptive_settings(20, 10, 640, 4) == (640, 4)


def test_simulated_stream_writes_latency_and_adapts(video_file, tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import pytest

    import courtside.stream as stream

    with pytest.raises(ValueError):
        stream.simulate(video_file, tmp_path, 1, 0)
    monkeypatch.setattr(stream, "analyze", lambda *args: SimpleNamespace(shots=[]))
    result = stream.simulate(video_file, tmp_path / "stream", 2, 10)
    assert len(result) == 2 and all(item["budget_met"] for item in result)
    assert json.loads((tmp_path / "stream/latency.json").read_text())["mode"] == "simulated-live"
    assert not (tmp_path / "stream/window-input.mp4").exists()
