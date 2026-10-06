import cv2
import numpy as np


class CourtCalibration:
    """Four singles corners: far-left, far-right, near-right, near-left."""

    def __init__(self, corners: list[list[float]], width: int, height: int):
        source = np.asarray(corners, dtype=np.float32)
        if (
            source.shape != (4, 2)
            or not np.isfinite(source).all()
            or (source < 0).any()
            or (source > 1).any()
        ):
            raise ValueError("Court needs four normalized corners")
        source = (source * [width, height]).astype(np.float32)
        if abs(cv2.contourArea(source.astype(np.float32))) < width * height * 0.01 or not cv2.isContourConvex(
            source.astype(np.float32)
        ):
            raise ValueError("Corners must form a convex court in perimeter order")
        self.corners = source
        self.matrix = cv2.getPerspectiveTransform(
            source.astype(np.float32),
            np.array([[0, 0], [8.23, 0], [8.23, 23.77], [0, 23.77]], dtype=np.float32),
        )

    def position(self, x: float, y: float) -> list[float] | None:
        point = cv2.perspectiveTransform(np.array([[[x, y]]], dtype=np.float32), self.matrix)[0, 0]
        return [round(float(v), 3) for v in point] if np.isfinite(point).all() else None


def line_candidates(image: np.ndarray) -> list[list[int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=image.shape[1] // 5, maxLineGap=25)
    return [] if lines is None else lines[:, 0, :].tolist()[:40]
