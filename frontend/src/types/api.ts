export type RollupMode = "micro" | "macro_topic" | "macro_question" | "macro_day";
export type RelLevelName = "awareness" | "assessment" | "action";
export type BehavioralState =
  | "event_hit"
  | "zero_hit_trigger"
  | "missed_event"
  | "true_abstention"
  | "false_alarm";

export interface ExplorerConfig {
  min_rel_level: RelLevelName;
  min_rel_gain: number;
  max_depth: number;
  runs: string[];
  num_topics: number;
  has_corpus: boolean;
}

export interface RunMetadata {
  runtag: string;
  description: string;
  run_type: "manual" | "automatic";
  models: string[];
  extern: string;
  extra?: Record<string, string> | null;
}

export interface MetricMap {
  num_topics?: number;
  num_days?: number;
  num_qs?: number;
  qranking_num_topics?: number;
  qranking_num_days?: number;
  num_ret?: number;
  num_rel?: number;
  num_rel_ret?: number;
  unjudged?: number;
  unjudged_rate?: number;
  "recip_rank'"?: number | null;
  "ap'"?: number | null;
  "ndcg'"?: number | null;
  "rbp'(p=0.8)"?: number | null;
  abstention?: number | null;
  noise?: number | null;
  "rbo(p=0.8)"?: number | null;
  [key: string]: number | null | undefined;
}

export interface BehavioralStats {
  total_points: number;
  answerable_points: number;
  nil_points: number;
  event_hit: number;
  zero_hit_trigger: number;
  missed_event: number;
  true_abstention: number;
  false_alarm: number;
  nil_noise_docs: number;
  nil_unjudged_docs: number;
  nil_judged_nonrel_docs: number;
  event_hit_rate: number | null;
  zero_hit_trigger_rate: number | null;
  missed_event_rate: number | null;
  trigger_rate_on_answerable: number | null;
  true_abstention_rate: number | null;
  false_alarm_rate: number | null;
  unjudged_fraction_of_noise: number;
  active_prime: Record<string, number | null>;
}

export interface RunSummaryEntry {
  runtag: string;
  metadata: RunMetadata;
  metrics: MetricMap;
  all_rollups: Record<RollupMode, MetricMap>;
  behavioral: BehavioralStats;
}

export interface RunsSummaryResponse {
  config: ExplorerConfig;
  rollup: RollupMode;
  runs: RunSummaryEntry[];
}

export interface ScopedSummary {
  metrics: MetricMap;
  behavioral: BehavioralStats;
}

export interface TopicOverviewItem {
  tid: string;
  label: string;
  narrative: string;
  num_days: number;
  num_qs: number;
  num_rel: number;
  runs: Record<string, ScopedSummary>;
}

export interface TopicsOverviewResponse {
  config: ExplorerConfig;
  topics: TopicOverviewItem[];
}

export interface QuestionDetailItem {
  qid: string;
  question: string;
  num_rel: number;
  answerable_days: number;
  runs: Record<string, ScopedSummary>;
}

export interface DaySummaryItem {
  day: string;
  qrel_qranking: string[];
  runs: Record<string, ScopedSummary>;
}

export interface TopicDetailResponse {
  tid: string;
  label: string;
  narrative: string;
  runs: Record<string, ScopedSummary>;
  questions: QuestionDetailItem[];
  days: DaySummaryItem[];
}

export interface CalendarCellRun {
  state: BehavioralState;
  scores: MetricMap;
}

export interface CalendarCell {
  num_rel: number;
  runs: Record<string, CalendarCellRun>;
}

export interface TopicCalendarResponse {
  tid: string;
  label: string;
  narrative: string;
  questions: { qid: string; question: string }[];
  days: string[];
  day_summaries: DaySummaryItem[];
  matrix: Record<string, Record<string, CalendarCell>>;
}

export interface RankedDocItem {
  rank: number;
  doc_id: string;
  score: number;
  rel: string;
  effective_gain: number;
  dcg_contribution: number;
}

export interface RelevantDocItem {
  doc_id: string;
  raw_rel: string;
  raw_gain: number;
  counts_as_relevant: boolean;
}

export interface CellRunDetail {
  state: BehavioralState;
  question_rank: number | null;
  scores: MetricMap;
  terminal_gain_rt: number | null;
  ranked_docs: RankedDocItem[];
  missed_relevant_docs: RelevantDocItem[];
}

export interface CellDetailResponse {
  tid: string;
  topic_label: string;
  topic_narrative: string;
  day: string;
  qid: string;
  question_text: string;
  num_rel: number;
  rel_counts_by_level: {
    action: number;
    assessment: number;
    awareness: number;
  };
  relevant_docs: RelevantDocItem[];
  qrel_qranking: string[];
  runs: Record<string, CellRunDetail>;
}

export interface DocJudgmentItem {
  topic: string;
  day: string;
  qid: string;
  question_text: string | null;
  rel: string;
  gain: number;
}

export interface DocumentResponse {
  id: string;
  document: {
    id: string;
    day: string;
    date: string;
    url: string;
    text: string;
  } | null;
  judgments: DocJudgmentItem[];
}
