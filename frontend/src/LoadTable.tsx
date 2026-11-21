import { Fragment } from "react";
import type { LoadTrace } from "./types";
import { ID_LABELS, STATE_LABELS, fmtAgo, fmtTime, stageLabel } from "./format";
import { Stepper } from "./Stepper";
import { Timeline } from "./Timeline";

export type SortKey = "state" | "load_id" | "customer" | "source" | "current_stage" | "last_update";
export interface Sort { key: SortKey; dir: "asc" | "desc" }

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: null, label: "", className: "col-toggle" },
  { key: "load_id", label: "Load" },
  { key: "customer", label: "Customer" },
  { key: "source", label: "Source" },
  { key: null, label: "Truck" },
  { key: null, label: "Pipeline", className: "col-pipeline" },
  { key: "current_stage", label: "Current stage" },
  { key: "state", label: "Status" },
  { key: "last_update", label: "Updated" },
];

interface Props {
  loads: LoadTrace[];
  now: string;
  sort: Sort;
  onSort: (key: SortKey) => void;
  expanded: Set<string>;
  onToggle: (loadId: string) => void;
}

export function LoadTable({ loads, now, sort, onSort, expanded, onToggle }: Props) {
  return (
    <div className="table-wrap">
      <table className="loads">
        <thead>
          <tr>
            {COLUMNS.map((c) => (
              <th key={c.label || "toggle"} className={c.className} aria-sort={c.key && sort.key === c.key ? (sort.dir === "asc" ? "ascending" : "descending") : undefined}>
                {c.key ? (
                  <button className="sort" onClick={() => onSort(c.key!)}>
                    {c.label}
                    <span className={`sort-icon ${sort.key === c.key ? sort.dir : ""}`} aria-hidden>
                      {sort.key === c.key ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}
                    </span>
                  </button>
                ) : (
                  c.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loads.map((load) => {
            const isOpen = expanded.has(load.load_id);
            return (
              <Fragment key={load.load_id}>
                <tr className={`row ${load.state} ${isOpen ? "open" : ""}`} onClick={() => onToggle(load.load_id)}>
                  <td className="col-toggle">
                    <button className="chevron" aria-expanded={isOpen} aria-label={`${isOpen ? "Collapse" : "Expand"} ${load.load_id}`}
                      onClick={(e) => { e.stopPropagation(); onToggle(load.load_id); }}>
                      <svg viewBox="0 0 16 16" width="14" height="14"><path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
                    </button>
                  </td>
                  <td>
                    <div className="load-id">{load.load_id}</div>
                    <div className="muted small">{load.origin} → {load.destination}</div>
                  </td>
                  <td>{load.customer}</td>
                  <td>
                    <div>{load.source}</div>
                    <div className="muted small">{load.source_ref}</div>
                  </td>
                  <td className="strong-ish">{load.truck?.replace("ELD-", "") ?? "—"}</td>
                  <td className="col-pipeline"><Stepper stages={load.stages} compact /></td>
                  <td className="nowrap">
                    {load.state === "in_progress" && <span className="live-dot" aria-hidden />}
                    {stageLabel(load.current_stage)}
                  </td>
                  <td><span className={`pill ${load.state}`}>{STATE_LABELS[load.state]}</span></td>
                  <td className="muted nowrap" title={fmtTime(load.last_update)}>{fmtAgo(load.last_update, now)}</td>
                </tr>
                {isOpen && (
                  <tr className="detail-row">
                    <td colSpan={COLUMNS.length}><LoadDetail load={load} /></td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function LoadDetail({ load }: { load: LoadTrace }) {
  const failure = load.stages.find((s) => s.stage === load.first_failure);
  return (
    <div className="detail">
      {failure && (
        <div className="callout fail">
          <strong>First failing stage: {stageLabel(failure.stage)}</strong>
          <span>{failure.reason}</span>
        </div>
      )}

      <Stepper stages={load.stages} />

      <div className="detail-grid">
        <dl className="ids">
          <div><dt>Internal load ID</dt><dd className="mono">{load.load_id}</dd></div>
          {Object.entries(load.external_ids).map(([sys, id]) => (
            <div key={sys}><dt>{ID_LABELS[sys] ?? sys}</dt><dd className="mono">{id}</dd></div>
          ))}
        </dl>

        <Timeline events={load.events} />
      </div>
    </div>
  );
}
