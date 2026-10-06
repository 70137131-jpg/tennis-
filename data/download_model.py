"""Download the versioned official MediaPipe task for local evaluation."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task"
EXPECTED_SHA256 = "5134a3aad27a58b93da0088d431f366da362b44e3ccfbe3462b3827a839011b1"
root = Path(__file__).resolve().parents[1]
target = root / "models/pose_landmarker_full.task"
target.parent.mkdir(exist_ok=True)
if not target.exists():
    partial = target.with_suffix(".partial")
    with urlopen(URL,timeout=90) as source, partial.open("wb") as output:
        while chunk := source.read(1024*1024):
            output.write(chunk)
    if hashlib.sha256(partial.read_bytes()).hexdigest() != EXPECTED_SHA256:
        partial.unlink(missing_ok=True)
        raise SystemExit("Downloaded pose model failed SHA256 verification")
    partial.replace(target)
digest = hashlib.sha256(target.read_bytes()).hexdigest()
if digest != EXPECTED_SHA256:
    raise SystemExit("Pose model failed SHA256 verification; remove the corrupted file and download again")
(target.parent / "manifest.json").write_text(json.dumps({"id":"mediapipe-pose-full-float16-v1","source":URL,"sha256":digest,
    "usage":"Local evaluation; model-specific redistribution/commercial terms require confirmation separately from SDK license"},indent=2))
print(f"Model ready: {target}\nSHA256: {digest}")
