import type { LoadState } from "./types";

export const STAGE_LABELS: Record<string, string> = {
  received: "Received",
  normalized: "Normalized",
  checked: "Checked",
  solve_run: "Solve run",
  recommended: "Recommended",
  planner_decision: "Planner",
  sent_back: "Sent back",
  acknowledged: "Acknowledged",
  confirmed: "Confirmed",
};

export const STATE_LABELS: Record<LoadState, string> = {
  failed: "Failed",
  in_progress: "In progress",
  complete: "Complete",
};

export const ID_LABELS: Record<string, string> = {
  tms_load_number: "TMS load #",
  edi_shipment_id: "EDI shipment ID",
  edi_control_number: "EDI control #",
  eld_unit: "Truck (ELD unit)",
};

export const stageLabel = (stage: string) => STAGE_LABELS[stage] ?? stage;

export const fmtTime = (iso: string | null) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", timeZone: "UTC" }) + " UTC" : "";

export function fmtAgo(iso: string | null, nowIso: string): string {
  if (!iso) return "";
  const min = Math.round((Date.parse(nowIso) - Date.parse(iso)) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  return `${Math.floor(min / 60)}h ${min % 60}m ago`;
}
