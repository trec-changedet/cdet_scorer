from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import logging
import json
import sys

from cdet_scorer.measures import (
    DocRankingMeasure,
    NDCGPrime,
    NumRel,
    NumRelRet,
    NumRetrieved,
    Numeric,
    Qrels,
    QuestionRankingMeasure,
    RBO,
    RBPPrime,
    RecipRankPrime,
    RelLevel,
    Unjudged,
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
    def __init__(self, min_rel_level: RelLevel = RelLevel.AWARENESS, max_depth: int | None = 100):
        self.doc_ops: list[DocRankingMeasure] = []
        self.qrank_ops: list[QuestionRankingMeasure] = []
        self.topics: dict[str, TopicEval] = {}
        self.min_rel_level = min_rel_level
        self.max_depth = max_depth
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

        for op in self.doc_ops:
            self.log.debug(f'{topic}/{day}/{qid} compute {op.label} ranking: {list(ranking_slice)}, qrels: {json.dumps(qrels)}')
            score = op.compute(ranking_slice, qrels)
            q_eval.set_score(str(op), 0 if score is None else score)

    def compute_qranking(
        self,
        topic: str,
        day: str,
        question_ranking: list[str],
        qrel_ranking: list[str],
    ):
        topic_eval = self.get_or_create_topic(topic)
        day_eval = topic_eval.get_or_create_day(day)
        for op in self.qrank_ops:
            score = op.compute(question_ranking, qrel_ranking)
            day_eval.set_qranking_score(str(op), 0 if score is None else score)

    def zero(self, topic: str, day: str, qid: str):
        topic_eval = self.get_or_create_topic(topic)
        day_eval = topic_eval.get_or_create_day(day)
        q_eval = day_eval.get_or_create_question(qid)
        for op in self.doc_ops:
            q_eval.set_score(str(op), 0)

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

    def print_day_means(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for day in sorted(topic_eval.days):
                day_eval = topic_eval.days[day]
                for op in self.doc_ops:
                    if not op.print_mean:
                        continue
                    scores = day_eval.qid_scores_for(str(op))
                    if scores:
                        mean_val = op.reduce(scores)
                        print(op.pretty_day_mean(topic, day, mean_val))

    def print_qid_means(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for qid in sorted(topic_eval.all_qids):
                for op in self.doc_ops:
                    if not op.print_mean:
                        continue
                    scores = topic_eval.day_scores_for(qid, str(op))
                    if scores:
                        mean_val = op.reduce(scores)
                        print(op.pretty_qid_mean(topic, qid, mean_val))

    def print_topic_means(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for op in self.doc_ops:
                if not op.print_mean:
                    continue
                scores = topic_eval.all_scores_for(str(op))
                if scores:
                    mean_val = op.reduce(scores)
                    print(op.pretty_topic_mean(topic, mean_val))

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

    def print_qranking_means(self):
        for topic in sorted(self.topics):
            topic_eval = self.topics[topic]
            for op in self.qrank_ops:
                if not op.print_mean:
                    continue
                scores = topic_eval.qranking_scores_for(str(op))
                if scores:
                    mean_val = op.reduce(scores)
                    print(op.pretty_topic_mean(topic, mean_val))


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

    qrels = Qrels(args.qrels_file)

    jig = EvalJig(min_rel_level=args.min_rel_level, max_depth=args.max_depth)
    jig.add_op(NumRetrieved())
    jig.add_op(NumRel())
    jig.add_op(NumRelRet())
    jig.add_op(Unjudged())
    jig.add_op(RecipRankPrime())
    jig.add_op(NDCGPrime())
    jig.add_op(RBPPrime(p=0.8))
    jig.add_op(RBO(p=0.8))

    with open(args.input_file) as f:
        metadata_json = f.readline()
        metadata = RunMetadata.model_validate_json(metadata_json)

        for line in f:
            topic_results = TopicResults.model_validate_json(line)
            topic = topic_results.topic
            if topic not in qrels.qrels:
                continue
            measured = defaultdict(set)

            for day in dates:
                if day not in topic_results.results:
                    sys.exit(f'Error: run is missing day {day} for topic {topic}')
                # Check doc rankings of questions the system returned docs for
                # There may be zero relevant documents
                # Note that a valid run must have a value for every day in the
                # collection.
                q_results = topic_results.results[day]
                for qres in q_results:
                    qid_qrels = qrels.get_qid(topic, day, qres.qid)
                    if qid_qrels:
                        measured[day].add(qres.qid)
                        jig.zero(topic, day, qres.qid)
                        doc_ranking = [hit.doc_id for hit in 
                                        sorted(qres.doc_ranking, 
                                            key=lambda x: x.score, 
                                            reverse=True)]
                        jig.compute(topic, day, qres.qid, doc_ranking, qid_qrels)

                # Check its question ranking, which may be empty
                if day in qrels.qranking[topic]:
                    jig.zero_qranking(topic, day)
                    question_ranking = [q_res.qid for q_res in
                                        sorted(topic_results.results[day],
                                               key=lambda q: q.question_rank)]
                    qrel_ranking = qrels.get_qranking(topic, day)
                    jig.compute_qranking(topic, day, question_ranking, qrel_ranking)

                # Score questions that the run did not retrieve
                if day in qrels.qrels[topic]:
                    qid_qrels = qrels.qrels[topic][day]
                    # Measure empty rankings for questions the system didn't return

                    for qid, doc_qrels in qid_qrels.items():
                        if qid in measured[day]:
                            continue
                        measured[day].add(qid)
                        jig.zero(topic, day, qid)
                        doc_ranking = []
                        jig.compute(topic, day, qid,
                                    doc_ranking, doc_qrels)


    jig.print_scores()
    jig.print_day_means()
    jig.print_qid_means()
    jig.print_topic_means()
    jig.print_qranking_scores()
    jig.print_qranking_means()


if __name__ == "__main__":
    from cdet_scorer.cli import main
    sys.exit(main())