# Change Detection scorer

This is the scoring script for the TREC Change Detection track.

## Installation

Requires Python > 3.12. From the repository root:

```
pip install -e .
```

This installs the `cdet_scorer` package and its one dependency (`pydantic`).

## Usage

```
python3 -m cdet_scorer.cli [options] <qrels> <topics> <runfile>
```

The three positional arguments are, in order:

1. `<qrels>` — the relevance judgments file.
2. `<topics>` — the topics file (defines the full set of questions per topic).
3. `<runfile>` — the run to be scored.

For example, using the included sample data:

```
python3 -m cdet_scorer.cli sample-data/qrels sample-data/test-topics-all-docs.jsonl sample-data/idaccs-csplx-z290
```

Scores are written to standard output.

### Options

| Option | Default | Description |
| --- | --- | --- |
| `-l`, `--min_rel_level` | `awareness` | Minimum relevance level for a document to count as relevant: `awareness`, `assessment`, or `action`. |
| `-M`, `--max_depth` | `100` | Maximum ranking depth to score. |
| `-v`, `-vv` | off | Increase verbosity: `-v` reports per-topic progress (INFO); `-vv` traces how every score is derived (DEBUG, see below). |

## Input files

### Qrels

One whitespace-separated judgment per line, in the order `topic day qid docid rel`:

```
topic day qid    docid rel          # a judged document (awareness|assessment|action)
topic day *      docid not-relevant # not relevant to any question that day
topic day *      docid unjudged     # pooled but not judged
topic day * qranking qid1,qid2,...  # the reference question ranking for that day
```

### Topics

JSON Lines, one topic per line. Each record has a `tid` and a `questions` list,
where each question has at least a `qid`. The topics file defines the complete
set of questions for a topic, which is what lets the scorer evaluate nil-answer
question-days (see below).

### Run

JSON Lines. The first line is the run metadata (runtag, description, etc.); each
remaining line is one topic's results, giving the per-day, per-question ranked
list of documents.

## Output and measures

Each output line is `topic day qid measure value`. Per-question-day scores use
the real `day` and `qid`; means collapse a dimension to `all`
(`topic day all …` is a day mean, `topic all qid …` a per-question mean,
`topic all all …` a topic mean, and `all all all …` the overall mean).

A question-day is scored when its day was assessed (it has at least one
judgment). On an assessed day, every question in the topic is an evaluation
point, and the measures split into two complementary families:

- **Answerable question-days** (at least one relevant document) are scored with
  the ranking-quality "prime" measures `recip_rank'`, `ap'`, `ndcg'`, and
  `rbp'(p=0.8)`.
- **Nil-answer question-days** (no relevant document, where the correct response
  is to return nothing) are scored with `abstention` and `noise`:
  - `abstention` — 1.0 when the system returned nothing, else 0.0. Its mean is
    the correct-rejection rate (specificity); `1 - abstention` is the
    detection-literature false-alarm rate.
  - `noise` — the number of documents returned on a nil-answer day (all of which
    are false positives). Its mean is the average number of spurious documents
    per nil-answer question-day. This is a *volume*, not a rate, so it can exceed
    1 when a system returns several documents on a quiet day.

The counts `num_ret`, `num_rel`, `num_rel_ret`, and `unjudged` are reported for
every question-day, and `rbo(p=0.8)` scores the per-day question ranking against
the reference ranking in the qrels.

## Tracing a score (`-vv`)

Run with `-vv` to see, for every evaluation point, one line showing how its
score was derived: whether the point was answerable (and its relevant count `R`)
or nil-answer, the system's depth-limited ranking, the gain of each retrieved
document, and the resulting value of each measure. For example:

```
eval:DEBUG: cd2026_001 2021-09-22 q_3 [nil-answer] ranking=['9e2834de-...'] gains=[0.0] -> num_ret=1 num_rel=0 num_rel_ret=0 unjudged=1 abstention=0.0000 noise=1.0000
```

Lines begin with `topic day qid`, so the trace can be filtered with `grep` to
follow a single question-day.

## Details on measures

Scoring for this track is tricky, because we want to penalize over-generation, and frequently there is no relevant information to be found. We have measures for over-generation, but when there is nothing to be returned and systems appropriately return nothing, those scores overwhelm the evaluation.

We fix this with two sets of measures. The first set are the measures described in the paper, "Quit While Ahead: Evaluting Truncated Rankings" by Fei Lu, Alistair Moffat, Timothy Baldwin, and Xiuzhen Zhang (SIGIR 2016, https://dl.acm.org/doi/10.1145/2911451.2914737). These are modifications to familiar measures that penalize the score when the ranked list includes more items than are relevant. We implement the "prime" variants of reciprocal rank (RR'), average precision (AP'), nDCG (NDCG'), and rank-biased precision (RBP').

The prime measures are only computed for topics/questions/days where there is at least one known relevant document.

The second set of measures get at whether the system was appropriately quiet on quiet days. The first measure is "abstention", which scores 1.0 if the system returned nothing when there was nothing relevant to return. The second is "noise" which is the count of documents returned on these "nil" days. These measures only report as averages (over days, qids, or overall).

This separation is needed, because the prime measures all tend towards 1.0 when the system retrieves nothing and there is nothing relevant. All those 1.0 scores dominate the average and make it harder to compare runs.

The script also reports the number of documents retrieved, relevant, relevant retrieved, questions, days, and topics as diagnostics.

For question rankings, the measure reported is rank-biased overlap (RBO), which is the only measure I can find for correlating two rankings when they might not contain all the items. RBO is only reported for topics/qids/days where there are relevant items, and thus a question ranking to compare to.

