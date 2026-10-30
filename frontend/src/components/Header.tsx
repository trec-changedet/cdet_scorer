import type { ExplorerConfig, RelLevelName, RollupMode } from "../types/api";

export type TabName = "overview" | "topics" | "calendar";

interface HeaderProps {
  activeTab: TabName;
  onTabChange: (tab: TabName) => void;
  rollup: RollupMode;
  onRollupChange: (rollup: RollupMode) => void;
  minRelLevel: RelLevelName;
  maxDepth: number;
  onConfigChange: (minRel: RelLevelName, maxDepth: number) => void;
  config: ExplorerConfig | null;
  loading: boolean;
}

export function Header({
  activeTab,
  onTabChange,
  rollup,
  onRollupChange,
  minRelLevel,
  maxDepth,
  onConfigChange,
  config,
  loading,
}: HeaderProps) {
  const statusText = loading
    ? "Scoring..."
    : config
    ? `${config.runs.length} runs • ${config.num_topics} topics • ${
        config.has_corpus ? "Corpus DB connected" : "No Corpus DB"
      }`
    : "Loading...";

  const tabs: { id: TabName; label: string }[] = [
    { id: "overview", label: "1. Leaderboard & Trade-Offs" },
    { id: "topics", label: "2. Topic & Question Breakdown" },
    { id: "calendar", label: "3. Topic Event Calendar" },
  ];

  return (
    <header className="bg-slate-900 text-white shadow-md sticky top-0 z-30">
      <div className="max-w-[1600px] mx-auto px-4 py-2.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="bg-indigo-600 text-xs font-bold uppercase tracking-wider px-2.5 py-1 rounded">
            TREC CDET
          </span>
          <h1 className="text-base font-semibold tracking-tight">
            Change Detection Evaluation Explorer
          </h1>
          <span className="text-xs bg-slate-800 text-slate-300 px-2 py-0.5 rounded border border-slate-700">
            {statusText}
          </span>
        </div>

        <nav className="flex items-center gap-1 bg-slate-800 p-1 rounded-lg">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => onTabChange(t.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium ${
                activeTab === t.id
                  ? "bg-indigo-600 text-white"
                  : "text-slate-300 hover:text-white"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-1.5">
            <label className="text-slate-400 font-medium">Rollup:</label>
            <select
              value={rollup}
              onChange={(e) => onRollupChange(e.target.value as RollupMode)}
              className="bg-slate-800 border border-slate-700 text-white rounded px-2 py-1 focus:outline-none focus:border-indigo-500"
            >
              <option value="micro">Micro (all all all)</option>
              <option value="macro_topic">Macro by Topic</option>
              <option value="macro_question">Macro by Question</option>
              <option value="macro_day">Macro by Day</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <label className="text-slate-400 font-medium">Min Rel:</label>
            <select
              value={minRelLevel}
              onChange={(e) =>
                onConfigChange(e.target.value as RelLevelName, maxDepth)
              }
              className="bg-slate-800 border border-slate-700 text-white rounded px-2 py-1 focus:outline-none focus:border-indigo-500"
            >
              <option value="awareness">awareness (≥1)</option>
              <option value="assessment">assessment (≥5)</option>
              <option value="action">action (20)</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5">
            <label className="text-slate-400 font-medium">Max Depth:</label>
            <input
              type="number"
              min={1}
              max={1000}
              defaultValue={maxDepth}
              onBlur={(e) => {
                const parsed = parseInt(e.target.value, 10) || 100;
                if (parsed !== maxDepth) onConfigChange(minRelLevel, parsed);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const parsed =
                    parseInt((e.target as HTMLInputElement).value, 10) || 100;
                  if (parsed !== maxDepth) onConfigChange(minRelLevel, parsed);
                }
              }}
              className="w-16 bg-slate-800 border border-slate-700 text-white rounded px-2 py-1 text-right focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>
      </div>
    </header>
  );
}
