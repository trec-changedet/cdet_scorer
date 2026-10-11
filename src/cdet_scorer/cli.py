from pathlib import Path
from collections import defaultdict

from cdet_scorer.measures import Qrels, Measure, NDCGPrime, NumRel, NumRelRet, NumRetrieved, RBPPrime, RecipRankPrime, RelLevel, Unjudged, str_to_gain
from cdet_scorer.api_types import RunMetadata, TopicResults

class EvalJig:
    def __init__(self, min_rel_level: RelLevel, max_depth: int|None):
        self.ops: list[Measure] = []
        self.score: defaultdict[str, dict[str, int | float ]] = defaultdict(dict)
        self.means: dict[str, int | float] = dict()
        self.topics: set[str] = set()
        self.min_rel_level = min_rel_level
        self.max_depth = max_depth

    def _level_qrels(self, qrels: dict[str, RelLevel]) -> dict[str, RelLevel]:
        return {docid: (rl if rl >= self.min_rel_level else RelLevel.NOT_RELEVANT)  for docid, rl in qrels.items()
        }
        
    def add_op(self, meas: Measure):
        self.ops.append(meas)

    def compute(self, topic: str, doc_ranking: list[str], qrels: dict[str, RelLevel]):
        self.topics.add(topic)
        ranking_slice = doc_ranking if self.max_depth is None else doc_ranking[:self.max_depth]
        if self.min_rel_level > RelLevel.AWARENESS:
            qrels = self._level_qrels(qrels)
        for op in self.ops:
            self.score[str(op)][topic] = op.compute(ranking_slice, qrels) or 0

    def zero(self, topic):
        self.topics.add(topic)
        for op in self.ops:
            self.score[str(op)][topic] = 0

    def comp_means(self):
        for op in self.ops:
            self.means[str(op)] = op.reduce(self.score[str(op)])

    def print_scores_for(self, topic):
        for op in self.ops:
            if not op.print_score: continue
            opname = str(op)
            if topic in self.score[opname]:
                print(op.pretty(topic, self.score[opname][topic]))

    def print_scores(self):
        for topic in sorted(self.topics):
            self.print_scores_for(topic)

    def print_means(self):
        for op in self.ops:
            if not op.print_mean: continue
            opname = str(op)
            if self.means[opname] is not None:
                print(op.pretty_mean(self.means[opname]))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Change detection scorer script")
    parser.add_argument('-l', '--min_rel_level',
                        type=str_to_gain,
                        default=RelLevel.AWARENESS,
                        help='Minimum relevance level to consider a document relevant. Default is AWARENESS.')
    parser.add_argument('-M', '--max_depth',
                        type=int,
                        default=100,
                        help='Maximum depth to consider in the ranking. Default is 100.')
    parser.add_argument('qrels_file', type=str, help='Path to the qrels file')
    parser.add_argument('input_file', type=str, help='Path to the input file')
    args = parser.parse_args()

    qrels = Qrels(args.qrels_file)

    jig = EvalJig(min_rel_level=args.min_rel_level, max_depth=args.max_depth)
    jig.add_op(NumRetrieved())
    jig.add_op(NumRel())
    jig.add_op(NumRelRet())
    jig.add_op(Unjudged())
    jig.add_op(RecipRankPrime())
    jig.add_op(NDCGPrime())
    jig.add_op(RBPPrime(p=0.8))

    with open(args.input_file) as f:
        metadata_json = f.readline()
        metadata = RunMetadata.model_validate_json(metadata_json)

        for line in f:
            topic_results = TopicResults.model_validate_json(line)
            print(topic_results.topic)

if __name__ == '__main__':
    import sys
    from cdet_scorer.cli import main
    sys.exit(main())