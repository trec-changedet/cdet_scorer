import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { TopicDetailResponse, TopicOverviewItem } from "../types/api";
import { fmtFloat, fmtInt } from "../utils/format";
import { PlotlyChart } from "./PlotlyChart";

interface TopicsTabProps {
  runs: string[];
  topics: TopicOverviewItem[];
  selectedTopicId: string | null;
  onSelectTopic: (tid: string) => void;
  onJumpToCalendar: (tid: string) => void;
}

type SortByOption = "tid" | "delta_desc" | "delta_abs" | "run_a_desc" | "num_rel_desc";

export function TopicsTab({
  runs,
  topics,
  selectedTopicId,
  onSelectTopic,
  onJumpToCalendar,
}: TopicsTabProps) {
  const [metric, setMetric] = useState("ndcg'");
  const [runA, setRunA] = useState(runs[0] ?? "");
  const [runB, setRunB] = useState(runs[1] ?? runs[0] ?? "");
  const [sortBy, setSortBy] = useState<SortByOption>("tid");
  const [topicDetail, setTopicDetail] = useState<TopicDetailResponse | null>(null);

  useEffect(() => {
    if (runs.length > 0 && !runs.includes(runA)) setRunA(runs[0]);
    if (runs.length > 0 && !runs.includes(runB)) setRunB(runs[1] ?? runs[0]);
  }, [runs, runA, runB]);

  useEffect(() => {
    if (!selectedTopicId) return;
    let cancelled = false;
    api
      .getTopicDetail(selectedTopicId)
      .then((detail) => {
        if (!cancelled) setTopicDetail(detail);
      })
      .catch((err) => console.error("Failed to load topic detail:", err));
    return () => {
      cancelled = true;
    };
  }, [selectedTopicId, topics]);

  const isIntMetric = ["num_rel_ret", "num_ret", "num_rel", "unjudged"].includes(metric);

  const sortedRows = useMemo(() => {
    const rows = topics.map((t) => {
      const valA = t.runs[runA] ? t.runs[runA].metrics[metric] ?? null : null;
      const valB = t.runs[runB] ? t.runs[runB].metrics[metric] ?? null : null;
      const delta = valA !== null && valB !== null ? Number(valA) - Number(valB) : 0;
      return { ...t, valA, valB, delta };
    });

    if (sortBy === "delta_desc") rows.sort((a, b) => b.delta - a.delta);
    else if (sortBy === "delta_abs")
      rows.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    else if (sortBy === "run_a_desc")
      rows.sort((a, b) => Number(b.valA ?? 0) - Number(a.valA ?? 0));
    else if (sortBy === "num_rel_desc") rows.sort((a, b) => b.num_rel - a.num_rel);
    else rows.sort((a, b) => a.tid.localeCompare(b.tid));

    return rows;
  }, [topics, runA, runB, metric, sortBy]);

  const deltaPlotSpec = useMemo(() => {
    const plotRows = [...sortedRows].reverse();
    const trace = {
      type: "bar",
      orientation: "h",
      y: plotRows.map((r) => r.tid),
      x: plotRows.map((r) => r.delta),
      text: plotRows.map((r) => `${r.tid}: ${r.label}`),
      marker: {
        color: plotRows.map((r) => (r.delta >= 0 ? "#4f46e5" : "#d97706")),
      },
      hovertemplate: "<b>%{text}</b><br>Delta (A − B): %{x:.4f}<extra></extra>",
    };
    const layout: Record<string, unknown> = {
      margin: { t: 10, r: 20, b: 40, l: 85 },
      xaxis: {
        title: `${metric} Delta (${runA} − ${runB})`,
        zeroline: true,
        zerolinewidth: 2,
        zerolinecolor: "#475569",
      },
      yaxis: { tickfont: { size: 10 } },
      paper_bgcolor: "transparent",
      plot_bgcolor: "#f8fafc",
    };
    return { traces: [trace], layout };
  }, [sortedRows, metric, runA, runB]);

  const fmtVal = (v: number | null | undefined) =>
    isIntMetric ? fmtInt(v) : fmtFloat(v);

  return (
    <section className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <label className="font-semibold text-slate-700">Metric:</label>
            <select
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
              className="border border-slate-300 rounded px-2.5 py-1 bg-white"
            >
              <option value="ndcg'">ndcg&apos;</option>
              <option value="rbp'(p=0.8)">rbp&apos;(p=0.8)</option>
              <option value="ap'">ap&apos;</option>
              <option value="recip_rank'">recip_rank&apos;</option>
              <option value="abstention">abstention</option>
              <option value="noise">noise</option>
              <option value="rbo(p=0.8)">rbo(p=0.8)</option>
              <option value="num_rel_ret">num_rel_ret</option>
              <option value="num_ret">num_ret</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <label className="font-semibold text-slate-700">Run A:</label>
            <select
              value={runA}
              onChange={(e) => setRunA(e.target.value)}
              className="border border-slate-300 rounded px-2.5 py-1 bg-white"
            >
              {runs.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <label className="font-semibold text-slate-700">Run B:</label>
            <select
              value={runB}
              onChange={(e) => setRunB(e.target.value)}
              className="border border-slate-300 rounded px-2.5 py-1 bg-white"
            >
              {runs.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <label className="font-semibold text-slate-700">Sort by:</label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortByOption)}
              className="border border-slate-300 rounded px-2.5 py-1 bg-white"
            >
              <option value="tid">Topic ID</option>
              <option value="delta_desc">Delta (A − B) High → Low</option>
              <option value="delta_abs">Largest Absolute Diff |A − B|</option>
              <option value="run_a_desc">Run A Score High → Low</option>
              <option value="num_rel_desc">Total Relevant Docs High → Low</option>
            </select>
          </div>
        </div>
        <div className="text-xs text-slate-500">
          Click any topic row to inspect its per-question breakdown or jump to its Event Calendar.
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 bg-white rounded-xl shadow-sm border border-slate-200 p-4">
          <h3 className="text-sm font-semibold text-slate-800 mb-1">
            Per-Topic Comparison &amp; Delta (Run A − Run B)
          </h3>
          <p className="text-xs text-slate-500 mb-2">
            Click a bar to select that topic below.
          </p>
          <PlotlyChart
            data={deltaPlotSpec.traces}
            layout={deltaPlotSpec.layout}
            className="w-full min-h-[520px]"
            onPointClick={(pt) => {
              if (typeof pt.y === "string") onSelectTopic(pt.y);
            }}
          />
        </div>

        <div className="lg:col-span-7 bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
          <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-800">Topics Summary Table</h3>
            <span className="text-xs text-slate-500">{sortedRows.length} topics</span>
          </div>
          <div className="overflow-x-auto max-h-[560px]">
            <table className="w-full text-left border-collapse text-xs">
              <thead className="sticky top-0 bg-slate-100 text-slate-600 border-b border-slate-200 z-10">
                <tr>
                  <th className="py-2 px-3">Topic</th>
                  <th className="py-2 px-2 text-right">Days</th>
                  <th className="py-2 px-2 text-right">Qs</th>
                  <th className="py-2 px-2 text-right">num_rel</th>
                  <th className="py-2 px-2 text-right bg-indigo-50/70">
                    {runA} ({metric})
                  </th>
                  <th className="py-2 px-2 text-right bg-amber-50/70">
                    {runB} ({metric})
                  </th>
                  <th className="py-2 px-2 text-right">Delta (A−B)</th>
                  <th className="py-2 px-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {sortedRows.map((r) => {
                  const isSelected = r.tid === selectedTopicId;
                  const deltaCls =
                    r.delta > 0.0001
                      ? "text-indigo-700 font-semibold"
                      : r.delta < -0.0001
                      ? "text-amber-700 font-semibold"
                      : "text-slate-400";
                  const sign = r.delta > 0 ? "+" : "";
                  const deltaStr = isIntMetric
                    ? `${sign}${r.delta}`
                    : `${sign}${r.delta.toFixed(4)}`;

                  return (
                    <tr
                      key={r.tid}
                      onClick={() => onSelectTopic(r.tid)}
                      className={`cursor-pointer transition-colors ${
                        isSelected ? "bg-indigo-50/90" : "hover:bg-slate-50"
                      }`}
                    >
                      <td className="py-2 px-3">
                        <div className="font-mono font-bold text-slate-900">{r.tid}</div>
                        <div
                          className="text-[11px] text-slate-500 truncate max-w-[240px]"
                          title={r.label}
                        >
                          {r.label}
                        </div>
                      </td>
                      <td className="py-2 px-2 text-right font-mono">{r.num_days}</td>
                      <td className="py-2 px-2 text-right font-mono">{r.num_qs}</td>
                      <td className="py-2 px-2 text-right font-mono font-medium">
                        {r.num_rel}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-indigo-50/40">
                        {fmtVal(r.valA)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-amber-50/40">
                        {fmtVal(r.valB)}
                      </td>
                      <td className={`py-2 px-2 text-right font-mono ${deltaCls}`}>
                        {deltaStr}
                      </td>
                      <td className="py-2 px-3 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onJumpToCalendar(r.tid);
                          }}
                          className="text-indigo-600 hover:underline font-medium"
                        >
                          Calendar →
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {topicDetail && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50 flex flex-wrap items-start justify-between gap-4">
            <div className="max-w-4xl">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold bg-indigo-100 text-indigo-800 px-2 py-0.5 rounded">
                  {topicDetail.tid}
                </span>
                <h3 className="text-sm font-semibold text-slate-800">
                  {topicDetail.label}
                </h3>
              </div>
              <p className="text-xs text-slate-600 mt-1 leading-relaxed">
                {topicDetail.narrative}
              </p>
            </div>
            <button
              onClick={() => onJumpToCalendar(topicDetail.tid)}
              className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium px-3 py-1.5 rounded-lg shadow-sm"
            >
              Open in Event Calendar →
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-100 text-slate-600 border-b border-slate-200">
                  <th className="py-2 px-3">QID</th>
                  <th className="py-2 px-3">Question Text</th>
                  <th
                    className="py-2 px-2 text-right"
                    title="Number of assessed days where this question had >=1 relevant doc"
                  >
                    Event Days
                  </th>
                  <th className="py-2 px-2 text-right">num_rel</th>
                  <th
                    className="py-2 px-2 text-right bg-indigo-50/60 border-l border-slate-200"
                    colSpan={4}
                  >
                    {runA}
                  </th>
                  <th
                    className="py-2 px-2 text-right bg-amber-50/60 border-l border-slate-200"
                    colSpan={4}
                  >
                    {runB}
                  </th>
                </tr>
                <tr className="bg-slate-50 text-slate-500 border-b border-slate-200 text-[11px]">
                  <th colSpan={4} />
                  <th className="py-1 px-2 text-right border-l border-slate-200">
                    ndcg&apos;
                  </th>
                  <th className="py-1 px-2 text-right">rel_ret / ret</th>
                  <th className="py-1 px-2 text-right">abst</th>
                  <th className="py-1 px-2 text-right">noise</th>
                  <th className="py-1 px-2 text-right border-l border-slate-200">
                    ndcg&apos;
                  </th>
                  <th className="py-1 px-2 text-right">rel_ret / ret</th>
                  <th className="py-1 px-2 text-right">abst</th>
                  <th className="py-1 px-2 text-right">noise</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {topicDetail.questions.map((q) => {
                  const ra = q.runs[runA]?.metrics ?? {};
                  const rb = q.runs[runB]?.metrics ?? {};
                  const quietRow = q.num_rel === 0 ? "opacity-60 bg-slate-50/60" : "";
                  return (
                    <tr key={q.qid} className={`hover:bg-slate-50 ${quietRow}`}>
                      <td className="py-2 px-3 font-mono font-bold text-slate-800">
                        {q.qid}
                      </td>
                      <td className="py-2 px-3 text-slate-700">{q.question}</td>
                      <td className="py-2 px-2 text-right font-mono">
                        {q.answerable_days}
                      </td>
                      <td className="py-2 px-2 text-right font-mono font-semibold">
                        {q.num_rel}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-indigo-50/20 border-l border-slate-200">
                        {fmtFloat(ra["ndcg'"])}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-indigo-50/20">
                        {fmtInt(ra.num_rel_ret)} / {fmtInt(ra.num_ret)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-indigo-50/20">
                        {fmtFloat(ra.abstention)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-indigo-50/20">
                        {fmtFloat(ra.noise)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-amber-50/20 border-l border-slate-200">
                        {fmtFloat(rb["ndcg'"])}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-amber-50/20">
                        {fmtInt(rb.num_rel_ret)} / {fmtInt(rb.num_ret)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-amber-50/20">
                        {fmtFloat(rb.abstention)}
                      </td>
                      <td className="py-2 px-2 text-right font-mono bg-amber-50/20">
                        {fmtFloat(rb.noise)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
