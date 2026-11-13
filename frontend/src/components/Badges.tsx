import type { BehavioralState } from "../types/api";

export const RELEVANCE_DEFINITIONS: Record<string, string> = {
  action: "Action (gain = 20): new information that changes what needs to be done.",
  assessment: "Assessment (gain = 5): new information that changes how the situation is interpreted.",
  awareness: "Awareness (gain = 1): new relevant information.",
  not_relevant: "Judged not relevant (gain = 0).",
  unjudged: "Pooled or retrieved document without a relevance judgment (treated as gain = 0).",
};

export const STATE_DEFINITIONS: Record<string, string> = {
  event_hit:
    "Answerable question-day (num_rel > 0) where the run retrieved at least one relevant document (num_rel_ret > 0).",
  zero_hit_trigger:
    "Answerable question-day (num_rel > 0) where the run returned documents (num_ret > 0) but none were relevant (num_rel_ret = 0). Scores 0 on prime measures.",
  missed_event:
    "Answerable question-day (num_rel > 0) where the run returned no documents (num_ret = 0). Scores 0 on prime measures.",
  true_abstention:
    "Nil-answer question-day (num_rel = 0) where the run returned no documents (num_ret = 0). Scores abstention = 1, noise = 0.",
  false_alarm:
    "Nil-answer question-day (num_rel = 0) where the run returned one or more documents (num_ret > 0). Scores abstention = 0, noise = num_ret.",
};

export function RelevanceBadge({ rel }: { rel: string }) {
  const styles: Record<string, string> = {
    action: "bg-emerald-700 text-white font-bold",
    assessment: "bg-emerald-500 text-white font-semibold",
    awareness: "bg-emerald-100 text-emerald-900 border border-emerald-300 font-medium",
    not_relevant: "bg-rose-100 text-rose-800 border border-rose-200",
    unjudged: "bg-slate-200 text-slate-700",
  };
  const cls = styles[rel] ?? styles.unjudged;
  const tip = RELEVANCE_DEFINITIONS[rel] ?? rel;
  return (
    <span title={tip} className={`px-1.5 py-0.5 rounded text-[10px] uppercase cursor-help ${cls}`}>
      {rel}
    </span>
  );
}

export function StateBadge({ state }: { state: BehavioralState | string }) {
  const styles: Record<string, [string, string]> = {
    event_hit: ["Event Hit", "bg-emerald-100 text-emerald-900 border border-emerald-300"],
    zero_hit_trigger: ["Zero-Hit Trigger", "bg-amber-100 text-amber-900 border border-amber-300"],
    missed_event: ["Missed Event", "bg-rose-100 text-rose-900 border border-rose-300"],
    true_abstention: ["Abstention", "bg-slate-100 text-slate-700 border border-slate-200"],
    false_alarm: ["False Alarm", "bg-purple-100 text-purple-900 border border-purple-300"],
  };
  const [label, cls] = styles[state] ?? [state, "bg-slate-100 text-slate-700"];
  const tip = STATE_DEFINITIONS[state] ?? String(state);
  return (
    <span title={tip} className={`px-2 py-0.5 rounded text-[11px] font-medium cursor-help ${cls}`}>
      {label}
    </span>
  );
}
