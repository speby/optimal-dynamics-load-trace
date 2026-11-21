"""Planner overrides, diagnosed from the solver's decision record."""

import pytest

from loadtrace import config
from loadtrace.seed import seed
from loadtrace.store import Store
from loadtrace.trace import build_trace


@pytest.fixture
def store() -> Store:
    return seed(Store())


@pytest.mark.parametrize("load_id, code", [
    ("LD-1014", "not_considered"),
    ("LD-1013", "ruled_out"),
    ("LD-1010", "scored_lower"),
    ("LD-1003", "planner_context"),
])
def test_each_override_gets_its_diagnosis(store, load_id, code):
    t = build_trace(store, load_id)
    assert t["state"] == "overridden"
    assert t["override"]["diagnosis"]["code"] == code
    # The truck that went back to the TMS is the planner's, not the solver's.
    assert t["truck"] == t["override"]["assigned_truck"] != t["override"]["recommended_truck"]


def test_ruled_out_points_at_stale_input_not_the_rule(store):
    d = build_trace(store, "LD-1013")["override"]["diagnosis"]
    assert "probably stale" in d["explanation"]
    assert d["where_to_fix"] == "Data: hours-of-service feed"


def test_planners_truck_is_shown_even_when_ruled_out(store):
    decision = build_trace(store, "LD-1013")["decision"]
    pick = next(c for c in decision["candidates"] if c["truck"] == "ELD-T418")
    assert pick["feasible"] is False and pick["eliminated_by"] == "hours_of_service"


def test_accepted_loads_have_a_decision_but_no_override(store):
    t = build_trace(store, "LD-1001")
    assert t["override"] is None
    assert t["decision"]["recommended"] == "ELD-T204"
    funnel = {f["step"]: f for f in t["decision"]["funnel"]}
    removed = sum(f.get("removed", 0) for f in t["decision"]["funnel"])
    assert funnel["considered"]["count"] - removed == funnel["feasible"]["count"]


def test_failed_before_solve_has_no_decision(store):
    assert build_trace(store, "LD-1004")["decision"] is None


def test_marginal_input_is_a_soft_warning(store):
    t = build_trace(store, "LD-1013")
    assert [w["stage"] for w in t["warnings"]] == ["checked"]
    assert t["stages"][2]["status"] == "done"


def test_reweighting_makes_the_solver_agree_with_the_planner(monkeypatch):
    # The live change suggested in config.py: weigh deadhead more, network balance not at all.
    monkeypatch.setattr(config, "OBJECTIVE_WEIGHTS",
                        {"deadhead": 0.50, "on_time": 0.30, "cost": 0.20, "network_balance": 0.00})
    t = build_trace(seed(Store()), "LD-1010")
    assert t["decision"]["recommended"] == "ELD-T355"
    assert t["planner_action"] == "accepted"
    assert t["state"] == "complete"
