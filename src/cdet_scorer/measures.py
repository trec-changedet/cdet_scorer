#!/usr/bin/env python3

# DOI: http://dx.doi.org/10.1145/2911451.2914737
from dataclasses import dataclass, field
import json
from math import log2
import sys
from typing import Any, override, Final
from enum import IntEnum
from collections import Counter, defaultdict
import logging

type Numeric = int | float

log = logging.getLogger(__name__)

class RelLevel(float):
    '''I wanted an enum, but I also wanted to allow arbitrary gain values 
    such as from r_t(). Pyright is not amused.
    '''
    UNJUDGED: Final['UNJUDGED']         # type: ignore
    NOT_RELEVANT: Final['NOT_RELEVANT'] # type: ignore
    AWARENESS: Final['AWARENESS']       # type: ignore
    ASSESSMENT: Final['ASSESSMENT']     # type: ignore
    ACTION: Final['ACTION']             # type: ignore

RelLevel.UNJUDGED = RelLevel(0.0)       # type: ignore
RelLevel.NOT_RELEVANT = RelLevel(0.0)   # type: ignore
RelLevel.AWARENESS = RelLevel(1.0)      # type: ignore
RelLevel.ASSESSMENT = RelLevel(5.0)     # type: ignore
RelLevel.ACTION = RelLevel(20.0)        # type: ignore

def str_to_gain(s: str) -> RelLevel:
    if s == 'not_relevant':
        return RelLevel.NOT_RELEVANT
    elif s == 'awareness':
        return RelLevel.AWARENESS
    elif s == 'assessment':
        return RelLevel.ASSESSMENT
    elif s == 'action':
        return RelLevel.ACTION
    elif s == 'unjudged':
        return RelLevel.UNJUDGED
    else:
        sys.exit(f'Unknown RelLevel string {s}')

def infinite_defaultdict():
    return defaultdict(infinite_defaultdict)

# Qrels format:
# topic qid day doc rel, or
# topic * day doc unjudged, or
# topic * day doc not-relevant, or
# topic * day qranking qid1,qid2,...,qidN

class Qrels:
    def __init__(self, filename):
        self.qrels = infinite_defaultdict()
        self.qranking = infinite_defaultdict()
        nonrel_lists = defaultdict(lambda: defaultdict(list))
        rel_counts = defaultdict(Counter)
        with open(filename) as fp:
            for line in fp:
                topic, day, qid, docid, rel = line.strip().split()
                if docid == 'qranking':
                    self.qranking[topic][day] = rel.split(',')
                elif rel == 'not-relevant':
                    # need to add nonrels to every qid that day
                    nonrel_lists[topic][day].append(docid)
                elif rel == 'unjudged':
                    continue
                elif qid == '*':
                    sys.exit(f'Qrels has bogus qid: {line}')
                else:
                    self.qrels[topic][day][qid][docid] = str_to_gain(rel)
                    rel_counts[topic][day] += 1
        for topic, days in nonrel_lists.items():
            for day, nonrels in days.items():
                for qid in self.qrels[topic][day]:
                    for docid in nonrels:
                        self.qrels[topic][day][qid][docid] = RelLevel.NOT_RELEVANT
        # Prune out topics with no judgments
        for topic, days in list(self.qrels.items()):
            for day in list(days):
                if rel_counts[topic][day] == 0:
                    del self.qrels[topic][day]

    def get_qid(self, topic: str, day: str, qid: str) -> dict[str, RelLevel]:
        if topic not in self.qrels:
            return {}
        if day not in self.qrels[topic]:
            return {}
        if qid not in self.qrels[topic][day]:
            return {}
        return self.qrels[topic][day][qid]

    def get_qranking(self, topic: str, day: str) -> list[str]:
        if topic not in self.qranking:
            return []
        if day not in self.qranking[topic]:
            return []
        return self.qranking[topic][day]


def ranking_to_gains(doc_ranking: list[str], qrels: dict[str, RelLevel]):
    return [ qrels[docid] if docid in qrels else RelLevel.UNJUDGED for docid in doc_ranking ]


class DocRankingMeasure:
    def __init__(self):
        self.formatstr: str = '{:.4f}'
        self.label: str = 'measure name'
        self.print_score: bool = True
        self.print_mean: bool = True
        self.log = logging.getLogger(self.__class__.__name__)

    def __str__(self):
        return self.label

    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> Numeric | None:
        return None

    def reduce(self, scores: dict[Any, Numeric]) -> Numeric:
        return sum(scores.values()) / len(scores.values())

    def pretty(self, topic: str, day: str, qid: str, value: Numeric) -> str:
        return f"{topic} {day} {qid} {self.label} {self.formatstr.format(value)}"

    def pretty_day_mean(self, topic, day, value) -> str:
        return f"{topic} {day} all {self.label} {self.formatstr.format(value)}"

    def pretty_qid_mean(self, topic, qid, value) -> str:
        return f"{topic} all {qid} {self.label} {self.formatstr.format(value)}"

    def pretty_topic_mean(self, topic, value) -> str:
        return f"{topic} all all {self.label} {self.formatstr.format(value)}"

class NumRetrieved(DocRankingMeasure):
    '''The number of documents retrieved above the args.depth cutoff.'''
    def __init__(self):
        super().__init__()
        self.formatstr = '{:d}'
        self.label = 'num_ret'
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> int:
        return len(doc_ranking)
    def reduce(self, scores):
        return sum(scores.values())

class NumRel(DocRankingMeasure):
    '''The number of relevant documents (rel >= args.minrel) 
    in the qrels for this topic.'''
    def __init__(self):
        super().__init__()
        self.formatstr = '{:d}'
        self.label = 'num_rel'
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> int:
        return sum(1 for rel in qrels.values() if rel >= RelLevel.AWARENESS)
    def reduce(self, scores):
        return sum(scores.values())

class NumRelRet(DocRankingMeasure):
    '''The number of relevant documents (rel >= args.minrel) retrieved
    above the args.depth cutoff.'''
    def __init__(self):
        super().__init__()
        self.formatstr = '{:d}'
        self.label = 'num_rel_ret'
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> int:
        return sum(1 for docid in doc_ranking if docid in qrels and qrels[docid] >= RelLevel.AWARENESS)
    def reduce(self, scores):
        return sum(scores.values())

class Unjudged(DocRankingMeasure):
    '''The number of unjudged documents retrieved above the args.depth cutoff.'''
    def __init__(self):
        super().__init__()
        self.formatstr = '{:d}'
        self.label = 'unjudged'
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> int:
        return sum(1 for docid in doc_ranking if docid not in qrels)
    def reduce(self, scores):
        return sum(scores.values())


def r_t(gain_ranking: list[RelLevel], all_gains: list[RelLevel]) -> RelLevel:
    '''r_t, a formula in the paper, is the gain value associated with the terminal document.
    '''
    R = sum(all_gains)
    if R == 0:
        return RelLevel.AWARENESS
    else:
        sum_r_i = sum(gain_ranking)
        return RelLevel(sum_r_i / R)

class RecipRankPrime(DocRankingMeasure):
    def __init__(self):
        super().__init__()
        self.label = "recip_rank'"

    @classmethod
    def _recip_rank(cls, gains: list[RelLevel]) -> float:
        first_rel = None
        for i in range(len(gains)):
            if gains[i] > 0:
                first_rel = i
                break

        if first_rel is not None:
            return 1.0 / (first_rel + 1.0)
        else:
            return 0.0

    @classmethod
    def _recip_rank_prime(cls, gains: list[RelLevel], num_rel: int) -> float:
        if num_rel > 0:
            return RecipRankPrime._recip_rank(gains)
        elif num_rel == 0:
            return RecipRankPrime._recip_rank(gains + [RelLevel.AWARENESS])
        else:
            raise ValueError('num_rel must be non-negative')

    @override
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> float:
        gains = ranking_to_gains(doc_ranking, qrels)
        num_rel = sum(1 for rl in qrels.values() if rl > RelLevel.NOT_RELEVANT)
        return RecipRankPrime._recip_rank_prime(gains, num_rel)

class RBPPrime(DocRankingMeasure):
    def __init__(self, p=0.8):
        super().__init__()
        self.label = f"rbp'(p={p})"
        self.p = p

    @classmethod
    def _rbp_prime(cls, 
                   gain_ranking: list[RelLevel], 
                   p: float, 
                   all_gains: list[RelLevel]) -> float:
        score = 0.0
        index = 0
        while index < len(gain_ranking):
            score += gain_ranking[index] * p ** index
            index += 1
        rt = r_t(gain_ranking, all_gains)
        return (1.0 - p) * score + rt * p ** index

    @override
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> float:
        gains = ranking_to_gains(doc_ranking, qrels)
        all_gains = list(qrels.values())
        return RBPPrime._rbp_prime(gains, self.p, all_gains)


# AP_Prime is based on a graded-relevance version of AP, rather than the TREC-style
# thresholded binary relevance version.
class APPrime(DocRankingMeasure):
    def __init__(self):
        super().__init__()

    @classmethod
    def _ap_prime(cls, gain_ranking: list[RelLevel], num_rel: int):
        all_gains = [RelLevel.AWARENESS for x in range(num_rel)]
        rt = r_t(gain_ranking, all_gains)

        gain_ranking.append(rt)

        index = 0
        sum_prec = 0.0
        rel_so_far = 0
        while index < len(gain_ranking):
            if gain_ranking[index] > 0:
                rel_so_far += gain_ranking[index]
                sum_prec += gain_ranking[index] * rel_so_far / (index + 1.0)
            index += 1
        return sum_prec / (num_rel + 1.0)

    @override
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> float:
        gains = ranking_to_gains(doc_ranking, qrels)
        num_rel = sum(1 for rl in qrels.values() if rl > RelLevel.NOT_RELEVANT)
        return APPrime._ap_prime(gains, num_rel)

class NDCGPrime(DocRankingMeasure):
    def __init__(self):
        super().__init__()
        self.label = "ndcg'"

    @classmethod
    def _ndcg(cls, gain_ranking: list[RelLevel], all_gains: list[RelLevel]):
        all_gains = sorted(all_gains, reverse=True)

        if not gain_ranking:
            return 0.0
        if not all_gains:
            raise ValueError('NDCG with no relevant documents is undefined')
        index = 0
        dcg = 0
        idcg = 0
        while index < len(gain_ranking):
            dcg += gain_ranking[index] / log2(index + 2)
            if index < len(all_gains):
                idcg += all_gains[index] / log2(index + 2)
            index += 1
        return dcg/idcg

    @classmethod
    def _ndcg_prime(cls, gain_ranking: list[RelLevel], all_gains: list[RelLevel]):
        rt = r_t(gain_ranking, all_gains)
        gain_ranking.append(rt)
        all_gains.append(RelLevel.AWARENESS)
        return NDCGPrime._ndcg(gain_ranking, all_gains)

    @override
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> float:
        gains = ranking_to_gains(doc_ranking, qrels)
        all_gains = list(qrels.values())
        return NDCGPrime._ndcg_prime(gains, all_gains)

class QuestionRankingMeasure:
    def __init__(self):
        self.formatstr: str = '{:.4f}'
        self.label: str = 'measure name'
        self.print_score: bool = True
        self.print_mean: bool = True

    def __str__(self):
        return self.label

    def compute(self, question_ranking: list[str], qrelranking: list[str]) -> Numeric | None:
        return None

    def reduce(self, scores: dict[str, Numeric]) -> Numeric:
        return sum(scores.values()) / len(scores.values())

    def pretty(self, topic: str, day: str, value: Numeric) -> str:
        return f"{topic} {day} qranking {self.label} {self.formatstr.format(value)}"

    def pretty_topic_mean(self, topic: str, value: Numeric) -> str:
        return f"{topic} all qranking {self.label} {self.formatstr.format(value)}"


class RBO(QuestionRankingMeasure):
    def __init__(self, p: float = 0.8):
        super().__init__()
        self.p = p
        self.label = f"rbo(p={p})"

    @classmethod
    def _rbo(cls, s: list[str], t: list[str], p: float) -> float:
        if not s and not t:
            return 1.0
        if not s or not t:
            return 0.0

        k = max(len(s), len(t))
        s_set: set[str] = set()
        t_set: set[str] = set()
        overlap = 0
        score = 0.0

        for d in range(1, k + 1):
            if d <= len(s):
                s_set.add(s[d - 1])
            if d <= len(t):
                t_set.add(t[d - 1])
            overlap = len(s_set & t_set)
            x_d = overlap / d
            score += x_d * (p ** (d - 1))

        x_k = overlap / k
        return (1.0 - p) * score + (p ** k) * x_k

    @override
    def compute(self, question_ranking: list[str], qrelranking: list[str]) -> float:
        return RBO._rbo(question_ranking, qrelranking, self.p)

