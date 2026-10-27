# Change Detection Evaluation Explorer — Design Document

## 1. Overview & Motivation

The TREC Change Detection scorer (`cdet-scorer`) evaluates systems at the granularity of `(topic, day, qid)` across ~31 topics, ~180 assessed days per topic, and 6–26 questions per topic (~80,000+ evaluation points and ~360,000+ output lines per run).

While the command-line scorer produces exact reference numbers, exploring raw `.eval` output directly is difficult for several reasons:

1. **Extreme Sparsity**: Most `(topic, day, qid)` evaluation points are quiet (`num_rel = 0, num_ret = 0`). Finding the days and questions where events happen—or where systems misbehave—is like looking for needles in a haystack.
2. **Detection vs. Ranking Conflation in Prime Metrics**: On answerable question-days (`num_rel > 0`), the prime measures (`recip_rank'`, `ap'`, `ndcg'`, `rbp'(p=0.8)`) score `0.0` when a system returns nothing (`num_ret = 0`). A low prime average does not tell you whether the system's ranker is poor or whether its firing threshold is simply too conservative.
3. **Micro-Averaging Asymmetry**: The overall `all all all` summary averages flatly across all valid `(topic, day, qid)` tuples. Topics with 26 questions carry >4× the weight of topics with 6 questions, and questions with many active event days dominate questions with rare events.
4. **Disconnected Context**: Raw scores reference opaque identifiers (`cd2026_001`, `q_14`, document UUIDs) separated from the topic narrative, question text, run metadata, and document text.

### Goal
Build an interactive web application (**Change Detection Evaluation Explorer**) backed by FastAPI and `cdet_scorer` in-memory that loads **2–10 run files**, **qrels**, **topics**, and a **SQLite-indexed document corpus** to support seamless top-down exploration: from multi-run trade-off plots down to individual `(topic, day, qid)` rankings and document text.

---

## 2. Guiding Constraints & Scope

- **Strict Adherence to Official Metrics**: The explorer uses the exact measures implemented in [`measures.py`](../src/cdet_scorer/measures.py):
  - **Counts**: `num_ret`, `num_rel`, `num_rel_ret`, `unjudged`
  - **Answerable-Day ("Prime") Measures** (`num_rel > 0`): `recip_rank'`, `ap'`, `ndcg'`, `rbp'(p=0.8)`
  - **Nil-Answer-Day Measures** (`num_rel == 0`): `abstention`, `noise`
  - **Question Ranking Measure**: `rbo(p=0.8)`
- **In-Memory Scoring from Raw Files**: Rather than parsing `.eval` text files, the server ingests raw run files + `qrels` + `topics` and runs `EvalJig` in memory. Because scoring a run takes <1 second in Python, this keeps full document rankings, retrieval scores, and leaf-level `abstention`/`noise` values immediately accessible and allows live toggling of `--min_rel_level` (`awareness`, `assessment`, `action`) and `--max_depth`.
- **Pre-Indexed SQLite Corpus**: Includes a standalone CLI indexing script (`cdet_scorer.index_corpus`) that ingests a JSONL or Parquet corpus file once into a **SQLite database** with a primary-key B-tree index on `doc_id` (and secondary index on `day`). SQLite is built into Python's standard library (`sqlite3`) and provides sub-millisecond $O(\log N)$ random point lookups (`WHERE id = ?`)—unlike DuckDB or Parquet, which are columnar engines optimized for analytical scans rather than single-row key lookups.

---

## 3. Analytical Framework

Without adding new official metrics, the explorer makes existing scores interpretable through three analytical lenses:

### 3.1. The 5-State Behavioral Partition
Every evaluated `(topic, day, qid)` point is classified into one of five mutually exclusive behavioral states based on `num_rel`, `num_ret`, and `num_rel_ret`:

| Ground Truth | System Action | Behavioral State | Metric Impact |
| :--- | :--- | :--- | :--- |
| **Answerable** (`num_rel > 0`) | `num_ret == 0` | **Missed Event (Silent)** | Scores `0.0000` on all Prime measures (`ndcg'`, `ap'`, `rbp'`, `recip_rank'`). |
| **Answerable** (`num_rel > 0`) | `num_ret > 0, num_rel_ret == 0` | **Zero-Hit Trigger** | System fired on an event day, but retrieved only `not-relevant` or `unjudged` docs. Scores `0.0000` on Prime measures. |
| **Answerable** (`num_rel > 0`) | `num_rel_ret > 0` | **Event Hit** | System retrieved $\ge 1$ relevant doc; Prime measures reflect ranking quality & truncation penalty ($r_t$). |
| **Nil-Answer** (`num_rel == 0`) | `num_ret == 0` | **True Abstention** | `abstention = 1.0`, `noise = 0`. |
| **Nil-Answer** (`num_rel == 0`) | `num_ret > 0` | **False Alarm** | `abstention = 0.0`, `noise = num_ret` (further decomposed into judged `not-relevant` vs. `unjudged`). |

### 3.2. Unconditional vs. Conditional ("Active") Prime Scores
To decouple **event detection (recall/triggering)** from **ranking & cutoff quality**:
- **Unconditional Prime (Official)**: Mean of `ndcg'` (or `ap'`, `rbp'`, `recip_rank'`) across all answerable question-days (`num_rel > 0`).
- **Active Prime (Conditional)**: Mean of `ndcg'` restricted to answerable question-days where the system actually returned documents (`num_rel > 0` and `num_ret > 0`).
- **Trigger Rate on Answerable Days**: Fraction of answerable question-days where `num_ret > 0`.

> *Note*: $\text{Unconditional Prime} = \text{Trigger Rate} \times \text{Active Prime}$. Showing all three numbers immediately explains why a quiet system like `idaccs-csplx-z290` has a low overall `ndcg'` (`0.1211`) despite high precision when it fires.

### 3.3. Multi-Level Aggregation Selector (Micro vs. Macro)
Users can switch the rollup mode across the entire UI:
1. **Micro (Official `all all all`)**: Flat mean across all applicable `(topic, day, qid)` evaluation points.
2. **Macro by Topic**: Mean of per-topic means (`topic all all`), weighting every topic equally regardless of question count or event frequency.
3. **Macro by Question**: Mean of per-question means (`topic all qid`), weighting every question equally.
4. **Macro by Day**: Mean of per-day means (`topic day all`).

---

## 4. User Interface & Visual Workflow (4 Zoom Levels)

The frontend is organized into four progressive views, with a persistent top bar for global controls (**Aggregation Mode**: Micro / Macro-Topic / Macro-Question; **Min Relevance Level**: `awareness` / `assessment` / `action`; **Max Depth**: `100`).

```
+-----------------------------------------------------------------------------------+
|  CDET Explorer   [Rollup: Micro v] [Min Rel: awareness v] [Depth: 100]            |
|  Tabs: [1. Leaderboard & Trade-offs] [2. Topic/Question Breakdown] [3. Calendar]  |
+-----------------------------------------------------------------------------------+
```

### Level 1: Multi-Run Leaderboard & Trade-Off Overview
Designed for comparing 2–10 runs at a glance.

1. **Interactive Leaderboard Table**:
   - One row per run (`runtag`, `run_type`, `models` badge, expandable `description`).
   - Columns grouped into:
     - **Answerable Days (`num_rel > 0`)**: `ndcg'`, `rbp'(p=0.8)`, `ap'`, `recip_rank'`, plus toggleable *Trigger Rate* & *Active `ndcg'`*.
     - **Nil-Answer Days (`num_rel == 0`)**: `abstention`, `noise`.
     - **Question Ranking**: `rbo(p=0.8)`.
     - **Volume & Pooling Diagnostics**: `num_ret`, `num_rel`, `num_rel_ret`, `unjudged`, and `unjudged %` (`unjudged / num_ret`).
2. **2D Pareto Trade-Off Scatter Plot**:
   - **X-Axis**: Quiet-day discipline (`abstention`, or `noise` inverted).
   - **Y-Axis**: Answerable-day effectiveness (selectable: `ndcg'`, `rbp'(p=0.8)`, `ap'`, `recip_rank'`).
   - **Points**: One point per run (or one point per topic for selected runs, connected by vectors from Run A $\to$ Run B).
3. **Small-Multiple / Grouped Behavioral Bar Charts (Common Baseline)**:
   - Instead of stacked bars (where middle segments lack a shared baseline and are hard to compare across runs), each behavioral state gets its own dedicated subplot or grouped bar cluster with a **0-baseline**:
     - **Answerable-Day Panels (`num_rel > 0`)**: Separate side-by-side horizontal bar charts for (a) **Event Hit Rate** (`num_rel_ret > 0`), (b) **Zero-Hit Trigger Rate** (`num_ret > 0, num_rel_ret == 0`), and (c) **Missed Event Rate** (`num_ret == 0`).
     - **Nil-Answer-Day Panels (`num_rel == 0`)**: Separate side-by-side horizontal bar charts for (d) **False Alarm Rate** (`1 - abstention`), (e) **Mean Noise Volume** (`noise`), and (f) **Unjudged Fraction of Noise**.

---

### Level 2: Topic & Question Breakdown (Cross-Run Comparison)
Designed to answer: *"On which topics or questions do my runs differ most, and why?"*

1. **Topic Comparison Grid & Delta Plot**:
   - Lists all 31 topics with their human-readable `label` (e.g., `cd2026_001: Advanced-degrees-in-AI...`), `num_days`, `num_qs`, and total `num_rel`.
   - In **Multi-Run Mode**, displays each run's score on the selected metric plus a **Delta Bar (`Run A - Run B`)** sortable by largest positive/negative difference.
   - Scatter/paired-dot plot showing per-topic distributions across all loaded runs so outlier topics stand out immediately.
2. **Question Table (within Selected Topic)**:
   - Expanding or clicking a topic reveals its questions (`q_1 ... q_n`) with full question text from the `.jsonl` topics file.
   - Columns show per-question metrics (`topic all qid`): how many assessed days had `num_rel > 0` for that question, `num_rel`, `num_rel_ret`, `ndcg'`, `abstention`, `noise`, and `unjudged`.
   - Highlights "dead" questions (`num_rel == 0` across the entire timeline) vs. high-activity questions.

---

### Level 3: The Topic "Event Calendar" (`Question × Day` Matrix)
Designed to visualize temporal behavior within a single topic.

```
Topic: cd2026_001 — Advanced-degrees-in-AI-integrated-with-other-areas-of-specialization
Mode: [Single Run: bm25-qwen-splade] or [Diff: bm25-qwen-splade vs idaccs-csplx-z290]
Filter Days: [x] Show all assessed days (178)  [ ] Only days with activity (num_rel > 0 or num_ret > 0)

            2021-08-19  2021-09-22  2021-11-27 ... 2023-06-21
qranking RBO    --          --        0.0000         0.4500
--------------------------------------------------------------
q_1 (AI deg)    .           .           .            [0.00]  <-- Missed Event (num_rel=1, num_ret=0)
q_3 (Quantum)   .          (!1)         .              .     <-- False Alarm (num_rel=0, noise=1)
q_8 (Vision)    .           .           .            [1.00]  <-- Hit (num_rel=1, ndcg'=1.00)
q_11 (Robot)    .           .         [0.00]         [0.00]
```

1. **Matrix Layout**:
   - **Rows**: Questions `q_1 ... q_n` (with hover/pinned question text).
   - **Columns**: Assessed days in chronological order (with a quick filter to collapse 100% quiet days across all questions).
   - **Top Summary Strip**: Per-day question ranking `rbo(p=0.8)` against the reference `qranking`, plus daily `num_rel` and `num_ret`.
2. **Cell Visual Encoding**:
   - **Answerable Cells (`num_rel > 0`)**: Heavy border/frame indicating ground-truth relevance exists.
     - Fill color encodes Prime score (`0.0` = red/amber for missed event or zero-hit; `0.0 < s <= 1.0` = viridis/green gradient).
   - **Nil-Answer Cells (`num_rel == 0`)**:
     - Quiet (`num_ret == 0`): Muted dot/blank.
     - False Alarm (`num_ret > 0`): Purple/orange warning badge showing `noise` count (e.g., `!3`).
3. **Comparison / Diff Mode (`Run A vs. Run B`)**:
   - On answerable cells: Diverging color scale (`Blue = Run A better`, `Red = Run B better`, `Gray = tie`).
   - On nil cells: Indicates which run abstained vs. which run generated noise.

---

### Level 4: Cell & Document Inspector (Slide-Out Drawer / Bottom Panel)
Clicking any `(topic, day, qid)` cell in the Event Calendar opens the deep-inspection view:

1. **Evaluation Point Header**:
   - Topic ID, label, and narrative.
   - Question ID and full question text.
   - Date (`YYYY-MM-DD`) and ground-truth summary (`num_rel` broken down by `action` [20], `assessment` [5], `awareness` [1]).
   - Exact metric table for all loaded runs at this point: `num_ret`, `num_rel_ret`, `unjudged`, `recip_rank'`, `ap'`, `ndcg'`, `rbp'(p=0.8)`, `abstention`, `noise`, and terminal document gain $r_t$.
2. **Side-by-Side Ranked Document Lists (plus Missed Relevant Docs)**:
   - Displays the ranked list returned by each selected run:
     - `Rank`, `doc_id`, retrieval `score`, and relevance judgment badge (`ACTION`, `ASSESSMENT`, `AWARENESS`, `NOT_RELEVANT`, `UNJUDGED`).
     - Shows per-rank discounted gain contribution so you can see exactly why a ranking achieved e.g. `ndcg' = 0.62` or how trailing non-relevant documents diluted $r_t$ and penalized the prime metrics.
   - **Missed Relevant Documents List**: Lists all documents judged relevant for `(topic, day, qid)` in `qrels` that the system failed to retrieve.
3. **Document Text Modal / Reader**:
   - Clicking any `doc_id` (retrieved or missed) fetches the document from the corpus file and displays:
     - `id`, `day`, `date`, `url`
     - Full document `text`
     - All `qrels` judgments for this document on that day across all questions in the topic.

---

## 5. Technical Architecture

### 5.1. Stack Choice & Corpus Indexer (`SQLite`)
- **Backend**: **Python 3.12+ & FastAPI** (`uvicorn`), living inside the repository (e.g., `cdet_scorer.explorer`) so it directly imports `Qrels`, `EvalJig`, `TopicResults`, `RunMetadata`, and `DocumentSchema`.
- **Why SQLite over DuckDB for Document Random Access**:
  - When a user clicks a `(topic, day, qid)` cell or a `doc_id`, the backend performs **point lookups by primary key** (`SELECT id, text, url, date, day FROM documents WHERE id IN (...)`).
  - **SQLite** uses a row-oriented B-tree storage engine (`WITHOUT ROWID` or `INTEGER PRIMARY KEY` + index on `id`), delivering sub-millisecond random access with zero external dependencies (`sqlite3` is in the Python standard library).
  - **DuckDB** is a columnar OLAP engine optimized for full-column scans and aggregations; point lookups on string IDs scan row-group zonemaps and are significantly slower and heavier for random access. (DuckDB or `pyarrow` can still be used by the *indexer script* to read an input `.parquet` file and stream rows into SQLite.)
- **Corpus Indexing Script (`cdet_scorer.index_corpus`)**:
  - A standalone CLI utility that reads a `.jsonl` or `.parquet` file of `DocumentSchema` objects and writes a `.sqlite` database file using **Peewee ORM** (`Document` model with `without_rowid = True`, primary key on `id`, and index on `day`), mapping directly to `DocumentSchema` via `ConfigDict(from_attributes=True)` with zero raw SQL strings.
  - Uses batched transactions (`Document.insert_many(batch).on_conflict_replace().execute()`) with `SqliteDatabase` pragmas (`synchronous=0`, `journal_mode="memory"`) during bulk load to index hundreds of thousands of documents in seconds.
- **Frontend**: **Single-Page Lightweight Web UI** served statically by FastAPI (HTML5 + Tailwind CSS + Alpine.js + Plotly.js, or a small Vite/React bundle). Zero Node.js build step required if using Alpine.js + Plotly.js CDN/vendored assets, keeping installation as simple as `pip install -e ".[explorer]"`.

### 5.2. Data Flow & In-Memory State

```
+-------------------+   +-------------------+   +--------------------+   +-------------------+
|   qrels file      |   |  topics.jsonl     |   |  runfiles (1..N)   |   | corpus (.jsonl /  |
+---------+---------+   +---------+---------+   +---------+----------+   | .parquet)         |
          |                       |                       |              +---------+---------+
          +-----------+-----------+-----------------------+                        |
                      |                                                            | (One-time CLI:
                      v                                                            v  index_corpus)
        +-----------------------------------+                        +---------------------------+
        |   In-Memory Evaluation Store      |                        |   SQLite Corpus DB        |
        | - Qrels & reference qrankings     |                        | - WITHOUT ROWID B-tree    |
        | - Topic narratives & questions    |                        | - Sub-ms doc_id lookup    |
        | - Raw TopicResults per run        |                        | - Returns DocumentSchema  |
        | - EvalJig cache per (rel, depth)  |                        +-------------+-------------+
        +-----------------+-----------------+                                      |
                          |                                                        |
                          +---------------------------+----------------------------+
                                                      |
                                                      v
                                        +---------------------------+
                                        |    FastAPI JSON Endpoints |
                                        +-------------+-------------+
                                                      |
                                                      v
                                        +---------------------------+
                                        |  Browser Interactive UI   |
                                        |  (Leaderboard, Plots,     |
                                        |   Calendar, Doc Reader)   |
                                        +---------------------------+
```

### 5.3. CLI Invocation

**Step 1: Index the corpus once into SQLite**
```bash
python3 -m cdet_scorer.index_corpus \
  --input /path/to/corpus.jsonl \
  --output /path/to/corpus.sqlite
```

**Step 2: Launch the interactive explorer**
```bash
python3 -m cdet_scorer.explorer \
  --qrels sample-data/qrels \
  --topics sample-data/test-topics-all-docs.jsonl \
  --corpus-db /path/to/corpus.sqlite \
  --runs sample-data/idaccs-csplx-z290 sample-data/bm25-qwen-splade \
  --port 8000
```

### 5.4. Core API Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/api/config` | `GET / POST` | Get or update scoring parameters (`min_rel_level`, `max_depth`); triggers re-scoring via `EvalJig` (~0.5s/run) and caches results. |
| `/api/runs/summary` | `GET` | Returns `RunMetadata`, official overall means (Micro, Macro-Topic, Macro-Question, Macro-Day), 5-state behavioral counts, and conditional "Active Prime" averages for all loaded runs. |
| `/api/topics` | `GET` | Returns all topics with metadata (`tid`, `label`, `narrative`, `num_days`, `num_qs`) and per-topic metric rollups for every run. |
| `/api/topics/{tid}` | `GET` | Returns question-level rollups (`topic all qid`), day-level rollups (`topic day all`), and daily `qranking` `rbo(p=0.8)` scores for a topic. |
| `/api/topics/{tid}/calendar` | `GET` | Returns the dense/sparse `Question × Day` matrix for the topic across requested runs, including behavioral state and metric values per cell. |
| `/api/cell/{tid}/{day}/{qid}` | `GET` | Returns full cell details: ground-truth `qrels` for that `(tid, day, qid)`, each run's ranked `doc_id` + `score` + gain + $r_t$, and leaf metric values. |
| `/api/docs/{doc_id}` | `GET` | Queries SQLite `documents` table by primary key `id` for `DocumentSchema` (`id`, `text`, `url`, `date`, `day`) plus all `qrels` judgments for that `doc_id`. |

---

## 6. Implementation Plan

### Phase 1: Corpus Indexer (`cdet_scorer.index_corpus`)
1. Create `src/cdet_scorer/index_corpus.py`:
   - Accepts a `.jsonl` (or `.parquet`) file matching `DocumentSchema` and outputs a SQLite database with `id TEXT PRIMARY KEY ... WITHOUT ROWID`.
   - Validates fields via `DocumentSchema` (or fast JSON parsing) and inserts in batches with progress reporting.

### Phase 2: In-Memory Engine & FastAPI Backend
1. Create `src/cdet_scorer/explorer/` package (`app.py`, `engine.py`, `corpus.py`).
2. Implement `ExplorerEngine`:
   - Loads `topics`, `Qrels`, and $N$ run files using existing Pydantic models (`RunMetadata`, `TopicResults`) and `EvalJig`.
   - Computes and caches Micro, Macro-Topic, Macro-Question, and Macro-Day aggregations, plus the 5-state behavioral counts and Active Prime means.
   - Retains the raw ranked lists (`QuestionResults`) per `(run, topic, day, qid)` for instant drill-down.
3. Implement `CorpusStore`:
   - Opens the `.sqlite` file in read-only mode (`?mode=ro`) for sub-millisecond point and batch `doc_id` lookups.

### Phase 3: Interactive Web Frontend
1. Build a clean, single-page frontend (`src/cdet_scorer/explorer/static/index.html` + `app.js`):
   - **Tab 1 (Overview)**: Leaderboard table with Micro/Macro toggle, 2D `Abstention` vs. Prime Plotly scatter plot, and small-multiple 0-baseline horizontal bar charts for each behavioral state.
   - **Tab 2 (Topics & Questions)**: Sortable per-topic comparison & delta chart (`Run A - Run B`) with expandable per-question tables showing full question text.
   - **Tab 3 (Event Calendar)**: Interactive `Question × Day` heatmap for any topic, supporting both Single-Run inspection and Two-Run diff mode, plus daily `rbo(p=0.8)` timeline.
   - **Slide-over Inspector**: Side-by-side ranked document lists, missed relevant documents, and full-text document viewer modal.

### Phase 4: Validation & Polish
1. Test against `sample-data/idaccs-csplx-z290` and `sample-data/bm25-qwen-splade` to verify that Micro means match the reference `.eval` files to 4 decimal places.
2. Add unit tests for the SQLite corpus indexer, aggregation modes, and behavioral state classification.
