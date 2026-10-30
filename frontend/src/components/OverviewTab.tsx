import { useMemo, useState } from "react";
import type { RunSummaryEntry, TopicOverviewItem } from "../types/api";
import { fmtFloat, fmtInt, fmtPct, RUN_COLORS } from "../utils/format";
import { PlotlyChart } from "./PlotlyChart";

interface OverviewTabProps {
  runs: RunSummaryEntry[];
  topics: TopicOverviewItem[];
}

export function OverviewTab({ runs, topics }: OverviewTabProps) {
  const [showActivePrime, setShowActivePrime] = useState(true);
  const [paretoY, setParetoY] = useState("ndcg'");
  const [paretoX, setParetoX] = useState<"abstention" | "noise">("abstention");
  const [showTopicsInPareto, setShowTopicsInPareto] = useState(false);

  const paretoSpec = useMemo(() => {
    const traces: Record<string, unknown>[] = [];

    if (showTopicsInPareto) {
      runs.forEach((r, i) => {
        const color = RUN_COLORS[i % RUN_COLORS.length];
        const xs: number[] = [];
        const ys: number[] = [];
        const texts: string[] = [];

        topics.forEach((t) => {
          const tr = t.runs[r.runtag];
          if (!tr) return;
          const xv = tr.metrics[paretoX];
          const yv =
            paretoY === "active_ndcg'"
              ? tr.behavioral.active_prime["ndcg'"]
              : tr.metrics[paretoY];
          if (xv !== null && xv !== undefined && yv !== null && yv !== undefined) {
            xs.push(xv);
            ys.push(yv);
            texts.push(`${r.runtag} • ${t.tid} (${t.label})`);
          }
        });

        traces.push({
          x: xs,
          y: ys,
          text: texts,
          mode: "markers",
          type: "scatter",
          name: `${r.runtag} (topics)`,
          marker: { color, size: 7, opacity: 0.35 },
          hovertemplate: `%{text}<br>${paretoX}: %{x:.4f}<br>${paretoY}: %{y:.4f}<extra></extra>`,
        });
      });
    }

    runs.forEach((r, i) => {
      const color = RUN_COLORS[i % RUN_COLORS.length];
      const xv = r.metrics[paretoX];
      const yv =
        paretoY === "active_ndcg'"
          ? r.behavioral.active_prime["ndcg'"]
          : r.metrics[paretoY];
      traces.push({
        x: [xv],
        y: [yv],
        text: [r.runtag],
        mode: "markers+text",
        textposition: "top center",
        type: "scatter",
        name: r.runtag,
        marker: { color, size: 15, line: { color: "#ffffff", width: 2 } },
        hovertemplate: `<b>${r.runtag}</b><br>${paretoX}: %{x:.4f}<br>${paretoY}: %{y:.4f}<extra></extra>`,
      });
    });

    const layout: Record<string, unknown> = {
      margin: { t: 20, r: 20, b: 45, l: 55 },
      xaxis: {
        title:
          paretoX === "abstention"
            ? "Abstention Rate (Quiet-Day Specificity →)"
            : "Mean Spurious Docs / Quiet Day (Noise)",
        zeroline: false,
      },
      yaxis: { title: paretoY, range: [0, 1.05], zeroline: false },
      showlegend: true,
      legend: { orientation: "h", y: -0.2 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "#f8fafc",
    };

    return { traces, layout };
  }, [runs, topics, paretoX, paretoY, showTopicsInPareto]);

  const behavioralSpec = useMemo(() => {
    const runNames = runs.map((r) => r.runtag);
    const colors = runs.map((_, i) => RUN_COLORS[i % RUN_COLORS.length]);

    const panels = [
      {
        title: "Event Hit Rate (num_rel_ret > 0)",
        vals: runs.map((r) => (r.behavioral.event_hit_rate ?? 0) * 100),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "Zero-Hit Trigger Rate",
        vals: runs.map((r) => (r.behavioral.zero_hit_trigger_rate ?? 0) * 100),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "Missed Event Rate (Silent)",
        vals: runs.map((r) => (r.behavioral.missed_event_rate ?? 0) * 100),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "False Alarm Rate (1 − abstention)",
        vals: runs.map((r) => (r.behavioral.false_alarm_rate ?? 0) * 100),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "Mean Noise (Docs / Nil Q-Day)",
        vals: runs.map((r) => Number(r.metrics.noise ?? 0)),
        suffix: "",
        range: null,
      },
      {
        title: "Unjudged % of Noise",
        vals: runs.map((r) => (r.behavioral.unjudged_fraction_of_noise ?? 0) * 100),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
    ];

    const traces = panels.map((p, idx) => ({
      type: "bar",
      orientation: "h",
      y: runNames,
      x: p.vals,
      xaxis: `x${idx + 1}`,
      yaxis: `y${idx + 1}`,
      marker: { color: colors },
      text: p.vals.map((v) =>
        p.suffix === "%" ? `${v.toFixed(1)}%` : v.toFixed(3)
      ),
      textposition: "auto",
      hovertemplate: `<b>%{y}</b>: %{text}<extra>${p.title}</extra>`,
      showlegend: false,
    }));

    const layout: Record<string, unknown> = {
      grid: {
        rows: 2,
        columns: 3,
        pattern: "independent",
        roworder: "top to bottom",
      },
      margin: { t: 28, r: 20, b: 30, l: 130 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "#f8fafc",
      annotations: panels.map((p, idx) => ({
        text: `<b>${p.title}</b>`,
        font: { size: 11, color: "#334155" },
        xref: `x${idx + 1} domain`,
        yref: `y${idx + 1} domain`,
        x: 0.5,
        y: 1.18,
        showarrow: false,
      })),
    };

    panels.forEach((p, idx) => {
      const axNum = idx + 1;
      layout[`xaxis${axNum}`] = {
        range: p.range,
        zeroline: true,
        zerolinecolor: "#94a3b8",
        tickfont: { size: 10 },
      };
      layout[`yaxis${axNum}`] = {
        autorange: "reversed",
        showticklabels: idx % 3 === 0,
        tickfont: { size: 10 },
      };
    });

    return { traces, layout };
  }, [runs]);

  return (
    <section className="space-y-6">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-slate-200 flex flex-wrap items-center justify-between gap-2 bg-slate-50/60">
          <div>
            <h2 className="text-sm font-semibold text-slate-800">System Leaderboard</h2>
            <p className="text-xs text-slate-500">
              Separating <strong>Answerable-Day Ranking Quality</strong> (
              <code className="text-indigo-600">num_rel &gt; 0</code>) from{" "}
              <strong>Nil-Answer Quiet-Day Discipline</strong> (
              <code className="text-emerald-600">num_rel == 0</code>). Note:{" "}
              <code className="text-slate-700">
                Unconditional Prime = Trigger Rate × Active Prime
              </code>{" "}
              (under Micro rollup).
            </p>
          </div>
          <label className="inline-flex items-center gap-1.5 cursor-pointer select-none text-xs text-slate-600">
            <input
              type="checkbox"
              checked={showActivePrime}
              onChange={(e) => setShowActivePrime(e.target.checked)}
              className="rounded text-indigo-600"
            />
            <span>Show Trigger Rate &amp; Active Prime</span>
          </label>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-100/80 text-slate-600 border-b border-slate-200 font-semibold">
                <th className="py-2.5 px-3">Run</th>
                <th className="py-2.5 px-2">Type</th>
                <th
                  className="py-2.5 px-2 text-right bg-indigo-50/60 border-l border-slate-200"
                  title="Official NDCG' across all answerable question-days"
                >
                  ndcg&apos;
                </th>
                {showActivePrime && (
                  <>
                    <th
                      className="py-2.5 px-2 text-right bg-indigo-50/60"
                      title="Fraction of answerable question-days where the system returned >=1 document"
                    >
                      Trig %
                    </th>
                    <th
                      className="py-2.5 px-2 text-right bg-indigo-50/60"
                      title="Conditional NDCG' on answerable question-days where the system returned >=1 document"
                    >
                      Active ndcg&apos;
                    </th>
                  </>
                )}
                <th className="py-2.5 px-2 text-right bg-indigo-50/60">rbp&apos;(0.8)</th>
                <th className="py-2.5 px-2 text-right bg-indigo-50/60">ap&apos;</th>
                <th className="py-2.5 px-2 text-right bg-indigo-50/60">recip_rank&apos;</th>
                <th
                  className="py-2.5 px-2 text-right bg-emerald-50/60 border-l border-slate-200"
                  title="Fraction of nil-answer question-days where system returned 0 docs"
                >
                  abstention
                </th>
                <th
                  className="py-2.5 px-2 text-right bg-emerald-50/60"
                  title="Mean spurious docs per nil-answer question-day"
                >
                  noise
                </th>
                <th
                  className="py-2.5 px-2 text-right bg-amber-50/60 border-l border-slate-200"
                  title="Question ranking RBO(p=0.8)"
                >
                  rbo(0.8)
                </th>
                <th className="py-2.5 px-2 text-right border-l border-slate-200">num_ret</th>
                <th className="py-2.5 px-2 text-right">num_rel</th>
                <th className="py-2.5 px-2 text-right">num_rel_ret</th>
                <th className="py-2.5 px-2 text-right">unjudged</th>
                <th className="py-2.5 px-3 text-right">unjudged %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {runs.map((r, i) => {
                const m = r.metrics;
                const b = r.behavioral;
                const color = RUN_COLORS[i % RUN_COLORS.length];
                const activeNdcg = b.active_prime ? b.active_prime["ndcg'"] : null;
                const trigRate = b.trigger_rate_on_answerable;
                const modelsStr = (r.metadata.models || []).join(", ") || "—";

                return (
                  <tr key={r.runtag} className="hover:bg-slate-50">
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <span
                          className="w-2.5 h-2.5 rounded-full inline-block shrink-0"
                          style={{ background: color }}
                        />
                        <div>
                          <div className="font-semibold text-slate-900">{r.runtag}</div>
                          <div
                            className="text-[11px] text-slate-500 truncate max-w-xs"
                            title={r.metadata.description || ""}
                          >
                            {modelsStr}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-2">
                      <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[11px]">
                        {r.metadata.run_type}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono font-bold text-indigo-700 bg-indigo-50/30 border-l border-slate-200">
                      {fmtFloat(m["ndcg'"])}
                    </td>
                    {showActivePrime && (
                      <>
                        <td className="py-2.5 px-2 text-right font-mono text-slate-600 bg-indigo-50/30">
                          {fmtPct(trigRate, 2)}
                        </td>
                        <td className="py-2.5 px-2 text-right font-mono text-indigo-900 bg-indigo-50/30">
                          {fmtFloat(activeNdcg)}
                        </td>
                      </>
                    )}
                    <td className="py-2.5 px-2 text-right font-mono bg-indigo-50/30">
                      {fmtFloat(m["rbp'(p=0.8)"])}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono bg-indigo-50/30">
                      {fmtFloat(m["ap'"])}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono bg-indigo-50/30">
                      {fmtFloat(m["recip_rank'"])}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono font-semibold text-emerald-700 bg-emerald-50/30 border-l border-slate-200">
                      {fmtFloat(m.abstention)}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono text-emerald-900 bg-emerald-50/30">
                      {fmtFloat(m.noise)}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono bg-amber-50/30 border-l border-slate-200">
                      {fmtFloat(m["rbo(p=0.8)"])}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono border-l border-slate-200">
                      {fmtInt(m.num_ret)}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono">{fmtInt(m.num_rel)}</td>
                    <td className="py-2.5 px-2 text-right font-mono font-semibold">
                      {fmtInt(m.num_rel_ret)}
                    </td>
                    <td className="py-2.5 px-2 text-right font-mono text-slate-600">
                      {fmtInt(m.unjudged)}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-600">
                      {fmtPct(m.unjudged_rate, 1)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-5 bg-white rounded-xl shadow-sm border border-slate-200 p-4 flex flex-col">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-800">
                Silence vs. Effectiveness Trade-Off
              </h3>
              <p className="text-xs text-slate-500">
                Top-right = high effectiveness on event days + high silence on quiet days.
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs">
              <select
                value={paretoY}
                onChange={(e) => setParetoY(e.target.value)}
                className="border border-slate-300 rounded px-2 py-1 bg-white"
              >
                <option value="ndcg'">Y: ndcg&apos;</option>
                <option value="rbp'(p=0.8)">Y: rbp&apos;(p=0.8)</option>
                <option value="ap'">Y: ap&apos;</option>
                <option value="recip_rank'">Y: recip_rank&apos;</option>
                <option value="active_ndcg'">Y: Active ndcg&apos;</option>
              </select>
              <select
                value={paretoX}
                onChange={(e) =>
                  setParetoX(e.target.value as "abstention" | "noise")
                }
                className="border border-slate-300 rounded px-2 py-1 bg-white"
              >
                <option value="abstention">X: abstention</option>
                <option value="noise">X: noise</option>
              </select>
              <label className="inline-flex items-center gap-1 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showTopicsInPareto}
                  onChange={(e) => setShowTopicsInPareto(e.target.checked)}
                  className="rounded text-indigo-600"
                />
                <span>Show topics</span>
              </label>
            </div>
          </div>
          <PlotlyChart
            data={paretoSpec.traces}
            layout={paretoSpec.layout}
            className="w-full flex-1 min-h-[360px]"
          />
        </div>

        <div className="lg:col-span-7 bg-white rounded-xl shadow-sm border border-slate-200 p-4 flex flex-col">
          <div className="mb-2">
            <h3 className="text-sm font-semibold text-slate-800">
              5-State Behavioral Breakdown (Common 0-Baseline Panels)
            </h3>
            <p className="text-xs text-slate-500">
              Top row: Answerable question-days (
              <code className="text-indigo-600">num_rel &gt; 0</code>). Bottom row:
              Nil-answer question-days (
              <code className="text-emerald-600">num_rel == 0</code>). Each state has
              its own 0-baseline axis for direct comparison.
            </p>
          </div>
          <PlotlyChart
            data={behavioralSpec.traces}
            layout={behavioralSpec.layout}
            className="w-full flex-1 min-h-[360px]"
          />
        </div>
      </div>
    </section>
  );
}
