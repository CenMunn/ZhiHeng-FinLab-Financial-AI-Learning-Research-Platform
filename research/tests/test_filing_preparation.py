"""D30 preparation qualification and independent human-review validation."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from research.filing_development import preparation


CANDIDATES = [
    {"symbol": "000333", "name": "美的集团", "period": "2025Q1"},
    {"symbol": "601318", "name": "中国平安", "period": "2025Q1"},
    {"symbol": "600887", "name": "伊利股份", "period": "2025Q1"},
]
METRICS = ("revenue", "net_profit_parent", "operating_cashflow")
COMPANIES = {"600519": "贵州茅台", "600036": "招商银行", "600585": "海螺水泥"}
MANUAL_COLUMNS = (
    "manual_value", "manual_unit", "manual_currency", "manual_period", "manual_scope",
    "value_page", "header_pages", "quote", "reviewer", "reviewed_at", "notes",
)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf8")


def metadata(candidate, identifier="1220000001"):
    return {
        "announcements": [{
            "secCode": candidate["symbol"], "secName": candidate["name"],
            "orgId": "official-org", "announcementId": identifier,
            "announcementTitle": "2025年第一季度报告",
            "announcementTime": int(datetime(2025, 4, 30, tzinfo=timezone(timedelta(hours=8))).timestamp() * 1000),
            "adjunctUrl": f"finalpage/2025-04-30/{identifier}.PDF", "adjunctType": "PDF",
        }],
        "totalAnnouncement": 1, "totalpages": 1, "hasMore": False,
    }


def organization_response(request):
    symbol = parse_qs(request.data.decode("ascii"))["keyWord"][0]
    candidate = next(c for c in CANDIDATES if c["symbol"] == symbol)
    return Response(json_bytes([{"code": symbol, "zwjc": candidate["name"], "orgId": "org" + symbol,
                                 "category": "A股"}]), request.full_url)


class Response:
    def __init__(self, raw, url, status=200, content_type="application/json"):
        self.raw = io.BytesIO(raw)
        self.url = url
        self.status = status
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, length=-1):
        return self.raw.read(length)

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, handler):
        self.handler = handler

    def open(self, request, timeout):
        return self.handler(request, timeout)


class PreparationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.corpus = self.project / "corpus.json"
        documents = []
        for symbol, company in COMPANIES.items():
            for period in ("2024Q1", "2025Q1"):
                doc_id = f"{symbol}-{period}"
                documents.append({
                    "doc_id": doc_id, "symbol": symbol, "period": period,
                    "title": company + period[:4] + "年第一季度报告", "page_count": 12,
                    "pdf_url": f"https://static.cninfo.com.cn/finalpage/{period[:4]}-04-30/{symbol}.PDF",
                    "pdf_path": f"frozen/{doc_id}/source.pdf",
                })
        self.corpus.write_bytes(json_bytes({"schema": "filing-extraction-corpus-v1", "documents": documents}))
        self.config = self.project / "config.json"
        self.config.write_bytes(json_bytes({
            "schema": "filing-development-design-v1", "new_evaluation_candidates": CANDIDATES,
        }))
        self.design = self.project / "design.md"
        self.design.write_text("Sealed metadata and PDF bytes only.\n", encoding="utf8")
        self.sealed_root = self.project / "sealed"
        self.kit_root = self.project / "human"
        replacements = {
            "PROJECT": self.project, "SOURCE_CORPUS": self.corpus,
            "SOURCE_CORPUS_SHA": hashlib.sha256(self.corpus.read_bytes()).hexdigest(),
            "CONFIG_PATH": self.config, "DESIGN_PATH": self.design,
            "SEALED_ROOT": self.sealed_root, "HUMAN_KIT_ROOT": self.kit_root,
        }
        for name, value in replacements.items():
            replacement = patch.object(preparation, name, value)
            replacement.start()
            self.addCleanup(replacement.stop)

    def make_kit(self):
        manifest = preparation.prepare_human_kit(output_dir=self.kit_root)
        path = self.kit_root / "checklist.csv"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            return manifest, path, list(reader), reader.fieldnames

    @staticmethod
    def write_rows(path, rows, columns):
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def complete(row):
        row.update(
            manual_value="-12.50", manual_unit="百万元", manual_currency="CNY",
            manual_period=row["doc_id"].split("-")[-1], manual_scope="consolidated",
            value_page="2", header_pages="2,9", quote="synthetic source quotation for validator testing",
            status="completed", reviewer="test reviewer", reviewed_at="2026-11-06T12:00:00+08:00",
        )

    def test_human_kit_has_exact_18_independent_blank_items_and_hashes(self):
        manifest, path, rows, _ = self.make_kit()
        self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(len(rows), 18)
        self.assertEqual({r["metric"] for r in rows}, set(METRICS))
        self.assertEqual(len({r["case_id"] for r in rows}), 18)
        self.assertEqual({r["company"] for r in rows}, set(COMPANIES.values()))
        for row in rows:
            self.assertEqual(row["status"], "unreviewed")
            self.assertTrue(all(row[column] == "" for column in MANUAL_COLUMNS))
        self.assertEqual(manifest["schema"], "filing-development-human-kit-v1")
        self.assertEqual((manifest["item_count"], manifest["completed"], manifest["status"]),
                         (18, 0, "pending_human_review"))
        for name, sha in manifest["artifacts"].items():
            self.assertEqual(hashlib.sha256((self.kit_root / name).read_bytes()).hexdigest(), sha)

    def test_human_kit_refuses_to_overwrite_an_existing_attempt(self):
        self.make_kit()
        original = (self.kit_root / "checklist.csv").read_bytes()
        with self.assertRaises(ValueError):
            preparation.prepare_human_kit(output_dir=self.kit_root)
        self.assertEqual((self.kit_root / "checklist.csv").read_bytes(), original)

    def test_changed_source_corpus_refused_before_creating_kit(self):
        self.corpus.write_bytes(self.corpus.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            preparation.prepare_human_kit(output_dir=self.kit_root)
        self.assertFalse(self.kit_root.exists())

    def test_blank_review_is_valid_pending_and_validation_is_read_only(self):
        _, path, _, _ = self.make_kit()
        original, corpus = path.read_bytes(), self.corpus.read_bytes()
        result = preparation.validate_review_csv(path)
        self.assertEqual((result["completed"], result["item_count"], result["status"]),
                         (0, 18, "pending_human_review"))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(self.corpus.read_bytes(), corpus)

    def test_review_summary_and_fingerprint_use_one_identical_byte_snapshot(self):
        _, path, rows, columns = self.make_kit()
        blank = path.read_bytes()
        original_read = Path.read_bytes

        def changed_after_read(file_path):
            raw = original_read(file_path)
            if file_path == path:
                for row in rows:
                    self.complete(row)
                self.write_rows(path, rows, columns)
            return raw

        with patch.object(Path, "read_bytes", changed_after_read):
            result = preparation.validate_review_csv(path)
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["review_csv_sha256"], hashlib.sha256(blank).hexdigest())

    def test_complete_review_uses_decimal_signed_values_and_later_header_pages(self):
        _, path, rows, columns = self.make_kit()
        for row in rows:
            self.complete(row)
        self.write_rows(path, rows, columns)
        original = path.read_bytes()
        result = preparation.validate_review_csv(path)
        self.assertEqual((result["completed"], result["status"]), (18, "review_complete"))
        self.assertEqual(path.read_bytes(), original)

    def test_completed_status_requires_every_financial_and_reviewer_evidence_field(self):
        _, path, rows, columns = self.make_kit()
        self.complete(rows[0])
        required = set(MANUAL_COLUMNS) - {"notes"}
        for column in required:
            with self.subTest(column=column):
                changed = [dict(row) for row in rows]
                changed[0][column] = ""
                self.write_rows(path, changed, columns)
                with self.assertRaises(ValueError):
                    preparation.validate_review_csv(path)

    def test_invalid_numeric_unit_currency_period_scope_pages_and_timestamp_refused(self):
        _, path, rows, columns = self.make_kit()
        self.complete(rows[0])
        changes = (
            ("manual_value", "NaN"), ("manual_value", "Infinity"), ("manual_value", "1,200.50"),
            ("manual_value", "1e6"), ("manual_value", "12%"), ("manual_unit", "元/股"),
            ("manual_currency", "USD"), ("manual_period", "2025Q1"),
            ("manual_scope", "parent"), ("value_page", "0"), ("value_page", "13"),
            ("header_pages", "2,13"), ("header_pages", "2,2"),
            ("reviewed_at", "2026-11-06"), ("reviewed_at", "2026-11-06T12:00:00"),
            ("status", "approved_by_ai"),
        )
        for column, value in changes:
            with self.subTest(column=column, value=value):
                changed = [dict(row) for row in rows]
                changed[0][column] = value
                self.write_rows(path, changed, columns)
                with self.assertRaises(ValueError):
                    preparation.validate_review_csv(path)

    def test_unknown_is_not_zero_and_disagreement_does_not_count_as_completed(self):
        _, path, rows, columns = self.make_kit()
        rows[0].update(status="uncertain", reviewer="r", reviewed_at="2026-11-06T12:00:00+08:00", notes="未找到足够证据")
        rows[1].update(status="disputed", manual_scope="parent", reviewer="r",
                       reviewed_at="2026-11-06T12:00:00+08:00", notes="范围有异议，保留记录")
        self.write_rows(path, rows, columns)
        result = preparation.validate_review_csv(path)
        self.assertEqual(result["completed"], 0)
        self.assertEqual(result["status"], "pending_human_review")
        rows[0]["notes"] = ""
        self.write_rows(path, rows, columns)
        with self.assertRaises(ValueError):
            preparation.validate_review_csv(path)

    def test_identity_duplicate_missing_item_and_duplicate_header_refused(self):
        _, path, rows, columns = self.make_kit()
        changes = []
        for field in ("case_id", "doc_id", "company", "metric", "source_url", "local_pdf"):
            changed = [dict(row) for row in rows]
            changed[0][field] += "tampered"
            changes.append(changed)
        changes.extend((rows[:-1], rows[:-1] + [dict(rows[0])], rows + [dict(rows[0])]))
        for changed in changes:
            self.write_rows(path, changed, columns)
            with self.assertRaises(ValueError):
                preparation.validate_review_csv(path)
        path.write_text(",".join(columns + ["status"]) + "\n", encoding="utf-8-sig")
        with self.assertRaises(ValueError):
            preparation.validate_review_csv(path)

    def test_unreviewed_cannot_hide_entered_human_values(self):
        _, path, rows, columns = self.make_kit()
        rows[0]["manual_value"] = "0"
        self.write_rows(path, rows, columns)
        with self.assertRaises(ValueError):
            preparation.validate_review_csv(path)

    def test_metadata_requires_exact_company_period_date_and_full_report(self):
        candidate = CANDIDATES[0]
        result = preparation.select_announcement(metadata(candidate), "000333", "2025Q1")
        self.assertEqual(result["publication_date"], "2025-04-30")
        self.assertEqual(result["pdf_url"], "https://static.cninfo.com.cn/finalpage/2025-04-30/1220000001.PDF")
        for key, value in (
            ("secCode", "600887"), ("secName", "另一家公司"),
            ("announcementTitle", "2025年第一季度报告摘要"),
            ("announcementTitle", "2025年第一季度报告（更正后）"),
            ("announcementTitle", "2024年第一季度报告"),
            ("announcementTime", 1761868800000),
            ("adjunctUrl", "https://unofficial.example/report.PDF"),
            ("adjunctUrl", "finalpage/2025-04-30/../1220000001.PDF"),
        ):
            with self.subTest(key=key):
                changed = metadata(candidate)
                changed["announcements"][0][key] = value
                with self.assertRaises(ValueError):
                    preparation.select_announcement(changed, "000333", "2025Q1")

    def test_missing_duplicate_or_incomplete_metadata_is_not_substituted(self):
        for payload in ({"announcements": [], "totalAnnouncement": 0}, metadata(CANDIDATES[0]), metadata(CANDIDATES[0])):
            if payload.get("announcements"):
                if payload.get("totalpages") == 1 and not payload.get("hasMore"):
                    payload["announcements"].append(dict(payload["announcements"][0], announcementId="1220000002"))
            with self.assertRaises(ValueError):
                preparation.select_announcement(payload, "000333", "2025Q1")
        payload = metadata(CANDIDATES[0])
        payload.update(totalpages=2, hasMore=True)
        with self.assertRaises(ValueError):
            preparation.select_announcement(payload, "000333", "2025Q1")

    def test_issuer_title_excludes_subsidiary_reports_posted_under_the_same_code(self):
        payload = metadata(CANDIDATES[1])
        subsidiary = dict(payload["announcements"][0], announcementTitle="中国平安：平安银行股份有限公司2025年第一季度报告")
        notice = dict(payload["announcements"][0], announcementTitle="中国平安关于披露平安银行2025年第一季度报告的公告")
        issuer = dict(payload["announcements"][0], announcementTitle="中国平安2025年第一季度报告")
        payload.update(announcements=[subsidiary, notice, issuer], totalAnnouncement=3)
        result = preparation.select_announcement(payload, "601318", "2025Q1")
        self.assertEqual(result["title"], "中国平安2025年第一季度报告")
        payload.update(announcements=[subsidiary], totalAnnouncement=1)
        with self.assertRaises(ValueError):
            preparation.select_announcement(payload, "601318", "2025Q1")

    def test_q1_synonym_title_retains_exact_issuer_period_and_full_report_requirements(self):
        payload = metadata(CANDIDATES[0])
        for title in ("2025年一季度报告", "美的集团：2025年一季度报告全文",
                      "美的集团股份有限公司2025年第一季度报告"):
            payload["announcements"][0]["announcementTitle"] = title
            self.assertEqual(preparation.select_announcement(payload, "000333", "2025Q1")["title"], title)
        for title in ("2025年一季度报告摘要", "2025年一季度报告（英文）", "2025年一季度报告（修订）",
                      "美的集团：子公司2025年一季度报告", "2025年半年度报告", "2024年一季度报告"):
            payload["announcements"][0]["announcementTitle"] = title
            with self.assertRaises(ValueError):
                preparation.select_announcement(payload, "000333", "2025Q1")

    def cached_source(self):
        folder = self.sealed_root / "previous"
        documents = []
        for candidate in CANDIDATES:
            dest = folder / "documents" / (candidate["symbol"] + "-2025Q1")
            dest.mkdir(parents=True)
            payload = metadata(candidate, "122" + candidate["symbol"])
            if candidate["symbol"] == "000333":
                payload = {"announcements": [], "totalAnnouncement": 0, "totalpages": 0, "hasMore": False}
            elif candidate["symbol"] == "601318":
                issuer = dict(payload["announcements"][0], announcementTitle="中国平安2025年第一季度报告")
                subsidiary = dict(payload["announcements"][0], announcementId="1220010001",
                                  adjunctUrl="finalpage/2025-04-30/1220010001.PDF",
                                  announcementTitle="中国平安：平安银行股份有限公司2025年第一季度报告")
                payload.update(announcements=[subsidiary, issuer], totalAnnouncement=2)
            (dest / "metadata.response").write_bytes(json_bytes(payload))
            org = [{"code": candidate["symbol"], "zwjc": candidate["name"],
                    "orgId": "990" + candidate["symbol"], "category": "A股"}]
            (dest / "organization.response").write_bytes(json_bytes(org))
            document = {**candidate, "status": "failed"}
            if candidate["symbol"] == "600887":
                pdf = dest / "source.pdf"
                pdf.write_bytes(b"%PDF-1.7\n" + b"y" * 200)
                document.update(status="sealed", title="2025年第一季度报告", publication_date="2025-04-30",
                                announcement_id="122600887",
                                pdf_url="https://static.cninfo.com.cn/finalpage/2025-04-30/122600887.PDF",
                                pdf_path=pdf.relative_to(self.project).as_posix(),
                                pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())
            documents.append(document)
        artifacts = {path.relative_to(self.project).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in folder.rglob("*") if path.is_file()}
        manifest = {"schema": "filing-development-sealed-v1", "content_accessed": False,
                    "documents": documents, "artifacts": artifacts}
        path = folder / "manifest.json"
        path.write_bytes(json_bytes(manifest))
        return path, hashlib.sha256(path.read_bytes()).hexdigest(), documents[-1]["pdf_sha256"]

    def test_cached_qualification_uses_one_title_free_diagnostic_and_two_pdf_requests(self):
        source, source_sha, yili_sha = self.cached_source()
        requests = []

        def handler(request, timeout):
            registration = json.loads((self.sealed_root / "qualified-metadata" / "preregistration.json").read_bytes())
            self.assertEqual(registration["source_manifest_sha256"], source_sha)
            requests.append(request.full_url)
            if request.data:
                self.assertEqual(request.full_url, "https://www.cninfo.com.cn/new/hisAnnouncement/query")
                query = parse_qs(request.data.decode("ascii"), keep_blank_values=True)
                self.assertEqual(query["stock"], ["000333,990000333"])
                self.assertEqual(query["searchkey"], [""])
                self.assertEqual(query["category"], ["category_yjdbg_szsh"])
                self.assertEqual(query["seDate"], ["2025-04-01~2025-04-30"])
                payload = metadata(CANDIDATES[0], "122000333")
                payload["announcements"][0]["announcementTitle"] = "美的集团：2025年一季度报告"
                return Response(json_bytes(payload), request.full_url)
            self.assertNotIn("600887", request.full_url)
            return Response(b"%PDF-1.7\n" + b"f" * 200, request.full_url, content_type="application/pdf")

        with patch.object(preparation, "build_opener", return_value=Opener(handler)):
            result = preparation.acquire_qualified_metadata(source_manifest=source, source_manifest_sha256=source_sha)
        self.assertEqual([d["status"] for d in result["documents"]], ["sealed"] * 3)
        self.assertEqual(len(requests), 3)
        self.assertEqual(result["documents"][-1]["pdf_sha256"], yili_sha)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), source_sha)
        self.assertFalse(result["content_accessed"])
        for name, sha in result["artifacts"].items():
            path = self.project / name
            self.assertTrue(path.is_relative_to(self.sealed_root / "qualified-metadata"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)

    def test_empty_diagnostic_stays_failed_while_cached_issuer_pdf_is_sealed(self):
        source, source_sha, yili_sha = self.cached_source()
        downloaded = []

        def handler(request, timeout):
            if request.data:
                return Response(json_bytes({"announcements": [], "totalAnnouncement": 0}), request.full_url)
            downloaded.append(request.full_url)
            return Response(b"%PDF-1.7\n" + b"p" * 200, request.full_url, content_type="application/pdf")

        with patch.object(preparation, "build_opener", return_value=Opener(handler)):
            result = preparation.acquire_qualified_metadata(source_manifest=source, source_manifest_sha256=source_sha)
        self.assertEqual([d["status"] for d in result["documents"]], ["failed", "sealed", "sealed"])
        self.assertEqual(len(result["failures"]), 1)
        self.assertEqual(downloaded, ["https://static.cninfo.com.cn/finalpage/2025-04-30/122601318.PDF"])
        self.assertEqual(result["documents"][-1]["pdf_sha256"], yili_sha)

    def test_pdf_only_validates_signature_size_and_strict_official_host(self):
        url = "https://static.cninfo.com.cn/finalpage/2025-04-30/1220000001.PDF"
        preparation.validate_pdf_bytes(b"%PDF-1.7\n" + b"x" * 200, url)
        for raw in (b"<html>access challenge</html>", b"%PDF-", b"%PDF-1.7\n" + b"x" * 8_000_000):
            with self.assertRaises(ValueError):
                preparation.validate_pdf_bytes(raw, url)
        for target in (
            "http://static.cninfo.com.cn/finalpage/2025-04-30/1.PDF",
            "https://static.cninfo.com.cn.evil.example/finalpage/2025-04-30/1.PDF",
            "https://user@static.cninfo.com.cn/finalpage/2025-04-30/1.PDF",
            "https://static.cninfo.com.cn:444/finalpage/2025-04-30/1.PDF",
        ):
            with self.assertRaises(ValueError):
                preparation.validate_pdf_bytes(b"%PDF-1.7\n" + b"x" * 200, target)

    def test_official_redirect_guard_blocks_external_requests_before_following(self):
        guard = preparation.OfficialRedirectHandler("pdf")
        with self.assertRaises(ValueError):
            guard.redirect_request(None, None, 302, "Found", {}, "https://evil.example/report.pdf")

    def test_official_code_lookup_replaces_unverified_organization_id_hints(self):
        organizations = {"000333": "9900003331", "601318": "9900601318", "600887": "gssh0600887"}

        def handler(request, timeout):
            if request.full_url.endswith("/topSearch/query"):
                query = parse_qs(request.data.decode("ascii"))
                symbol = query["keyWord"][0]
                candidate = next(c for c in CANDIDATES if c["symbol"] == symbol)
                return Response(json_bytes([{"code": symbol, "zwjc": candidate["name"],
                                             "orgId": organizations[symbol], "category": "A股"}]), request.full_url)
            if request.data:
                query = parse_qs(request.data.decode("ascii"))
                symbol = query["stock"][0].split(",")[0]
                self.assertEqual(query["stock"], [symbol + "," + organizations[symbol]])
                candidate = next(c for c in CANDIDATES if c["symbol"] == symbol)
                return Response(json_bytes(metadata(candidate, "122" + symbol)), request.full_url)
            return Response(b"%PDF-1.7\n" + b"x" * 200, request.full_url, content_type="application/pdf")

        with patch.object(preparation, "build_opener", return_value=Opener(handler)):
            result = preparation.acquire_sealed()
        self.assertEqual([row["status"] for row in result["documents"]], ["sealed"] * 3)

    def test_official_organization_lookup_refuses_wrong_or_ambiguous_company(self):
        valid = [{"code": "000333", "zwjc": "美的集团", "orgId": "9900003331", "category": "A股"}]
        self.assertEqual(preparation.select_organization(valid, "000333")["org_id"], "9900003331")
        for rows in ([], [dict(valid[0], code="600887")], [dict(valid[0], zwjc="其他公司")],
                     valid + [dict(valid[0], orgId="another-org")], [dict(valid[0], orgId="../escape")]):
            with self.assertRaises(ValueError):
                preparation.select_organization(rows, "000333")

    def test_reuse_verifies_source_manifest_and_pdf_sha_without_new_downloads(self):
        def handler(request, timeout):
            if request.full_url.endswith("/topSearch/query"):
                return organization_response(request)
            if request.data:
                symbol = parse_qs(request.data.decode("ascii"))["stock"][0].split(",")[0]
                candidate = next(c for c in CANDIDATES if c["symbol"] == symbol)
                return Response(json_bytes(metadata(candidate, "122" + symbol)), request.full_url)
            return Response(b"%PDF-1.7\n" + b"r" * 200, request.full_url, content_type="application/pdf")

        with patch.object(preparation, "build_opener", return_value=Opener(handler)):
            original = preparation.acquire_sealed()
        manifest_path = self.sealed_root / "initial" / "manifest.json"
        manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        with patch.object(preparation, "build_opener", side_effect=AssertionError("verified sealed reports must be reused")):
            copied = preparation.acquire_sealed("copied", reuse_manifest=manifest_path, reuse_manifest_sha256=manifest_sha)
        self.assertEqual([d["status"] for d in copied["documents"]], ["sealed"] * 3)
        self.assertEqual([d["pdf_sha256"] for d in copied["documents"]], [d["pdf_sha256"] for d in original["documents"]])
        self.assertEqual(copied["reused_manifest_sha256"], manifest_sha)
        for document in copied["documents"]:
            self.assertTrue((self.project / document["pdf_path"]).is_relative_to(self.sealed_root / "copied"))
        (self.project / original["documents"][0]["pdf_path"]).write_bytes(b"%PDF-1.7\n" + b"tampered" * 50)
        with self.assertRaises(ValueError):
            preparation.acquire_sealed("tampered", reuse_manifest=manifest_path, reuse_manifest_sha256=manifest_sha)
        self.assertFalse((self.sealed_root / "tampered").exists())

    def test_acquisition_preregisters_candidates_and_hashes_before_any_network(self):
        queried, downloaded = [], []

        def handler(request, timeout):
            registration_path = self.sealed_root / "initial" / "preregistration.json"
            registration = json.loads(registration_path.read_text("utf8"))
            self.assertEqual(registration["documents"], CANDIDATES)
            self.assertEqual(registration["config_sha256"], hashlib.sha256(self.config.read_bytes()).hexdigest())
            self.assertFalse(registration["content_accessed"])
            self.assertLessEqual(timeout, 30)
            if request.full_url.endswith("/topSearch/query"):
                return organization_response(request)
            if request.full_url == "https://www.cninfo.com.cn/new/hisAnnouncement/query":
                query = parse_qs(request.data.decode("ascii"))
                symbol = query["stock"][0].split(",")[0]
                self.assertEqual(query["searchkey"], ["2025年第一季度报告"])
                self.assertEqual(query["isHLtitle"], ["false"])
                self.assertEqual(query["seDate"], ["2025-04-01~2025-04-30"])
                self.assertEqual(query["pageNum"], ["1"])
                self.assertLessEqual(int(query["pageSize"][0]), 30)
                queried.append(symbol)
                candidate = next(c for c in CANDIDATES if c["symbol"] == symbol)
                return Response(json_bytes(metadata(candidate, "122" + symbol)), request.full_url)
            downloaded.append(request.full_url)
            return Response(b"%PDF-1.7\n" + b"s" * 200, request.full_url, content_type="application/pdf")

        with patch.object(preparation, "build_opener", return_value=Opener(handler)):
            result = preparation.acquire_sealed()
        self.assertEqual(queried, ["000333", "601318", "600887"])
        self.assertEqual(len(downloaded), 3)
        self.assertEqual([d["status"] for d in result["documents"]], ["sealed"] * 3)
        self.assertFalse(result["content_accessed"])
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["schema"], "filing-development-sealed-v1")
        for name, sha in result["artifacts"].items():
            artifact = self.project / name
            self.assertTrue(artifact.is_relative_to(self.sealed_root / "initial"))
            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), sha)
        with patch.object(preparation, "build_opener", side_effect=AssertionError("must not retry an existing attempt")):
            with self.assertRaises(ValueError):
                preparation.acquire_sealed()

    def test_acquisition_keeps_failed_pdf_receipt_and_fixed_company_denominator(self):
        def handler(request, timeout):
            if request.full_url.endswith("/topSearch/query"):
                return organization_response(request)
            if request.data:
                symbol = parse_qs(request.data.decode("ascii"))["stock"][0].split(",")[0]
                candidate = next(c for c in CANDIDATES if c["symbol"] == symbol)
                return Response(json_bytes(metadata(candidate, "122" + symbol)), request.full_url)
            if "601318" in request.full_url:
                return Response(b"<html>challenge</html>", request.full_url, content_type="text/html")
            return Response(b"%PDF-1.7\n" + b"s" * 200, request.full_url, content_type="application/pdf")

        with patch.object(preparation, "build_opener", return_value=Opener(handler)):
            result = preparation.acquire_sealed()
        self.assertEqual([d["symbol"] for d in result["documents"]], ["000333", "601318", "600887"])
        self.assertEqual([d["status"] for d in result["documents"]], ["sealed", "failed", "sealed"])
        failed = result["documents"][1]
        self.assertNotIn("pdf_path", failed)
        self.assertEqual(len(result["failures"]), 1)
        receipt_path = self.sealed_root / "initial" / "documents" / "601318-2025Q1" / "pdf.receipt.json"
        self.assertEqual(json.loads(receipt_path.read_text("utf8"))["status"], "failed")
        self.assertEqual(receipt_path.with_name("pdf.response").read_bytes(), b"<html>challenge</html>")

    def test_unsafe_attempt_and_changed_candidate_list_are_refused_before_network(self):
        with patch.object(preparation, "build_opener", side_effect=AssertionError("no network allowed")):
            for attempt in ("../escape", "..", "a/b", "a\\b", ""):
                with self.assertRaises(ValueError):
                    preparation.acquire_sealed(attempt)
            self.config.write_bytes(json_bytes({"schema": "filing-development-design-v1", "new_evaluation_candidates": CANDIDATES[:-1]}))
            with self.assertRaises(ValueError):
                preparation.acquire_sealed()
        self.assertFalse(self.sealed_root.exists())


if __name__ == "__main__":
    unittest.main()
