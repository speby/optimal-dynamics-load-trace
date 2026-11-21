# AI use log (running notes for the one-page write-up)

Tool: Claude Code (Claude Opus 5.5), driven from the Claude desktop app.

## How AI was used

1. **Design discussion before code.** Fed it the handoff notes (Scenario 2 design, agreed scope)
   and asked it to propose a design first. It suggested:
   - deriving status from events instead of storing it
   - treating the two failures differently: one is a fail event, the other is a missing event
     caught by a timeout rule

   Human decisions at this point:
   - **TypeScript front end** instead of the plain HTML it first suggested, to match their
     single-page app.
   - **Timeout worked out on read** (its recommendation), with production noted as a scheduled job.
2. **Scaffolding.** It wrote the backend (store, trace logic, seed simulator, API), the tests and
   the React front end in one pass, then ran the tests and checked the page in a browser.
3. **Seed data that runs real checks.** It made the seed data go through the actual freshness check
   rather than hard-coding a fail event, so changing the threshold changes the result. That makes a
   live change in the interview meaningful.

## Where AI got it wrong (and what fixed it)

| # | What went wrong | How it was caught | Fix | Who fixed it |
|---|-----------------|-------------------|-----|--------------|
| 1 | `pyproject.toml` had no build system, so the package was never installed and pytest couldn't import `loadtrace`. | First test run: `ModuleNotFoundError` | Added `pythonpath = ["."]` to pytest config | AI, after seeing the error |
| 2 | Failure reason read "ELD ELD-T089 last ping…": the unit ID already starts with `ELD-`. | Reading the printed output before building the UI | Reworded to "ELD-T089 last location ping…" | AI, on review |
| 3 | **Unrealistic ID model.** Every load had a TMS load #, an EDI control # *and* an ELD unit, as if each load came in from three systems at once. It also treated the ELD unit (the *truck's* ID) as a load ID. The ID table's primary key let each external ID map to only one load, so a truck could never appear on a second load. | **Sean**, looking at the first UI: "Some loads would be sourced from a single TMS, or a single EDI feed, right?" | Each load now comes from exactly one source: a TMS load # **or** an EDI 204 shipment ID + control #. The ELD unit is linked when a truck is checked/assigned. The ID table now allows one ID → many loads (like a DynamoDB GSI). New tests: one source per load; a truck search returns every load it hauled. | Sean caught it; AI implemented |
| 4 | Made-up EDI control numbers came from a formula that gave two loads from the same shipper the same number. | AI, re-reading its own seed code before running it | Switched to a CRC32 of the shipment ID | AI, on review |
| 5 | **Thread-safety bug.** The AI opened one SQLite connection with `check_same_thread=False` and shared it across FastAPI's worker threads with no lock. Two requests at the same moment (React dev mode fetches twice) got each other's rows and crashed with 500s. It only happened sometimes, so all the single-request tests passed. | **Sean** saw "API 500" in the page | Server logs showed two different crashes from the same line, which pointed to interleaving. Wrote a test with 200 parallel requests that failed first, then routed every query through a lock. The page's error text also blamed a stopped backend for any error, so it now says when the API returned an error instead. | Sean caught it; AI diagnosed and fixed |

## Known gaps left on purpose

- Only `confirmed` has a timeout. A stuck solve would show as "waiting" forever. (Good
  candidate for a live change: one line in `STAGE_TIMEOUT_MINUTES`.)
- The UI loads every trace once and filters in the browser. That's fine for a demo, but at real
  volume the filters and search would move to the API (`/api/loads?q=` already searches by any ID).
- There's a FastAPI/httpx test-client deprecation warning; it's harmless and was left alone.
- npm skipped esbuild's install script (new npm allowlist); Vite works without it.

## Manual fixes and direction (Sean)

1. **Realistic sources and IDs** (mistake #3 above). The AI generated plausible-looking data that
   didn't match how loads actually arrive. It took someone who knows trucking to see it.
2. **UI direction after the first pass.** The AI's first view was a dark page of separate cards,
   with stages as a row of boxes. Sean asked for:
   - a light design
   - a table/grid, so loads can be compared row by row
   - stages shown as a connected sequence (stepper)
   - a visible expand control
   - filters (customer, source, current stage, status) and sortable columns

   The AI also made failures sort to the top by default, with status tabs showing counts.
   (Planner overrides now show as "Changed" under the Planner step in the expanded view.)
3. **Brand look and "in progress" motion.** Sean pasted a screenshot of the Optimal Dynamics home
   page and asked for the same look and feel, plus a subtle pulse on the stage a load is waiting at.
   - The AI sampled pixel colors from the screenshot instead of guessing, which gave brand green
     `#37A267`. It identified the font as Poppins.
   - It applied black bold headings, grey body text, pill inputs and tabs, and 20px rounded cards.
     It didn't copy the logo.
   - In-progress loads now use brand green with a soft glow that pulses around the current stage,
     replacing the earlier amber. The motion stops for users who've turned on reduced motion.
4. **Readable event details, raw JSON on request.** Sean asked for formatted event details, with
   the raw JSON hidden by default.
   - The AI split the timeline into its own component (`Timeline.tsx`).
   - Known keys get readable labels, falling back to sentence case for others. Values are
     formatted: minutes show as "373 min", booleans as Yes/No, IDs and paths in monospace.
   - A failure reason gets its own highlighted line.
   - Raw, pretty-printed JSON opens per event (`{ }` button) or for the whole timeline at once
     ("Show raw JSON").
