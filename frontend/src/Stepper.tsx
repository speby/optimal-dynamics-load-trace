import type { StageEntry } from "./types";
import { fmtTime, stageLabel } from "./format";

/** Stages as a connected sequence. `compact` = dots only (table row); full = labels and times. */
export function Stepper({ stages, compact = false }: { stages: StageEntry[]; compact?: boolean }) {
  return (
    <ol className={`stepper ${compact ? "compact" : "full"}`} style={{ gridTemplateColumns: `repeat(${stages.length}, 1fr)` }}>
      {stages.map((s, i) => {
        const prevDone = i > 0 && stages[i - 1].status === "done";
        const tip = [stageLabel(s.stage), s.status.replace("_", " "), fmtTime(s.time), s.reason, sublabel(s), s.detail.warning as string | undefined]
          .filter(Boolean)
          .join(" · ");
        return (
          <li key={s.stage} className={`step ${s.status} ${i === 0 ? "first" : ""} ${prevDone ? "from-done" : ""} ${attention(s) ? "attention" : ""}`} title={tip}>
            <span className="dot" aria-hidden>
              {s.status === "done" && <Check />}
              {s.status === "failed" && <Cross />}
            </span>
            {!compact && (
              <span className="step-text">
                <span className="step-label">{stageLabel(s.stage)}</span>
                {sublabel(s) && <span className="step-sub">{sublabel(s)}</span>}
                <span className="step-time">{s.time ? fmtTime(s.time) : s.status === "waiting" ? "waiting" : ""}</span>
              </span>
            )}
            {compact && <span className="sr-only">{tip}</span>}
          </li>
        );
      })}
    </ol>
  );
}

// A stage that passed but deserves a look: a planner rejection, or a soft input warning.
const attention = (s: StageEntry) => s.detail.action === "rejected" || !!s.detail.warning;

function sublabel(s: StageEntry): string | null {
  if (s.stage === "planner_decision" && s.detail.action) return s.detail.action === "rejected" ? "Rejected" : "Accepted";
  if (s.detail.warning) return "Warning";
  return null;
}

const Check = () => (
  <svg viewBox="0 0 12 12" width="8" height="8"><path d="M2.5 6.2 5 8.5l4.5-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
);
const Cross = () => (
  <svg viewBox="0 0 12 12" width="8" height="8"><path d="M3 3l6 6M9 3l-6 6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
);
