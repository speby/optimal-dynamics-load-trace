"""HTTP API for the load trace view. Run: uv run uvicorn loadtrace.api:app --reload"""

from fastapi import FastAPI, HTTPException

from . import config
from .seed import seed
from .store import Store
from .trace import build_trace

app = FastAPI(title="Load trace")
store = seed(Store())


@app.get("/api/loads")
def list_loads(q: str = "") -> dict:
    """Search by internal load ID or any external ID (TMS number, EDI control number, ELD unit)."""
    return {
        "now": config.NOW.isoformat(),
        "stages": config.STAGES,
        "loads": [build_trace(store, load_id) for load_id in store.find(q)],
    }


@app.get("/api/loads/{load_id}")
def get_load(load_id: str) -> dict:
    if not store.events_for(load_id):
        raise HTTPException(status_code=404, detail=f"Unknown load {load_id}")
    return build_trace(store, load_id)
