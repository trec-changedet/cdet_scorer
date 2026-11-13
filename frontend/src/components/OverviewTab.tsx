import { useMemo, useState } from "react";
import type { RunSummaryEntry, TopicOverviewItem } from "../types/api";
import { fmtFloat, fmtInt, fmtPct, RUN_COLORS, RUN_SYMBOLS } from "../utils/format";
import { PlotlyChart } from "./PlotlyChart";

interface OverviewTabProps {
  runs: RunSummaryEntry[];
  topics: TopicOverviewItem[];
}

type TopicOverlayMode = "none" | "iqr" | "single_run";

interface IndexedRun {
  run: RunSummaryEntry;
  index: number; // 1-based (#1..#N)
  badge: string;
  color: string;
  symbol: string;
}

interface CoordGroup {
  key: string;
  x: number;
  y: number;
  members: IndexedRun[];
  isPareto: boolean;
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 0;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }
  return sorted[base];
}

function computePaddedRange(
  vals: number[],
  clampMin: number | null = 0,
  clampMax: number | null = 1.02
): [number, number] {
  if (vals.length === 0) return [0, 1];
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const span = Math.max(maxV - minV, 0.02);
  const pad = span * 0.22;
  let lo = minV - pad;
  let hi = maxV + pad;
  if (clampMin !== null) lo = Math.max(clampMin, lo);
  if (clampMax !== null) hi = Math.min(clampMax, hi);
  if (hi - lo < 0.02) {
    lo = Math.max(clampMin ?? -Infinity, minV - 0.015);
    hi = Math.min(clampMax ?? Infinity, maxV + 0.015);
  }
  return [lo, hi];
}

export function OverviewTab({ runs, topics }: OverviewTabProps) {
  const [showActivePrime, setShowActivePrime] = useState(true);
  const [paretoY, setParetoY] = useState("ndcg'");
  const [paretoX, setParetoX] = useState<"abstention" | "noise">("abstention");
  const [fullScale, setFullScale] = useState(false);
  const [showFrontier, setShowFrontier] = useState(true);
  const [topicOverlay, setTopicOverlay] = useState<TopicOverlayMode>("none");
  const [focusedRuntag, setFocusedRuntag] = useState<string>("");
  const [hiddenRuntags, setHiddenRuntags] = useState<Set<string>>(() => new Set());
  const [hoveredRuntag, setHoveredRuntag] = useState<string | null>(null);

  const indexedRuns = useMemo<IndexedRun[]>(
    () =>
      runs.map((run, i) => ({
        run,
        index: i + 1,
        badge: `#${i + 1}`,
        color: RUN_COLORS[i % RUN_COLORS.length],
        symbol: RUN_SYMBOLS[i % RUN_SYMBOLS.length],
      })),
    [runs]
  );

  const visibleRuns = useMemo(
    () => indexedRuns.filter((ir) => !hiddenRuntags.has(ir.run.runtag)),
    [indexedRuns, hiddenRuntags]
  );

  const effectiveFocusedRuntag = useMemo(() => {
    if (focusedRuntag && runs.some((r) => r.runtag === focusedRuntag)) {
      return focusedRuntag;
    }
    return visibleRuns[0]?.run.runtag ?? runs[0]?.runtag ?? "";
  }, [focusedRuntag, runs, visibleRuns]);

  const toggleRunVisibility = (runtag: string) => {
    setHiddenRuntags((prev) => {
      const next = new Set(prev);
      if (next.has(runtag)) {
        next.delete(runtag);
      } else {
        next.add(runtag);
      }
      return next;
    });
  };

  const { paretoSpec, coordGroups, collidedGroups } = useMemo(() => {
    const getRunY = (r: RunSummaryEntry): number | null => {
      const val =
        paretoY === "active_ndcg'"
          ? r.behavioral.active_prime["ndcg'"]
          : r.metrics[paretoY];
      return val !== null && val !== undefined ? Number(val) : null;
    };

    const getRunX = (r: RunSummaryEntry): number | null => {
      const val = r.metrics[paretoX];
      return val !== null && val !== undefined ? Number(val) : null;
    };

    const traces: Record<string, unknown>[] = [];
    const groupsMap = new Map<string, CoordGroup>();

    visibleRuns.forEach((ir) => {
      const xv = getRunX(ir.run);
      const yv = getRunY(ir.run);
      if (xv === null || yv === null) return;
      // Group runs that land on the exact same 4-decimal coordinate
      const key = `${xv.toFixed(4)}_${yv.toFixed(4)}`;
      const existing = groupsMap.get(key);
      if (existing) {
        existing.members.push(ir);
      } else {
        groupsMap.set(key, {
          key,
          x: xv,
          y: yv,
          members: [ir],
          isPareto: false,
        });
      }
    });

    const groups = Array.from(groupsMap.values());

    // Compute Pareto-optimal frontier
    // For abstention: maximize X and maximize Y
    // For noise: minimize X and maximize Y
    const sortedForPareto = [...groups].sort((a, b) =>
      paretoX === "abstention" ? b.x - a.x || b.y - a.y : a.x - b.x || b.y - a.y
    );
    const frontierGroups: CoordGroup[] = [];
    let bestY = -Infinity;
    for (const g of sortedForPareto) {
      if (g.y > bestY + 1e-9) {
        g.isPareto = true;
        frontierGroups.push(g);
        bestY = g.y;
      }
    }
    // Sort frontier left-to-right on X for clean line plotting
    frontierGroups.sort((a, b) => a.x - b.x);

    const xBoundsValues: number[] = groups.map((g) => g.x);
    const yBoundsValues: number[] = groups.map((g) => g.y);

    // 1. Optional Topic Overlay (Single Run Topics or Per-Group IQR Crosshairs)
    if (topicOverlay === "single_run" && effectiveFocusedRuntag) {
      const focusedIr =
        indexedRuns.find((ir) => ir.run.runtag === effectiveFocusedRuntag) ??
        visibleRuns[0];
      if (focusedIr) {
        const xs: number[] = [];
        const ys: number[] = [];
        const texts: string[] = [];

        topics.forEach((t) => {
          const tr = t.runs[focusedIr.run.runtag];
          if (!tr) return;
          const xv = tr.metrics[paretoX];
          const yv =
            paretoY === "active_ndcg'"
              ? tr.behavioral.active_prime["ndcg'"]
              : tr.metrics[paretoY];
          if (xv !== null && xv !== undefined && yv !== null && yv !== undefined) {
            xs.push(Number(xv));
            ys.push(Number(yv));
            texts.push(`${focusedIr.badge} ${focusedIr.run.runtag} • ${t.tid} (${t.label})`);
          }
        });

        xBoundsValues.push(...xs);
        yBoundsValues.push(...ys);

        traces.push({
          x: xs,
          y: ys,
          text: texts,
          mode: "markers",
          type: "scatter",
          name: `${focusedIr.badge} topics`,
          marker: {
            color: focusedIr.color,
            symbol: focusedIr.symbol,
            size: 7,
            opacity: 0.4,
          },
          hovertemplate: `%{text}<br>${paretoX}: %{x:.4f}<br>${paretoY}: %{y:.4f}<extra></extra>`,
          showlegend: false,
        });
      }
    } else if (topicOverlay === "iqr") {
      groups.forEach((g) => {
        const rep = g.members[0];
        const topicXs: number[] = [];
        const topicYs: number[] = [];
        topics.forEach((t) => {
          const tr = t.runs[rep.run.runtag];
          if (!tr) return;
          const xv = tr.metrics[paretoX];
          const yv =
            paretoY === "active_ndcg'"
              ? tr.behavioral.active_prime["ndcg'"]
              : tr.metrics[paretoY];
          if (xv !== null && xv !== undefined && yv !== null && yv !== undefined) {
            topicXs.push(Number(xv));
            topicYs.push(Number(yv));
          }
        });
        topicXs.sort((a, b) => a - b);
        topicYs.sort((a, b) => a - b);
        if (topicXs.length > 0 && topicYs.length > 0) {
          const xQ25 = quantile(topicXs, 0.25);
          const xQ75 = quantile(topicXs, 0.75);
          const yQ25 = quantile(topicYs, 0.25);
          const yQ75 = quantile(topicYs, 0.75);
          xBoundsValues.push(xQ25, xQ75);
          yBoundsValues.push(yQ25, yQ75);

          traces.push({
            x: [g.x],
            y: [g.y],
            type: "scatter",
            mode: "markers",
            marker: { size: 0, opacity: 0, color: rep.color },
            error_x: {
              type: "data",
              symmetric: false,
              array: [Math.max(0, xQ75 - g.x)],
              arrayminus: [Math.max(0, g.x - xQ25)],
              color: rep.color,
              thickness: 1.5,
              width: 4,
            },
            error_y: {
              type: "data",
              symmetric: false,
              array: [Math.max(0, yQ75 - g.y)],
              arrayminus: [Math.max(0, g.y - yQ25)],
              color: rep.color,
              thickness: 1.5,
              width: 4,
            },
            hoverinfo: "skip",
            showlegend: false,
          });
        }
      });
    }

    // 2. Optional Pareto Frontier Line
    if (showFrontier && frontierGroups.length >= 2) {
      traces.push({
        x: frontierGroups.map((g) => g.x),
        y: frontierGroups.map((g) => g.y),
        mode: "lines",
        type: "scatter",
        name: "Pareto Frontier",
        line: { color: "#6366f1", width: 2, dash: "dot" },
        hoverinfo: "skip",
        showlegend: false,
      });
    }

    // Compute axis ranges first so we can do smart normalized label repulsion
    const xRange: [number, number] | undefined = fullScale
      ? paretoX === "abstention"
        ? [0, 1.04]
        : undefined
      : computePaddedRange(
          xBoundsValues,
          0,
          paretoX === "abstention" ? 1.02 : null
        );
    const yRange: [number, number] = fullScale
      ? [0, 1.05]
      : computePaddedRange(yBoundsValues, 0, 1.02);

    const xSpan = xRange ? Math.max(xRange[1] - xRange[0], 1e-6) : 1;
    const xMin = xRange ? xRange[0] : Math.min(...xBoundsValues, 0);
    const ySpan = Math.max(yRange[1] - yRange[0], 1e-6);
    const yMin = yRange[0];

    // 3. Plot each distinct coordinate group with smart non-overlapping label positions
    groups.forEach((g, gIdx) => {
      const primary = g.members[0];
      const isMulti = g.members.length > 1;
      const isHovered =
        hoveredRuntag !== null &&
        g.members.some((m) => m.run.runtag === hoveredRuntag);

      // Compact label: show runtag only when <= 2 total runs, otherwise use #badges
      const shortBadges = g.members.map((m) => m.badge).join(", ");
      const pointLabel =
        visibleRuns.length <= 2 && !isMulti
          ? `${primary.badge} ${primary.run.runtag}`
          : isMulti
          ? `${shortBadges} (×${g.members.length})`
          : primary.badge;

      // Determine smart textposition by repelling from nearest neighbor in normalized plot coords
      const nx = (g.x - xMin) / xSpan;
      const ny = (g.y - yMin) / ySpan;

      let nearestIdx = -1;
      let nearestDist2 = Infinity;
      groups.forEach((other, oIdx) => {
        if (oIdx === gIdx) return;
        const onx = (other.x - xMin) / xSpan;
        const ony = (other.y - yMin) / ySpan;
        const d2 = (nx - onx) ** 2 + (ny - ony) ** 2;
        if (d2 < nearestDist2) {
          nearestDist2 = d2;
          nearestIdx = oIdx;
        }
      });

      let textPosition = ny > 0.82 ? "bottom center" : "top center";
      if (nearestIdx !== -1 && nearestDist2 < 0.08) {
        const other = groups[nearestIdx];
        const dx = nx - (other.x - xMin) / xSpan;
        const dy = ny - (other.y - yMin) / ySpan;
        if (dy >= 0) {
          textPosition = dx <= 0 ? "top left" : "top right";
          if (ny > 0.85) textPosition = dx <= 0 ? "middle left" : "middle right";
        } else {
          textPosition = dx <= 0 ? "bottom left" : "bottom right";
          if (ny < 0.15) textPosition = dx <= 0 ? "middle left" : "middle right";
        }
      }
      // Keep labels away from horizontal edges
      if (nx < 0.14 && textPosition.includes("left")) {
        textPosition = ny > 0.5 ? "bottom right" : "top right";
      } else if (nx > 0.86 && textPosition.includes("right")) {
        textPosition = ny > 0.5 ? "bottom left" : "top left";
      }

      const hoverLines = g.members.map(
        (m) => `<b>${m.badge} ${m.run.runtag}</b> (${m.run.metadata.run_type})`
      );
      if (isMulti) {
        hoverLines.unshift(
          `<b>${g.members.length} runs share this exact point:</b>`
        );
      }
      if (g.isPareto) {
        hoverLines.push(`<span style="color:#4f46e5">★ On Pareto frontier</span>`);
      }

      // If multiple runs share this exact point, draw an outer halo ring first
      if (isMulti) {
        traces.push({
          x: [g.x],
          y: [g.y],
          mode: "markers",
          type: "scatter",
          marker: {
            color: "rgba(99, 102, 241, 0.16)",
            size: isHovered ? 28 : 24,
            symbol: "circle",
            line: {
              color: isHovered ? "#1e1b4b" : "#4f46e5",
              width: isHovered ? 2.5 : 2,
            },
          },
          hoverinfo: "skip",
          showlegend: false,
        });
      }

      traces.push({
        x: [g.x],
        y: [g.y],
        text: [pointLabel],
        mode: "markers+text",
        textposition: textPosition,
        textfont: {
          size: isHovered ? 12 : 11,
          color: isHovered ? "#0f172a" : "#1e293b",
          family: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        },
        cliponaxis: false,
        type: "scatter",
        name: pointLabel,
        marker: {
          color: primary.color,
          symbol: isMulti ? "circle" : primary.symbol,
          size: isHovered ? 17 : isMulti ? 14 : 13,
          line: {
            color: isHovered ? "#0f172a" : "#ffffff",
            width: isHovered ? 2.5 : 2,
          },
        },
        hovertemplate: `${hoverLines.join("<br>")}<br>${paretoX}: <b>%{x:.4f}</b><br>${paretoY}: <b>%{y:.4f}</b><extra></extra>`,
        showlegend: false,
      });
    });

    const layout: Record<string, unknown> = {
      margin: { t: 24, r: 28, b: 48, l: 58 },
      xaxis: {
        title:
          paretoX === "abstention"
            ? "Abstention Rate (Quiet-Day Specificity →)"
            : "Mean Spurious Docs / Quiet Day (← Lower Noise Better)",
        range: xRange,
        zeroline: false,
      },
      yaxis: {
        title: paretoY,
        range: yRange,
        zeroline: false,
      },
      showlegend: false,
      paper_bgcolor: "transparent",
      plot_bgcolor: "#f8fafc",
    };

    return {
      paretoSpec: { traces, layout },
      coordGroups: groups,
      collidedGroups: groups.filter((g) => g.members.length > 1),
    };
  }, [
    visibleRuns,
    indexedRuns,
    topics,
    paretoX,
    paretoY,
    fullScale,
    showFrontier,
    topicOverlay,
    effectiveFocusedRuntag,
    hoveredRuntag,
  ]);

  const behavioralSpec = useMemo(() => {
    const activeList = visibleRuns.length > 0 ? visibleRuns : indexedRuns;
    const runNames = activeList.map((ir) => `${ir.badge} ${ir.run.runtag}`);
    const colors = activeList.map((ir) => ir.color);

    const panels = [
      {
        title: "Event Hit Rate (num_rel_ret > 0)",
        vals: activeList.map((ir) => (ir.run.behavioral.event_hit_rate ?? 0) * 100),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "Zero-Hit Trigger Rate",
        vals: activeList.map(
          (ir) => (ir.run.behavioral.zero_hit_trigger_rate ?? 0) * 100
        ),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "Missed Event Rate (Silent)",
        vals: activeList.map(
          (ir) => (ir.run.behavioral.missed_event_rate ?? 0) * 100
        ),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "False Alarm Rate (1 − abstention)",
        vals: activeList.map(
          (ir) => (ir.run.behavioral.false_alarm_rate ?? 0) * 100
        ),
        suffix: "%",
        range: [0, 100] as [number, number] | null,
      },
      {
        title: "Mean Noise (Docs / Nil Q-Day)",
        vals: activeList.map((ir) => Number(ir.run.metrics.noise ?? 0)),
        suffix: "",
        range: null,
      },
      {
        title: "Unjudged % of Noise",
        vals: activeList.map(
          (ir) => (ir.run.behavioral.unjudged_fraction_of_noise ?? 0) * 100
        ),
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
      margin: { t: 28, r: 20, b: 30, l: 155 },
      paper_bgcolor: "transparent",
      plot_bgcolor: "#f8fafc",
      annotations: panels.map((p, idx) => ({
        text: `<b>${p.title}</b>`,
        font: { size: 11, color: "#334155" },
        xref: `x${idx + 1} domain`,
        yref: `y${idx + 1} domain`,
        x: 0.5,
        y: 1.12,
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
  }, [visibleRuns, indexedRuns]);

  const chartMinHeight = Math.max(380, visibleRuns.length * 32 + 120);

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
              <code className="text-emerald-600">num_rel == 0</code>). Toggle checkboxes
              or hover a row to filter and highlight runs in the charts below.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600">
            {hiddenRuntags.size > 0 && (
              <button
                type="button"
                onClick={() => setHiddenRuntags(new Set())}
                className="text-indigo-600 hover:text-indigo-800 font-medium underline"
              >
                Show all {runs.length} runs ({visibleRuns.length} plotted)
              </button>
            )}
            <label className="inline-flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showActivePrime}
                onChange={(e) => setShowActivePrime(e.target.checked)}
                className="rounded text-indigo-600"
              />
              <span>Show Trigger Rate &amp; Active Prime</span>
            </label>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-100/80 text-slate-600 border-b border-slate-200 font-semibold">
                <th className="py-2.5 pl-3 pr-1 w-8 text-center" title="Plot run in charts below">
                  <input
                    type="checkbox"
                    checked={hiddenRuntags.size === 0}
                    onChange={() => {
                      if (hiddenRuntags.size === 0) {
                        // Keep at least first 2 visible if user unchecks all
                        setHiddenRuntags(
                          new Set(runs.slice(2).map((r) => r.runtag))
                        );
                      } else {
                        setHiddenRuntags(new Set());
                      }
                    }}
                    className="rounded text-indigo-600"
                    title="Toggle all runs"
                  />
                </th>
                <th className="py-2.5 px-2">Run</th>
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
              {indexedRuns.map((ir) => {
                const { run: r, badge, color } = ir;
                const m = r.metrics;
                const b = r.behavioral;
                const isVisible = !hiddenRuntags.has(r.runtag);
                const isHovered = hoveredRuntag === r.runtag;
                const activeNdcg = b.active_prime ? b.active_prime["ndcg'"] : null;
                const trigRate = b.trigger_rate_on_answerable;
                const modelsStr = (r.metadata.models || []).join(", ") || "—";

                return (
                  <tr
                    key={r.runtag}
                    onMouseEnter={() => setHoveredRuntag(r.runtag)}
                    onMouseLeave={() => setHoveredRuntag(null)}
                    className={`transition-colors ${
                      !isVisible
                        ? "opacity-45 bg-slate-50/40"
                        : isHovered
                        ? "bg-indigo-50/60"
                        : "hover:bg-slate-50"
                    }`}
                  >
                    <td className="py-2.5 pl-3 pr-1 text-center">
                      <input
                        type="checkbox"
                        checked={isVisible}
                        onChange={() => toggleRunVisibility(r.runtag)}
                        className="rounded text-indigo-600 cursor-pointer"
                        title={`Show/hide ${r.runtag} in plots`}
                      />
                    </td>
                    <td className="py-2.5 px-2">
                      <div className="flex items-center gap-2">
                        <span
                          className="px-1.5 py-0.5 rounded font-mono text-[11px] font-bold text-white shrink-0 shadow-xs"
                          style={{ background: color }}
                          title={`Plot marker ${badge}`}
                        >
                          {badge}
                        </span>
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
          <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
            <div>
              <h3 className="text-sm font-semibold text-slate-800">
                Silence vs. Effectiveness Trade-Off
              </h3>
              <p className="text-xs text-slate-500">
                {paretoX === "abstention"
                  ? "Top-right = high effectiveness on event days + high silence on quiet days."
                  : "Top-left = high effectiveness on event days + low noise on quiet days."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-xs">
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
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 mb-2 pb-2 border-b border-slate-100 text-xs text-slate-600">
            <label className="inline-flex items-center gap-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showFrontier}
                onChange={(e) => setShowFrontier(e.target.checked)}
                className="rounded text-indigo-600"
              />
              <span>Pareto frontier</span>
            </label>
            <label className="inline-flex items-center gap-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={fullScale}
                onChange={(e) => setFullScale(e.target.checked)}
                className="rounded text-indigo-600"
              />
              <span>Full [0, 1] scale</span>
            </label>
            <div className="inline-flex items-center gap-1">
              <span className="text-slate-500">Topics:</span>
              <select
                value={topicOverlay}
                onChange={(e) =>
                  setTopicOverlay(e.target.value as TopicOverlayMode)
                }
                className="border border-slate-300 rounded px-1.5 py-0.5 bg-white text-xs"
              >
                <option value="none">Off</option>
                <option value="iqr">IQR crosshairs (25–75%)</option>
                <option value="single_run">Single run dots</option>
              </select>
              {topicOverlay === "single_run" && (
                <select
                  value={effectiveFocusedRuntag}
                  onChange={(e) => setFocusedRuntag(e.target.value)}
                  className="border border-slate-300 rounded px-1.5 py-0.5 bg-white text-xs max-w-[140px]"
                >
                  {indexedRuns.map((ir) => (
                    <option key={ir.run.runtag} value={ir.run.runtag}>
                      {ir.badge} {ir.run.runtag}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </div>

          <PlotlyChart
            data={paretoSpec.traces}
            layout={paretoSpec.layout}
            className="w-full flex-1 min-h-[340px]"
          />

          {/* Compact Run & Shared-Coordinate Key */}
          <div className="mt-2 pt-2 border-t border-slate-100 space-y-1.5 text-[11px]">
            {collidedGroups.length > 0 && (
              <div className="bg-indigo-50/70 border border-indigo-200/80 rounded-lg px-2.5 py-1.5 text-slate-700">
                <div className="font-semibold text-indigo-900 mb-0.5">
                  Shared Coordinates ({visibleRuns.length} runs → {coordGroups.length} distinct{" "}
                  {coordGroups.length === 1 ? "point" : "points"}):
                </div>
                <div className="space-y-0.5">
                  {collidedGroups.map((g) => (
                    <div key={g.key} className="flex flex-wrap items-center gap-1">
                      <span className="font-mono font-bold text-indigo-700">
                        ({g.x.toFixed(4)}, {g.y.toFixed(4)}):
                      </span>
                      {g.members.map((m) => (
                        <button
                          key={m.run.runtag}
                          type="button"
                          onMouseEnter={() => setHoveredRuntag(m.run.runtag)}
                          onMouseLeave={() => setHoveredRuntag(null)}
                          onClick={() => {
                            setFocusedRuntag(m.run.runtag);
                            if (topicOverlay === "none") setTopicOverlay("single_run");
                          }}
                          className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded bg-white border border-slate-200 font-mono text-[10px] hover:border-indigo-400"
                        >
                          <span
                            className="w-2 h-2 rounded-full inline-block"
                            style={{ background: m.color }}
                          />
                          <strong>{m.badge}</strong> {m.run.runtag}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-1.5">
              {visibleRuns.map((ir) => (
                <button
                  key={ir.run.runtag}
                  type="button"
                  onMouseEnter={() => setHoveredRuntag(ir.run.runtag)}
                  onMouseLeave={() => setHoveredRuntag(null)}
                  onClick={() => {
                    setFocusedRuntag(ir.run.runtag);
                    if (topicOverlay === "none") setTopicOverlay("single_run");
                  }}
                  className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[11px] transition-colors ${
                    hoveredRuntag === ir.run.runtag
                      ? "border-slate-800 bg-slate-100 font-semibold"
                      : "border-slate-200 bg-slate-50/70 hover:bg-slate-100 text-slate-700"
                  }`}
                  title="Hover to highlight on plot; click to show this run's topic dots"
                >
                  <span
                    className="px-1 rounded font-mono text-[10px] font-bold text-white"
                    style={{ background: ir.color }}
                  >
                    {ir.badge}
                  </span>
                  <span className="truncate max-w-[130px]">{ir.run.runtag}</span>
                </button>
              ))}
            </div>
          </div>
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
          <div style={{ minHeight: `${chartMinHeight}px` }} className="w-full flex-1 flex">
            <PlotlyChart
              data={behavioralSpec.traces}
              layout={behavioralSpec.layout}
              className="w-full flex-1"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
