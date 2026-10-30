"""In-memory evaluation engine for the Change Detection Evaluation Explorer."""

from collections import defaultdict
from dataclasses import dataclass, field
import logging
from math import log2
from pathlib import Path
from typing import Any, Literal

from cdet_scorer.api_types import Hit, RunMetadata, TopicResults
from cdet_scorer.cli import EvalJig, evaluate_run, load_run_file, load_topics
from cdet_scorer.measures import (
    Numeric,
    Qrels,
    RelLevel,
    r_t,
    ranking_to_gains,
    str_to_gain,
)

log = logging.getLogger("explorer.engine")

RollupMode = Literal["micro", "macro_topic", "macro_question", "macro_day"]
BehavioralState = Literal[
    "event_hit",
    "zero_hit_trigger",
    "missed_event",
    "true_abstention",
    "false_alarm",
]

SUM_MEASURES = ("num_ret", "num_rel", "num_rel_ret", "unjudged")
PRIME_MEASURES = ("recip_rank'", "ap'", "ndcg'", "rbp'(p=0.8)")
NIL_MEASURES = ("abstention", "noise")
QRANK_MEASURES = ("rbo(p=0.8)",)
ALL_DOC_MEASURES = SUM_MEASURES + PRIME_MEASURES + NIL_MEASURES

REL_LEVEL_NAMES: dict[RelLevel, str] = {
    RelLevel.UNJUDGED: "unjudged",
    RelLevel.NOT_RELEVANT: "not_relevant",
    RelLevel.AWARENESS: "awareness",
    RelLevel.ASSESSMENT: "assessment",
    RelLevel.ACTION: "action",
}


def rel_level_to_name(rel: RelLevel | float) -> str:
    if rel >= RelLevel.ACTION:
        return "action"
    if rel >= RelLevel.ASSESSMENT:
        return "assessment"
    if rel >= RelLevel.AWARENESS:
        return "awareness"
    return "not_relevant"


def classify_cell_state(num_rel: int, num_ret: int, num_rel_ret: int) -> BehavioralState:
    if num_rel > 0:
        if num_ret == 0:
            return "missed_event"
        if num_rel_ret > 0:
            return "event_hit"
        return "zero_hit_trigger"
    else:
        return "true_abstention" if num_ret == 0 else "false_alarm"


def _mean(values: list[Numeric]) -> float | None:
    if not values:
        return None
    return float(sum(values)) / len(values)


@dataclass
class LoadedRun:
    path: Path
    metadata: RunMetadata
    topics: dict[str, TopicResults] = field(default_factory=dict)

    @property
    def runtag(self) -> str:
        return self.metadata.runtag


@dataclass
class ScoredRunCache:
    """Cached EvalJig and precomputed rollups for a single run at a specific (min_rel_level, max_depth)."""

    run: LoadedRun
    jig: EvalJig
    summary_by_mode: dict[RollupMode, dict[str, Any]]
    behavioral_counts: dict[str, Any]
    topic_summaries: dict[str, dict[str, Any]]
    question_summaries: dict[str, dict[str, dict[str, Any]]]
    day_summaries: dict[str, dict[str, dict[str, Any]]]


class ExplorerEngine:
    """Loads qrels, topics, and run files once, and computes/caches EvalJig evaluations in memory."""

    def __init__(
        self,
        qrels_path: str | Path,
        topics_path: str | Path,
        run_paths: list[str | Path],
        *,
        min_rel_level: RelLevel = RelLevel.AWARENESS,
        max_depth: int = 100,
    ):
        self.qrels_path = Path(qrels_path)
        self.topics_path = Path(topics_path)
        self.min_rel_level = min_rel_level
        self.max_depth = max_depth

        self.topics: dict[str, dict[str, Any]] = {}
        self.question_info: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._load_topics()

        self.qrels = Qrels(str(self.qrels_path), self.topics)
        self.doc_judgments_index: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._build_doc_judgments_index()

        self.runs: dict[str, LoadedRun] = {}
        self.run_order: list[str] = []
        for path in run_paths:
            self.load_run(path)

        self._cache: dict[tuple[str, RelLevel, int | None], ScoredRunCache] = {}
        self._ensure_scored()

    def _load_topics(self) -> None:
        self.topics = load_topics(self.topics_path)
        for tid, tobj in self.topics.items():
            for q in tobj.get("questions", []):
                self.question_info[tid][q["qid"]] = q

    def _build_doc_judgments_index(self) -> None:
        """Build an inverted lookup from doc_id -> list of {topic, day, qid, rel, gain} judgments."""
        for tid, days_map in self.qrels.qrels.items():
            for day, qids_map in days_map.items():
                for qid, docs_map in qids_map.items():
                    for doc_id, gain in docs_map.items():
                        self.doc_judgments_index[doc_id].append(
                            {
                                "topic": tid,
                                "day": day,
                                "qid": qid,
                                "question_text": self.get_question_text(tid, qid),
                                "rel": rel_level_to_name(gain),
                                "gain": float(gain),
                            }
                        )
        # Deduplicate non-relevant wildcard expansions where the same doc_id is not-relevant across all qids on a day
        for doc_id, entries in list(self.doc_judgments_index.items()):
            rel_entries = [e for e in entries if e["gain"] > 0]
            if rel_entries:
                # Keep positive judgments plus unique (topic, day) non-relevant summary if needed
                rel_topic_days = {(e["topic"], e["day"]) for e in rel_entries}
                other_nonrel: dict[tuple[str, str], dict[str, Any]] = {}
                for e in entries:
                    key = (e["topic"], e["day"])
                    if e["gain"] == 0 and key not in rel_topic_days and key not in other_nonrel:
                        other_nonrel[key] = {
                            "topic": e["topic"],
                            "day": e["day"],
                            "qid": "*",
                            "question_text": None,
                            "rel": "not_relevant",
                            "gain": 0.0,
                        }
                self.doc_judgments_index[doc_id] = rel_entries + list(other_nonrel.values())
            else:
                by_topic_day: dict[tuple[str, str], dict[str, Any]] = {}
                for e in entries:
                    key = (e["topic"], e["day"])
                    if key not in by_topic_day:
                        by_topic_day[key] = {
                            "topic": e["topic"],
                            "day": e["day"],
                            "qid": "*",
                            "question_text": None,
                            "rel": "not_relevant",
                            "gain": 0.0,
                        }
                self.doc_judgments_index[doc_id] = list(by_topic_day.values())

    def get_question_text(self, tid: str, qid: str) -> str | None:
        q = self.question_info.get(tid, {}).get(qid)
        return q.get("question") if q else None

    def load_run(self, run_path: str | Path) -> LoadedRun:
        path = Path(run_path)
        metadata, topic_results_list = load_run_file(path)
        topics_map = {tr.topic: tr for tr in topic_results_list}

        runtag = metadata.runtag
        # Disambiguate if two files share a runtag
        if runtag in self.runs and self.runs[runtag].path != path:
            runtag = f"{runtag}:{path.name}"
            metadata = metadata.model_copy(update={"runtag": runtag})

        loaded = LoadedRun(path=path, metadata=metadata, topics=topics_map)
        self.runs[runtag] = loaded
        if runtag not in self.run_order:
            self.run_order.append(runtag)
        return loaded

    def set_config(
        self,
        *,
        min_rel_level: str | RelLevel | None = None,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        if min_rel_level is not None:
            if isinstance(min_rel_level, str):
                self.min_rel_level = str_to_gain(min_rel_level.lower())
            else:
                self.min_rel_level = min_rel_level
        if max_depth is not None:
            self.max_depth = max_depth
        self._ensure_scored()
        return self.get_config()

    def get_config(self) -> dict[str, Any]:
        return {
            "min_rel_level": rel_level_to_name(self.min_rel_level),
            "min_rel_gain": float(self.min_rel_level),
            "max_depth": self.max_depth,
            "runs": self.run_order,
            "num_topics": len(self.qrels.qrels),
        }

    def _ensure_scored(self) -> None:
        for runtag in self.run_order:
            key = (runtag, self.min_rel_level, self.max_depth)
            if key not in self._cache:
                self._cache[key] = self._score_run(self.runs[runtag])

    def _get_scored(self, runtag: str) -> ScoredRunCache:
        self._ensure_scored()
        return self._cache[(runtag, self.min_rel_level, self.max_depth)]

    def _effective_qrels(
        self, jig: EvalJig, tid: str, day: str, qid: str
    ) -> dict[str, RelLevel]:
        raw = self.qrels.get_qid(tid, day, qid)
        if jig.min_rel_level > RelLevel.AWARENESS:
            return jig._level_qrels(raw)
        return raw

    def _score_run(self, run: LoadedRun) -> ScoredRunCache:
        jig = evaluate_run(
            self.qrels,
            run.metadata,
            list(run.topics.values()),
            min_rel_level=self.min_rel_level,
            max_depth=self.max_depth,
            logger=log,
        )
        return self._build_aggregations(run, jig)

    def _compute_behavioral_stats(
        self, cells: list[dict[str, Numeric | None]]
    ) -> dict[str, Any]:
        counts = {
            "total_points": len(cells),
            "answerable_points": 0,
            "nil_points": 0,
            "event_hit": 0,
            "zero_hit_trigger": 0,
            "missed_event": 0,
            "true_abstention": 0,
            "false_alarm": 0,
            "nil_noise_docs": 0,
            "nil_unjudged_docs": 0,
            "nil_judged_nonrel_docs": 0,
        }
        active_primes: dict[str, list[float]] = {m: [] for m in PRIME_MEASURES}

        for c in cells:
            num_rel = int(c.get("num_rel") or 0)
            num_ret = int(c.get("num_ret") or 0)
            num_rel_ret = int(c.get("num_rel_ret") or 0)
            unjudged = int(c.get("unjudged") or 0)
            state = classify_cell_state(num_rel, num_ret, num_rel_ret)
            counts[state] += 1
            if num_rel > 0:
                counts["answerable_points"] += 1
                if num_ret > 0:
                    for m in PRIME_MEASURES:
                        val = c.get(m)
                        if val is not None:
                            active_primes[m].append(float(val))
            else:
                counts["nil_points"] += 1
                if num_ret > 0:
                    counts["nil_noise_docs"] += num_ret
                    counts["nil_unjudged_docs"] += unjudged
                    counts["nil_judged_nonrel_docs"] += max(0, num_ret - unjudged)

        ans = counts["answerable_points"]
        nil = counts["nil_points"]
        noise_docs = counts["nil_noise_docs"]

        rates = {
            "event_hit_rate": counts["event_hit"] / ans if ans else None,
            "zero_hit_trigger_rate": counts["zero_hit_trigger"] / ans if ans else None,
            "missed_event_rate": counts["missed_event"] / ans if ans else None,
            "trigger_rate_on_answerable": (
                (counts["event_hit"] + counts["zero_hit_trigger"]) / ans if ans else None
            ),
            "true_abstention_rate": counts["true_abstention"] / nil if nil else None,
            "false_alarm_rate": counts["false_alarm"] / nil if nil else None,
            "unjudged_fraction_of_noise": (
                counts["nil_unjudged_docs"] / noise_docs if noise_docs else 0.0
            ),
            "active_prime": {m: _mean(vals) for m, vals in active_primes.items()},
        }
        return {**counts, **rates}

    def _build_aggregations(self, run: LoadedRun, jig: EvalJig) -> ScoredRunCache:
        topic_summaries: dict[str, dict[str, Any]] = {}
        question_summaries: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        day_summaries: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        all_cells: list[dict[str, Numeric | None]] = []

        mean_doc_labels = [
            str(op) for op in jig.doc_ops if op.print_mean and str(op) not in SUM_MEASURES
        ]
        qrank_labels = [str(op) for op in jig.qrank_ops if op.print_mean]

        for tid in sorted(jig.topics):
            t_eval = jig.topics[tid]
            topic_cells: list[dict[str, Numeric | None]] = []

            # Day rollups within topic (delegating directly to jig.get_day_means)
            for day in sorted(t_eval.days):
                d_eval = t_eval.days[day]
                day_cells = [dict(q_eval.scores) for q_eval in d_eval.questions.values()]
                topic_cells.extend(day_cells)
                all_cells.extend(day_cells)

                day_metrics: dict[str, Numeric | None] = dict(jig.get_day_means(tid, day))
                for m in mean_doc_labels:
                    day_metrics.setdefault(m, None)
                for m in qrank_labels:
                    day_metrics[m] = d_eval.get_qranking_score(m)

                day_summaries[tid][day] = {
                    "metrics": day_metrics,
                    "behavioral": self._compute_behavioral_stats(day_cells),
                }

            # Question rollups within topic (delegating directly to jig.get_qid_means)
            for qid in sorted(t_eval.all_qids):
                q_cells = [
                    t_eval.days[d].questions[qid].scores
                    for d in sorted(t_eval.days)
                    if qid in t_eval.days[d].questions
                ]
                q_metrics: dict[str, Numeric | None] = dict(jig.get_qid_means(tid, qid))
                for m in mean_doc_labels:
                    q_metrics.setdefault(m, None)

                question_summaries[tid][qid] = {
                    "metrics": q_metrics,
                    "behavioral": self._compute_behavioral_stats(q_cells),
                }

            # Topic rollup (delegating directly to jig.get_topic_means & jig.get_topic_qranking_means)
            t_metrics: dict[str, Numeric | None] = dict(jig.get_topic_means(tid))
            t_qrank = jig.get_topic_qranking_means(tid)
            t_metrics["qranking_num_days"] = int(t_qrank.get("num_days", 0))
            for m in mean_doc_labels:
                t_metrics.setdefault(m, None)
            for m in qrank_labels:
                t_metrics[m] = t_qrank.get(m)

            topic_summaries[tid] = {
                "metrics": t_metrics,
                "behavioral": self._compute_behavioral_stats(topic_cells),
            }

        # 1. Micro (official `all all all` + `all all qranking` directly from EvalJig)
        all_means = jig.get_all_means()
        all_qrank = jig.get_all_qranking_means()
        base_counts: dict[str, Numeric] = {
            "num_topics": int(all_means.get("num_topics", 0)),
            "num_days": int(all_means.get("num_days", 0)),
            "num_qs": int(all_means.get("num_qs", 0)),
            "qranking_num_topics": int(all_qrank.get("num_topics", 0)),
            "qranking_num_days": int(all_qrank.get("num_days", 0)),
        }
        for m in SUM_MEASURES:
            base_counts[m] = int(all_means.get(m, 0))

        micro_metrics: dict[str, Numeric | None] = dict(base_counts)
        for m in mean_doc_labels:
            micro_metrics[m] = all_means.get(m)
        for m in qrank_labels:
            micro_metrics[m] = all_qrank.get(m)

        # 2. Macro by Topic (mean of official `topic all all`)
        macro_topic_metrics: dict[str, Numeric | None] = dict(base_counts)
        for m in mean_doc_labels + qrank_labels:
            vals = [
                ts["metrics"][m]
                for ts in topic_summaries.values()
                if ts["metrics"].get(m) is not None
            ]
            macro_topic_metrics[m] = _mean(vals)

        # 3. Macro by Question (mean of official `topic all qid`)
        macro_question_metrics: dict[str, Numeric | None] = dict(base_counts)
        for m in mean_doc_labels:
            vals = [
                qs["metrics"][m]
                for tid_qs in question_summaries.values()
                for qs in tid_qs.values()
                if qs["metrics"].get(m) is not None
            ]
            macro_question_metrics[m] = _mean(vals)
        for m in qrank_labels:
            macro_question_metrics[m] = micro_metrics[m]

        # 4. Macro by Day (mean of official `topic day all`)
        macro_day_metrics: dict[str, Numeric | None] = dict(base_counts)
        for m in mean_doc_labels + qrank_labels:
            vals = [
                ds["metrics"][m]
                for tid_ds in day_summaries.values()
                for ds in tid_ds.values()
                if ds["metrics"].get(m) is not None
            ]
            macro_day_metrics[m] = _mean(vals)

        behavioral = self._compute_behavioral_stats(all_cells)
        summary_by_mode: dict[RollupMode, dict[str, Any]] = {
            "micro": micro_metrics,
            "macro_topic": macro_topic_metrics,
            "macro_question": macro_question_metrics,
            "macro_day": macro_day_metrics,
        }

        return ScoredRunCache(
            run=run,
            jig=jig,
            summary_by_mode=summary_by_mode,
            behavioral_counts=behavioral,
            topic_summaries=topic_summaries,
            question_summaries=question_summaries,
            day_summaries=day_summaries,
        )

    def get_runs_summary(self, rollup: RollupMode = "micro") -> dict[str, Any]:
        self._ensure_scored()
        runs_out = []
        for runtag in self.run_order:
            scored = self._get_scored(runtag)
            metrics = scored.summary_by_mode.get(rollup, scored.summary_by_mode["micro"])
            num_ret = int(metrics.get("num_ret") or 0)
            unjudged = int(metrics.get("unjudged") or 0)
            runs_out.append(
                {
                    "runtag": runtag,
                    "metadata": scored.run.metadata.model_dump(),
                    "metrics": {
                        **metrics,
                        "unjudged_rate": (unjudged / num_ret) if num_ret > 0 else 0.0,
                    },
                    "all_rollups": scored.summary_by_mode,
                    "behavioral": scored.behavioral_counts,
                }
            )
        return {
            "config": self.get_config(),
            "rollup": rollup,
            "runs": runs_out,
        }

    def get_topics_overview(self) -> dict[str, Any]:
        self._ensure_scored()
        topics_out = []
        for tid in sorted(self.qrels.qrels.keys()):
            tmeta = self.topics.get(tid, {})
            per_run: dict[str, Any] = {}
            num_days = 0
            num_qs = 0
            num_rel = 0
            for runtag in self.run_order:
                scored = self._get_scored(runtag)
                ts = scored.topic_summaries.get(tid)
                if ts:
                    per_run[runtag] = ts
                    num_days = int(ts["metrics"].get("num_days") or 0)
                    num_qs = int(ts["metrics"].get("num_qs") or 0)
                    num_rel = int(ts["metrics"].get("num_rel") or 0)
            topics_out.append(
                {
                    "tid": tid,
                    "label": tmeta.get("label", tid),
                    "narrative": tmeta.get("narrative", ""),
                    "num_days": num_days,
                    "num_qs": num_qs,
                    "num_rel": num_rel,
                    "runs": per_run,
                }
            )
        return {
            "config": self.get_config(),
            "topics": topics_out,
        }

    def get_topic_detail(self, tid: str) -> dict[str, Any]:
        if tid not in self.qrels.qrels:
            raise KeyError(f"Topic not found: {tid}")
        self._ensure_scored()
        tmeta = self.topics.get(tid, {})

        all_qids = sorted(
            self.qrels.topic_questions.get(tid, set()),
            key=lambda q: (int(q.split("_")[1]) if "_" in q and q.split("_")[1].isdigit() else 9999, q),
        )
        questions_out = []
        for qid in all_qids:
            q_runs: dict[str, Any] = {}
            num_rel = 0
            answerable_days = 0
            for runtag in self.run_order:
                scored = self._get_scored(runtag)
                qs = scored.question_summaries.get(tid, {}).get(qid)
                if qs:
                    q_runs[runtag] = qs
                    num_rel = int(qs["metrics"].get("num_rel") or 0)
                    answerable_days = int(qs["behavioral"].get("answerable_points") or 0)
            questions_out.append(
                {
                    "qid": qid,
                    "question": self.get_question_text(tid, qid) or qid,
                    "num_rel": num_rel,
                    "answerable_days": answerable_days,
                    "runs": q_runs,
                }
            )

        assessed_days = sorted(self.qrels.qrels[tid].keys())
        days_out = []
        for day in assessed_days:
            d_runs: dict[str, Any] = {}
            for runtag in self.run_order:
                scored = self._get_scored(runtag)
                ds = scored.day_summaries.get(tid, {}).get(day)
                if ds:
                    d_runs[runtag] = ds
            days_out.append(
                {
                    "day": day,
                    "qrel_qranking": self.qrels.get_qranking(tid, day),
                    "runs": d_runs,
                }
            )

        topic_runs = {
            runtag: self._get_scored(runtag).topic_summaries.get(tid)
            for runtag in self.run_order
        }

        return {
            "tid": tid,
            "label": tmeta.get("label", tid),
            "narrative": tmeta.get("narrative", ""),
            "runs": topic_runs,
            "questions": questions_out,
            "days": days_out,
        }

    def get_topic_calendar(
        self,
        tid: str,
        *,
        active_days_only: bool = False,
    ) -> dict[str, Any]:
        if tid not in self.qrels.qrels:
            raise KeyError(f"Topic not found: {tid}")
        self._ensure_scored()
        tmeta = self.topics.get(tid, {})

        all_qids = sorted(
            self.qrels.topic_questions.get(tid, set()),
            key=lambda q: (int(q.split("_")[1]) if "_" in q and q.split("_")[1].isdigit() else 9999, q),
        )
        assessed_days = sorted(self.qrels.qrels[tid].keys())

        if active_days_only:
            filtered_days = []
            for day in assessed_days:
                has_activity = False
                for runtag in self.run_order:
                    ds = self._get_scored(runtag).day_summaries.get(tid, {}).get(day)
                    if ds:
                        m = ds["metrics"]
                        if (m.get("num_rel") or 0) > 0 or (m.get("num_ret") or 0) > 0:
                            has_activity = True
                            break
                if has_activity:
                    filtered_days.append(day)
            assessed_days = filtered_days

        cells_by_qid_day: dict[str, dict[str, Any]] = defaultdict(dict)
        any_jig = self._get_scored(self.run_order[0]).jig
        for qid in all_qids:
            for day in assessed_days:
                qrels_cell = self._effective_qrels(any_jig, tid, day, qid)
                num_rel = sum(1 for g in qrels_cell.values() if g > RelLevel.NOT_RELEVANT)
                run_cells: dict[str, Any] = {}
                for runtag in self.run_order:
                    scored = self._get_scored(runtag)
                    q_eval = (
                        scored.jig.topics.get(tid, None)
                        and scored.jig.topics[tid].days.get(day, None)
                        and scored.jig.topics[tid].days[day].questions.get(qid, None)
                    )
                    scores = dict(q_eval.scores) if q_eval else {}
                    n_ret = int(scores.get("num_ret") or 0)
                    n_rel_ret = int(scores.get("num_rel_ret") or 0)
                    run_cells[runtag] = {
                        "state": classify_cell_state(num_rel, n_ret, n_rel_ret),
                        "scores": scores,
                    }
                cells_by_qid_day[qid][day] = {
                    "num_rel": num_rel,
                    "runs": run_cells,
                }

        day_strips = []
        for day in assessed_days:
            day_strips.append(
                {
                    "day": day,
                    "qrel_qranking": self.qrels.get_qranking(tid, day),
                    "runs": {
                        runtag: self._get_scored(runtag).day_summaries.get(tid, {}).get(day)
                        for runtag in self.run_order
                    },
                }
            )

        return {
            "tid": tid,
            "label": tmeta.get("label", tid),
            "narrative": tmeta.get("narrative", ""),
            "questions": [
                {"qid": qid, "question": self.get_question_text(tid, qid) or qid}
                for qid in all_qids
            ],
            "days": assessed_days,
            "day_summaries": day_strips,
            "matrix": cells_by_qid_day,
        }

    def get_cell_detail(self, tid: str, day: str, qid: str) -> dict[str, Any]:
        if tid not in self.qrels.qrels or day not in self.qrels.qrels[tid]:
            raise KeyError(f"Evaluation point not found: {tid} {day} {qid}")
        self._ensure_scored()

        tmeta = self.topics.get(tid, {})
        any_jig = self._get_scored(self.run_order[0]).jig
        raw_qrels = self.qrels.get_qid(tid, day, qid)
        eff_qrels = self._effective_qrels(any_jig, tid, day, qid)

        relevant_docs = []
        rel_counts_by_level = {"action": 0, "assessment": 0, "awareness": 0}
        for doc_id, raw_gain in sorted(
            raw_qrels.items(), key=lambda kv: (-float(kv[1]), kv[0])
        ):
            if raw_gain > RelLevel.NOT_RELEVANT:
                lvl = rel_level_to_name(raw_gain)
                if lvl in rel_counts_by_level:
                    rel_counts_by_level[lvl] += 1
                relevant_docs.append(
                    {
                        "doc_id": doc_id,
                        "raw_rel": lvl,
                        "raw_gain": float(raw_gain),
                        "counts_as_relevant": bool(eff_qrels.get(doc_id, 0.0) > 0),
                    }
                )

        all_gains = [g for g in eff_qrels.values()]
        num_rel = sum(1 for g in all_gains if g > RelLevel.NOT_RELEVANT)

        runs_detail: dict[str, Any] = {}
        for runtag in self.run_order:
            scored = self._get_scored(runtag)
            run = scored.run

            # Find raw QuestionResults for (tid, day, qid)
            raw_hits: list[Hit] = []
            question_rank: int | None = None
            if tid in run.topics and day in run.topics[tid].results:
                for qres in run.topics[tid].results[day]:
                    if qres.qid == qid:
                        question_rank = qres.question_rank
                        raw_hits = sorted(
                            qres.doc_ranking, key=lambda h: h.score, reverse=True
                        )
                        break

            sliced_hits = (
                raw_hits if self.max_depth is None else raw_hits[: self.max_depth]
            )
            doc_ids = [h.doc_id for h in sliced_hits]
            gains = ranking_to_gains(doc_ids, eff_qrels)
            rt_val = float(r_t(gains, all_gains)) if num_rel > 0 else None

            ranked_docs = []
            retrieved_set = set(doc_ids)
            for idx, (hit, gain) in enumerate(zip(sliced_hits, gains)):
                raw_doc_gain = raw_qrels.get(hit.doc_id)
                rel_status = (
                    "unjudged"
                    if raw_doc_gain is None
                    else rel_level_to_name(raw_doc_gain)
                )
                ranked_docs.append(
                    {
                        "rank": idx + 1,
                        "doc_id": hit.doc_id,
                        "score": hit.score,
                        "rel": rel_status,
                        "effective_gain": float(gain),
                        "dcg_contribution": float(gain) / log2(idx + 2),
                    }
                )

            missed_rel_docs = [
                d for d in relevant_docs if d["counts_as_relevant"] and d["doc_id"] not in retrieved_set
            ]

            q_eval = (
                scored.jig.topics.get(tid, None)
                and scored.jig.topics[tid].days.get(day, None)
                and scored.jig.topics[tid].days[day].questions.get(qid, None)
            )
            scores = dict(q_eval.scores) if q_eval else {}
            n_ret = int(scores.get("num_ret") or 0)
            n_rel_ret = int(scores.get("num_rel_ret") or 0)

            runs_detail[runtag] = {
                "state": classify_cell_state(num_rel, n_ret, n_rel_ret),
                "question_rank": question_rank,
                "scores": scores,
                "terminal_gain_rt": rt_val,
                "ranked_docs": ranked_docs,
                "missed_relevant_docs": missed_rel_docs,
            }

        return {
            "tid": tid,
            "topic_label": tmeta.get("label", tid),
            "topic_narrative": tmeta.get("narrative", ""),
            "day": day,
            "qid": qid,
            "question_text": self.get_question_text(tid, qid) or qid,
            "num_rel": num_rel,
            "rel_counts_by_level": rel_counts_by_level,
            "relevant_docs": relevant_docs,
            "qrel_qranking": self.qrels.get_qranking(tid, day),
            "runs": runs_detail,
        }

    def get_doc_judgments(self, doc_id: str) -> list[dict[str, Any]]:
        return self.doc_judgments_index.get(doc_id, [])
