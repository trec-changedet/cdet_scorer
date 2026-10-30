import gzip
import json
from pathlib import Path
import tempfile
import unittest

from cdet_scorer.api_types import DocumentSchema
from cdet_scorer.index_corpus import CorpusStore, index_corpus


class IndexCorpusTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmppath = Path(self.tmpdir.name)
        self.sample_docs = [
            {
                "id": "doc-001",
                "day": "2021-08-19",
                "date": "2021-08-19T10:15:00Z",
                "url": "https://example.org/1",
                "text": "First university program in Artificial Intelligence.",
            },
            {
                "id": "doc-002",
                "day": "2021-09-22",
                "date": "2021-09-22T14:30:00Z",
                "url": "https://example.org/2",
                "text": "Quantum computing degree announcement.",
            },
            {
                "id": "doc-003",
                "day": "2023-06-21",
                "date": "2023-06-21T08:00:00Z",
                "url": "https://example.org/3",
                "text": "Computer vision and AR/VR fellowship.",
            },
        ]

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_index_jsonl_and_random_access_lookup(self):
        jsonl_path = self.tmppath / "corpus.jsonl"
        db_path = self.tmppath / "corpus.sqlite"

        with jsonl_path.open("w", encoding="utf-8") as fp:
            for doc in self.sample_docs:
                fp.write(json.dumps(doc) + "\n")

        count = index_corpus(jsonl_path, db_path, batch_size=2, validate=True)
        self.assertEqual(count, 3)
        self.assertTrue(db_path.exists())

        with CorpusStore(db_path) as store:
            self.assertEqual(store.count(), 3)

            doc2 = store.get("doc-002")
            self.assertIsNotNone(doc2)
            assert doc2 is not None
            self.assertIsInstance(doc2, DocumentSchema)
            self.assertEqual(doc2.id, "doc-002")
            self.assertEqual(doc2.day, "2021-09-22")
            self.assertEqual(doc2.url, "https://example.org/2")
            self.assertEqual(doc2.text, "Quantum computing degree announcement.")

            self.assertIsNone(store.get("nonexistent-doc"))

            batch = store.get_many(["doc-003", "doc-001", "missing"])
            self.assertEqual(set(batch.keys()), {"doc-001", "doc-003"})
            self.assertEqual(batch["doc-003"].day, "2023-06-21")

    def test_index_no_validate_and_overwrite(self):
        jsonl_path = self.tmppath / "corpus.jsonl"
        db_path = self.tmppath / "corpus.sqlite"

        with jsonl_path.open("w", encoding="utf-8") as fp:
            fp.write(json.dumps(self.sample_docs[0]) + "\n")

        index_corpus(jsonl_path, db_path, validate=False)
        with CorpusStore(db_path) as store:
            self.assertEqual(store.count(), 1)

        # Write two docs and overwrite
        with jsonl_path.open("w", encoding="utf-8") as fp:
            for doc in self.sample_docs[:2]:
                fp.write(json.dumps(doc) + "\n")

        index_corpus(jsonl_path, db_path, validate=False, overwrite=True)
        with CorpusStore(db_path) as store:
            self.assertEqual(store.count(), 2)

    def test_index_gzip_compressed_jsonl(self):
        gz_path = self.tmppath / "corpus.jsonl.gz"
        db_path = self.tmppath / "corpus.sqlite"

        with gzip.open(gz_path, "wt", encoding="utf-8") as fp:
            for doc in self.sample_docs:
                fp.write(json.dumps(doc) + "\n")

        count = index_corpus(gz_path, db_path, batch_size=2, validate=True)
        self.assertEqual(count, 3)

        with CorpusStore(db_path) as store:
            self.assertEqual(store.count(), 3)
            doc1 = store.get("doc-001")
            self.assertIsNotNone(doc1)
            assert doc1 is not None
            self.assertEqual(doc1.text, "First university program in Artificial Intelligence.")

    def test_index_jsonl_without_day_field_derives_day_from_date(self):
        jsonl_path = self.tmppath / "no_day.jsonl"
        db_path = self.tmppath / "no_day.sqlite"

        raw_doc = {
            "id": "0e4ae416-c558-4741-9e4a-4988869bcd74_2154817",
            "text": "Sample text without explicit day field.",
            "url": "https://example.org/article",
            "date": "2021-08-01T02:08:10.000Z",
        }
        with jsonl_path.open("w", encoding="utf-8") as fp:
            fp.write(json.dumps(raw_doc) + "\n")

        count = index_corpus(jsonl_path, db_path, validate=True)
        self.assertEqual(count, 1)

        with CorpusStore(db_path) as store:
            doc = store.get(raw_doc["id"])
            self.assertIsNotNone(doc)
            assert doc is not None
            self.assertEqual(doc.day, "2021-08-01")
            self.assertEqual(doc.date, "2021-08-01T02:08:10.000Z")


if __name__ == "__main__":
    unittest.main()
