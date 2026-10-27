#!/usr/bin/env python3
"""Index a JSONL or Parquet corpus of DocumentSchema records into a SQLite database using Peewee ORM."""

import argparse
from collections.abc import Iterable, Iterator
import gzip
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, TextIO

from peewee import DatabaseProxy, Model, SqliteDatabase, TextField

from cdet_scorer.api_types import DocumentSchema

log = logging.getLogger("index_corpus")

db_proxy = DatabaseProxy()


class Document(Model):
    id = TextField(primary_key=True)
    day = TextField(index=True)
    date = TextField()
    url = TextField()
    text = TextField()

    class Meta:
        database = db_proxy
        table_name = "documents"
        without_rowid = True


def _open_text_maybe_gzip(path: Path) -> TextIO:
    """Open a text file, transparently decompressing if it is gzip-compressed."""
    with path.open("rb") as probe:
        magic = probe.read(2)
    if magic == b"\x1f\x8b":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def _is_parquet_path(path: Path) -> bool:
    """Return True if path has a .parquet or .pq suffix (ignoring a trailing .gz)."""
    suffixes = [s.lower() for s in path.suffixes]
    if suffixes and suffixes[-1] == ".gz":
        suffixes = suffixes[:-1]
    return bool(suffixes and suffixes[-1] in {".parquet", ".pq"})


def _iter_jsonl_rows(
    path: Path,
    validate: bool = True,
) -> Iterator[dict[str, str]]:
    """Stream document attribute dicts from a plain or gzip-compressed JSONL file."""
    with _open_text_maybe_gzip(path) as fp:
        for line_no, line in enumerate(fp, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            if validate:
                doc = DocumentSchema.model_validate_json(stripped)
                yield doc.model_dump()
            else:
                obj = json.loads(stripped)
                try:
                    date_str = str(obj["date"])
                    day_str = str(obj["day"]) if "day" in obj and obj["day"] is not None else date_str[:10]
                    yield {
                        "id": str(obj["id"]),
                        "day": day_str,
                        "date": date_str,
                        "url": str(obj["url"]),
                        "text": str(obj["text"]),
                    }
                except KeyError as exc:
                    raise ValueError(
                        f"Missing required field {exc} at {path}:{line_no}"
                    ) from exc


def _iter_parquet_rows(
    path: Path,
    batch_size: int = 10_000,
    validate: bool = True,
) -> Iterator[dict[str, str]]:
    """Stream document attribute dicts from a Parquet file using pyarrow or duckdb."""
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]

        parquet_file = pq.ParquetFile(path)
        available_cols = set(parquet_file.schema.names)
        cols = ["id", "date", "url", "text"] + (["day"] if "day" in available_cols else [])
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=cols):
            col_dict = batch.to_pydict()
            days = col_dict.get("day")
            for idx, (doc_id, date, url, text) in enumerate(
                zip(
                    col_dict["id"],
                    col_dict["date"],
                    col_dict["url"],
                    col_dict["text"],
                )
            ):
                date_str = str(date)
                day_val = days[idx] if days is not None and days[idx] is not None else date_str[:10]
                row = {
                    "id": str(doc_id),
                    "day": str(day_val),
                    "date": date_str,
                    "url": str(url),
                    "text": str(text),
                }
                if validate:
                    yield DocumentSchema.model_validate(row).model_dump()
                else:
                    yield row
        return
    except ImportError:
        pass

    try:
        import duckdb  # type: ignore[import-not-found]

        conn = duckdb.connect(":memory:")
        base_rel = conn.from_parquet(str(path))
        has_day = "day" in base_rel.columns
        proj = "id, day, date, url, text" if has_day else "id, substr(CAST(date AS VARCHAR), 1, 10) AS day, date, url, text"
        rel = base_rel.project(proj)
        while True:
            rows = rel.fetchmany(batch_size)
            if not rows:
                break
            for doc_id, day, date, url, text in rows:
                row = {
                    "id": str(doc_id),
                    "day": str(day),
                    "date": str(date),
                    "url": str(url),
                    "text": str(text),
                }
                if validate:
                    yield DocumentSchema.model_validate(row).model_dump()
                else:
                    yield row
        return
    except ImportError as exc:
        raise RuntimeError(
            "Reading Parquet files requires either 'pyarrow' or 'duckdb' to be installed."
        ) from exc


def index_corpus(
    input_path: str | Path,
    output_path: str | Path,
    *,
    batch_size: int = 2_000,
    validate: bool = True,
    overwrite: bool = False,
) -> int:
    """Build or update a SQLite corpus database from a JSONL or Parquet file using Peewee.

    Returns the total number of indexed documents.
    """
    in_path = Path(input_path)
    out_path = Path(output_path)

    if not in_path.exists():
        raise FileNotFoundError(f"Input corpus file not found: {in_path}")

    if out_path.exists() and overwrite:
        out_path.unlink()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    if _is_parquet_path(in_path):
        row_iter = _iter_parquet_rows(in_path, batch_size=batch_size, validate=validate)
    else:
        row_iter = _iter_jsonl_rows(in_path, validate=validate)

    start_time = time.monotonic()
    total_indexed = 0

    db = SqliteDatabase(
        str(out_path),
        pragmas={
            "synchronous": 0,
            "journal_mode": "memory",
            "temp_store": "memory",
            "cache_size": -64000,
        },
    )
    db_proxy.initialize(db)
    db.connect()
    try:
        db.create_tables([Document], safe=True)

        batch: list[dict[str, str]] = []
        for row in row_iter:
            batch.append(row)
            if len(batch) >= batch_size:
                with db.atomic():
                    Document.insert_many(batch).on_conflict_replace().execute()
                total_indexed += len(batch)
                elapsed = time.monotonic() - start_time
                rate = total_indexed / elapsed if elapsed > 0 else 0.0
                log.info(f"Indexed {total_indexed:,} documents ({rate:,.0f} docs/s)")
                batch.clear()

        if batch:
            with db.atomic():
                Document.insert_many(batch).on_conflict_replace().execute()
            total_indexed += len(batch)
            batch.clear()
    finally:
        db.close()

    elapsed = time.monotonic() - start_time
    rate = total_indexed / elapsed if elapsed > 0 else 0.0
    log.info(
        f"Completed indexing {total_indexed:,} documents into {out_path} "
        f"in {elapsed:.2f}s ({rate:,.0f} docs/s)"
    )
    return total_indexed


class CorpusStore:
    """Read-only random-access lookup wrapper around a Peewee SQLite corpus database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Corpus SQLite database not found: {self.db_path}")
        uri = f"{self.db_path.resolve().as_uri()}?mode=ro"
        self._db = SqliteDatabase(uri, uri=True, check_same_thread=False)
        self._model = Document.bind_ctx(self._db)
        self._db.connect()

    def close(self) -> None:
        if not self._db.is_closed():
            self._db.close()

    def __enter__(self) -> "CorpusStore":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def get(self, doc_id: str) -> DocumentSchema | None:
        """Retrieve a single document by ID in O(log N) time."""
        with self._model:
            doc = Document.get_or_none(Document.id == doc_id)
            if doc is None:
                return None
            return DocumentSchema.model_validate(doc)

    def get_many(self, doc_ids: Iterable[str]) -> dict[str, DocumentSchema]:
        """Retrieve multiple documents by ID in a single query."""
        ids = list(dict.fromkeys(doc_ids))
        if not ids:
            return {}
        with self._model:
            query = Document.select().where(Document.id.in_(ids))
            return {doc.id: DocumentSchema.model_validate(doc) for doc in query}

    def count(self) -> int:
        """Return total number of documents in the SQLite database."""
        with self._model:
            return int(Document.select().count())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Index a JSONL or Parquet corpus into a SQLite database for random access."
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        type=Path,
        help="Path to input corpus file (.jsonl, .jsonl.gz, or .parquet)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Path to output SQLite database (.sqlite / .db)",
    )
    parser.add_argument(
        "-b",
        "--batch-size",
        type=int,
        default=2_000,
        help="Number of records per SQLite transaction batch (default: 2000)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip per-record Pydantic validation for faster bulk ingestion",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output SQLite database if it already exists",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable progress logging",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(name)s:%(levelname)s: %(message)s",
    )

    index_corpus(
        args.input,
        args.output,
        batch_size=args.batch_size,
        validate=not args.no_validate,
        overwrite=args.overwrite,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

