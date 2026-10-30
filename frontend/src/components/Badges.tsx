import type { BehavioralState } from "../types/api";

export function RelevanceBadge({ rel }: { rel: string }) {
  const styles: Record<string, string> = {
    action: "bg-emerald-700 text-white font-bold",
    assessment: "bg-emerald-500 text-white font-semibold",
    awareness: "bg-emerald-100 text-emerald-900 border border-emerald-300 font-medium",
    not_relevant: "bg-rose-100 text-rose-800 border border-rose-200",
    unjudged: "bg-slate-200 text-slate-700",
  };
  const cls = styles[rel] ?? styles.unjudged;
  return <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase ${cls}`}>{rel}</span>;
}

export function StateBadge({ state }: { state: BehavioralState | string }) {
  const styles: Record<string, [string, string]> = {
    event_hit: ["Event Hit", "bg-emerald-100 text-emerald-900 border border-emerald-300"],
    zero_hit_trigger: ["Zero-Hit Trigger", "bg-amber-100 text-amber-900 border border-amber-300"],
    missed_event: ["Missed Event (Silent)", "bg-rose-100 text-rose-900 border border-rose-300"],
    true_abstention: ["True Abstention", "bg-slate-100 text-slate-700 border border-slate-200"],
    false_alarm: ["False Alarm", "bg-purple-100 text-purple-900 border border-purple-300"],
  };
  const [label, cls] = styles[state] ?? [state, "bg-slate-100 text-slate-700"];
  return <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${cls}`}>{label}</span>;
}
