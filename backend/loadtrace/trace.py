"""Derive a load's trace from its events. Nothing about current status is stored."""

from datetime import datetime
from typing import Any

from . import config
from .diagnose import diagnose
from .store import Event, Store

TOP_CANDIDATES = 5


def _decision(store: Store, load_id: str, solve_id: str | None) -> dict[str, Any] | None:
    """The solver's decision record, fetched through the pointer on the solve_run event."""
    if not solve_id:
        return None
    return store.decision_record(solve_id, load_id)


def decision_view(record: dict[str, Any], pick: str | None) -> dict[str, Any]:
    """Trim a decision record for the page: top candidates plus the planner's truck."""
    top = [c for c in record["candidates"] if c["feasible"]][:TOP_CANDIDATES]
    extra = [c for c in record["candidates"] if c["truck"] == pick and c not in top]
    return {k: v for k, v in record.items() if k != "candidates"} | {"candidates": top + extra}


def build_trace(store: Store, load_id: str, now: datetime | None = None) -> dict[str, Any]:
    now = now or config.NOW
    events = store.events_for(load_id)
    latest: dict[str, Event] = {}
    for e in events:  # ordered by time, so the last one for a stage wins
        latest[e.stage] = e

    stages: list[dict[str, Any]] = []
    first_failure: str | None = None
    blocked = False
    prev: Event | None = None

    for stage in config.STAGES:
        e = latest.get(stage)
        entry: dict[str, Any] = {"stage": stage, "status": "not_reached", "time": None, "reason": None, "detail": {}}

        if blocked:
            pass
        elif e is not None:
            entry.update(time=e.event_time.isoformat(), detail=e.detail)
            if e.status == "ok":
                entry["status"] = "done"
            else:
                entry.update(status="failed", reason=e.detail.get("reason"))
                blocked = True
        elif prev is not None or stage == config.STAGES[0]:
            # This is the next expected stage. Is it late enough to call it failed?
            timeout = config.STAGE_TIMEOUT_MINUTES.get(stage)
            waited = (now - prev.event_time).total_seconds() / 60 if prev else 0
            if timeout is not None and waited > timeout:
                entry.update(
                    status="failed",
                    reason=f"No '{stage}' event {waited:.0f} min after '{prev.stage}' (limit {timeout} min)",
                )
            else:
                entry["status"] = "waiting"
            blocked = True

        if entry["status"] == "failed" and first_failure is None:
            first_failure = stage
        prev = e if entry["status"] == "done" else None
        stages.append(entry)

    # Load facts come from the events themselves, not a separate table.
    def fact(stage: str, key: str) -> Any:
        return latest[stage].detail.get(key) if stage in latest else None

    rejected = fact("planner_decision", "action") == "rejected"
    if first_failure:
        state = "failed"
    elif all(s["status"] == "done" for s in stages):
        # The pipeline worked; if the planner rejected the answer, that's its own outcome.
        state = "overridden" if rejected else "complete"
    else:
        state = "in_progress"

    # Soft warnings: stages that passed but were close to a limit.
    warnings = [{"stage": s["stage"], "warning": s["detail"]["warning"]}
                for s in stages if s["status"] == "done" and s["detail"].get("warning")]

    decision = _decision(store, load_id, fact("solve_run", "solve_id"))
    override = None
    if rejected and decision:
        pick = fact("planner_decision", "assigned_truck")
        code = fact("planner_decision", "reason_code")
        override = {
            "recommended_truck": fact("planner_decision", "recommended_truck"),
            "assigned_truck": pick,
            "driver": fact("planner_decision", "driver"),
            "reason_code": code,
            "reason": config.PLANNER_REASON_CODES.get(code, code),
            "note": fact("planner_decision", "note"),
            "diagnosis": diagnose(decision, pick, code),
        }

    # Where the load is now: the failed or waiting stage, else the last one done.
    current = next((s["stage"] for s in stages if s["status"] in ("failed", "waiting")), None)
    if current is None:
        current = next((s["stage"] for s in reversed(stages) if s["status"] == "done"), config.STAGES[0])

    return {
        "load_id": load_id,
        "external_ids": store.external_ids_for(load_id),
        "customer": fact("received", "customer"),
        "source": fact("received", "source"),
        "source_kind": fact("received", "source_kind"),
        "source_ref": fact("received", "ref"),
        "origin": fact("normalized", "origin"),
        "destination": fact("normalized", "destination"),
        "truck": fact("planner_decision", "assigned_truck") or fact("recommended", "truck") or fact("checked", "truck"),
        "planner_action": fact("planner_decision", "action"),
        "state": state,
        "override": override,
        "decision": decision_view(decision, override["assigned_truck"] if override else None) if decision else None,
        "warnings": warnings,
        "current_stage": current,
        "first_failure": first_failure,
        "last_update": events[-1].event_time.isoformat() if events else None,
        "stages": stages,
        "events": [
            {"time": e.event_time.isoformat(), "stage": e.stage, "status": e.status, "detail": e.detail}
            for e in events
        ],
    }
