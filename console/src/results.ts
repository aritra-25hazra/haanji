/** The benchmark's measured numbers, copied from research/results.json by
 *  research/harness/console_results.py (a test fails when the copy is stale). */
import RESULTS from "./results.json";

export interface Measured {
  how_to_reproduce: string; measured_at: string; reps: number; packs: number; scenarios: number;
  headline: Record<string, number>;
  ledger: { chain_length: number; clean_chain_valid: boolean; mutations_attempted: number; mutations_detected: number; detection_rate: number; unconfirmed_writes_accepted: number };
  configs: Record<string, { calls: number; outcome_accuracy: number; unconfirmed_writes: number }>;
  noise: { noise: number; sentences: number; error_without: number; error_with: number }[];
}
export const MEASURED = RESULTS as unknown as Measured;
export const pct = (x: number, digits = 1) => `${(x * 100).toFixed(digits).replace(/\.0+$/, "")}%`;
export const ms = (x: number) => `${Math.round(x)} ms`;
export const measuredOn = () => new Date(MEASURED.measured_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
