// Mirrors the shapes returned by backend/loadtrace/trace.py.

export type StageStatus = "done" | "failed" | "waiting" | "not_reached";
export type LoadState = "complete" | "in_progress" | "failed" | "overridden";

export interface StageEntry {
  stage: string;
  status: StageStatus;
  time: string | null;
  reason: string | null;
  detail: Record<string, unknown>;
}

export interface TimelineEvent {
  time: string;
  stage: string;
  status: "ok" | "fail";
  detail: Record<string, unknown>;
}

export interface LoadTrace {
  load_id: string;
  external_ids: Record<string, string>;
  customer: string | null;
  source: string | null;
  source_kind: "tms" | "edi" | null;
  source_ref: string | null;
  origin: string | null;
  destination: string | null;
  truck: string | null;
  planner_action: "accepted" | "rejected" | null;
  state: LoadState;
  override: Override | null;
  decision: Decision | null;
  warnings: { stage: string; warning: string }[];
  current_stage: string;
  first_failure: string | null;
  last_update: string | null;
  stages: StageEntry[];
  events: TimelineEvent[];
}

export interface Diagnosis {
  code: "not_considered" | "ruled_out" | "scored_lower" | "planner_context";
  title: string;
  explanation: string;
  where_to_fix: string;
}

export interface Override {
  recommended_truck: string;
  assigned_truck: string;
  driver: string;
  reason_code: string;
  reason: string;
  note: string | null;
  diagnosis: Diagnosis;
}

export interface Candidate {
  truck: string;
  hos_hours_left: number;
  hos_age_min: number;
  eld_age_min: number;
  equipment: string;
  deadhead_mi: number;
  components: Record<string, number>;
  feasible: boolean;
  eliminated_by: string | null;
  eliminated_detail: string | null;
  score: number;
  rank: number | null;
  warnings: string[];
}

export interface FunnelStep {
  step: string;
  label: string;
  count?: number;
  removed?: number;
}

/** The solver's decision record, trimmed to top candidates plus the planner's truck. */
export interface Decision {
  solve_id: string;
  model_version: string;
  objective_config: string;
  constraint_set: string;
  input_snapshot: string;
  weights: Record<string, number>;
  funnel: FunnelStep[];
  recommended: string | null;
  recommended_score: number | null;
  margin: number | null;
  input_warnings: string[];
  candidates: Candidate[];
}

export interface LoadsResponse {
  now: string;
  stages: string[];
  loads: LoadTrace[];
}

export async function fetchLoads(): Promise<LoadsResponse> {
  const res = await fetch("/api/loads");
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}
