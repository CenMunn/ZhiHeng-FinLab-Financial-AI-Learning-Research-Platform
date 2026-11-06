import copy
import hashlib
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from research.ingest.fetch_finqa import COMMIT, FILES, REPOSITORY


def row(identifier="A/2020/page_1.pdf-1"):
    return {"id": identifier, "pre_text": ["Revenue increased", "Costs decreased"],
            "post_text": [], "table": [["metric", "2020", "2019"], ["revenue", "10", "8"]],
            "qa": {"question": "What was revenue in 2020?", "gold_inds": {"table_1": "IGNORED_GOLD"},
                   "answer": "SECRET_ANSWER", "program": "SECRET_PROGRAM", "model_input": "SECRET_INPUT"},
            "text_retrieved": "SECRET_RETRIEVED"}


def fixture(data, train, dev):
    files = []
    for name in FILES:
        path = data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        value = json.dumps(train if name == "dataset/train.json" else dev).encode() if name.endswith(".json") else b"MIT fixture"
        path.write_bytes(value)
        files.append({"path": name, "url": f"https://raw.githubusercontent.com/czyssrs/FinQA/{COMMIT}/{name}",
                      "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()})
    (data / "acquisition.json").write_text(json.dumps({"commit": COMMIT, "repository": REPOSITORY,
        "allowed_files": list(FILES), "files": files, "test_data_fetched": False}), encoding="utf-8")


class PreparationTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module("research.training.prepare_finqa")
        except ModuleNotFoundError:
            self.fail("M2 preparation implementation is missing")

    def prepare(self, train, dev=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data, output = root / "data", root / "out"
        fixture(data, train, dev or [row("Z/2021/page_2.pdf-1")])
        manifest = self.module().prepare(data, output)
        return data, output, manifest

    def test_inference_whitelist_ignores_gold_answer_program_and_retrieved(self):
        _, output, manifest = self.prepare([row()])
        inference = (output / "inference/train.jsonl").read_text(encoding="utf-8")
        for text in ("IGNORED_GOLD", "SECRET", "gold_ids", "gold_inds", '"answer"', '"program"'):
            self.assertNotIn(text, inference)
        record = json.loads(inference)
        self.assertIn("2020", record["candidates"]["table_1"])
        self.assertEqual(set(record["bm25_top20"]), set(record["candidates"]))
        self.assertEqual(manifest["eligible_counts"], {"train": 1, "dev": 1})
        self.assertEqual(json.loads((output / "labels/train.jsonl").read_text())["gold_ids"], ["table_1"])

    def test_invalid_gold_is_quarantined_without_negative_index_repair(self):
        invalid = row("A/2020/page_1.pdf-2")
        invalid["qa"]["gold_inds"] = {"text_-1": "Costs decreased"}
        _, output, manifest = self.prepare([row(), invalid])
        self.assertEqual(manifest["eligible_counts"]["train"], 1)
        quarantine = json.loads((output / "quarantine.jsonl").read_text())
        self.assertEqual(quarantine["missing_gold_ids"], ["text_-1"])
        self.assertNotIn("text_-1", (output / "inference/train.jsonl").read_text())

    def test_source_tampering_and_unexpected_receipt_are_rejected(self):
        data, output, _ = self.prepare([row()])
        (data / "dataset/train.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "source"):
            self.module().prepare(data, output)
        fixture(data, [row()], [row("Z/2021/page_2.pdf-1")])
        receipt_path = data / "acquisition.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["files"].append({"path": "dataset/test.json"})
        receipt_path.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(ValueError, "allowlist"):
            self.module().prepare(data, output)

    def test_company_diagnostic_is_train_only_disjoint_and_deterministic(self):
        rows = [row(f"C{i}/2020/page_1.pdf-1") for i in range(20)]
        _, output, first = self.prepare(rows)
        splits = json.loads((output / "splits.json").read_text())
        groups = splits["train_company_diagnostic"]
        fit, validation = groups["fit_ids"], groups["validation_ids"]
        self.assertTrue(fit and validation)
        self.assertFalse(set(fit) & set(validation))
        self.assertEqual(set(fit + validation), {r["id"] for r in rows})
        self.assertFalse({v.split('/')[0] for v in fit} & {v.split('/')[0] for v in validation})
        data = output.parent / "data"
        self.assertEqual(first, self.module().prepare(data, output))
        for relative, sha in first["outputs_sha256"].items():
            self.assertEqual(hashlib.sha256((output / relative).read_bytes()).hexdigest(), sha)

    def test_duplicate_ids_empty_labels_and_missing_question_are_quarantined(self):
        empty = row("B/2020/page_1.pdf-1")
        empty["qa"]["gold_inds"] = {}
        no_question = row("C/2020/page_1.pdf-1")
        no_question["qa"]["question"] = " "
        _, output, manifest = self.prepare([row(), copy.deepcopy(row()), empty, no_question])
        self.assertEqual(manifest["eligible_counts"]["train"], 0)
        self.assertEqual(len((output / "quarantine.jsonl").read_text().splitlines()), 4)

    def test_more_than_five_gold_fragments_stay_in_denominator(self):
        record = row()
        record["pre_text"] = [f"Source {i}" for i in range(6)]
        record["qa"]["gold_inds"] = {f"text_{i}": f"Source {i}" for i in range(6)}
        _, _, manifest = self.prepare([record])
        self.assertEqual(manifest["eligible_counts"]["train"], 1)
        self.assertEqual(manifest["gold_over_five_counts"]["train"], 1)


if __name__ == "__main__":
    unittest.main()
