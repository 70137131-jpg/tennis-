"""Concatenate only bounded, reviewed intervals from the privacy-processed video."""

import subprocess
from pathlib import Path

from courtside.video import ffmpeg_executable


def export_highlights(source: Path, target: Path, intervals: list[tuple[float, float]]):
    if not intervals or len(intervals) > 50:
        raise ValueError("Select between 1 and 50 rallies")
    if sum(end - start for start, end in intervals) > 300:
        raise ValueError("Highlight exports are limited to five minutes")
    chains = []
    for index, (start, end) in enumerate(intervals):
        chains.append(f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]")
    chains.append(
        "".join(f"[v{i}]" for i in range(len(intervals))) + f"concat=n={len(intervals)}:v=1:a=0[out]"
    )
    subprocess.run(
        [
            ffmpeg_executable(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            ";".join(chains),
            "-map",
            "[out]",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target),
        ],
        check=True,
        capture_output=True,
        timeout=900,
    )

    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError("Exported video is unavailable. Check the storage path and available disk space.")
