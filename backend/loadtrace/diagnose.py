"""Why did the planner override the recommendation? Worked out from the solver's decision record.

The key question is where the planner's truck sat in the solver's view:
  not_considered   not in the fleet snapshot              -> data gap
  ruled_out        removed by a hard constraint           -> rule wrong, or its input stale
  planner_context  feasible, ranked lower, context reason -> knowledge the solver doesn't have
  scored_lower     feasible, ranked lower                 -> objective weights don't match planners
"""

from typing import Any

from . import config
from .solver import CONSTRAINT_LABELS

TITLES = {
    "not_considered": "Data gap: the planner's truck was never a candidate",
    "ruled_out": "Constraint or input: the planner's truck was ruled out",
    "planner_context": "Missing context: the planner knew something the solver doesn't",
    "scored_lower": "Scoring: the planner's truck was feasible but scored lower",
}

COMPONENT_LABELS = {
    "deadhead": "deadhead",
    "on_time": "on-time",
    "cost": "cost",
    "network_balance": "network balance",
}


def _age(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def diagnose(record: dict[str, Any], pick: str, reason_code: str) -> dict[str, Any]:
    cands = record["candidates"]
    rec_truck, rec_score = record["recommended"], record["recommended_score"]
    cand = next((c for c in cands if c["truck"] == pick), None)
    reason = config.PLANNER_REASON_CODES.get(reason_code, reason_code)

    if cand is None:
        code = "not_considered"
        text = (f"{pick} wasn't in the fleet snapshot the solver used ({len(cands)} trucks). "
                f"Check the fleet feed: the truck may be missing, renamed or newly added.")
        fix = "Data: fleet feed"

    elif not cand["feasible"]:
        code = "ruled_out"
        label = CONSTRAINT_LABELS.get(cand["eliminated_by"], cand["eliminated_by"])
        text = f"Ruled out by the {label.lower()} constraint: {cand['eliminated_detail']}."
        stale = cand["eliminated_by"] == "hours_of_service" and cand["hos_age_min"] > config.HOS_STALE_MINUTES
        if stale:
            text += (f" The hours-of-service reading behind that was {_age(cand['hos_age_min'])} old, "
                     f"so the input was probably stale, not the rule.")
        if cand["score"] > rec_score:
            text += (f" Without that constraint it would have been the top pick "
                     f"(score {cand['score']:.2f} vs {rec_score:.2f}).")
        fix = "Data: hours-of-service feed" if stale else f"Rule: {label.lower()} constraint"

    else:
        rec = next(c for c in cands if c["truck"] == rec_truck)
        weights = record["weights"]
        # Weighted difference per component: where the planner's truck won and lost.
        diff = {k: weights[k] * (cand["components"][k] - rec["components"][k]) for k in weights}
        won = max(diff, key=diff.get)
        lost = min(diff, key=diff.get)
        head = f"{pick} was feasible and ranked #{cand['rank']} (score {cand['score']:.2f} vs {rec_score:.2f})."
        if reason_code in config.CONTEXT_REASONS:
            code = "planner_context"
            text = (f"{head} The planner's reason ({reason.lower()}) isn't in the solver's data. "
                    f"If it comes up often, it's a candidate new input or constraint.")
            fix = "New input: capture it as data"
        else:
            code = "scored_lower"
            text = (f"{head} It beat {rec_truck} on {COMPONENT_LABELS[won]} but lost on "
                    f"{COMPONENT_LABELS[lost]} (weight {weights[lost]:.2f}). If planners keep choosing "
                    f"this way, the objective weights may not match how they think.")
            fix = "Model: objective weights"

    return {"code": code, "title": TITLES[code], "explanation": text, "where_to_fix": fix}
