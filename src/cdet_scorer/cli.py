from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import logging
import json
import sys

from cdet_scorer.measures import (
    APPrime,
    Abstention,
    DocRankingMeasure,
    NDCGPrime,
    NumRel,
    NumRelRet,
    NumRetrieved,
    Numeric,
    Noise,
    Qrels,
    QuestionRankingMeasure,
    RBO,
    RBPPrime,
    RecipRankPrime,
    RelLevel,
    Unjudged,
    ranking_to_gains,
    str_to_gain,
)
from cdet_scorer.api_types import RunMetadata, TopicResults
from cdet_scorer.data import dates

@dataclass
class QuestionEval:
    qid: str
    scores: dict[str, Numeric] = field(default_factory=dict)

    def set_score(self, op_name: str, value: Numeric):
        self.scores[op_name] = value

    def get_score(self, op_name: str) -> Numeric | None:
        return self.scores.get(op_name)


@dataclass
class DayEval:
    day: str
    questions: dict[str, QuestionEval] = field(default_factory=dict)
    qranking_scores: dict[str, Numeric] = field(default_factory=dict)

    def get_or_create_question(self, qid: str) -> QuestionEval:
        if qid not in self.questions:
            self.questions[qid] = QuestionEval(qid=qid)
        return self.questions[qid]

    def set_qranking_score(self, op_name: str, value: Numeric):
        self.qranking_scores[op_name] = value

    def get_qranking_score(self, op_name: str) -> Numeric | None:
        return self.qranking_scores.get(op_name)

    def qid_scores_for(self, op_name: str) -> dict[str, Numeric]:
        """Returns {qid: score} for all questions evaluated on this day."""
        return {
            qid: q_eval.scores[op_name]
            for qid, q_eval in self.questions.items()
            if op_name in q_eval.scores
        }


@dataclass
class TopicEval:
    topic: str
    days: dict[str, DayEval] = field(default_factory=dict)

    def get_or_create_day(self, day: str) -> DayEval:
        if day not in self.days:
            self.days[day] = DayEval(day=day)
        return self.days[day]

    @property
    def all_qids(self) -> set[str]:
        """All unique QIDs that appeared across any day in this topic."""
        return {qid for day_eval in self.days.values() for qid in day_eval.questions}

    def day_scores_for(self, qid: str, op_name: str) -> dict[str, Numeric]:
        """Returns {day: score} for a specific QID across all days it appeared."""
        return {
            day: day_eval.questions[qid].scores[op_name]
            for day, day_eval in self.days.items()
            if qid in day_eval.questions and op_name in day_eval.questions[qid].scores
        }

    def qranking_scores_for(self, op_name: str) -> dict[str, Numeric]:
        """Returns {day: score} for question ranking across all days."""
        return {
            day: day_eval.qranking_scores[op_name]
            for day, day_eval in self.days.items()
            if op_name in day_eval.qranking_scores
        }

    def all_scores_for(self, op_name: str) -> dict[tuple[str, str], Numeric]:
        """Returns {(day, qid): score} across all days and questions in this topic."""
        return {
            (day, qid): q_eval.scores[op_name]
            for day, day_eval in self.days.items()
            for qid, q_eval in day_eval.questions.items()
            if op_name in q_eval.scores
        }


class EvalJig:
    def __init__(
        self,
        min_rel_level: RelLevel = RelLevel.AWARENESS,
        max_depth: int | None = 100,
        runtag: str | None = None,
    ):
        self.doc_ops: list[DocRankingMeasure] = []
        self.qrank_ops: list[QuestionRankingMeasure] = []
        self.topics: dict[str, TopicEval] = {}
        self.min_rel_level = min_rel_level
        self.max_depth = max_depth
        self.runtag = runtag
        self.log = logging.getLogger('eval')

    def get_or_create_topic(self, topic: str) -> TopicEval:
        if topic not in self.topics:
            self.topics[topic] = TopicEval(topic=topic)
        return self.topics[topic]

    def _level_qrels(self, qrels: dict[str, RelLevel]) -> dict[str, RelLevel]:
        return {
            docid: (rl if rl >= self.min_rel_level else RelLevel.NOT_RELEVANT)
            for docid, rl in qrels.items()
        }

    def add_op(self, meas: DocRankingMeasure | QuestionRankingMeasure):
        if isinstance(meas, QuestionRankingMeasure):
            self.qrank_ops.append(meas)
        elif isinstance(meas, DocRankingMeasure):
            self.doc_ops.append(meas)
        else:
            raise TypeError(f"Unknown measure type: {type(meas)}")

    def compute(
        self,
        topic: str,
        day: str,
        qid: str,
        doc_ranking: list[str],
        qrels: dict[str, RelLevel],
    ):
        topic_eval = self.get_or_create_topic(topic)
        day_eval = topic_eval.get_or_create_day(day)
        q_eval = day_eval.get_or_create_question(qid)

        ranking_slice = doc_ranking if self.max_depth is None else doc_ranking[: self.max_depth]
        if self.min_rel_level > RelLevel.AWARENESS:
            qrels = self._level_qrels(qrels)

        debug = self.log.isEnabledFor(logging.DEBUG)
        scored = []
        for op in self.doc_ops:
            score = op.compute(ranking_slice, qrels)
            # A measure returns None when it does not apply to this question-day
            # (e.g. a prime measure on a nil-answer day). Skip it so it is absent
            # from the output and excluded from means, rather than recorded as 0.
            if score is None:
                continue
            q_eval.set_score(str(op), score)
            if debug:
                scored.append(f'{op.label}={op.formatstr.format(score)}')
        if debug:
            # One greppable line per evaluation point showing how its scores
            # were derived: whether it was answerable (and the relevant count R)
            # or nil-answer, the system's depth-limited ranking, the gain of each
            # retrieved document, and the resulting value of every measure.
            num_rel = sum(1 for g in qrels.values() if g > RelLevel.NOT_RELEVANT)
            kind = f'answerable R={num_rel}' if num_rel else 'nil-answer'
            gains = [float(g) for g in ranking_to_gains(ranking_slice, qrels)]
            self.log.debug(
                f'{topic} {day} {qid} [{kind}] ranking={list(ranking_slice)} '
                f'gains={gains} -> {" ".join(scored)}'
            )

    def compute_qranking(
        self,
        topic: str,
        day: str,
        question_ranking: list[str],
        qrel_ranking: list[str],
    ):
        topic_eval = self.get_or_create_topic(topic)
        day_eval = topic_eval.get_or_create_day(day)
        debug = self.log.isEnabledFor(logging.DEBUG)
        scored = []
        for op in self.qrank_ops:
            score = op.compute(question_ranking, qrel_ranking)
            value = 0 if score is None else score
            day_eval.set_qranking_score(str(op), value)
            if debug:
                scored.append(f'{op.label}={op.formatstr.format(value)}')
        if debug:
            self.log.debug(
                f'{topic} {day} qranking system={question_ranking} '
                f'qrel={qrel_ranking} -> {" ".join(scored)}'
            )

    def zero_qranking(self, topic: str, day: str):
        topic_eval = self.get_or_create_topic(topic)
        day_eval = topic_eval.get_or_create_day(day)
        for op in self.qrank_ops:
            day_eval.set_qranking_score(str(op), 0)

    def print_scores_for(self, topic: str):
        if topic not in self.topics:
            return
        topic_eval = self.topics[topic]
        for day in sorted(topic_eval.days):
            day_eval = topic_eval.days[day]
            for qid in sorted(day_eval.questions):
                q_eval = day_eval.questions[qid]
                for op in self.doc_ops:
                    if not op.print_score:
                        continue
                    val = q_eval.get_score(str(op))
                    if val is not None:
                        print(op.pretty(topic, day, qid, val))

    def print_scores(self):
        for topic in sorted(self.topics):
            self.print_scores_for(topic)

    def get_day_means(self, topic: str, day: str) -> dict[str, Numeric]:
        """Compute official day means (`topic day all`) using each measure's reduce()."""
        if topic not in self.topics or day not in self.topics[topic].days:
            return {}
        day_eval = self.topics[topic].days[day]
        if not day_eval.questions:
            return {}
        result: dict[str, Numeric] = {"num_qs": len(day_eval.questions)}
        for op in self.doc_ops:
            if not op.print_mean:
                continue
            scores = day_eval.qid_scores_for(str(op))
            if scores:
                result[str(op)] = op.reduce(scores)
        return result

    def print_day_means(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for day in sorted(topic_eval.days):
                means = self.get_day_means(topic, day)
                if not means:
                    continue
                print(f"{topic} {day} all num_qs {means['num_qs']}")
                for op in self.doc_ops:
                    if str(op) in means:
                        print(op.pretty_day_mean(topic, day, means[str(op)]))

    def get_qid_means(self, topic: str, qid: str) -> dict[str, Numeric]:
        """Compute official question means (`topic all qid`) using each measure's reduce()."""
        if topic not in self.topics:
            return {}
        topic_eval = self.topics[topic]
        num_days = sum(
            1 for day_eval in topic_eval.days.values() if qid in day_eval.questions
        )
        if num_days == 0:
            return {}
        result: dict[str, Numeric] = {"num_days": num_days}
        for op in self.doc_ops:
            if not op.print_mean:
                continue
            scores = topic_eval.day_scores_for(qid, str(op))
            if scores:
                result[str(op)] = op.reduce(scores)
        return result

    def print_qid_means(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for qid in sorted(topic_eval.all_qids):
                means = self.get_qid_means(topic, qid)
                if not means:
                    continue
                print(f"{topic} all {qid} num_days {means['num_days']}")
                for op in self.doc_ops:
                    if str(op) in means:
                        print(op.pretty_qid_mean(topic, qid, means[str(op)]))

    def get_topic_means(self, topic: str) -> dict[str, Numeric]:
        """Compute official topic means (`topic all all`) using each measure's reduce()."""
        if topic not in self.topics:
            return {}
        topic_eval = self.topics[topic]
        result: dict[str, Numeric] = {
            "num_days": len(topic_eval.days),
            "num_qs": len(topic_eval.all_qids),
        }
        for op in self.doc_ops:
            if not op.print_mean:
                continue
            scores = topic_eval.all_scores_for(str(op))
            if scores:
                result[str(op)] = op.reduce(scores)
        return result

    def print_topic_means(self):
        for topic in sorted(self.topics):
            means = self.get_topic_means(topic)
            print(f"{topic} all all num_days {means['num_days']}")
            print(f"{topic} all all num_qs {means['num_qs']}")
            for op in self.doc_ops:
                if str(op) in means:
                    print(op.pretty_topic_mean(topic, means[str(op)]))

    def print_qranking_scores(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for day in sorted(topic_eval.days):
                day_eval = topic_eval.days[day]
                for op in self.qrank_ops:
                    if not op.print_score:
                        continue
                    val = day_eval.get_qranking_score(str(op))
                    if val is not None:
                        print(op.pretty(topic, day, val))

    def get_topic_qranking_means(self, topic: str) -> dict[str, Numeric]:
        """Compute official topic question-ranking means (`topic all qranking`)."""
        if topic not in self.topics:
            return {}
        topic_eval = self.topics[topic]
        num_days = sum(
            1 for day_eval in topic_eval.days.values() if day_eval.qranking_scores
        )
        result: dict[str, Numeric] = {"num_days": num_days}
        for op in self.qrank_ops:
            if not op.print_mean:
                continue
            scores = topic_eval.qranking_scores_for(str(op))
            if scores:
                result[str(op)] = op.reduce(scores)
        return result

    def print_qranking_means(self):
        for topic in sorted(self.topics):
            means = self.get_topic_qranking_means(topic)
            if means.get("num_days", 0) > 0:
                print(f"{topic} all qranking num_days {means['num_days']}")
            for op in self.qrank_ops:
                if str(op) in means:
                    print(op.pretty_topic_mean(topic, means[str(op)]))

    def all_scores_for(self, op_name: str) -> dict[tuple[str, str, str], Numeric]:
        """Returns {(topic, day, qid): score} across all topics, days, and questions."""
        return {
            (topic, day, qid): q_eval.scores[op_name]
            for topic, topic_eval in self.topics.items()
            for day, day_eval in topic_eval.days.items()
            for qid, q_eval in day_eval.questions.items()
            if op_name in q_eval.scores
        }

    def all_qranking_scores_for(self, op_name: str) -> dict[tuple[str, str], Numeric]:
        """Returns {(topic, day): score} across all topics and days."""
        return {
            (topic, day): day_eval.qranking_scores[op_name]
            for topic, topic_eval in self.topics.items()
            for day, day_eval in topic_eval.days.items()
            if op_name in day_eval.qranking_scores
        }

    def get_all_means(self) -> dict[str, Numeric]:
        """Compute official overall means (`all all all`) using each measure's reduce()."""
        if not self.topics:
            return {}
        result: dict[str, Numeric] = {
            "num_topics": len(self.topics),
            "num_days": len(
                {day for topic_eval in self.topics.values() for day in topic_eval.days}
            ),
            "num_qs": sum(len(topic_eval.all_qids) for topic_eval in self.topics.values()),
        }
        for op in self.doc_ops:
            if not op.print_mean:
                continue
            scores = self.all_scores_for(str(op))
            if scores:
                result[str(op)] = op.reduce(scores)
        return result

    def print_all_means(self):
        means = self.get_all_means()
        if not means:
            return
        if self.runtag is not None:
            print(f"all all all runtag {self.runtag}")
        print(f"all all all num_topics {means['num_topics']}")
        print(f"all all all num_days {means['num_days']}")
        print(f"all all all num_qs {means['num_qs']}")
        for op in self.doc_ops:
            if str(op) in means:
                print(op.pretty_all_mean(means[str(op)]))

    def get_all_qranking_means(self) -> dict[str, Numeric]:
        """Compute official overall question-ranking means (`all all qranking`)."""
        qrank_topics = [
            topic_eval
            for topic_eval in self.topics.values()
            if any(day_eval.qranking_scores for day_eval in topic_eval.days.values())
        ]
        if not qrank_topics:
            return {}
        result: dict[str, Numeric] = {
            "num_topics": len(qrank_topics),
            "num_days": len(
                {
                    day
                    for topic_eval in qrank_topics
                    for day, day_eval in topic_eval.days.items()
                    if day_eval.qranking_scores
                }
            ),
        }
        for op in self.qrank_ops:
            if not op.print_mean:
                continue
            scores = self.all_qranking_scores_for(str(op))
            if scores:
                result[str(op)] = op.reduce(scores)
        return result

    def print_all_qranking_means(self):
        means = self.get_all_qranking_means()
        if not means:
            return
        print(f"all all qranking num_topics {means['num_topics']}")
        print(f"all all qranking num_days {means['num_days']}")
        for op in self.qrank_ops:
            if str(op) in means:
                print(op.pretty_all_mean(means[str(op)]))

    print_qranking_all_means = print_all_qranking_means


def load_topics(topics_file: str | Path) -> dict[str, dict]:
    """Load topics JSONL file into a {tid: topic_dict} mapping."""
    topics: dict[str, dict] = {}
    with open(topics_file, encoding="utf-8") as fp:
        for line in fp:
            stripped = line.strip()
            if not stripped:
                continue
            tobj = json.loads(stripped)
            topics[tobj["tid"]] = tobj
    return topics


def load_run_file(input_file: str | Path) -> tuple[RunMetadata, list[TopicResults]]:
    """Parse a run JSONL file into its RunMetadata header and TopicResults records."""
    topic_results_list: list[TopicResults] = []
    with open(input_file, encoding="utf-8") as f:
        metadata_json = f.readline()
        metadata = RunMetadata.model_validate_json(metadata_json)
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            topic_results_list.append(TopicResults.model_validate_json(stripped))
    return metadata, topic_results_list


def build_default_jig(
    min_rel_level: RelLevel = RelLevel.AWARENESS,
    max_depth: int | None = 100,
    runtag: str | None = None,
) -> EvalJig:
    """Create an EvalJig configured with the standard official measures."""
    jig = EvalJig(min_rel_level=min_rel_level, max_depth=max_depth, runtag=runtag)
    jig.add_op(NumRetrieved())
    jig.add_op(NumRel())
    jig.add_op(NumRelRet())
    jig.add_op(Unjudged())
    jig.add_op(RecipRankPrime())
    jig.add_op(APPrime())
    jig.add_op(NDCGPrime())
    jig.add_op(RBPPrime(p=0.8))
    jig.add_op(Abstention())
    jig.add_op(Noise())
    jig.add_op(RBO(p=0.8))
    return jig


def evaluate_run(
    qrels: Qrels,
    metadata: RunMetadata,
    topic_results_iter: list[TopicResults],
    *,
    min_rel_level: RelLevel = RelLevel.AWARENESS,
    max_depth: int | None = 100,
    logger: logging.Logger | None = None,
) -> EvalJig:
    """Score a parsed run against Qrels using the canonical TREC Change Detection scoring loop."""
    log = logger or logging.getLogger("main")
    jig = build_default_jig(
        min_rel_level=min_rel_level,
        max_depth=max_depth,
        runtag=metadata.runtag,
    )

    for topic_results in topic_results_iter:
        tid = topic_results.topic
        if tid not in qrels.qrels:
            log.debug(f"{tid}: no judgments, skipping")
            continue
        log.info(f"Scoring topic {tid}")
        measured = defaultdict(set)

        for day in dates:
            if day not in topic_results.results:
                sys.exit(f"Error: run is missing day {day} for topic {tid}")
            # Check doc rankings of questions the system returned docs for
            # There may be zero relevant documents
            # Note that a valid run must have a value for every day in the
            # collection.
            q_results = topic_results.results[day]
            eval_qids = qrels.eval_qids(tid, day)
            for qres in q_results:
                if qres.qid in eval_qids:
                    measured[day].add(qres.qid)
                    doc_ranking = [
                        hit.doc_id
                        for hit in sorted(
                            qres.doc_ranking,
                            key=lambda x: x.score,
                            reverse=True,
                        )
                    ]
                    jig.compute(
                        tid,
                        day,
                        qres.qid,
                        doc_ranking,
                        qrels.get_qid(tid, day, qres.qid),
                    )
                else:
                    log.debug(
                        f"{tid} {day} {qres.qid}: returned by run but "
                        f"not an evaluation point, ignoring"
                    )
            # Check its question ranking, which may be empty
            if day in qrels.qranking[tid]:
                jig.zero_qranking(tid, day)
                question_ranking = [
                    q_res.qid
                    for q_res in sorted(
                        topic_results.results[day],
                        key=lambda q: q.question_rank,
                    )
                ]
                qrel_ranking = qrels.get_qranking(tid, day)
                jig.compute_qranking(tid, day, question_ranking, qrel_ranking)

            # Score evaluation points the run did not return as empty rankings.
            for qid in eval_qids:
                if qid in measured[day]:
                    continue
                measured[day].add(qid)
                jig.compute(
                    tid,
                    day,
                    qid,
                    [],
                    qrels.get_qid(tid, day, qid),
                )

    return jig


def main():
    import argparse
    import logging

    parser = argparse.ArgumentParser(description="Change detection scorer script")
    parser.add_argument(
        "-l",
        "--min_rel_level",
        type=str_to_gain,
        default=RelLevel.AWARENESS,
        help="Minimum relevance level to consider a document relevant. Default is AWARENESS.",
    )
    parser.add_argument(
        "-M",
        "--max_depth",
        type=int,
        default=100,
        help="Maximum depth to consider in the ranking. Default is 100.",
    )
    parser.add_argument(
        '-v',
        '--verbosity',
        action='count',
        default=0,
        help='Increase verbosity (-v for INFO, -vv for DEBUG)'
    )
    parser.add_argument("qrels_file", type=str, help="Path to the qrels file")
    parser.add_argument("topics_file", type=str, help="Path to the topics file")
    parser.add_argument("input_file", type=str, help="Path to the input file")
    args = parser.parse_args()

    log_levels = [
        logging.WARNING,
        logging.INFO,
        logging.DEBUG
    ]
    logging.basicConfig(
        level = log_levels[min(args.verbosity, len(log_levels) - 1)],
        format="%(name)s:%(levelname)s: %(message)s",
    )
    log = logging.getLogger('main')

    topics = load_topics(args.topics_file)
    qrels = Qrels(args.qrels_file, topics)
    metadata, topic_results_list = load_run_file(args.input_file)
    jig = evaluate_run(
        qrels,
        metadata,
        topic_results_list,
        min_rel_level=args.min_rel_level,
        max_depth=args.max_depth,
        logger=log,
    )

    jig.print_scores()
    jig.print_day_means()
    jig.print_qid_means()
    jig.print_topic_means()
    jig.print_qranking_scores()
    jig.print_qranking_means()
    jig.print_all_means()
    jig.print_all_qranking_means()


if __name__ == "__main__":
    from cdet_scorer.cli import main
    sys.exit(main())