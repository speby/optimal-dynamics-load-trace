"""A stand-in for the optimization engine, just detailed enough to leave a decision trace.

Given the candidate trucks in an input snapshot, it applies the hard constraints in order,
scores the feasible trucks with the objective weights, and returns a decision record:
versions, the elimination funnel, every candidate with its score breakdown, and the pick.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

from . import config


@dataclass
class Candidate:
    truck: str
    hos_hours_left: float        # hours-of-service the driver has left
    hos_age_min: int             # how old that hours-of-service reading is
    eld_age_min: int             # how old the truck's last location ping is
    equipment: str
    deadhead_mi: int             # empty miles to pickup
    components: dict[str, float]  # objective components, each 0..1
    # Filled in by solve():
    feasible: bool = True
    eliminated_by: str | None = None
    eliminated_detail: str | None = None
    score: float = 0.0
    rank: int | None = None
    warnings: list[str] = field(default_factory=list)


CONSTRAINT_LABELS = {
    "hours_of_service": "Hours of service",
    "equipment": "Equipment",
    "deadhead_distance": "Deadhead distance",
}


def _apply_constraints(c: Candidate) -> None:
    if c.hos_hours_left < config.TRIP_HOURS_NEEDED:
        c.feasible, c.eliminated_by = False, "hours_of_service"
        c.eliminated_detail = f"{c.hos_hours_left:g}h left, trip needs {config.TRIP_HOURS_NEEDED:g}h"
    elif c.equipment != config.REQUIRED_EQUIPMENT:
        c.feasible, c.eliminated_by = False, "equipment"
        c.eliminated_detail = f"has {c.equipment}, load needs {config.REQUIRED_EQUIPMENT}"
    elif c.deadhead_mi > config.MAX_DEADHEAD_MILES:
        c.feasible, c.eliminated_by = False, "deadhead_distance"
        c.eliminated_detail = f"{c.deadhead_mi} mi from pickup, max {config.MAX_DEADHEAD_MILES}"


def _warn(c: Candidate) -> None:
    if c.hos_age_min > config.HOS_STALE_MINUTES:
        c.warnings.append(f"hours-of-service data {c.hos_age_min // 60}h{c.hos_age_min % 60:02d}m old")
    if c.eld_age_min > config.ELD_FRESHNESS_MAX_MINUTES * config.SOFT_WARNING_RATIO:
        c.warnings.append(f"location ping {c.eld_age_min}m old (limit {config.ELD_FRESHNESS_MAX_MINUTES}m)")


def solve(solve_id: str, load_id: str, input_snapshot: str, candidates: list[Candidate]) -> dict[str, Any]:
    weights = config.OBJECTIVE_WEIGHTS
    for c in candidates:
        _apply_constraints(c)
        _warn(c)
        # Score everyone, even ruled-out trucks, so we can say how they would have ranked.
        c.score = round(sum(weights[k] * c.components.get(k, 0.0) for k in weights), 3)

    feasible = sorted((c for c in candidates if c.feasible), key=lambda c: (-c.score, c.truck))
    for i, c in enumerate(feasible, start=1):
        c.rank = i

    funnel: list[dict[str, Any]] = [{"step": "considered", "label": "Considered", "count": len(candidates)}]
    for name, label in CONSTRAINT_LABELS.items():
        removed = sum(1 for c in candidates if c.eliminated_by == name)
        funnel.append({"step": name, "label": label, "removed": removed})
    funnel.append({"step": "feasible", "label": "Feasible", "count": len(feasible)})

    best = feasible[0] if feasible else None
    runner_up = feasible[1] if len(feasible) > 1 else None
    return {
        "solve_id": solve_id,
        "load_id": load_id,
        "model_version": config.MODEL_VERSION,
        "objective_config": config.OBJECTIVE_CONFIG,
        "constraint_set": config.CONSTRAINT_SET,
        "input_snapshot": input_snapshot,
        "weights": dict(weights),
        "constraints": {
            "trip_hours_needed": config.TRIP_HOURS_NEEDED,
            "max_deadhead_miles": config.MAX_DEADHEAD_MILES,
            "required_equipment": config.REQUIRED_EQUIPMENT,
        },
        "funnel": funnel,
        "recommended": best.truck if best else None,
        "recommended_score": best.score if best else None,
        "margin": round(best.score - runner_up.score, 3) if best and runner_up else None,
        "input_warnings": [f"{c.truck}: {w}" for c in candidates for w in c.warnings],
        "candidates": [asdict(c) for c in sorted(candidates, key=lambda c: (c.rank or 10_000, -c.score))],
    }
