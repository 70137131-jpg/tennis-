"""Simulated-live windows with adaptive workload; experimental, not a live camera server."""

import json
import time
from pathlib import Path

from courtside.pipeline import analyze
from courtside.video import encode_video, inspect_video


def adaptive_settings(seconds: float, budget: float, width: int, fps: int) -> tuple[int, int]:
    if seconds <= budget:
        return width, fps
    return max(640, width - 320), max(4, fps // 2)


def simulate(video: Path, output: Path, window_seconds=6.0, budget_seconds=10.0):
    if window_seconds < 2 or budget_seconds <= 0:
        raise ValueError("Window must be at least 2 seconds; budget must be positive")
    info = inspect_video(video)
    output.mkdir(parents=True, exist_ok=True)
    start, width, fps = 0.0, 1280, 15
    diagnostics: list[dict] = []
    while start < info.duration:
        remaining = info.duration - start
        if remaining < 1:
            break
        clip = output / "window-input.mp4"
        encode_video(video, clip, start, min(window_seconds, remaining))
        stamp = time.perf_counter()
        directory = output / f"window-{len(diagnostics) + 1:04d}"
        report = analyze(clip, directory, {"analysis_fps": fps, "max_width": width})
        elapsed = time.perf_counter() - stamp
        diagnostics.append(
            {
                "start": start,
                "latency_seconds": round(elapsed, 3),
                "max_width": width,
                "analysis_fps": fps,
                "shots": len(report.shots),
                "budget_met": elapsed <= budget_seconds,
            }
        )
        print(json.dumps(diagnostics[-1]), flush=True)
        width, fps = adaptive_settings(elapsed, budget_seconds, width, fps)
        start += window_seconds
    (output / "latency.json").write_text(
        json.dumps(
            {"mode": "simulated-live", "target_seconds": budget_seconds, "windows": diagnostics}, indent=2
        )
    )
    (output / "window-input.mp4").unlink(missing_ok=True)
    return diagnostics
