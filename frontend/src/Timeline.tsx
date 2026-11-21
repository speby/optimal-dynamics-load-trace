import { useState, type ReactNode } from "react";
import type { TimelineEvent } from "./types";
import { fmtTime, stageLabel } from "./format";

// Friendlier names for detail keys we know about. Anything else falls back to "Sentence case".
const KEY_LABELS: Record<string, string> = {
  source_kind: "Source type",
  ref: "Reference",
  raw_payload: "Raw payload",
  edi_control_number: "EDI control #",
  canonical_version: "Canonical model",
  check: "Check",
  eld_age_minutes: "ELD ping age",
  limit_minutes: "Limit",
  model_version: "Model version",
  input_snapshot: "Input snapshot",
  from_driver: "From driver",
  to_driver: "To driver",
  reason_code: "Reason code",
  write_id: "Write ID",
  http_status: "HTTP status",
  shipment_id: "Shipment ID",
  assignment_matches: "Assignment matches",
};

// Keys whose values are identifiers/paths and read better in monospace.
const CODE_KEYS = new Set(["raw_payload", "input_snapshot", "write_id", "edi_control_number", "ref", "shipment_id", "model_version"]);

const humanize = (key: string) => KEY_LABELS[key] ?? key.charAt(0).toUpperCase() + key.slice(1).replaceAll("_", " ");

function formatValue(key: string, value: unknown): ReactNode {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (key.endsWith("_minutes") && typeof value === "number") return `${value} min`;
  if (key === "score" && typeof value === "number") return value.toFixed(2);
  if (key === "source_kind") return String(value).toUpperCase();
  if (key === "check") return String(value).replaceAll("_", " ");
  if (key === "action") return String(value).charAt(0).toUpperCase() + String(value).slice(1);
  if (value !== null && typeof value === "object") return <code>{JSON.stringify(value)}</code>;
  if (CODE_KEYS.has(key)) return <code>{String(value)}</code>;
  return String(value);
}

export function Timeline({ events }: { events: TimelineEvent[] }) {
  const [raw, setRaw] = useState<Set<number>>(new Set());
  const allOpen = raw.size === events.length;

  const toggle = (i: number) =>
    setRaw((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });

  return (
    <div className="timeline-card">
      <div className="timeline-head">
        <span className="timeline-title">Event timeline <span className="muted">· {events.length} events</span></span>
        <button className="raw-all" aria-pressed={allOpen} onClick={() => setRaw(allOpen ? new Set() : new Set(events.map((_, i) => i)))}>
          {allOpen ? "Hide raw JSON" : "Show raw JSON"}
        </button>
      </div>

      <table className="timeline">
        <thead>
          <tr><th>Time</th><th>Stage</th><th>Result</th><th>Detail</th><th aria-label="Raw JSON" /></tr>
        </thead>
        <tbody>
          {events.map((e, i) => {
            const { reason, ...fields } = e.detail as Record<string, unknown>;
            const isRaw = raw.has(i);
            return (
              <tr key={i} className={e.status}>
                <td className="nowrap">{fmtTime(e.time)}</td>
                <td className="nowrap">{stageLabel(e.stage)}</td>
                <td><span className={`result ${e.status}`}>{e.status === "ok" ? "OK" : "Failed"}</span></td>
                <td className="detail-cell">
                  {typeof reason === "string" && <p className="reason">{reason}</p>}
                  <dl className="fields">
                    {Object.entries(fields).map(([k, v]) => (
                      <div key={k} className="field">
                        <dt>{humanize(k)}</dt>
                        <dd>{formatValue(k, v)}</dd>
                      </div>
                    ))}
                  </dl>
                  {isRaw && <pre className="raw-json">{JSON.stringify(e.detail, null, 2)}</pre>}
                </td>
                <td className="raw-toggle-cell">
                  <button className="raw-toggle" aria-expanded={isRaw} title={isRaw ? "Hide raw JSON" : "Show raw JSON"} onClick={() => toggle(i)}>
                    {"{ }"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
