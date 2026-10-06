import json
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

root = Path(__file__).resolve().parent
ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
results = []
for name in ("courtside-walkthrough-voiceover.mp4", "courtside-voiceover.mp3"):
    path = root / name
    decoded = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-af",
         "loudnorm=I=-16:TP=-1.5:LRA=7:print_format=json",
         "-f", "null", "NUL"],
        capture_output=True, text=True, check=True,
    )
    loudness = json.loads(re.findall(r'\{\s*"input_i".*?\}', decoded.stderr, re.S)[-1])
    streams = [line.strip() for line in decoded.stderr.split("Stream mapping:")[0].splitlines()
               if "Stream #" in line or "Duration:" in line]
    result = {
        "file": str(path),
        "size_bytes": path.stat().st_size,
        "full_decode": "passed",
        "streams": streams,
        "integrated_loudness_lufs": float(loudness["input_i"]),
        "true_peak_dbtp": float(loudness["input_tp"]),
    }
    assert -17 <= result["integrated_loudness_lufs"] <= -15, result
    results.append(result)

(root / "voiceover-verification.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
