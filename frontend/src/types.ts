// Mirrors the shapes returned by backend/loadtrace/trace.py.

export type StageStatus = "done" | "failed" | "waiting" | "not_reached";
export type LoadState = "complete" | "in_progress" | "failed";

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
  planner_action: "accepted" | "changed" | null;
  state: LoadState;
  current_stage: string;
  first_failure: string | null;
  last_update: string | null;
  stages: StageEntry[];
  events: TimelineEvent[];
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
