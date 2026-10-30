import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { CalendarTab } from "./components/CalendarTab";
import { CellDrawer } from "./components/CellDrawer";
import { DocModal } from "./components/DocModal";
import { Header, type TabName } from "./components/Header";
import { OverviewTab } from "./components/OverviewTab";
import { TopicsTab } from "./components/TopicsTab";
import type {
  ExplorerConfig,
  RelLevelName,
  RollupMode,
  RunSummaryEntry,
  TopicOverviewItem,
} from "./types/api";

export function App() {
  const [activeTab, setActiveTab] = useState<TabName>("overview");
  const [rollup, setRollup] = useState<RollupMode>("micro");
  const [minRelLevel, setMinRelLevel] = useState<RelLevelName>("awareness");
  const [maxDepth, setMaxDepth] = useState<number>(100);

  const [config, setConfig] = useState<ExplorerConfig | null>(null);
  const [runs, setRuns] = useState<RunSummaryEntry[]>([]);
  const [topics, setTopics] = useState<TopicOverviewItem[]>([]);
  const [selectedTopicId, setSelectedTopicId] = useState<string | null>(null);
  const [selectedCell, setSelectedCell] = useState<{
    tid: string;
    day: string;
    qid: string;
  } | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const loadData = useCallback(async (currentRollup: RollupMode) => {
    setLoading(true);
    try {
      const [runsRes, topicsRes] = await Promise.all([
        api.getRunsSummary(currentRollup),
        api.getTopicsOverview(),
      ]);
      setConfig(runsRes.config);
      setMinRelLevel(runsRes.config.min_rel_level);
      setMaxDepth(runsRes.config.max_depth);
      setRuns(runsRes.runs);
      setTopics(topicsRes.topics);
      setSelectedTopicId((prev) => prev ?? topicsRes.topics[0]?.tid ?? null);
    } catch (err) {
      console.error("Error loading evaluation data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(rollup);
  }, [loadData, rollup]);

  const handleConfigChange = async (newRel: RelLevelName, newDepth: number) => {
    setLoading(true);
    try {
      await api.updateConfig(newRel, newDepth);
      await loadData(rollup);
    } catch (err) {
      console.error("Failed to update config:", err);
      setLoading(false);
    }
  };

  const handleJumpToCalendar = (tid: string) => {
    setSelectedTopicId(tid);
    setActiveTab("calendar");
  };

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <Header
        activeTab={activeTab}
        onTabChange={setActiveTab}
        rollup={rollup}
        onRollupChange={setRollup}
        minRelLevel={minRelLevel}
        maxDepth={maxDepth}
        onConfigChange={handleConfigChange}
        config={config}
        loading={loading}
      />

      <main className="max-w-[1600px] w-full mx-auto px-4 py-5 flex-1 space-y-6">
        {activeTab === "overview" && <OverviewTab runs={runs} topics={topics} />}

        {activeTab === "topics" && (
          <TopicsTab
            runs={config?.runs ?? []}
            topics={topics}
            selectedTopicId={selectedTopicId}
            onSelectTopic={setSelectedTopicId}
            onJumpToCalendar={handleJumpToCalendar}
          />
        )}

        {activeTab === "calendar" && (
          <CalendarTab
            runs={config?.runs ?? []}
            topics={topics}
            selectedTopicId={selectedTopicId}
            onSelectTopic={setSelectedTopicId}
            onSelectCell={(tid, day, qid) => setSelectedCell({ tid, day, qid })}
          />
        )}
      </main>

      <CellDrawer
        selectedCell={selectedCell}
        onClose={() => setSelectedCell(null)}
        onSelectDoc={(docId) => setSelectedDocId(docId)}
      />

      <DocModal docId={selectedDocId} onClose={() => setSelectedDocId(null)} />
    </div>
  );
}
