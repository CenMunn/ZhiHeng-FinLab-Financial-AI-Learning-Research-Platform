import importlib.util
import sys
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "evaluation" / "audit_finqa.py"


def audit_module():
    if not MODULE.exists():
        raise AssertionError("FinQA audit implementation is not present yet")
    spec = importlib.util.spec_from_file_location("finqa_audit", MODULE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AuditBehaviorTests(unittest.TestCase):
    def test_candidates_use_only_source_fields_and_keep_year_headers(self):
        audit = audit_module()
        record = {"pre_text": ["Source introduction"], "post_text": ["Source ending"],
                  "table": [["metric", "2024", "2023"], ["revenue", "10", "8"]],
                  "qa": {"gold_inds": {"text_0": "GOLD_ONLY"}, "answer": "ANSWER_ONLY",
                         "model_input": "LEAKED_INPUT"},
                  "text_retrieved": "RETRIEVER_ONLY"}
        candidates = audit.build_candidates(record)
        self.assertEqual(candidates["text_1"], "Source ending")
        self.assertEqual(candidates["table_1"], "metric the revenue of 2024 is 10 ; the revenue of 2023 is 8 ;")
        joined = " ".join(candidates.values())
        for forbidden in ("GOLD_ONLY", "ANSWER_ONLY", "LEAKED_INPUT", "RETRIEVER_ONLY"):
            self.assertNotIn(forbidden, joined)

    def test_report_group_does_not_treat_each_page_as_a_report(self):
        audit = audit_module()
        first = audit.parse_id("INTC/2015/page_41.pdf-4")
        second = audit.parse_id("INTC/2015/page_44.pdf-1")
        self.assertEqual(first["annual_report_id"], second["annual_report_id"])
        self.assertNotEqual(first["page_id"], second["page_id"])
        with self.assertRaises(ValueError):
            audit.parse_id("unknown_id")

    def test_missing_candidate_stays_a_coverage_failure(self):
        audit = audit_module()
        self.assertEqual(audit.coverage({"text_1", "table_2"}, ["text_1", "table_2"]), 1)
        self.assertEqual(audit.coverage({"text_1", "table_2"}, ["text_1"]), 0)
        self.assertEqual(audit.coverage({"text_1"}, ["table_2"]), 0)
        with self.assertRaises(ValueError):
            audit.coverage(set(), ["table_2"])

    def test_bm25_ranks_evidence_without_labels_and_breaks_ties_stably(self):
        audit = audit_module()
        candidates = {"text_0": "revenue revenue", "text_1": "receivables collection",
                      "text_2": "receivables collection"}
        ranked = audit.bm25_rank("receivables", candidates)
        self.assertEqual(ranked[:2], ["text_1", "text_2"])
        self.assertEqual(set(ranked), set(candidates))

    def test_ragged_table_is_reported_instead_of_silently_truncated(self):
        audit = audit_module()
        with self.assertRaises(ValueError):
            audit.build_candidates({"pre_text": [], "post_text": [],
                                    "table": [["metric", "2024"], ["revenue", "10", "8"]]})


if __name__ == "__main__":
    unittest.main()
