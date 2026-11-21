"""Everything you'd want to change live lives here."""

from datetime import datetime, timezone

# Fixed "now" so the demo looks the same on every run.
NOW = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)

# Pipeline stages, in order. A load's status is derived from its events against this list.
STAGES: list[str] = [
    "received",          # raw payload landed (S3 first in production)
    "normalized",        # mapped to the canonical load model
    "checked",           # data checks: freshness, required fields
    "solve_run",         # optimization engine ran on an input snapshot
    "recommended",       # driver/truck recommendation produced
    "planner_decision",  # planner accepted or rejected it
    "sent_back",         # write to the customer TMS queued/sent
    "acknowledged",      # TMS returned 2xx / ack
    "confirmed",         # we re-read the TMS and the assignment is really there
]

# External IDs that map to our internal load ID (the GSI in DynamoDB).
# A load arrives with the IDs of its one source: a TMS load number, or an EDI 204
# shipment ID plus the control number of the transmission it came in. The ELD unit is
# the truck's ID, linked once a truck is considered or assigned; one truck, many loads.
EXTERNAL_ID_SYSTEMS: list[str] = ["tms_load_number", "edi_shipment_id", "edi_control_number", "eld_unit"]

# Data check: an ELD location older than this at check time fails the load.
ELD_FRESHNESS_MAX_MINUTES = 30

# "Missing event" rules: if the previous stage finished more than N minutes ago and this
# stage has no event, the stage is failed. Worked out on read; production would run this
# as a scheduled job that writes a timeout event and alerts.
STAGE_TIMEOUT_MINUTES: dict[str, int] = {
    "confirmed": 15,
}

# Soft warning: a check that passes but is close to its limit (this fraction of it) is
# flagged, so a later override can be traced back to marginal inputs.
SOFT_WARNING_RATIO = 0.8

# ---- Solver / model engine -------------------------------------------------------------

MODEL_VERSION = "dispatch-model-2.3.1"
OBJECTIVE_CONFIG = "weights-v14"
CONSTRAINT_SET = "constraints-v9"

# How the solver scores a feasible truck: weighted sum of components, each 0..1.
# The recommendation is the top-scoring feasible truck, so changing these changes outcomes.
# Try deadhead 0.50 / network_balance 0.00: the solver then agrees with LD-1010's planner.
OBJECTIVE_WEIGHTS: dict[str, float] = {
    "deadhead": 0.35,         # fewer empty miles to pickup
    "on_time": 0.30,          # predicted on-time pickup and delivery
    "cost": 0.20,             # cost to serve
    "network_balance": 0.15,  # leaves the truck somewhere useful afterwards
}

# Hard constraints, applied in this order. A truck failing one is ruled out.
TRIP_HOURS_NEEDED = 6.0       # hours-of-service the trip needs
MAX_DEADHEAD_MILES = 250
REQUIRED_EQUIPMENT = "53' dry van"

# Hours-of-service data older than this is flagged as stale in the decision record.
HOS_STALE_MINUTES = 60

# ---- Planner overrides -----------------------------------------------------------------

# One-click reasons a planner gives when rejecting a recommendation.
PLANNER_REASON_CODES: dict[str, str] = {
    "driver_actually_available": "Driver is actually available",
    "better_truck": "A better truck was available",
    "truck_not_suggested": "The truck I wanted wasn't suggested",
    "customer_requirement": "Customer requirement",
    "driver_preference": "Driver preference",
    "other": "Other",
}

# Reasons that point at knowledge the solver has no data for.
CONTEXT_REASONS = {"customer_requirement", "driver_preference"}
