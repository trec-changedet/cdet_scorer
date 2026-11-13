import { useEffect, useState } from "react";
import { api } from "../api";
import type { DocumentResponse } from "../types/api";
import { RelevanceBadge } from "./Badges";

interface DocModalProps {
  docId: string | null;
  onClose: () => void;
}

export function DocModal({ docId, onClose }: DocModalProps) {
  const [data, setData] = useState<DocumentResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!docId) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setError(null);
    api
      .getDocument(docId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [docId]);

  if (!docId) return null;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 bg-slate-950/60 backdrop-blur-[1px] z-50 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-2xl border border-slate-200 w-full max-w-4xl max-h-[88vh] flex flex-col overflow-hidden"
      >
        <div className="px-5 py-3.5 bg-slate-900 text-white flex items-center justify-between">
          <div>
            <span className="text-xs text-slate-400">Document</span>
            <h4 className="font-mono text-sm font-semibold mt-0.5">{docId}</h4>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-lg font-bold px-2"
          >
            ✕
          </button>
        </div>

        <div className="p-5 overflow-y-auto space-y-4 text-xs flex-1">
          {error ? (
            <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg text-rose-800">
              Could not load document: {error}
            </div>
          ) : !data ? (
            <div className="text-slate-500">Loading document...</div>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200">
                {data.document ? (
                  <>
                    <div>
                      <span className="text-slate-400 block">Day</span>
                      <span className="font-mono font-semibold">
                        {data.document.day}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-400 block">Timestamp</span>
                      <span className="font-mono">{data.document.date}</span>
                    </div>
                    <div className="truncate">
                      <span className="text-slate-400 block">Source URL</span>
                      <a
                        href={data.document.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-600 hover:underline"
                      >
                        {data.document.url}
                      </a>
                    </div>
                  </>
                ) : (
                  <div className="col-span-3 text-amber-700">
                    Document metadata not found in SQLite corpus (or no --corpus-db
                    provided).
                  </div>
                )}
              </div>

              <div>
                <h5 className="font-semibold text-slate-700 mb-1.5">
                  Qrels Judgments for this Document
                </h5>
                {data.judgments.length === 0 ? (
                  <div className="text-slate-400 italic">
                    Unjudged across all topics/days in qrels.
                  </div>
                ) : (
                  <div className="space-y-1">
                    {data.judgments.map((j, idx) => (
                      <div
                        key={`${j.topic}-${j.day}-${j.qid}-${idx}`}
                        className="flex items-center gap-2 bg-slate-50 px-2.5 py-1.5 rounded border border-slate-200"
                      >
                        <span className="font-mono font-semibold">{j.topic}</span>
                        <span className="font-mono text-slate-600">{j.day}</span>
                        <span className="font-mono font-bold text-indigo-700">
                          {j.qid}
                        </span>
                        <RelevanceBadge rel={j.rel} />
                        <span className="text-slate-600 truncate">
                          {j.question_text ?? "(All questions on day)"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <h5 className="font-semibold text-slate-700 mb-1.5">Document Text</h5>
                <pre className="bg-slate-900 text-slate-100 p-4 rounded-lg whitespace-pre-wrap font-sans text-xs leading-relaxed max-h-[420px] overflow-y-auto">
                  {data.document?.text ?? "(Document text unavailable)"}
                </pre>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
