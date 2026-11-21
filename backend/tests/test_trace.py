from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from loadtrace import config
from loadtrace.api import app
from loadtrace.seed import seed
from loadtrace.store import Store
from loadtrace.trace import build_trace


@pytest.fixture
def store() -> Store:
    return seed(Store())


def test_stale_eld_fails_at_checked(store):
    t = build_trace(store, "LD-1004")
    assert t["state"] == "failed"
    assert t["first_failure"] == "checked"
    checked = next(s for s in t["stages"] if s["stage"] == "checked")
    assert "ELD-T089" in checked["reason"]
    assert t["current_stage"] == "checked"
    # Quarantined: nothing downstream ran.
    assert all(s["status"] == "not_reached" for s in t["stages"][3:])


def test_ack_without_confirm_fails_at_confirmed(store):
    t = build_trace(store, "LD-1005")
    assert t["state"] == "failed"
    assert t["first_failure"] == "confirmed"
    # Nothing in the timeline says it failed; the failure comes from the missing event.
    assert all(e["status"] == "ok" for e in t["events"])


def test_ack_without_confirm_is_waiting_inside_the_timeout(store):
    ack = next(e for e in store.events_for("LD-1005") if e.stage == "acknowledged")
    just_after = ack.event_time + timedelta(minutes=config.STAGE_TIMEOUT_MINUTES["confirmed"] - 1)
    t = build_trace(store, "LD-1005", now=just_after)
    assert t["state"] == "in_progress"
    assert t["stages"][-1]["status"] == "waiting"


def test_seeded_states(store):
    states = {l: build_trace(store, l)["state"] for l in store.find()}
    assert sorted(l for l, s in states.items() if s == "failed") == ["LD-1004", "LD-1005"]
    assert sorted(l for l, s in states.items() if s == "in_progress") == ["LD-1006", "LD-1008", "LD-1011"]


def test_recent_ack_is_waiting_not_failed(store):
    t = build_trace(store, "LD-1011")
    assert t["state"] == "in_progress"
    assert t["current_stage"] == "confirmed"


def test_each_load_has_ids_from_one_source_only(store):
    for load_id in store.find():
        ids = set(store.external_ids_for(load_id)) - {"eld_unit"}
        assert ids in ({"tms_load_number"}, {"edi_shipment_id", "edi_control_number"}), load_id


@pytest.mark.parametrize("query", ["LD-1004", "MCL-88440", "mcl-88440"])
def test_search_by_load_or_source_id(query):
    body = TestClient(app).get("/api/loads", params={"q": query}).json()
    assert [l["load_id"] for l in body["loads"]] == ["LD-1004"]


def test_search_by_truck_finds_every_load_it_hauled():
    body = TestClient(app).get("/api/loads", params={"q": "ELD-T204"}).json()
    assert [l["load_id"] for l in body["loads"]] == ["LD-1001", "LD-1009"]


def test_search_by_edi_shipment_id():
    body = TestClient(app).get("/api/loads", params={"q": "HF-20931"}).json()
    assert [l["load_id"] for l in body["loads"]] == ["LD-1003"]


def test_concurrent_requests_share_the_store_safely():
    # Regression: two parallel /api/loads calls (React dev mode fetches twice) used to
    # interleave on one SQLite connection and 500 with garbled rows.
    from concurrent.futures import ThreadPoolExecutor

    client = TestClient(app)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: client.get("/api/loads").status_code, range(200)))
    assert set(codes) == {200}
