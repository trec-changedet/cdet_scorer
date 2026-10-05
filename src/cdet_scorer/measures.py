#!/usr/bin/env python3

# DOI: http://dx.doi.org/10.1145/2911451.2914737
from math import log2
from typing import override, Any
from enum import IntEnum
from collections import defaultdict
import logging

type Numeric = int | float

log = logging.getLogger(__name__)

class RelLevel(IntEnum):
    UNJUDGED = -1
    NOT_RELEVANT = 0
    AWARENESS = 1
    ASSESSMENT = 5
    ACTION = 20

def str_to_gain(s: str) -> RelLevel:
    if s == 'not_relevant':
        return RelLevel.NOT_RELEVANT
    elif s == 'awareness':
        return RelLevel.AWARENESS
    elif s == 'assessment':
        return RelLevel.ASSESSMENT
    elif s == 'action':
        return RelLevel.ACTION
    else:
        return RelLevel.UNJUDGED

def infinite_defaultdict():
    return defaultdict(infinite_defaultdict)

# Assuming a qrels format like:
# topic qid doc rel
class Qrels:
    def __init__(self, filename):
        self.qrels = infinite_defaultdict()
        with open(filename) as fp:
            for line in fp:
                topic, qid, docid, rel = line.strip().split()
                self.qrels[topic][qid][docid] = str_to_gain(rel)

    def get(self, topic: str, qid: str, docid: str) -> RelLevel:
        if topic in self.qrels and qid in self.qrels[topic] and docid in self.qrels[topic][qid]:
            return self.qrels[topic][qid][docid]
        else:
            log.warning(f'No {topic}, {qid}, or {docid} in qrels')
            return RelLevel.UNJUDGED

    def get_qid(self, topic, qid) -> dict[str, RelLevel]:
        if topic in self.qrels and qid in self.qrels[topic]:
            return self.qrels[topic][docid]
        else:
            log.warning(f'No {topic} or {qid} in qrels')
            return {}

def ranking_to_gains(doc_ranking: list[str], qrels: dict[str, RelLevel]):
    return [ qrels[docid] if docid in qrels else RelLevel.UNJUDGED for docid in doc_ranking ]


class Measure:
    def __init__(self):
        self.formatstr: str = '{:.4f}'
        self.label: str = 'measure name'
        self.print_score: bool = True
        self.print_mean: bool = True

    def __str__(self):
        return self.label

    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> Numeric | None:
        return None

    def reduce(self, scores: dict[str, Numeric]) -> Numeric:
        return sum(scores.values()) / len(scores.values())

    def pretty(self, topic: str, value: Numeric) -> str:
        return topic + " " + self.label + " " + self.formatstr.format(value)

    def pretty_mean(self, value) -> str:
        return "all " + self.label + " " + self.formatstr.format(value)

def r_t(gain_ranking: list[int], all_gains: list[int]) -> float:
    '''r_t, a formula in the paper, is the gain value associated with the terminal document.
    '''
    if len(all_gains) == 0:
        return 1.0
    else:
        all_gains = sorted(all_gains, reverse=True)
        R = sum(all_gains)
        sum_r_i = sum(gain_ranking)
        return sum_r_i / R


class RecipRankPrime(Measure):
    def __init__(self):
        super().__init__()
        self.label = "recip_rank'"

    @classmethod
    def _recip_rank(cls, gains: list[int]) -> float:
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
    def _recip_rank_prime(cls, gains: list[int], num_rel: int) -> float:
        if num_rel > 0:
            return RecipRankPrime._recip_rank(gains)
        elif num_rel == 0:
            return RecipRankPrime._recip_rank(gains + [1])
        else:
            raise ValueError('num_rel must be non-negative')

    @override
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> float:
        gains = ranking_to_gains(doc_ranking, qrels)
        num_rel = sum(1 for rl in qrels.values() if rl > RelLevel.NOT_RELEVANT)
        return RecipRankPrime._recip_rank_prime(gains, num_rel)


class RBPPrime(Measure):
    def __init__(self, p=0.8):
        super().__init__()
        self.label = f"rbp'(p={p})"
        self.p = p

    @classmethod
    def _rbp_prime(cls, gain_ranking: list[int], p: float, all_gains: list[int]) -> float:
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

class APPrime(Measure):
    def __init__(self):
        super().__init__()

    @classmethod
    def _ap_prime(cls, gain_ranking: list[int], num_rel: int):
        all_gains = [1 for x in range(num_rel)]
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

class NDCGPrime(Measure):
    def __init__(self):
        super().__init__()
        self.label = "ndcg'"

    @classmethod
    def _ndcg(cls, gain_ranking: list[int], all_gains: list[int]):
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
    def _ndcg_prime(cls, gain_ranking: list[int], all_gains: list[int]):
        rt = r_t(gain_ranking, all_gains)
        gain_ranking.append(rt)
        all_gains.append(1)
        return NDCGPrime._ndcg(gain_ranking, all_gains)

    @override
    def compute(self, doc_ranking: list[str], qrels: dict[str, RelLevel]) -> float:
        gains = ranking_to_gains(doc_ranking, qrels)
        all_gains = list(qrels.values())
        return NDCGPrime._ndcg_prime(gains, all_gains)
    