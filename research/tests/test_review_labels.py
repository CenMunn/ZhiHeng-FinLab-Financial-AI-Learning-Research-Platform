import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest

from research.evaluation.audit_finqa import digest
from research.ingest.fetch_finqa import COMMIT
from research.tests.test_training_preparation import fixture, row
from research.training.prepare_finqa import prepare


class ReviewTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module("research.training.review_labels")
        except ModuleNotFoundError:
            self.fail("Review-label implementation is missing")

    def queue(self):
        record = {"question_id": "A/2020/page_1.pdf-1", "split": "train", "question": "Revenue?",
                  "serialization": "finqa-header-aware-v1", "candidates": {"text_0": "Revenue 10", "text_1": "Costs 5"},
                  "bm25_top20": ["text_0", "text_1"]}
        return self.module().make_review_queue([record], "train", {record["question_id"]: ["text_0"]})

    def test_queue_is_unreviewed_train_only_and_does_not_make_nongold_negative(self):
        queue = self.queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["evidence_id"], "text_1")
        self.assertEqual(queue[0]["label"], "uncertain")
        self.assertEqual(queue[0]["review_status"], "pending")
        result = self.module().validate_reviews(queue, queue)
        self.assertEqual(result["confirmed_negatives"], [])
        self.assertEqual(result["pending"], 1)
        with self.assertRaisesRegex(ValueError, "train"):
            self.module().make_review_queue([], "dev", {})

    def completed(self, label="confirmed_conflict"):
        queue = self.queue()
        reviewed = copy.deepcopy(queue)
        reviewed[0].update(review_status="completed", label=label, reviewer="fixture-reviewer",
                           reviewer_type="human", rationale="Costs measure differs from requested revenue.",
                           conflict_type="metric" if label == "confirmed_conflict" else None)
        return queue, reviewed

    def test_only_completed_human_confirmed_conflicts_export(self):
        queue, reviewed = self.completed()
        self.assertEqual(len(self.module().validate_reviews(reviewed, queue)["confirmed_negatives"]), 1)
        for label in ("support", "uncertain"):
            queue, reviewed = self.completed(label)
            self.assertEqual(self.module().validate_reviews(reviewed, queue)["confirmed_negatives"], [])

    def test_pending_negative_missing_reason_or_machine_review_is_rejected(self):
        for patch in ({"review_status": "pending"}, {"rationale": ""}, {"reviewer_type": "assistant"},
                      {"reviewer": None}, {"conflict_type": "guess"}):
            queue, reviewed = self.completed()
            reviewed[0].update(patch)
            with self.assertRaises(ValueError):
                self.module().validate_reviews(reviewed, queue)

    def test_tampered_source_unknown_duplicate_and_dev_are_rejected(self):
        for field, value in (("evidence_text", "Altered"), ("question", "Altered?"),
                             ("source_context", {"text_1": "Altered"}), ("split", "dev"),
                             ("task_id", "unknown"), ("serialization", "unknown")):
            queue, reviewed = self.completed()
            reviewed[0][field] = value
            with self.assertRaises(ValueError):
                self.module().validate_reviews(reviewed, queue)
        queue, reviewed = self.completed()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.module().validate_reviews(reviewed * 2, queue)

    def test_partial_reviews_report_missing_tasks(self):
        queue = self.queue()
        result = self.module().validate_reviews([], queue)
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["confirmed_negatives"], [])

    def package_fixture(self, invalid_sample=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        rows = [row(f"C{i}/2020/page_1.pdf-1") for i in range(31)]
        selected = sorted((r["id"] for r in rows), key=lambda q: digest([COMMIT, "train", q]))[:30]
        if invalid_sample:
            next(r for r in rows if r["id"] == selected[0])["qa"]["gold_inds"] = {"text_-1": "bad"}
        fixture(root / "data", rows, [row("Z/2021/page_2.pdf-1")])
        prepare(root / "data", root / "prepared")
        pilot = root / "pilot.json"
        pilot.write_text(json.dumps([{"split": "train", "question_id": q} for q in selected]))
        return root, pilot, selected, {r["id"] for r in rows}

    def test_package_rejects_wrong_manifest_identity_even_with_matching_file_hashes(self):
        for field, value in (("commit", "WRONG"), ("repository", "https://example.com"),
                             ("schema_version", "unknown"), ("serialization", "unknown"),
                             ("candidate_scope", "global_corpus"), ("test_content_accessed", True)):
            root, pilot, _, _ = self.package_fixture()
            manifest_path = root / "prepared/manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest[field] = value
            manifest_path.write_text(json.dumps(manifest))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "identity"):
                self.module().create_package(root / "prepared", pilot, root / "review")

    def test_package_rejects_same_count_substitution_outside_original_pilot(self):
        root, pilot, selected, all_ids = self.package_fixture()
        selected[-1] = next(iter(all_ids - set(selected)))
        pilot.write_text(json.dumps([{"split": "train", "question_id": q} for q in selected]))
        with self.assertRaisesRegex(ValueError, "fixed"):
            self.module().create_package(root / "prepared", pilot, root / "review")

    def test_quarantined_pilot_item_is_not_silently_replaced(self):
        root, pilot, _, _ = self.package_fixture(invalid_sample=True)
        with self.assertRaisesRegex(ValueError, "ineligible"):
            self.module().create_package(root / "prepared", pilot, root / "review")


if __name__ == "__main__":
    unittest.main()
