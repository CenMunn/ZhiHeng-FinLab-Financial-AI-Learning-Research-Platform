import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"src"))


def source_fixture(root: Path):
    pdf=root/"data/research_checklists/sources/000692_1225240687.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.7 synthetic integrity fixture")
    sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
    url="https://static.cninfo.com.cn/finalpage/2026-04-29/1225240687.PDF"
    case={"stock_code":"000692","report_id":"1225240687","fiscal_year":"2025",
        "company":"惠天热电","period_kind":"annual","scope":"consolidated","sha256":sha,
        "source_url":url,"local_pdf":"data/research_checklists/sources/000692_1225240687.pdf",
        "audit_warning":"","source_cutoff":"2026-09-29"}
    metric={"stock_code":"000692","report_id":"1225240687","period_kind":"annual",
        "metric":"revenue","unit":"CNY","current":"2103585508.31",
        "current_period_start":"2025-01-01","current_period_end":"2025-12-31",
        "current_evidence_id":"revenue-current"}
    evidence={"evidence_id":"revenue-current","report_id":"1225240687","stock_code":"000692",
        "statement_scope":"consolidated","period_kind":"annual","period_role":"current",
        "metric":"revenue","value":"2103585508.31","unit":"CNY",
        "source_value_signed":"2103585508.31","multiplier_to_cny":"1","source_pdf_sha256":sha,
        "source_url":url,"pdf_page":69,"printed_page":69,"unit_evidence_page":64,
        "excerpt":"营业收入 2,103,585,508.31", "value_period_start":"2025-01-01",
        "value_period_end":"2025-12-31","review_status":"pending_human",
        "availability_review_status":"unverified","version_history_status":"incomplete"}
    payload={"queries":{name:{"rows":[row]} for name,row in
        (("workspace_cases",case),("workspace_metrics",metric),("workspace_evidence",evidence))}}
    source=root/"source.json"
    source.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
    return source,pdf,payload


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.source,self.pdf,self.payload=source_fixture(self.root)

    def tearDown(self): self.tmp.cleanup()

    def load(self):
        from platform_app.adapters.corporate_risk import load_huitian_2025
        return load_huitian_2025(self.source,self.root)

    def write(self): self.source.write_text(json.dumps(self.payload,ensure_ascii=False),encoding="utf-8")

    def test_preserves_value_scope_period_evidence_and_quality(self):
        case=self.load()
        self.assertEqual((case.revenue,case.days,case.scope),("2103585508.31",365,"consolidated"))
        self.assertEqual(case.evidence.value_page,69)
        self.assertEqual(case.evidence.header_pages,(64,))
        self.assertEqual(case.evidence.review_status,"pending_human")
        self.assertEqual(case.evidence.availability_status,"unverified")
        self.assertEqual(case.evidence.file_status,"verified_at_load")
        self.assertTrue(any("季节" in text for text in case.limitations))

    def test_missing_and_changed_pdf_do_not_rewrite_financial_identity(self):
        first=self.load()
        self.pdf.write_bytes(b"changed")
        changed=self.load()
        self.assertEqual(changed.evidence.file_status,"changed")
        self.assertEqual(first.snapshot_sha256,changed.snapshot_sha256)
        self.pdf.unlink()
        missing=self.load()
        self.assertEqual(missing.evidence.file_status,"missing")
        self.assertEqual(first.snapshot_sha256,missing.snapshot_sha256)

    def test_ambiguous_or_missing_rows_are_rejected(self):
        rows=self.payload["queries"]["workspace_metrics"]["rows"]
        rows.append(copy.deepcopy(rows[0]));self.write()
        with self.assertRaises(ValueError): self.load()
        rows.clear();self.write()
        with self.assertRaises(ValueError): self.load()

    def test_unit_conversion_is_reconciled_and_used_once(self):
        ev=self.payload["queries"]["workspace_evidence"]["rows"][0]
        ev["source_value_signed"]="2103585.50831";ev["multiplier_to_cny"]="1000";self.write()
        self.assertEqual(self.load().revenue,"2103585508.31")
        ev["multiplier_to_cny"]="10000";self.write()
        with self.assertRaises(ValueError): self.load()

    def test_mixed_scope_dates_hashes_and_unregistered_path_are_rejected(self):
        for name,value in (("statement_scope","parent"),("value_period_end","2024-12-31"),
                           ("source_pdf_sha256","a"*64),("unit","USD")):
            with self.subTest(name=name):
                original=copy.deepcopy(self.payload)
                self.payload["queries"]["workspace_evidence"]["rows"][0][name]=value;self.write()
                with self.assertRaises(ValueError): self.load()
                self.payload=original
        self.payload["queries"]["workspace_cases"]["rows"][0]["local_pdf"]="../../outside.pdf";self.write()
        with self.assertRaises(ValueError): self.load()

    def test_case_service_returns_registered_immutable_snapshot_only(self):
        from platform_app.evidence.service import CaseService
        case=self.load(); service=CaseService((case,))
        self.assertEqual(service.get(case.snapshot_id),case)
        with self.assertRaises(KeyError): service.get("not-registered")


if __name__ == "__main__": unittest.main()
