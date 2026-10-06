import os
import shutil
import subprocess
from pathlib import Path

import cv2

from courtside.schemas import VideoInfo


def inspect_video(path: Path, max_duration=3600) -> VideoInfo:
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError("The file cannot be decoded as a video. Use an MP4 or MOV file.")
        width, height = int(cap.get(3)), int(cap.get(4))
        fps, frames = float(cap.get(5)), int(cap.get(7))
        ok, _ = cap.read()
        if not ok or width <= 0 or height <= 0 or fps <= 0 or frames <= 0:
            raise ValueError("Video has invalid dimensions, frame rate or no readable frames")
        duration = frames / fps
        if duration < 1 or duration > max_duration:
            raise ValueError(f"Videos must be between 1 second and {max_duration // 60} minutes")
        warnings = []
        if height < 1080:
            warnings.append(
                "Below recommended 1080p: distant joints and the ball may be difficult to measure."
            )
        if fps < 59:
            warnings.append("Below recommended 60 fps: contact timing is less precise.")
        return VideoInfo(
            width=width, height=height, fps=fps, frames=frames, duration=duration, warnings=warnings
        )
    finally:
        cap.release()


def ffmpeg_executable() -> str:
    explicit = os.environ.get("COURTSIDE_FFMPEG")
    if explicit:
        return explicit
    if shutil.which("ffmpeg"):
        return str(shutil.which("ffmpeg"))
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as exc:
        raise RuntimeError(
            "H.264 encoder unavailable. Install imageio-ffmpeg or configure COURTSIDE_FFMPEG"
        ) from exc


def encode_video(source: Path, target: Path, start=None, duration=None):
    command = [ffmpeg_executable(), "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        command += ["-ss", str(start)]
    command += ["-i", str(source)]
    if duration is not None:
        command += ["-t", str(duration)]
    command += [
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
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=7200)
