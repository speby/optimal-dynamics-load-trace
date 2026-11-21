# Load trace prototype

A small working version of the Scenario 2 idea: every load gets one internal ID, every stage
appends an event to that load's timeline, and one view shows where each load is and which
stage failed first.

## Build and run

The app has two parts, each run in its own terminal:

- **API:** Python + FastAPI on port 8000
- **Web page:** TypeScript + React, served by Vite on port 5173. It forwards `/api` calls to the API.

### 1. Install the prerequisites (once)

| Tool | Version | Install |
|------|---------|---------|
| [uv](https://docs.astral.sh/uv/) | any recent | `curl -LsSf https://astral.sh/uv/install.sh \| sh` (installs Python 3.12 for you on first run) |
| [Node.js](https://nodejs.org/) | 18 or newer | from nodejs.org, or `brew install node` |
| Git | any | to clone the repo |

### 2. Get the code

```bash
git clone https://github.com/speby/optimal-dynamics-load-trace.git
cd optimal-dynamics-load-trace
```

### 3. Start the API (terminal 1)

```bash
cd backend
uv sync
uv run uvicorn loadtrace.api:app --reload --port 8000
```

Wait for `Application startup complete`. To check it's up, open
http://localhost:8000/api/loads; you should see JSON for 12 loads.

### 4. Start the web page (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

### 5. Open it

Go to **http://localhost:5173**. You should see 12 loads: 2 failed, 3 in progress, 7 complete.
Click any row to expand it.

To stop, press `Ctrl+C` in each terminal. The data is made up and rebuilt each time the API
starts, so there's nothing to reset.

### Run the tests

```bash
cd backend
uv run pytest -q
```

### Build for production (optional)

```bash
cd frontend
npm run build
```

This typechecks the code and writes a static site to `frontend/dist/`. It still needs the API
running behind `/api`.

### If something goes wrong

| What you see | What to do |
|--------------|------------|
| "Couldn't load traces… Is the backend running on :8000?" | The API isn't running. Start it (step 3). |
| "Couldn't load traces: API 500…" | The API is running but hit an error. Check the traceback in terminal 1. |
| `Address already in use` | Something else is on port 8000 or 5173. Stop it, or find it with `lsof -i :8000`. |
| `uv: command not found` | Install uv (step 1), then open a new terminal. |

## How it maps to the Scenario 2 design

| Design (production)                         | Prototype                                          |
|---------------------------------------------|----------------------------------------------------|
| DynamoDB timeline, PK load ID, SK event time | SQLite `events` table, append-only (`store.py`)    |
| GSI on external IDs                          | `external_ids` table: TMS number, EDI control number, ELD unit |
| Load trace view                              | React table, search by any ID, filter, sort (`frontend/src/App.tsx`, `LoadTable.tsx`, `Stepper.tsx`) |
| Current status                               | Never stored; derived from events on every read (`trace.py`) |

## The two planted failures

| Load    | Failure                                | Kind    | How it's caught |
|---------|----------------------------------------|---------|-----------------|
| LD-1004 | ELD location 6h old                    | Input   | Freshness check writes a `checked` **fail event**; the load is quarantined and never reaches the solver. |
| LD-1005 | TMS acknowledged, never confirmed      | Output  | **No event says it failed.** A timeout rule sees `acknowledged` with no `confirmed` after 15 min. |

The second kind is the interesting one: some failures only show up as a missing event. Here the
rule runs when the page is read; in production it would be a scheduled job that writes a timeout
event and alerts.

## Seed data

12 loads for two carrier customers, from four sources: two TMSs (McLeod, MercuryGate) and two
shippers' EDI 204 tender feeds. Each load carries only its source's IDs:
- a TMS load number, **or**
- an EDI shipment ID plus control number

The ELD unit is the truck's ID. It's linked when a truck is checked/assigned, so searching a
truck (`ELD-T204`) returns every load it hauled.

Besides the two failures, the seed includes:
- planner overrides (LD-1003, LD-1010)
- loads still in flight: solve running (LD-1006) and waiting on the planner (LD-1008)
- **LD-1011**, acknowledged 4 minutes ago and not yet confirmed. It's inside the 15-minute window,
  so it shows as *waiting*, next to LD-1005, which is past it and *failed*.

## The view

- A table with filters for customer, source and current stage, plus status tabs with counts.
- Columns can be sorted. Failures sort to the top by default.
- Each row shows the pipeline as a compact stepper. Expanding a row shows:
  - the full labeled stepper
  - every external ID
  - the event timeline, with details as readable fields; raw JSON opens per event or for all events

## Where to make common changes

| Change                                  | Where |
|-----------------------------------------|-------|
| Freshness threshold, confirm timeout    | `backend/loadtrace/config.py` |
| Add a timeout to another stage          | `STAGE_TIMEOUT_MINUTES` in `config.py` |
| Add or reorder a stage                  | `STAGES` in `config.py`, emit it in `seed.py`, label in `frontend/src/format.ts` |
| Add a column or filter                  | `frontend/src/LoadTable.tsx` (`COLUMNS`), `frontend/src/App.tsx` (`Filters`) |
| Add a new data check                    | `_simulate` in `seed.py`, next to the freshness check |
| Add a new load or failure               | `LOADS` in `seed.py` |

The demo clock is fixed (`config.NOW`) so it looks the same on every run.
