"""Masterpiece helper calculations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from craftworld_api import predict_reward

MP_TIER_THRESHOLDS = [
    10_000,
    35_000,
    85_000,
    250_000,
    1_000_000,
    3_250_000,
    15_000_000,
    50_000_000,
    100_000_000,
    200_000_000,
]


def get_mp_per_unit_rewards(mp_id: str, symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Pre-compute masterpiece points, XP, and power per 1 unit."""
    unique_syms = sorted({(s or "").upper() for s in symbols if s})
    points: Dict[str, float] = {}
    xp: Dict[str, float] = {}
    power: Dict[str, float] = {}

    if not mp_id or not unique_syms:
        return {"points": points, "xp": xp, "power": power}

    for sym in unique_syms:
        try:
            pr = predict_reward(mp_id, [{"symbol": sym, "amount": 1.0}]) or {}
            points[sym] = float(pr.get("masterpiecePoints") or 0.0)
            xp[sym] = float(pr.get("experiencePoints") or 0.0)
            power[sym] = float(pr.get("requiredPower") or 0.0)
        except Exception:
            points[sym] = 0.0
            xp[sym] = 0.0
            power[sym] = 0.0

    return {"points": points, "xp": xp, "power": power}


def compute_leaderboard_gap_for_highlight(
    rows: List[Dict[str, Any]],
    highlight_query: str,
) -> Optional[Dict[str, Any]]:
    """Find a highlighted leaderboard row and calculate the gaps above/below."""
    highlight_query = (highlight_query or "").strip()
    if not highlight_query or not rows:
        return None

    q = highlight_query.lower()

    def _get_points(r: Dict[str, Any]) -> float:
        try:
            return float(r.get("masterpiecePoints") or 0)
        except Exception:
            return 0.0

    def _get_name(r: Dict[str, Any]) -> str:
        prof = r.get("profile") or {}
        return prof.get("displayName") or prof.get("uid") or "?"

    idx = None
    for i, row in enumerate(rows):
        prof = row.get("profile") or {}
        name = (prof.get("displayName") or "").lower()
        uid = (prof.get("uid") or "").lower()
        if q in name or q in uid:
            idx = i
            break

    if idx is None:
        return None

    cur_row = rows[idx]
    cur_pts = _get_points(cur_row)
    cur_pos = cur_row.get("position")

    above = rows[idx - 1] if idx > 0 else None
    gap_up = None
    above_name = None
    above_pos = None
    if above is not None:
        above_pts = _get_points(above)
        gap_up = max(0.0, above_pts - cur_pts + 1.0)
        above_name = _get_name(above)
        above_pos = above.get("position")

    below = rows[idx + 1] if idx + 1 < len(rows) else None
    gap_down = None
    below_name = None
    below_pos = None
    if below is not None:
        below_pts = _get_points(below)
        gap_down = max(0.0, cur_pts - below_pts + 1.0)
        below_name = _get_name(below)
        below_pos = below.get("position")

    return {
        "position": cur_pos,
        "points": cur_pts,
        "gap_up": gap_up,
        "gap_down": gap_down,
        "above_name": above_name,
        "above_pos": above_pos,
        "below_name": below_name,
        "below_pos": below_pos,
    }
