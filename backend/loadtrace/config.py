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
    "planner_decision",  # planner accepted or changed it
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

MODEL_VERSION = "dispatch-model-2.3.1"
