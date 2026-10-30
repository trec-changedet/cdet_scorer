import type {
  CellDetailResponse,
  DocumentResponse,
  ExplorerConfig,
  RelLevelName,
  RollupMode,
  RunsSummaryResponse,
  TopicCalendarResponse,
  TopicDetailResponse,
  TopicsOverviewResponse,
} from "./types/api";

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, options);
  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${errText}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  getRunsSummary: (rollup: RollupMode) =>
    fetchJson<RunsSummaryResponse>(`/api/runs/summary?rollup=${encodeURIComponent(rollup)}`),

  getTopicsOverview: () => fetchJson<TopicsOverviewResponse>("/api/topics"),

  getTopicDetail: (tid: string) =>
    fetchJson<TopicDetailResponse>(`/api/topics/${encodeURIComponent(tid)}`),

  getTopicCalendar: (tid: string, activeDaysOnly: boolean) =>
    fetchJson<TopicCalendarResponse>(
      `/api/topics/${encodeURIComponent(tid)}/calendar?active_days_only=${activeDaysOnly}`
    ),

  getCellDetail: (tid: string, day: string, qid: string) =>
    fetchJson<CellDetailResponse>(
      `/api/cell/${encodeURIComponent(tid)}/${encodeURIComponent(day)}/${encodeURIComponent(qid)}`
    ),

  getDocument: (docId: string) =>
    fetchJson<DocumentResponse>(`/api/docs/${encodeURIComponent(docId)}`),

  updateConfig: (minRelLevel: RelLevelName, maxDepth: number) =>
    fetchJson<ExplorerConfig>("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ min_rel_level: minRelLevel, max_depth: maxDepth }),
    }),
};
