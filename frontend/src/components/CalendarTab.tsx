import { useEffect, useState } from "react";
import { api } from "../api";
import type {
  CalendarCell,
  TopicCalendarResponse,
  TopicOverviewItem,
} from "../types/api";
import { fmtFloat } from "../utils/format";

interface CalendarTabProps {
  runs: string[];
  topics: TopicOverviewItem[];
  selectedTopicId: string | null;
  onSelectTopic: (tid: string) => void;
  onSelectCell: (tid: string, day: string, qid: string) => void;
}

export function CalendarTab({
  runs,
  topics,
  selectedTopicId,
  onSelectTopic,
  onSelectCell,
}: CalendarTabProps) {
  const [viewMode, setViewMode] = useState<"single" | "diff">("single");
  const [runA, setRunA] = useState(runs[0] ?? "");
  const [runB, setRunB] = useState(runs[1] ?? runs[0] ?? "");
  const [primeMetric, setPrimeMetric] = useState("ndcg'");
  const [activeDaysOnly, setActiveDaysOnly] = useState(true);
  const [calendarData, setCalendarData] = useState<TopicCalendarResponse | null>(null);

  useEffect(() => {
    if (runs.length > 0 && !runs.includes(runA)) setRunA(runs[0]);
    if (runs.length > 0 && !runs.includes(runB)) setRunB(runs[1] ?? runs[0]);
  }, [runs, runA, runB]);

  useEffect(() => {
    const tid = selectedTopicId ?? topics[0]?.tid;
    if (!tid) return;
    let cancelled = false;
    api
      .getTopicCalendar(tid, activeDaysOnly)
      .then((cal) => {
        if (!cancelled) setCalendarData(cal);
      })
      .catch((err) => console.error("Failed to load topic calendar:", err));
    return () => {
      cancelled = true;
    };
  }, [selectedTopicId, activeDaysOnly, topics]);

  return (
    <section className="space-y-5">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <div className="flex items-center gap-1.5">
              <label className="font-semibold text-slate-700">Topic:</label>
              <select
                value={selectedTopicId ?? ""}
                onChange={(e) => onSelectTopic(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 bg-white font-medium"
              >
                {topics.map((t) => (
                  <option key={t.tid} value={t.tid}>
                    {t.tid} — {t.label} (rel={t.num_rel})
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-1.5">
              <label className="font-semibold text-slate-700">View Mode:</label>
              <select
                value={viewMode}
                onChange={(e) => setViewMode(e.target.value as "single" | "diff")}
                className="border border-slate-300 rounded px-2.5 py-1.5 bg-white"
              >
                <option value="single">Single Run Inspection</option>
                <option value="diff">Run A vs. Run B Diff</option>
              </select>
            </div>

            <div className="flex items-center gap-1.5">
              <label className="font-semibold text-slate-700">Run A:</label>
              <select
                value={runA}
                onChange={(e) => setRunA(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 bg-white"
              >
                {runs.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </div>

            {viewMode === "diff" && (
              <div className="flex items-center gap-1.5">
                <label className="font-semibold text-slate-700">Run B:</label>
                <select
                  value={runB}
                  onChange={(e) => setRunB(e.target.value)}
                  className="border border-slate-300 rounded px-2.5 py-1.5 bg-white"
                >
                  {runs.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex items-center gap-1.5">
              <label className="font-semibold text-slate-700">Prime Metric:</label>
              <select
                value={primeMetric}
                onChange={(e) => setPrimeMetric(e.target.value)}
                className="border border-slate-300 rounded px-2.5 py-1.5 bg-white"
              >
                <option value="ndcg'">ndcg&apos;</option>
                <option value="rbp'(p=0.8)">rbp&apos;(p=0.8)</option>
                <option value="ap'">ap&apos;</option>
                <option value="recip_rank'">recip_rank&apos;</option>
              </select>
            </div>

            <label className="inline-flex items-center gap-1.5 cursor-pointer select-none text-slate-700 font-medium ml-2">
              <input
                type="checkbox"
                checked={activeDaysOnly}
                onChange={(e) => setActiveDaysOnly(e.target.checked)}
                className="rounded text-indigo-600"
              />
              <span>Active days only (num_rel &gt; 0 or num_ret &gt; 0)</span>
            </label>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-600">
            <span className="inline-flex items-center gap-1">
              <span className="w-3.5 h-3.5 rounded bg-emerald-600 border-2 border-slate-900 inline-block" />{" "}
              Event Hit
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-3.5 h-3.5 rounded bg-amber-300 border-2 border-slate-900 inline-block" />{" "}
              Zero-Hit Trigger
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-3.5 h-3.5 rounded bg-rose-200 border-2 border-slate-900 inline-block" />{" "}
              Missed Event (0.0)
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-3.5 h-3.5 rounded bg-purple-200 border border-purple-400 inline-block" />{" "}
              False Alarm (!noise)
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="w-3.5 h-3.5 rounded bg-slate-100 border border-slate-200 inline-block" />{" "}
              True Abstention
            </span>
          </div>
        </div>

        {calendarData && (
          <div className="border-t border-slate-100 pt-2">
            <p className="text-xs text-slate-600 leading-relaxed">
              {calendarData.narrative}
            </p>
          </div>
        )}
      </div>

      {calendarData && (
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50 flex items-center justify-between text-xs">
            <span className="font-medium text-slate-700">
              {calendarData.tid} ({calendarData.label}) • Showing{" "}
              {calendarData.days.length} days × {calendarData.questions.length} questions
            </span>
            <span className="text-slate-500">
              Click any <code className="text-slate-700">(Question, Day)</code> cell to
              inspect ranked documents and judgments.
            </span>
          </div>

          <div className="overflow-x-auto max-h-[680px]">
            {calendarData.days.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-sm">
                No active days match the filter. Uncheck &ldquo;Active days only&rdquo; to see
                all assessed days.
              </div>
            ) : (
              <table className="border-collapse text-xs w-full">
                <thead className="sticky-header bg-slate-100 border-b border-slate-300">
                  <tr>
                    <th className="sticky-col bg-slate-100 py-2 px-3 text-left min-w-[240px] border-r border-slate-300">
                      Question / Day
                    </th>
                    {calendarData.days.map((day) => (
                      <th
                        key={day}
                        title={day}
                        className="py-1.5 px-1 text-center font-mono text-[10px] text-slate-600 border-r border-slate-200 min-w-[44px]"
                      >
                        <div className="text-slate-400 text-[9px]">{day.slice(0, 4)}</div>
                        <div>{day.slice(5)}</div>
                      </th>
                    ))}
                  </tr>

                  <tr className="bg-amber-50/70 border-b border-slate-300 text-[10px]">
                    <td className="sticky-col bg-amber-50 py-1 px-3 font-semibold text-amber-900 border-r border-slate-300">
                      Daily qranking RBO(0.8) (
                      {viewMode === "diff" ? `${runA} − ${runB}` : runA})
                    </td>
                    {calendarData.day_summaries.map((ds) => {
                      const hasQrank = ds.qrel_qranking && ds.qrel_qranking.length > 0;
                      if (!hasQrank) {
                        return (
                          <td
                            key={ds.day}
                            className="text-center text-slate-300 border-r border-slate-200"
                          >
                            —
                          </td>
                        );
                      }
                      if (viewMode === "single") {
                        const rbo = ds.runs[runA]?.metrics["rbo(p=0.8)"] ?? null;
                        return (
                          <td
                            key={ds.day}
                            title={`${ds.day} RBO: ${fmtFloat(rbo)}`}
                            className="text-center font-mono text-amber-900 border-r border-slate-200"
                          >
                            {rbo !== null ? Number(rbo).toFixed(2) : "—"}
                          </td>
                        );
                      }
                      const rboA = Number(ds.runs[runA]?.metrics["rbo(p=0.8)"] ?? 0);
                      const rboB = Number(ds.runs[runB]?.metrics["rbo(p=0.8)"] ?? 0);
                      const diff = rboA - rboB;
                      const cls =
                        diff > 0.01
                          ? "text-indigo-700 font-bold"
                          : diff < -0.01
                          ? "text-amber-700 font-bold"
                          : "text-slate-500";
                      return (
                        <td
                          key={ds.day}
                          title={`${ds.day} RBO Δ: ${diff.toFixed(4)}`}
                          className={`text-center font-mono ${cls} border-r border-slate-200`}
                        >
                          {diff >= 0 ? "+" : ""}
                          {diff.toFixed(2)}
                        </td>
                      );
                    })}
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-200">
                  {calendarData.questions.map((q) => (
                    <tr key={q.qid} className="hover:bg-slate-50/80">
                      <td
                        className="sticky-col bg-white py-1.5 px-3 border-r border-slate-300 max-w-[260px]"
                        title={q.question}
                      >
                        <div className="flex items-center gap-1.5">
                          <span className="font-mono font-bold text-slate-900 shrink-0">
                            {q.qid}
                          </span>
                          <span className="text-[11px] text-slate-600 truncate">
                            {q.question}
                          </span>
                        </div>
                      </td>
                      {calendarData.days.map((day) => {
                        const cell = calendarData.matrix[q.qid]?.[day];
                        if (!cell) return <td key={day} />;
                        return (
                          <CalendarMatrixCell
                            key={day}
                            tid={calendarData.tid}
                            day={day}
                            qid={q.qid}
                            cell={cell}
                            viewMode={viewMode}
                            runA={runA}
                            runB={runB}
                            primeMetric={primeMetric}
                            onClick={() =>
                              onSelectCell(calendarData.tid, day, q.qid)
                            }
                          />
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

interface CalendarMatrixCellProps {
  tid: string;
  day: string;
  qid: string;
  cell: CalendarCell;
  viewMode: "single" | "diff";
  runA: string;
  runB: string;
  primeMetric: string;
  onClick: () => void;
}

function CalendarMatrixCell({
  tid,
  day,
  qid,
  cell,
  viewMode,
  runA,
  runB,
  primeMetric,
  onClick,
}: CalendarMatrixCellProps) {
  const numRel = cell.num_rel;
  const rcA = cell.runs[runA];
  if (!rcA) return <td />;

  if (viewMode === "single") {
    const st = rcA.state;
    const sc = rcA.scores;
    const nRet = sc.num_ret ?? 0;
    let bgCls = "bg-slate-50 text-slate-300";
    let borderCls = "border border-slate-200";
    let label = "·";
    let tooltip = `${tid} • ${day} • ${qid}\nState: ${st}\nnum_rel=${numRel}, num_ret=${nRet}`;

    if (numRel > 0) {
      borderCls = "border-2 border-slate-900";
      const pv = Number(sc[primeMetric] ?? 0);
      tooltip += `\n${primeMetric}=${fmtFloat(pv)}`;
      if (st === "missed_event") {
        bgCls = "bg-rose-200 text-rose-900 font-semibold";
        label = "0.00";
      } else if (st === "zero_hit_trigger") {
        bgCls = "bg-amber-300 text-amber-950 font-semibold";
        label = fmtFloat(pv, 2);
      } else {
        bgCls =
          pv >= 0.7
            ? "bg-emerald-600 text-white font-bold"
            : "bg-emerald-400 text-slate-950 font-semibold";
        label = fmtFloat(pv, 2);
      }
    } else if (st === "false_alarm") {
      bgCls = "bg-purple-200 text-purple-900 font-semibold";
      borderCls = "border border-purple-400";
      label = `!${nRet}`;
      tooltip += ` (unjudged=${sc.unjudged ?? 0})`;
    }

    return (
      <td
        onClick={onClick}
        title={tooltip}
        className={`cal-cell cursor-pointer text-center font-mono select-none ${bgCls} ${borderCls}`}
      >
        {label}
      </td>
    );
  }

  const rcB = cell.runs[runB] ?? rcA;
  const scA = rcA.scores;
  const scB = rcB.scores;
  let bgCls = "bg-slate-50 text-slate-300";
  let borderCls = "border border-slate-200";
  let label = "·";

  if (numRel > 0) {
    borderCls = "border-2 border-slate-900";
    const pvA = Number(scA[primeMetric] ?? 0);
    const pvB = Number(scB[primeMetric] ?? 0);
    const diff = pvA - pvB;
    if (Math.abs(diff) < 0.005) {
      bgCls = pvA > 0 ? "bg-slate-200 text-slate-800" : "bg-rose-100 text-rose-700";
      label = fmtFloat(pvA, 2);
    } else if (diff > 0) {
      bgCls = "bg-indigo-600 text-white font-bold";
      label = `+${diff.toFixed(2)}`;
    } else {
      bgCls = "bg-amber-500 text-white font-bold";
      label = `${diff.toFixed(2)}`;
    }
  } else {
    const retA = scA.num_ret ?? 0;
    const retB = scB.num_ret ?? 0;
    if (retA > 0 || retB > 0) {
      bgCls = "bg-purple-100 text-purple-900 font-medium";
      borderCls = "border border-purple-300";
      label = `${retA}/${retB}`;
    }
  }

  const tooltip = `${tid} • ${day} • ${qid} (num_rel=${numRel})\n${runA}: ${
    rcA.state
  } (ret=${scA.num_ret ?? 0}, ${primeMetric}=${fmtFloat(
    scA[primeMetric]
  )})\n${runB}: ${rcB.state} (ret=${scB.num_ret ?? 0}, ${primeMetric}=${fmtFloat(
    scB[primeMetric]
  )})`;

  return (
    <td
      onClick={onClick}
      title={tooltip}
      className={`cal-cell cursor-pointer text-center font-mono select-none ${bgCls} ${borderCls}`}
    >
      {label}
    </td>
  );
}
