"""FastAPI application and CLI entry point for the Change Detection Evaluation Explorer."""

import argparse
import logging
from pathlib import Path
import sys
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cdet_scorer.explorer.engine import ExplorerEngine, RollupMode
from cdet_scorer.index_corpus import CorpusStore
from cdet_scorer.measures import RelLevel, str_to_gain

log = logging.getLogger("explorer.app")


class ConfigUpdateRequest(BaseModel):
    min_rel_level: str | None = None
    max_depth: int | None = None


def create_app(
    engine: ExplorerEngine,
    corpus_store: CorpusStore | None = None,
) -> FastAPI:
    app = FastAPI(
        title="TREC Change Detection Evaluation Explorer",
        version="1.0.0",
    )
    app.state.engine = engine
    app.state.corpus_store = corpus_store

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        cfg = engine.get_config()
        cfg["has_corpus"] = corpus_store is not None
        return cfg

    @app.post("/api/config")
    def update_config(req: ConfigUpdateRequest) -> dict[str, Any]:
        if req.min_rel_level is not None and req.min_rel_level.lower() not in {
            "awareness",
            "assessment",
            "action",
        }:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid min_rel_level: {req.min_rel_level}. Must be awareness, assessment, or action.",
            )
        if req.max_depth is not None and req.max_depth < 1:
            raise HTTPException(
                status_code=400,
                detail="max_depth must be >= 1",
            )
        cfg = engine.set_config(
            min_rel_level=req.min_rel_level,
            max_depth=req.max_depth,
        )
        cfg["has_corpus"] = corpus_store is not None
        return cfg

    @app.get("/api/runs/summary")
    def get_runs_summary(
        rollup: RollupMode = Query(default="micro"),
    ) -> dict[str, Any]:
        summary = engine.get_runs_summary(rollup=rollup)
        summary["config"]["has_corpus"] = corpus_store is not None
        return summary

    @app.get("/api/topics")
    def get_topics() -> dict[str, Any]:
        overview = engine.get_topics_overview()
        overview["config"]["has_corpus"] = corpus_store is not None
        return overview

    @app.get("/api/topics/{tid}")
    def get_topic_detail(tid: str) -> dict[str, Any]:
        try:
            return engine.get_topic_detail(tid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/topics/{tid}/calendar")
    def get_topic_calendar(
        tid: str,
        active_days_only: bool = Query(default=False),
    ) -> dict[str, Any]:
        try:
            return engine.get_topic_calendar(tid, active_days_only=active_days_only)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/cell/{tid}/{day}/{qid}")
    def get_cell_detail(tid: str, day: str, qid: str) -> dict[str, Any]:
        try:
            return engine.get_cell_detail(tid, day, qid)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/docs/{doc_id}")
    def get_document(doc_id: str) -> dict[str, Any]:
        judgments = engine.get_doc_judgments(doc_id)
        doc_obj = None
        if corpus_store is not None:
            doc = corpus_store.get(doc_id)
            if doc is not None:
                doc_obj = doc.model_dump()
        if doc_obj is None and not judgments:
            raise HTTPException(
                status_code=404,
                detail=f"Document '{doc_id}' not found in corpus or qrels.",
            )
        return {
            "id": doc_id,
            "document": doc_obj,
            "judgments": judgments,
        }

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/")
        def index() -> Any:
            index_file = static_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return JSONResponse({"status": "ok", "message": "Explorer API running"})

    return app


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    parser = argparse.ArgumentParser(
        description="Launch the TREC Change Detection Evaluation Explorer web server."
    )
    parser.add_argument(
        "--qrels",
        required=True,
        type=Path,
        help="Path to the qrels file",
    )
    parser.add_argument(
        "--topics",
        required=True,
        type=Path,
        help="Path to the topics .jsonl file",
    )
    parser.add_argument(
        "--runs",
        required=True,
        nargs="+",
        type=Path,
        help="One or more run files to score and compare",
    )
    parser.add_argument(
        "--corpus-db",
        type=Path,
        default=None,
        help="Optional path to the indexed SQLite corpus database (.sqlite)",
    )
    parser.add_argument(
        "-l",
        "--min_rel_level",
        type=str_to_gain,
        default=RelLevel.AWARENESS,
        help="Initial minimum relevance level (awareness, assessment, action)",
    )
    parser.add_argument(
        "-M",
        "--max_depth",
        type=int,
        default=100,
        help="Initial maximum ranking depth (default: 100)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind (default: 8000)",
    )

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s:%(levelname)s: %(message)s",
    )

    corpus_store = CorpusStore(args.corpus_db) if args.corpus_db else None
    engine = ExplorerEngine(
        qrels_path=args.qrels,
        topics_path=args.topics,
        run_paths=args.runs,
        min_rel_level=args.min_rel_level,
        max_depth=args.max_depth,
    )
    app = create_app(engine, corpus_store=corpus_store)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
