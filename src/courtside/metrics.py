import math

import numpy as np

from courtside.schemas import Keypoint, Metric, PoseFrame


def angle(a: Keypoint, b: Keypoint, c: Keypoint) -> float | None:
    u = np.array([a.x - b.x, a.y - b.y])
    v = np.array([c.x - b.x, c.y - b.y])
    denominator = float(np.linalg.norm(u) * np.linalg.norm(v))
    if denominator < 1e-8:
        return None
    return round(math.degrees(math.acos(float(np.clip(np.dot(u, v) / denominator, -1, 1)))), 1)


def compute_metrics(
    preparation: PoseFrame, contact: PoseFrame, finish: PoseFrame, handedness="right", min_confidence=0.65
) -> list[Metric]:
    arm = [5, 7, 9] if handedness == "left" else [6, 8, 10]
    results = []

    def add(name, label, phase, value, joints, unit, points):
        confidence = min(points[i].confidence for i in joints)
        measurable = confidence >= min_confidence and value is not None and math.isfinite(value)
        results.append(
            Metric(
                name=name,
                label=label,
                phase=phase,
                value=round(value, 2) if measurable else None,
                unit=unit,
                confidence=round(confidence, 3),
                measurable=measurable,
                reason=None if measurable else "Occluded, low-confidence or degenerate keypoints",
            )
        )

    p, c, f = preparation.keypoints, contact.keypoints, finish.keypoints
    knee_side = (
        [11, 13, 15]
        if min(p[i].confidence for i in [11, 13, 15]) >= min(p[i].confidence for i in [12, 14, 16])
        else [12, 14, 16]
    )
    add("knee_angle", "Knee bend", "preparation", angle(*(p[i] for i in knee_side)), knee_side, "°", p)
    add("elbow_extension", "Arm extension", "contact", angle(*(c[i] for i in arm)), arm, "°", c)
    torso = abs(((f[11].y + f[12].y) - (f[5].y + f[6].y)) / 2)
    height = (((f[11].y + f[12].y) / 2) - f[arm[2]].y) / torso if torso > 1e-6 else None
    add("finish_height", "Finish height", "finish", height, [5, 6, 11, 12, arm[2]], "× torso", f)
    tilt = math.degrees(math.atan2(abs(c[5].y - c[6].y), abs(c[5].x - c[6].x)))
    add("shoulder_tilt", "Shoulder tilt", "contact", tilt, [5, 6], "°", c)
    for name, label in [
        ("contact_in_front", "Contact in front"),
        ("weight_transfer", "Weight transfer"),
        ("racket_path", "Racket path"),
    ]:
        results.append(
            Metric(
                name=name,
                label=label,
                phase="contact",
                value=None,
                unit="",
                confidence=0,
                measurable=False,
                reason="Not reliably measurable from one rear-facing 2D camera",
            )
        )
    return results
