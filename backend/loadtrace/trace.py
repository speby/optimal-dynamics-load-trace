"""Derive a load's trace from its events. Nothing about current status is stored."""

from datetime import datetime
from typing import Any

from . import config
from .store import Event, Store


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

    if first_failure:
        state = "failed"
    elif all(s["status"] == "done" for s in stages):
        state = "complete"
    else:
        state = "in_progress"

    # Where the load is now: the failed or waiting stage, else the last one done.
    current = next((s["stage"] for s in stages if s["status"] in ("failed", "waiting")), None)
    if current is None:
        current = next((s["stage"] for s in reversed(stages) if s["status"] == "done"), config.STAGES[0])

    # Load facts come from the events themselves, not a separate table.
    def fact(stage: str, key: str) -> Any:
        return latest[stage].detail.get(key) if stage in latest else None

    return {
        "load_id": load_id,
        "external_ids": store.external_ids_for(load_id),
        "customer": fact("received", "customer"),
        "source": fact("received", "source"),
        "source_kind": fact("received", "source_kind"),
        "source_ref": fact("received", "ref"),
        "origin": fact("normalized", "origin"),
        "destination": fact("normalized", "destination"),
        "truck": fact("recommended", "truck") or fact("checked", "truck"),
        "planner_action": fact("planner_decision", "action"),
        "state": state,
        "current_stage": current,
        "first_failure": first_failure,
        "last_update": events[-1].event_time.isoformat() if events else None,
        "stages": stages,
        "events": [
            {"time": e.event_time.isoformat(), "stage": e.stage, "status": e.status, "detail": e.detail}
            for e in events
        ],
    }
