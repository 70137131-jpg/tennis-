"""Deterministic tennis scoring and conservative, reviewable video segmentation."""

import math
from typing import Any


def score_match(events: list[dict], config: dict) -> dict:
    games, points, sets = [0, 0], [0, 0], [0, 0]
    history: list[list[int]] = []
    server = config.get("first_server", 0)
    tiebreak_server = server
    winner = None
    tiebreak = False
    target_sets = config.get("best_of", 3) // 2 + 1
    for event in events:
        if winner is not None:
            raise ValueError("The match is complete. Undo the last point to correct it.")
        player = event["winner"]
        if player not in (0, 1):
            raise ValueError("Point winner must identify a player")
        points[player] += 1
        other = 1 - player
        game_won = (
            points[player] >= 7 and points[player] - points[other] >= 2
            if tiebreak
            else points[player] >= 4 and (config.get("no_ad", False) or points[player] - points[other] >= 2)
        )
        if game_won:
            games[player] += 1
            server = 1 - (tiebreak_server if tiebreak else server)
            if tiebreak or (games[player] >= 6 and games[player] - games[other] >= 2):
                history.append(games.copy())
                sets[player] += 1
                games = [0, 0]
                tiebreak = False
                if sets[player] == target_sets:
                    winner = player
            points = [0, 0]
            if games == [6, 6]:
                tiebreak = True
                tiebreak_server = server
        elif tiebreak:
            count = sum(points)
            server = 1 - tiebreak_server if ((count - 1) // 2) % 2 == 0 else tiebreak_server
    if tiebreak:
        display = [str(value) for value in points]
    elif min(points) >= 3:
        display = (
            ["40", "40"] if points[0] == points[1] else ["AD" if p > min(points) else "40" for p in points]
        )
    else:
        display = [str([0, 15, 30, 40][min(p, 3)]) for p in points]
    return {
        "points": display,
        "games": games,
        "sets": sets,
        "set_history": history,
        "server": server,
        "tiebreak": tiebreak,
        "winner": winner,
        "points_played": len(events),
    }


def detect_rallies(shots: list[dict], duration: float, gap: float = 4.0) -> list[dict]:
    """Group contact candidates, never infer a point winner from a tracking gap."""
    ordered = sorted((s for s in shots if 0 <= s["contact"] < duration), key=lambda s: s["contact"])
    groups: list[list[dict]] = []
    for shot in ordered:
        if not groups or shot["contact"] - groups[-1][-1]["contact"] > gap:
            groups.append([])
        groups[-1].append(shot)
    rallies = []
    for index, group in enumerate(groups):
        previous = groups[index - 1][-1]["contact"] if index else 0
        following = groups[index + 1][0]["contact"] if index + 1 < len(groups) else duration
        start = max(0, group[0]["contact"] - 1.5, (previous + group[0]["contact"]) / 2 if index else 0)
        end = min(duration, group[-1]["contact"] + 2, (following + group[-1]["contact"]) / 2)
        rallies.append(
            {
                "id": f"rally-{index + 1:04d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "shots": len(group),
                "shot_types": sorted({s["type"] for s in group}),
                "confidence": round(sum(s["confidence"] for s in group) / len(group), 3),
                "source": "contact_gap_heuristic",
                "winner": None,
            }
        )
    return rallies


def bounce_candidates(samples: list[dict | None], contacts: list[float]) -> list[dict]:
    """Image-space turns are review prompts, NOT confirmed ground contacts."""
    candidates: list[dict] = []
    for before, center, after in zip(samples, samples[1:], samples[2:]):
        if not before or not center or not after:
            continue
        if any(s.get("interpolated") or s.get("confidence", 0) < 0.75 for s in (before, center, after)):
            continue
        dt1, dt2 = center["time"] - before["time"], after["time"] - center["time"]
        if not (0 < dt1 <= 0.15 and 0 < dt2 <= 0.15):
            continue
        if any(abs(center["time"] - contact) < 0.25 for contact in contacts):
            continue
        if center["y"] - before["y"] > 1 and after["y"] - center["y"] < -1:
            if not candidates or center["time"] - candidates[-1]["time"] >= 0.3:
                candidates.append(
                    {"time": center["time"], "x": center["x"], "y": center["y"], "status": "needs_review"}
                )
    return candidates[:500]


def judge_bounce(position: list[float], zone: str, uncertainty: float = 0.12) -> dict[str, Any]:
    """Calibrated ground contact only. Borderline evidence always stays uncertain."""
    zones = {
        "singles": (0.0, 8.23, 0.0, 23.77),
        "doubles": (-1.37, 9.60, 0.0, 23.77),
        "far-left-service": (0.0, 4.115, 5.485, 11.885),
        "far-right-service": (4.115, 8.23, 5.485, 11.885),
        "near-left-service": (0.0, 4.115, 11.885, 18.285),
        "near-right-service": (4.115, 8.23, 11.885, 18.285),
    }
    if zone not in zones or len(position) != 2 or not all(math.isfinite(v) for v in position):
        raise ValueError("A valid court zone and finite ground-contact position are required")
    left, right, top, bottom = zones[zone]
    x, y = position
    outside = math.hypot(max(left - x, 0, x - right), max(top - y, 0, y - bottom))
    distance = outside if outside else -min(x - left, right - x, y - top, bottom - y)
    # The ball's footprint can overlap the line even if its center is outside.
    clearance = distance - 0.0335
    call = "out" if clearance > uncertainty else "in" if clearance < -uncertainty else "uncertain"
    return {
        "call": call,
        "position": position,
        "uncertainty_m": uncertainty,
        "clearance_m": round(clearance, 3),
        "zone": zone,
    }
