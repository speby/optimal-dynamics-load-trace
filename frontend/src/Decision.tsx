import type { Candidate, Decision, Override } from "./types";
import { COMPONENT_LABELS, truckLabel } from "./format";

/** Why the solver recommended what it did, and (if overridden) why the planner disagreed. */
export function DecisionPanel({ decision, override }: { decision: Decision; override: Override | null }) {
  const pick = override?.assigned_truck ?? null;
  const pickCandidate = pick ? decision.candidates.find((c) => c.truck === pick) : undefined;
  const components = Object.keys(decision.weights);

  return (
    <section className="decision" aria-label="Solver decision">
      {override && <OverrideCallout override={override} />}

      <div className="decision-head">
        <h3>Solver decision</h3>
        <div className="meta-chips">
          <span><em>Model</em> {decision.model_version}</span>
          <span><em>Weights</em> {decision.objective_config}</span>
          <span><em>Constraints</em> {decision.constraint_set}</span>
          <span><em>Snapshot</em> <code>{decision.input_snapshot}</code></span>
          <span><em>Full record</em> <code>s3://decision-records/{decision.solve_id}.json</code></span>
        </div>
      </div>

      <Funnel decision={decision} />

      {decision.input_warnings.length > 0 && (
        <ul className="input-warnings">
          {decision.input_warnings.map((w) => <li key={w}>⚠ Input warning: {w}</li>)}
        </ul>
      )}

      <div className="cand-wrap">
        <table className="candidates">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Truck</th>
              <th>Score</th>
              {components.map((k) => (
                <th key={k}>{COMPONENT_LABELS[k] ?? k} <span className="weight">×{decision.weights[k].toFixed(2)}</span></th>
              ))}
              <th />
            </tr>
          </thead>
          <tbody>
            {decision.candidates.map((c) => (
              <CandidateRow key={c.truck} c={c} components={components}
                recommended={c.truck === decision.recommended} pick={c.truck === pick} />
            ))}
            {pick && !pickCandidate && (
              <tr className="cand pick missing">
                <td>—</td>
                <td><strong>{truckLabel(pick)}</strong><div className="muted small">{override?.driver}</div></td>
                <td colSpan={components.length + 1}>Not in the solver's fleet snapshot, so it was never scored.</td>
                <td><span className="tag pick">Planner's pick</span></td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Top {decision.candidates.filter((c) => c.feasible).length} feasible trucks shown
        {pick && pickCandidate && !decision.candidates.slice(0, 5).includes(pickCandidate) ? ", plus the planner's pick" : ""}.
        Score = weighted sum of the components.
      </p>
    </section>
  );
}

function OverrideCallout({ override }: { override: Override }) {
  const d = override.diagnosis;
  return (
    <div className={`callout override ${d.code}`}>
      <div className="override-line">
        <strong>Planner rejected {truckLabel(override.recommended_truck)}</strong>
        <span className="arrow">→</span>
        <strong>assigned {truckLabel(override.assigned_truck)}</strong>
        <span className="muted">({override.driver})</span>
        <span className="reason-chip">{override.reason}</span>
      </div>
      {override.note && <p className="note">“{override.note}”</p>}
      <div className="diagnosis">
        <div className="diagnosis-title">{d.title}</div>
        <p>{d.explanation}</p>
        <div className="fix"><em>Where to fix</em> {d.where_to_fix}</div>
      </div>
    </div>
  );
}

function Funnel({ decision }: { decision: Decision }) {
  return (
    <ol className="funnel">
      {decision.funnel.map((f) => (
        <li key={f.step} className={f.removed !== undefined ? "removed" : "count"}>
          {f.removed !== undefined ? (
            <><span className="num">−{f.removed}</span><span className="lbl">{f.label}</span></>
          ) : (
            <><span className="num">{f.count}</span><span className="lbl">{f.label}</span></>
          )}
        </li>
      ))}
      {decision.recommended && (
        <li className="count chosen">
          <span className="num">{truckLabel(decision.recommended)}</span>
          <span className="lbl">Recommended{decision.margin !== null ? ` · +${decision.margin.toFixed(2)} over #2` : ""}</span>
        </li>
      )}
    </ol>
  );
}

function CandidateRow({ c, components, recommended, pick }: {
  c: Candidate; components: string[]; recommended: boolean; pick: boolean;
}) {
  return (
    <tr className={`cand ${recommended ? "rec" : ""} ${pick ? "pick" : ""} ${c.feasible ? "" : "out"}`}>
      <td>{c.rank ? `#${c.rank}` : "—"}</td>
      <td>
        <strong>{truckLabel(c.truck)}</strong>
        <div className="muted small">{c.deadhead_mi} mi · {c.hos_hours_left}h left</div>
      </td>
      <td className="score">{c.score.toFixed(2)}{!c.feasible && <div className="muted small">if allowed</div>}</td>
      {c.feasible ? (
        components.map((k) => <td key={k}><Bar value={c.components[k]} /></td>)
      ) : (
        <td colSpan={components.length} className="ruled-out">
          Ruled out: {c.eliminated_detail}
          {c.warnings.length > 0 && <span className="warn-inline"> · ⚠ {c.warnings.join("; ")}</span>}
        </td>
      )}
      <td className="tags">
        {recommended && <span className="tag rec">Recommended</span>}
        {pick && <span className="tag pick">Planner's pick</span>}
      </td>
    </tr>
  );
}

function Bar({ value }: { value: number }) {
  return (
    <span className="bar" title={value.toFixed(2)}>
      <span className="bar-fill" style={{ width: `${Math.round(value * 100)}%` }} />
      <span className="bar-val">{value.toFixed(2)}</span>
    </span>
  );
}
