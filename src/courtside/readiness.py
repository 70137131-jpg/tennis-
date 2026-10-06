"""Check concrete local prerequisites without claiming empirical release readiness."""

import hashlib
import importlib.util
import os
import subprocess
from pathlib import Path

import yaml

from courtside.video import ffmpeg_executable

OFFICIAL_POSE_SHA256 = "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1"


def installation_status(root: Path | None = None) -> dict:
    root = root or Path(__file__).resolve().parents[2]
    model = Path(os.environ.get("COURTSIDE_MODEL", str(root / "models/pose_landmarker_full.task")))
    errors = []
    if not model.is_file():
        errors.append("Pose model missing: run python data/download_model.py")
    elif (
        model.name == "pose_landmarker_full.task"
        and hashlib.sha256(model.read_bytes()).hexdigest() != OFFICIAL_POSE_SHA256
    ):
        errors.append("Official pose model SHA256 mismatch")
    if importlib.util.find_spec("mediapipe") is None:
        errors.append("MediaPipe is missing: install the vision extra")
    try:
        result = subprocess.run(
            [ffmpeg_executable(), "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=10
        )
        if result.returncode or "libx264" not in result.stdout:
            errors.append("FFmpeg with libx264 is required for the current local evaluation renderer")
    except (RuntimeError, OSError, subprocess.TimeoutExpired):
        errors.append("FFmpeg is unavailable")
    if not (root / "web/dist/index.html").is_file():
        errors.append("Frontend build missing: run npm ci and npm run build")
    for name in ["pipeline", "feedback_rules", "training", "live"]:
        if not (root / f"configs/{name}.yaml").is_file():
            errors.append(f"Missing {name} config")
    host = os.environ.get("COURTSIDE_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "localhost"} and len(os.environ.get("COURTSIDE_TOKEN", "")) < 24 and os.environ.get("COURTSIDE_ACCOUNTS", "0") != "1":
        errors.append("Remote binding requires a workspace token of at least 24 characters")
    rules_path = root / "configs/feedback_rules.yaml"
    validated = (
        bool(yaml.safe_load(rules_path.read_text())["coach_validated"]) if rules_path.is_file() else False
    )
    return {
        "local_ready": not errors,
        "errors": errors,
        "coach_rules_validated": validated,
        "commercial_release_ready": False,
        "outstanding_release_evidence": [
            "Held-out end-to-end tennis evaluation",
            "Qualified coach review study",
            "Academy pilot",
            "Model-weight and FFmpeg distribution terms review",
            "Target-country privacy/legal review",
            "HTTPS and backup/restore checks on target host",
        ],
    }
