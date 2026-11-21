"""Made-up loads, pushed through a tiny simulated pipeline.

Each load arrives from exactly one source: a carrier's TMS (API/webhook) or a shipper's
EDI 204 tender feed. It carries only that source's IDs. The ELD unit is the truck's ID and
is linked when a truck is checked/assigned, so one truck can show up on many loads.

The pipeline runs the real freshness check and the real solver against config, so changing
thresholds or objective weights changes the outcome.

Planted pipeline failures:
  LD-1004  stale ELD location   -> 'checked' writes a fail event (input problem)
  LD-1005  ack but no confirm   -> 'confirmed' never arrives; the timeout rule catches it (output problem)

Planted planner overrides (the pipeline worked, the answer didn't). The diagnosis is worked
out from the solver's decision record, not from these specs:
  LD-1014  planner's truck was never a candidate       -> data gap (fleet feed)
  LD-1013  planner's truck was ruled out by a rule     -> stale hours-of-service input
  LD-1010  planner's truck was feasible, scored lower  -> objective weights
  LD-1003  feasible, scored lower, customer reason     -> context the solver doesn't have
"""

import random
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from . import config
from .solver import Candidate, solve
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


@dataclass(frozen=True)
class Override:
    """A planner rejecting the recommendation and assigning their own truck."""
    pick: str                        # the truck the planner chose
    reason_code: str                 # key into config.PLANNER_REASON_CODES
    note: str
    # How the planner's truck appears in the solver's input snapshot:
    #   "absent"    not in the fleet snapshot at all
    #   "ruled_out" present, but fails hours-of-service on stale data
    #   "feasible"  present and feasible, with these objective components
    shape: str
    components: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


@dataclass
class LoadSpec:
    load_id: str
    source: str                     # key into SOURCES
    ref: str                        # the source's own ID: TMS load number or EDI shipment ID
    truck: str                      # ELD unit of the truck the solver should prefer
    received_ago_min: int           # minutes before NOW that the load arrived
    eld_ping_age_min: int           # how old that truck's last ELD ping was when the load arrived
    origin: str
    destination: str
    override: Override | None = None
    writeback: str = "confirms"     # "confirms" | "ack_only"
    stop_after: str | None = None   # simulate a load still moving through the pipeline


LOADS: list[LoadSpec] = [
    LoadSpec("LD-1001", "mcleod", "MCL-88412", "ELD-T204", 300, 4, "Dallas, TX", "Memphis, TN"),
    LoadSpec("LD-1002", "mgate", "MG-551207", "ELD-T117", 270, 9, "Atlanta, GA", "Charlotte, NC"),
    # Override: planner's truck was feasible but ranked lower; the reason is a customer rule
    # the solver has no data for.
    LoadSpec("LD-1003", "harbor", "HF-20931", "ELD-T331", 240, 2, "Columbus, OH", "Chicago, IL",
             override=Override("ELD-T274", "customer_requirement",
                               "Harbor Foods only accepts drivers with their dock-safety certification.",
                               "feasible", (0.70, 0.85, 0.80, 0.60))),
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
    # Override: planner's truck had much less deadhead but lost on network balance.
    LoadSpec("LD-1010", "mcleod", "MCL-88461", "ELD-T372", 150, 12, "Oklahoma City, OK", "Wichita, KS",
             override=Override("ELD-T355", "better_truck",
                               "T355 is 4 miles from the shipper. Why send T372 from 40 miles out?",
                               "feasible", (0.98, 0.90, 0.85, 0.20))),
    # Acknowledged a few minutes ago: still inside the confirm window, so waiting, not failed.
    LoadSpec("LD-1011", "northline", "NP-7781-09", "ELD-T221", 15, 8, "Appleton, WI", "Milwaukee, WI",
             writeback="ack_only"),
    LoadSpec("LD-1012", "mgate", "MG-551251", "ELD-T305", 45, 3, "Birmingham, AL", "Mobile, AL"),
    # Override: the solver ruled the planner's truck out on hours of service, using a reading
    # that was 4h22m old. The driver had already reset. The recommended truck's own location
    # ping is also close to its limit (soft warning).
    LoadSpec("LD-1013", "mcleod", "MCL-88470", "ELD-T263", 200, 24, "Tulsa, OK", "Little Rock, AR",
             override=Override("ELD-T418", "driver_actually_available",
                               "R. Vance finished a 10-hour reset at 6am. He has a full clock.",
                               "ruled_out", (0.95, 0.90, 0.85, 0.80))),
    # Override: the planner's truck wasn't in the solver's fleet snapshot at all.
    LoadSpec("LD-1014", "mgate", "MG-551262", "ELD-T182", 180, 5, "Charlotte, NC", "Raleigh, NC",
             override=Override("ELD-T509", "truck_not_suggested",
                               "T509 joined the fleet Monday and is sitting in Charlotte.",
                               "absent")),
]

DRIVERS = {"T204": "D. Alvarez", "T117": "K. Osei", "T331": "M. Brennan", "T089": "R. Patel",
           "T262": "J. Kowalski", "T145": "S. Nguyen", "T058": "A. Lindqvist", "T190": "T. Okafor",
           "T372": "B. Hale", "T221": "P. Romero", "T305": "C. Dubois", "T263": "E. Sato",
           "T182": "G. Farah", "T274": "N. Whitfield", "T355": "H. Ruiz", "T418": "R. Vance",
           "T509": "V. Castillo"}

# The truck the solver should prefer always gets these components, so it beats random filler.
PREFERRED = {"deadhead": 0.80, "on_time": 0.90, "cost": 0.85, "network_balance": 0.90}
COMPONENT_KEYS = ["deadhead", "on_time", "cost", "network_balance"]

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


def driver_for(truck: str | None) -> str:
    return DRIVERS.get((truck or "").removeprefix("ELD-"), "Unassigned")


def _candidates(spec: LoadSpec) -> list[Candidate]:
    """The fleet snapshot the solver sees for this load. Deterministic per load."""
    rng = random.Random(spec.load_id)
    reserved = {spec.truck} | ({spec.override.pick} if spec.override else set())
    pool = [f"ELD-T{n:03d}" for n in rng.sample(range(100, 700), 60)]
    filler = [t for t in pool if t not in reserved][: rng.randint(30, 42)]

    out = [
        Candidate(
            truck=t,
            hos_hours_left=round(rng.uniform(0, 11), 1),
            hos_age_min=rng.randint(2, 40),
            eld_age_min=rng.randint(1, 20),
            equipment=config.REQUIRED_EQUIPMENT if rng.random() > 0.2 else "48' flatbed",
            deadhead_mi=rng.randint(5, 400),
            components={k: round(rng.uniform(0.25, 0.75), 2) for k in COMPONENT_KEYS},
        )
        for t in filler
    ]
    out.append(Candidate(spec.truck, 9.5, 6, spec.eld_ping_age_min + 1, config.REQUIRED_EQUIPMENT, 18, dict(PREFERRED)))

    o = spec.override
    if o and o.shape != "absent":
        comps = dict(zip(COMPONENT_KEYS, o.components))
        if o.shape == "ruled_out":
            out.append(Candidate(o.pick, 1.5, 262, 4, config.REQUIRED_EQUIPMENT, 9, comps))
        else:
            out.append(Candidate(o.pick, 8.0, 12, 5, config.REQUIRED_EQUIPMENT, 12, comps))
    return out


def _simulate(store: Store, spec: LoadSpec, now: datetime) -> None:
    src = SOURCES[spec.source]
    t = now - timedelta(minutes=spec.received_ago_min)

    def emit(stage: str, minutes_later: float, status: str = "ok", **detail: Any) -> None:
        nonlocal t
        t = t + timedelta(minutes=minutes_later)
        store.append(Event(spec.load_id, t, stage, status, detail))

    def stop(stage: str) -> bool:
        return spec.stop_after == stage

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
    checked: dict[str, Any] = {"check": "eld_freshness", "truck": spec.truck, "eld_age_minutes": eld_age,
                               "limit_minutes": limit}
    if eld_age > limit * config.SOFT_WARNING_RATIO:
        checked["warning"] = f"Passed, but close to the limit: {eld_age}m old against {limit}m."
    emit("checked", 0.5, **checked)
    if stop("checked"): return

    # Solve: the full decision record goes to the record store (S3 in production);
    # the timeline event carries a summary and a pointer.
    snapshot = f"snap-{spec.load_id.lower()}-{int(t.timestamp())}"
    solve_id = f"solve-{int(t.timestamp())}-{spec.load_id.lower()}"
    record = solve(solve_id, spec.load_id, snapshot, _candidates(spec))
    store.put_decision_record(solve_id, spec.load_id, record)
    feasible = next(f["count"] for f in record["funnel"] if f["step"] == "feasible")
    emit("solve_run", 2, model_version=config.MODEL_VERSION, objective_config=config.OBJECTIVE_CONFIG,
         input_snapshot=snapshot, solve_id=solve_id, candidates_considered=len(record["candidates"]),
         feasible=feasible, decision_record=f"s3://decision-records/{solve_id}.json",
         input_warnings=len(record["input_warnings"]))

    recommended = record["recommended"]
    store.link(spec.load_id, "eld_unit", recommended)
    emit("recommended", 0.5, truck=recommended, driver=driver_for(recommended),
         score=record["recommended_score"], margin=record["margin"], model_version=config.MODEL_VERSION)
    if stop("recommended"): return

    o = spec.override
    if o and o.pick != recommended:
        store.link(spec.load_id, "eld_unit", o.pick)
        emit("planner_decision", 8, action="rejected", recommended_truck=recommended, assigned_truck=o.pick,
             driver=driver_for(o.pick), reason_code=o.reason_code, note=o.note)
    else:
        # Also covers an override whose truck the solver now recommends itself (e.g. after a
        # weights change): the planner would simply accept.
        emit("planner_decision", 6, action="accepted", assigned_truck=recommended, driver=driver_for(recommended))
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
