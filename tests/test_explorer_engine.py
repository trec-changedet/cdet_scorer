import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from cdet_scorer.cli import main as cli_main
from cdet_scorer.explorer.app import create_app
from cdet_scorer.explorer.engine import ExplorerEngine


def _parse_eval_all_means_text(eval_text: str) -> dict[str, str]:
    means: dict[str, str] = {}
    for line in eval_text.splitlines():
        parts = line.strip().split()
        if len(parts) == 5 and parts[0] == "all" and parts[1] == "all":
            scope = parts[2]  # 'all' or 'qranking'
            measure = parts[3]
            val = parts[4]
            key = measure if scope == "all" else f"qranking_{measure}"
            means[key] = val
    return means


class ExplorerEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.sample_dir = root / "sample-data"
        cls.engine = ExplorerEngine(
            qrels_path=cls.sample_dir / "qrels",
            topics_path=cls.sample_dir / "test-topics-all-docs.jsonl",
            run_paths=[
                cls.sample_dir / "idaccs-csplx-z290",
                cls.sample_dir / "bm25-qwen-splade",
            ],
        )
        cls.client = TestClient(create_app(cls.engine))

    def test_micro_means_match_cli_output(self):
        summary = self.engine.get_runs_summary(rollup="micro")
        runs_by_tag = {r["runtag"]: r for r in summary["runs"]}

        for runtag in ("idaccs-csplx-z290", "bm25-qwen-splade"):
            buf = io.StringIO()
            argv = [
                "cdet_scorer.cli",
                str(self.sample_dir / "qrels"),
                str(self.sample_dir / "test-topics-all-docs.jsonl"),
                str(self.sample_dir / runtag),
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(buf):
                cli_main()
            ref = _parse_eval_all_means_text(buf.getvalue())
            metrics = runs_by_tag[runtag]["metrics"]

            for int_key in ("num_topics", "num_days", "num_qs", "num_ret", "num_rel", "num_rel_ret", "unjudged"):
                self.assertEqual(str(metrics[int_key]), ref[int_key], f"{runtag} {int_key}")

            for float_key in ("recip_rank'", "ap'", "ndcg'", "rbp'(p=0.8)", "abstention", "noise"):
                self.assertEqual(
                    f"{metrics[float_key]:.4f}",
                    ref[float_key],
                    f"{runtag} {float_key}",
                )

            self.assertEqual(
                f"{metrics['rbo(p=0.8)']:.4f}",
                ref["qranking_rbo(p=0.8)"],
                f"{runtag} rbo(p=0.8)",
            )

    def test_behavioral_partition_identities(self):
        summary = self.engine.get_runs_summary(rollup="micro")
        for run in summary["runs"]:
            b = run["behavioral"]
            self.assertEqual(
                b["answerable_points"] + b["nil_points"],
                b["total_points"],
            )
            self.assertEqual(
                b["event_hit"] + b["zero_hit_trigger"] + b["missed_event"],
                b["answerable_points"],
            )
            self.assertEqual(
                b["true_abstention"] + b["false_alarm"],
                b["nil_points"],
            )
            # Unconditional Prime == Trigger Rate * Active Prime
            trig_rate = b["trigger_rate_on_answerable"]
            active_ndcg = b["active_prime"]["ndcg'"]
            uncond_ndcg = run["all_rollups"]["micro"]["ndcg'"]
            self.assertAlmostEqual(trig_rate * active_ndcg, uncond_ndcg, places=6)

    def test_api_endpoints(self):
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["min_rel_level"], "awareness")

        resp = self.client.get("/api/runs/summary?rollup=macro_topic")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["rollup"], "macro_topic")
        self.assertIn("has_corpus", resp.json()["config"])
        self.assertEqual(len(resp.json()["runs"]), 2)

        resp = self.client.get("/api/topics")
        self.assertEqual(resp.status_code, 200)
        topics = resp.json()["topics"]
        self.assertEqual(len(topics), 31)
        self.assertEqual(topics[0]["tid"], "cd2026_001")

        resp = self.client.get("/api/topics/cd2026_001")
        self.assertEqual(resp.status_code, 200)
        detail = resp.json()
        self.assertEqual(detail["tid"], "cd2026_001")
        self.assertGreater(len(detail["questions"]), 0)

        resp = self.client.get("/api/topics/cd2026_001/calendar?active_days_only=true")
        self.assertEqual(resp.status_code, 200)
        cal = resp.json()
        self.assertLess(len(cal["days"]), 178)

        resp = self.client.get("/api/cell/cd2026_001/2023-06-21/q_8")
        self.assertEqual(resp.status_code, 200)
        cell = resp.json()
        self.assertEqual(cell["num_rel"], 1)
        self.assertEqual(
            cell["runs"]["idaccs-csplx-z290"]["state"],
            "event_hit",
        )
        self.assertAlmostEqual(
            cell["runs"]["idaccs-csplx-z290"]["scores"]["ndcg'"],
            1.0,
        )

        # Static frontend assets
        resp_index = self.client.get("/")
        self.assertEqual(resp_index.status_code, 200)
        self.assertIn("Change Detection Evaluation Explorer", resp_index.text)
        self.assertIn("/assets/", resp_index.text)


if __name__ == "__main__":
    unittest.main()
