"""Create a disposable, person-free browser upload fixture."""

from pathlib import Path

import cv2
import numpy as np

output = Path("test-results/qa-input.mp4")
output.parent.mkdir(exist_ok=True)
writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), 30, (320, 240))
for frame in range(90):
    image = np.full((240, 320, 3), (45, 80, 55), np.uint8)
    cv2.circle(image, (30 + frame * 2, 100), 4, (0, 230, 230), -1)
    writer.write(image)
writer.release()
print(output.resolve())
