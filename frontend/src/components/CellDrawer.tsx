import { useEffect, useState } from "react";
import { api } from "../api";
import type { CellDetailResponse } from "../types/api";
import { fmtFloat, fmtInt } from "../utils/format";
import { RelevanceBadge, StateBadge } from "./Badges";

interface CellDrawerProps {
  selectedCell: { tid: string; day: string; qid: string } | null;
  onClose: () => void;
  onSelectDoc: (docId: string) => void;
}

export function CellDrawer({ selectedCell, onClose, onSelectDoc }: CellDrawerProps) {
  const [detail, setDetail] = useState<CellDetailResponse | null>(null);

  useEffect(() => {
    if (!selectedCell) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    api
      .getCellDetail(selectedCell.tid, selectedCell.day, selectedCell.qid)
      .then((res) => {
        if (!cancelled) setDetail(res);
      })
      .catch((err) => console.error("Failed to fetch cell detail:", err));
    return () => {
      cancelled = true;
    };
  }, [selectedCell]);

  if (!selectedCell) return null;

  return (
    <>
      <div
        onClick={onClose}
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-[1px] z-40"
      />
      <aside className="fixed top-0 right-0 h-full w-full max-w-5xl bg-white shadow-2xl border-l border-slate-200 z-50 flex flex-col">
        <div className="px-6 py-4 bg-slate-900 text-white flex items-start justify-between gap-4">
          {detail ? (
            <div>
              <div className="flex items-center gap-2 text-xs text-indigo-300 font-mono">
                <span>
                  {detail.tid} ({detail.topic_label})
                </span>
                <span>•</span>
                <span className="bg-slate-800 px-2 py-0.5 rounded text-white font-semibold">
                  {detail.day}
                </span>
                <span>•</span>
                <span className="bg-indigo-600 px-2 py-0.5 rounded text-white font-bold">
                  {detail.qid}
                </span>
              </div>
              <h3 className="text-sm font-semibold mt-1.5 text-white">
                {detail.question_text}
              </h3>
              <div className="text-xs text-slate-300 mt-1">
                Ground truth: <b>{detail.num_rel}</b> relevant docs (action:{" "}
                {detail.rel_counts_by_level.action}, assessment:{" "}
                {detail.rel_counts_by_level.assessment}, awareness:{" "}
                {detail.rel_counts_by_level.awareness})
              </div>
            </div>
          ) : (
            <div className="text-xs text-slate-300">Loading cell details...</div>
          )}
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-lg font-bold px-2 py-1"
          >
            ✕
          </button>
        </div>

        {detail && (
          <div className="p-6 overflow-y-auto flex-1 space-y-6 bg-slate-50">
            <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
              <div className="px-4 py-2.5 bg-slate-100 border-b border-slate-200 text-xs font-semibold text-slate-700">
                Evaluation Point Scores Across Runs
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-slate-200 text-slate-600 bg-slate-50">
                      <th className="py-2 px-3">Run</th>
                      <th className="py-2 px-2">Behavioral State</th>
                      <th className="py-2 px-2 text-right">Q-Rank</th>
                      <th className="py-2 px-2 text-right">num_ret</th>
                      <th className="py-2 px-2 text-right">num_rel_ret</th>
                      <th className="py-2 px-2 text-right">unjudged</th>
                      <th
                        className="py-2 px-2 text-right"
                        title="Terminal document gain r_t"
                      >
                        r_t
                      </th>
                      <th className="py-2 px-2 text-right">ndcg&apos;</th>
                      <th className="py-2 px-2 text-right">rbp&apos;(0.8)</th>
                      <th className="py-2 px-2 text-right">ap&apos;</th>
                      <th className="py-2 px-2 text-right">recip_rank&apos;</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {Object.entries(detail.runs).map(([runtag, r]) => {
                      const s = r.scores;
                      return (
                        <tr key={runtag} className="hover:bg-slate-50">
                          <td className="py-2 px-3 font-semibold text-slate-900">
                            {runtag}
                          </td>
                          <td className="py-2 px-2">
                            <StateBadge state={r.state} />
                          </td>
                          <td className="py-2 px-2 text-right font-mono">
                            {r.question_rank ?? "—"}
                          </td>
                          <td className="py-2 px-2 text-right font-mono">
                            {fmtInt(s.num_ret)}
                          </td>
                          <td className="py-2 px-2 text-right font-mono font-bold">
                            {fmtInt(s.num_rel_ret)}
                          </td>
                          <td className="py-2 px-2 text-right font-mono text-slate-500">
                            {fmtInt(s.unjudged)}
                          </td>
                          <td className="py-2 px-2 text-right font-mono text-indigo-700">
                            {fmtFloat(r.terminal_gain_rt)}
                          </td>
                          <td className="py-2 px-2 text-right font-mono font-bold">
                            {fmtFloat(s["ndcg'"])}
                          </td>
                          <td className="py-2 px-2 text-right font-mono">
                            {fmtFloat(s["rbp'(p=0.8)"])}
                          </td>
                          <td className="py-2 px-2 text-right font-mono">
                            {fmtFloat(s["ap'"])}
                          </td>
                          <td className="py-2 px-2 text-right font-mono">
                            {fmtFloat(s["recip_rank'"])}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {detail.relevant_docs.length > 0 && (
              <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                <div className="px-4 py-2.5 bg-slate-100 border-b border-slate-200 text-xs font-semibold text-slate-700 flex items-center justify-between">
                  <span>Ground-Truth Relevant Documents in Qrels</span>
                  <span className="text-[11px] font-normal text-slate-500">
                    Click any document ID to read full text
                  </span>
                </div>
                <div className="p-3 flex flex-wrap gap-2">
                  {detail.relevant_docs.map((d) => (
                    <button
                      key={d.doc_id}
                      onClick={() => onSelectDoc(d.doc_id)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-slate-300 bg-slate-50 hover:bg-indigo-50 hover:border-indigo-300 text-xs font-mono"
                    >
                      <span>{d.doc_id}</span>
                      <RelevanceBadge rel={d.raw_rel} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(detail.runs).map(([runtag, r]) => (
                <div
                  key={runtag}
                  className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden flex flex-col"
                >
                  <div className="px-3.5 py-2.5 bg-slate-100 border-b border-slate-200 flex items-center justify-between">
                    <span className="font-semibold text-xs text-slate-800">
                      {runtag}
                    </span>
                    <StateBadge state={r.state} />
                  </div>

                  <div className="overflow-y-auto max-h-[380px] flex-1">
                    {r.ranked_docs.length === 0 ? (
                      <div className="p-4 text-xs text-slate-400 italic">
                        No documents returned (num_ret = 0).
                      </div>
                    ) : (
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 text-[11px]">
                            <th className="py-1.5 px-2.5">#</th>
                            <th className="py-1.5 px-2">Document ID</th>
                            <th className="py-1.5 px-2 text-right">Score</th>
                            <th className="py-1.5 px-2">Judgment</th>
                            <th className="py-1.5 px-2.5 text-right">DCG</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {r.ranked_docs.map((d) => (
                            <tr
                              key={d.doc_id}
                              onClick={() => onSelectDoc(d.doc_id)}
                              className="hover:bg-indigo-50/50 cursor-pointer"
                            >
                              <td className="py-1.5 px-2.5 font-mono text-slate-500">
                                {d.rank}
                              </td>
                              <td
                                className="py-1.5 px-2 font-mono text-indigo-700 hover:underline truncate max-w-[180px]"
                                title={d.doc_id}
                              >
                                {d.doc_id}
                              </td>
                              <td className="py-1.5 px-2 text-right font-mono">
                                {d.score.toFixed(3)}
                              </td>
                              <td className="py-1.5 px-2">
                                <RelevanceBadge rel={d.rel} />
                              </td>
                              <td className="py-1.5 px-2.5 text-right font-mono">
                                {d.dcg_contribution.toFixed(3)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>

                  {r.missed_relevant_docs.length > 0 && (
                    <div className="px-3 py-2 bg-rose-50/70 border-t border-rose-200 text-[11px]">
                      <span className="font-semibold text-rose-800">
                        Missed Relevant ({r.missed_relevant_docs.length}):
                      </span>
                      <div className="flex flex-wrap gap-1.5 mt-1">
                        {r.missed_relevant_docs.map((m) => (
                          <button
                            key={m.doc_id}
                            onClick={() => onSelectDoc(m.doc_id)}
                            className="font-mono text-rose-700 hover:underline bg-white px-1.5 py-0.5 rounded border border-rose-200"
                          >
                            {m.doc_id} ({m.raw_rel})
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
