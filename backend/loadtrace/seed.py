"""Made-up loads, pushed through a tiny simulated pipeline.

Each load arrives from exactly one source: a carrier's TMS (API/webhook) or a shipper's
EDI 204 tender feed. It carries only that source's IDs. The ELD unit is the truck's ID and
is linked when a truck is checked/assigned, so one truck can show up on many loads.

The pipeline runs the real freshness check against config, so changing
ELD_FRESHNESS_MAX_MINUTES changes which loads fail. The two planted failures:

  LD-1004  stale ELD location   -> 'checked' writes a fail event (input problem)
  LD-1005  ack but no confirm   -> 'confirmed' never arrives; the timeout rule catches it (output problem)
"""

import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from . import config
from .store import Event, Store


@dataclass(frozen=True)
class Source:
    name: str       # what the UI shows and filters on
    kind: str       # "tms" | "edi"
    customer: str   # the carrier using our product


SOURCES: dict[str, Source] = {
    "mcleod": Source("McLeod TMS", "tms", "Ridgeline Freight"),
    "mgate": Source("MercuryGate TMS", "tms", "Bluewater Logistics"),
    "harbor": Source("EDI 204 · Harbor Foods", "edi", "Ridgeline Freight"),
    "northline": Source("EDI 204 · Northline Paper", "edi", "Bluewater Logistics"),
}


@dataclass
class LoadSpec:
    load_id: str
    source: str                     # key into SOURCES
    ref: str                        # the source's own ID: TMS load number or EDI shipment ID
    truck: str                      # ELD unit of the candidate/assigned truck
    received_ago_min: int           # minutes before NOW that the load arrived
    eld_ping_age_min: int           # how old the truck's last ELD ping was when the load arrived
    origin: str
    destination: str
    planner: str = "accepted"       # "accepted" | "changed"
    writeback: str = "confirms"     # "confirms" | "ack_only"
    stop_after: str | None = None   # simulate a load still moving through the pipeline


LOADS: list[LoadSpec] = [
    LoadSpec("LD-1001", "mcleod", "MCL-88412", "ELD-T204", 300, 4, "Dallas, TX", "Memphis, TN"),
    LoadSpec("LD-1002", "mgate", "MG-551207", "ELD-T117", 270, 9, "Atlanta, GA", "Charlotte, NC"),
    LoadSpec("LD-1003", "harbor", "HF-20931", "ELD-T331", 240, 2, "Columbus, OH", "Chicago, IL",
             planner="changed"),
    # Fail 1: the truck's last ELD ping is hours old, so its location can't be trusted.
    LoadSpec("LD-1004", "mcleod", "MCL-88440", "ELD-T089", 120, 372, "Phoenix, AZ", "Denver, CO"),
    # Fail 2: the TMS acknowledged our write, but re-reading it never shows the assignment.
    LoadSpec("LD-1005", "mgate", "MG-551233", "ELD-T262", 90, 6, "Nashville, TN", "Louisville, KY",
             writeback="ack_only"),
    # Still in flight: solve is running.
    LoadSpec("LD-1006", "mcleod", "MCL-88452", "ELD-T145", 4, 3, "Houston, TX", "San Antonio, TX",
             stop_after="checked"),
    LoadSpec("LD-1007", "northline", "NP-7781-02", "ELD-T058", 210, 11, "Green Bay, WI", "Minneapolis, MN"),
    # Waiting on the planner.
    LoadSpec("LD-1008", "mgate", "MG-551240", "ELD-T190", 9, 5, "Savannah, GA", "Jacksonville, FL",
             stop_after="recommended"),
    # Same truck as LD-1001, later in the day.
    LoadSpec("LD-1009", "harbor", "HF-20958", "ELD-T204", 60, 7, "Memphis, TN", "St. Louis, MO"),
    LoadSpec("LD-1010", "mcleod", "MCL-88461", "ELD-T372", 150, 12, "Oklahoma City, OK", "Wichita, KS",
             planner="changed"),
    # Acknowledged a few minutes ago: still inside the confirm window, so waiting, not failed.
    LoadSpec("LD-1011", "northline", "NP-7781-09", "ELD-T221", 15, 8, "Appleton, WI", "Milwaukee, WI",
             writeback="ack_only"),
    LoadSpec("LD-1012", "mgate", "MG-551251", "ELD-T305", 45, 3, "Birmingham, AL", "Mobile, AL"),
]

DRIVERS = {"T204": "D. Alvarez", "T117": "K. Osei", "T331": "M. Brennan", "T089": "R. Patel",
           "T262": "J. Kowalski", "T145": "S. Nguyen", "T058": "A. Lindqvist", "T190": "T. Okafor",
           "T372": "B. Hale", "T221": "P. Romero", "T305": "C. Dubois"}

# How write-back looks depends on where the load came from.
WRITEBACK = {
    "tms": {
        "sent_back": lambda ref: {"method": f"TMS API: assign driver on {ref}"},
        "acknowledged": lambda ref: {"http_status": 202},
        "confirmed": lambda ref: {"method": f"re-read {ref} from TMS", "assignment_matches": True},
    },
    "edi": {
        "sent_back": lambda ref: {"document": "EDI 990 (tender accepted)", "shipment_id": ref},
        "acknowledged": lambda ref: {"document": "EDI 997 functional ack"},
        "confirmed": lambda ref: {"document": f"EDI 204 update for {ref} shows tender accepted"},
    },
}


def _simulate(store: Store, spec: LoadSpec, now: datetime) -> None:
    src = SOURCES[spec.source]
    t = now - timedelta(minutes=spec.received_ago_min)

    def emit(stage: str, minutes_later: float, status: str = "ok", **detail: Any) -> None:
        nonlocal t
        t = t + timedelta(minutes=minutes_later)
        store.append(Event(spec.load_id, t, stage, status, detail))

    def stop(stage: str) -> bool:
        return spec.stop_after == stage

    unit = spec.truck.removeprefix("ELD-")
    driver = DRIVERS.get(unit, "Unassigned")

    received = {"source": src.name, "source_kind": src.kind, "customer": src.customer, "ref": spec.ref}
    if src.kind == "edi":
        control = f"{zlib.crc32(spec.ref.encode()) % 10**9:09d}"  # stable made-up ISA control number
        received |= {"edi_control_number": control, "raw_payload": f"s3://raw-edi/{control}.x12"}
        store.link(spec.load_id, "edi_shipment_id", spec.ref)
        store.link(spec.load_id, "edi_control_number", control)
    else:
        received |= {"raw_payload": f"s3://raw-tms/{spec.ref}.json"}
        store.link(spec.load_id, "tms_load_number", spec.ref)
    emit("received", 0, **received)
    if stop("received"): return

    emit("normalized", 0.5, origin=spec.origin, destination=spec.destination, canonical_version="load-v1")
    if stop("normalized"): return

    # Data check on the solve inputs: is the candidate truck's location fresh enough to trust?
    store.link(spec.load_id, "eld_unit", spec.truck)
    eld_age = spec.eld_ping_age_min + 1  # check runs ~1 min after receipt
    limit = config.ELD_FRESHNESS_MAX_MINUTES
    if eld_age > limit:
        emit("checked", 0.5, status="fail", check="eld_freshness", truck=spec.truck,
             eld_age_minutes=eld_age, limit_minutes=limit,
             reason=f"Truck {spec.truck}'s last location ping is {eld_age // 60}h{eld_age % 60:02d}m old "
                    f"(limit {limit}m). Load quarantined; not sent to solve.")
        return
    emit("checked", 0.5, check="eld_freshness", truck=spec.truck, eld_age_minutes=eld_age, limit_minutes=limit)
    if stop("checked"): return

    snapshot = f"snap-{spec.load_id.lower()}-{int(t.timestamp())}"
    emit("solve_run", 2, model_version=config.MODEL_VERSION, input_snapshot=snapshot)
    emit("recommended", 0.5, truck=spec.truck, driver=driver, score=0.91, model_version=config.MODEL_VERSION)
    if stop("recommended"): return

    if spec.planner == "changed":
        emit("planner_decision", 8, action="changed", from_driver=driver, to_driver="L. Moreau",
             reason_code="driver_hours_preference")
    else:
        emit("planner_decision", 6, action="accepted", driver=driver)
    if stop("planner_decision"): return

    wb = WRITEBACK[src.kind]
    emit("sent_back", 1, **wb["sent_back"](spec.ref))
    emit("acknowledged", 0.5, **wb["acknowledged"](spec.ref))
    if spec.writeback == "confirms":
        emit("confirmed", 2, **wb["confirmed"](spec.ref))
    # "ack_only": no confirmed event. Nothing says it failed; the timeout rule finds it.


def seed(store: Store, now: datetime | None = None) -> Store:
    now = now or config.NOW
    for spec in LOADS:
        _simulate(store, spec, now)
    return store
