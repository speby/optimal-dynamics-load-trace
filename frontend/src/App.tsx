import { useEffect, useMemo, useState } from "react";
import { fetchLoads, type LoadState, type LoadTrace, type LoadsResponse } from "./types";
import { DIAGNOSIS_LABELS, STATE_LABELS, stageLabel } from "./format";
import { LoadTable, type Sort, type SortKey } from "./LoadTable";

const STATE_ORDER: LoadState[] = ["failed", "overridden", "in_progress", "complete"];
const ALL = "";

interface Filters {
  q: string;
  customer: string;
  source: string;
  stage: string;
  diagnosis: string;
  state: LoadState | typeof ALL;
}

const EMPTY: Filters = { q: "", customer: ALL, source: ALL, stage: ALL, diagnosis: ALL, state: ALL };

export function App() {
  const [data, setData] = useState<LoadsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [sort, setSort] = useState<Sort>({ key: "state", dir: "asc" });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchLoads().then(setData).catch((e: Error) => setError(e.message));
  }, []);

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));

  const options = useMemo(() => {
    const loads = data?.loads ?? [];
    const uniq = (xs: (string | null)[]) => [...new Set(xs.filter((x): x is string => !!x))].sort();
    return {
      customers: uniq(loads.map((l) => l.customer)),
      sources: uniq(loads.map((l) => l.source)),
      stages: data?.stages ?? [],
      diagnoses: Object.keys(DIAGNOSIS_LABELS),
    };
  }, [data]);

  // Everything except the status filter, so the status tabs can show counts.
  const matching = useMemo(
    () => (data?.loads ?? []).filter((l) => matches(l, filters)),
    [data, filters.q, filters.customer, filters.source, filters.stage, filters.diagnosis],
  );

  const rows = useMemo(() => {
    const stageIdx = (s: string) => options.stages.indexOf(s);
    const value = (l: LoadTrace, key: SortKey): string | number => {
      switch (key) {
        case "state": return STATE_ORDER.indexOf(l.state);
        case "current_stage": return stageIdx(l.current_stage);
        case "last_update": return l.last_update ?? "";
        default: return l[key] ?? "";
      }
    };
    const dir = sort.dir === "asc" ? 1 : -1;
    return matching
      .filter((l) => !filters.state || l.state === filters.state)
      .sort((a, b) => {
        const va = value(a, sort.key), vb = value(b, sort.key);
        if (va !== vb) return (va < vb ? -1 : 1) * dir;
        return (b.last_update ?? "").localeCompare(a.last_update ?? ""); // tie-break: most recent first
      });
  }, [matching, filters.state, sort, options.stages]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { [ALL]: matching.length };
    for (const l of matching) c[l.state] = (c[l.state] ?? 0) + 1;
    return c;
  }, [matching]);

  const onSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "last_update" ? "desc" : "asc" }));

  const onToggle = (id: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const filtered = filters.q || filters.customer || filters.source || filters.stage || filters.diagnosis || filters.state;

  return (
    <>
    <nav className="topbar">
      <div className="topbar-inner">
        <span className="brand"><span className="brand-mark" aria-hidden />Load trace</span>
        <span className="topbar-note">Demo data · fixed clock</span>
      </div>
    </nav>
    <main>
      <header className="page-head">
        <p className="eyebrow">Trace every load, intake to write-back</p>
        <h1>Where is each load, and what broke?</h1>
        <p className="sub">One internal ID per load. Search any TMS, EDI or truck ID, and see the first stage that failed.</p>
      </header>

      <section className="toolbar" aria-label="Filters">
        <input
          type="search"
          className="search"
          placeholder="Search load ID, TMS load #, EDI shipment ID or control #, truck"
          value={filters.q}
          onChange={(e) => set({ q: e.target.value })}
        />
        <Select label="Customer" value={filters.customer} options={options.customers} onChange={(customer) => set({ customer })} />
        <Select label="Source" value={filters.source} options={options.sources} onChange={(source) => set({ source })} />
        <Select label="Current stage" value={filters.stage} options={options.stages} format={stageLabel} onChange={(stage) => set({ stage })} />
        <Select label="Override diagnosis" value={filters.diagnosis} options={options.diagnoses} format={(d) => DIAGNOSIS_LABELS[d] ?? d} onChange={(diagnosis) => set({ diagnosis })} />
        {filtered && <button className="link" onClick={() => setFilters(EMPTY)}>Clear filters</button>}
      </section>

      <nav className="tabs" aria-label="Status">
        {[ALL, ...STATE_ORDER].map((s) => (
          <button key={s || "all"} className={`tab ${s} ${filters.state === s ? "active" : ""}`} onClick={() => set({ state: s as Filters["state"] })}>
            {s ? STATE_LABELS[s as LoadState] : "All"} <span className="count">{counts[s] ?? 0}</span>
          </button>
        ))}
      </nav>

      {error && (
        <p className="error">
          Couldn't load traces: {error}.{" "}
          {error.startsWith("API") ? "The API returned an error; check the backend logs." : "Is the backend running on :8000?"}
        </p>
      )}

      {data && (
        rows.length ? (
          <LoadTable loads={rows} now={data.now} sort={sort} onSort={onSort} expanded={expanded} onToggle={onToggle} />
        ) : (
          <p className="empty">No loads match these filters.</p>
        )
      )}
    </main>
    </>
  );
}

function matches(l: LoadTrace, f: Filters): boolean {
  if (f.customer && l.customer !== f.customer) return false;
  if (f.source && l.source !== f.source) return false;
  if (f.stage && l.current_stage !== f.stage) return false;
  if (f.diagnosis && l.override?.diagnosis.code !== f.diagnosis) return false;
  const q = f.q.trim().toLowerCase();
  if (q) {
    const ids = [l.load_id, ...Object.values(l.external_ids)].map((x) => x.toLowerCase());
    if (!ids.some((id) => id.includes(q))) return false;
  }
  return true;
}

function Select({ label, value, options, onChange, format = (x) => x }: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  format?: (v: string) => string;
}) {
  return (
    <label className="select">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value={ALL}>All</option>
        {options.map((o) => <option key={o} value={o}>{format(o)}</option>)}
      </select>
    </label>
  );
}
