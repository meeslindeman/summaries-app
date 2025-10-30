from __future__ import annotations
from typing import List, Dict
from datetime import datetime, timezone
from math import exp
from collections import defaultdict

def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def pick_home_items(items: List[Dict],
                    home_count: int,
                    per_domain_quota: int,
                    half_life_hours: int) -> List[Dict]:
    now = datetime.now(timezone.utc)

    def score_one(it: Dict) -> float:
        # recency
        ts = _parse_dt(it.get("published_at")) or now
        age_h = max(0.0, (now - ts).total_seconds() / 3600.0)
        recency = exp(-age_h / max(1.0, float(half_life_hours)))
        return recency

    # pre-sort by recency
    candidates = sorted(items, key=score_one, reverse=True)

    used_per_domain = defaultdict(int)
    picked: List[Dict] = []

    # first pass: respect quota
    for it in candidates:
        d = (it.get("domain") or "").lower()
        if used_per_domain[d] >= per_domain_quota:
            continue
        picked.append(it)
        used_per_domain[d] += 1
        if len(picked) >= home_count:
            return picked

    # second pass: fill remaining ignoring quota
    if len(picked) < home_count:
        for it in candidates:
            if it in picked:
                continue
            picked.append(it)
            if len(picked) >= home_count:
                break

    return picked
