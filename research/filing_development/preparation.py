"""D30 sealed source acquisition and a blank, independently completed review kit.

This module has no PDF parser, model dependency, or reference-label reader. New
reports are checked only as bounded bytes plus official announcement metadata.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


PROJECT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT / "research/configs/filing-development-v1.json"
DESIGN_PATH = PROJECT / "docs/superpowers/specs/2026-11-06-filing-development-design.md"
SOURCE_CORPUS = PROJECT / "research/artifacts/filing-extraction/corpus/v2/manifest.json"
SOURCE_CORPUS_SHA = "12111d7cc30ac15d9a55facac06ea6e15443bc401a2a880bc87076e344347da3"
SEALED_ROOT = PROJECT / "research/artifacts/filing-development/sealed-evaluation"
HUMAN_KIT_ROOT = PROJECT / "docs/research/human-review/2026-11-06"
METADATA_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
ORGANIZATION_URL = "https://www.cninfo.com.cn/new/information/topSearch/query"
MAX_METADATA_BYTES = 1_000_000
MAX_PDF_BYTES = 8_000_000
MAX_METADATA_ROWS = 20
REQUEST_TIMEOUT = 25

CANDIDATES = (
    {"symbol": "000333", "name": "美的集团", "period": "2025Q1"},
    {"symbol": "601318", "name": "中国平安", "period": "2025Q1"},
    {"symbol": "600887", "name": "伊利股份", "period": "2025Q1"},
)
ISSUER_TITLE_PREFIXES = {
    "000333": ("美的集团", "美的集团股份有限公司"),
    "601318": ("中国平安", "中国平安保险（集团）股份有限公司", "中国平安保险(集团)股份有限公司"),
    "600887": ("伊利股份", "内蒙古伊利实业集团股份有限公司"),
}
COMPANIES = {"600519": "贵州茅台", "600036": "招商银行", "600585": "海螺水泥"}
METRICS = ("revenue", "net_profit_parent", "operating_cashflow")
IDENTITY_COLUMNS = ("case_id", "doc_id", "company", "metric", "source_url", "local_pdf")
HUMAN_COLUMNS = (
    "manual_value", "manual_unit", "manual_currency", "manual_period", "manual_scope",
    "value_page", "header_pages", "quote", "reviewer", "reviewed_at", "notes",
)
COLUMNS = (
    "case_id", "doc_id", "company", "metric", "source_url", "local_pdf",
    "manual_value", "manual_unit", "manual_currency", "manual_period", "manual_scope",
    "value_page", "header_pages", "quote", "status", "reviewer", "reviewed_at", "notes",
)
REVIEW_STATUSES = ("unreviewed", "in_progress", "completed", "uncertain", "disputed")
UNITS = ("元", "千元", "万元", "百万元", "亿元")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _write_bytes(path: Path, raw: bytes) -> None:
    with path.open("xb") as stream:
        stream.write(raw)


def _inside_project(path: str | Path) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(PROJECT.resolve()) or resolved == PROJECT.resolve():
        raise ValueError("Output must be a child of the project directory")
    return resolved


def _relative(path: Path) -> str:
    return path.resolve().relative_to(PROJECT.resolve()).as_posix()


def _validate_url(url: str, kind: str) -> None:
    parsed = urlsplit(url)
    host = "www.cninfo.com.cn" if kind in ("metadata", "organization") else "static.cninfo.com.cn"
    if (kind not in ("metadata", "organization", "pdf") or parsed.scheme != "https" or parsed.hostname != host
            or parsed.username is not None or parsed.password is not None or parsed.port is not None
            or parsed.query or parsed.fragment):
        raise ValueError("Source URL is outside the strict official HTTPS allowlist")
    if kind == "metadata" and parsed.path != "/new/hisAnnouncement/query":
        raise ValueError("Only the fixed official announcement metadata endpoint is allowed")
    if kind == "organization" and parsed.path != "/new/information/topSearch/query":
        raise ValueError("Only exact-code official organisation metadata lookup is allowed")
    if kind == "pdf" and not re.fullmatch(r"/finalpage/\d{4}-\d{2}-\d{2}/\d+\.pdf", parsed.path, re.IGNORECASE):
        raise ValueError("Unexpected official PDF path")


class OfficialRedirectHandler(HTTPRedirectHandler):
    """Validate a redirect before urllib can send a request to its target."""

    def __init__(self, kind: str):
        super().__init__()
        self.kind = kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl, self.kind)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_pdf_bytes(raw: bytes, url: str) -> None:
    """Check the official host, byte bound and PDF magic; never interpret pages."""
    _validate_url(url, "pdf")
    if not 16 <= len(raw) <= MAX_PDF_BYTES or not raw.startswith(b"%PDF-"):
        raise ValueError("Response is not a bounded PDF-signature payload; content remains unread")


def _request_bytes(url: str, folder: Path, kind: str, body: bytes | None = None):
    """Keep one bounded raw response and its success/failure receipt, without retries."""
    maximum = MAX_PDF_BYTES if kind == "pdf" else MAX_METADATA_BYTES
    receipt = {
        "url": url, "started_at": _now(), "kind": kind, "max_bytes": maximum,
        "status": "failed", "content_accessed": False,
    }
    raw = None
    valid = False
    try:
        _validate_url(url, kind)
        headers = {
            "User-Agent": "Mozilla/5.0 FinancialLearningLab/0.1 (bounded public metadata research)",
            "Referer": "https://www.cninfo.com.cn/",
            "Accept": "application/pdf" if kind == "pdf" else "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        request = Request(url, data=body, headers=headers)
        opener = build_opener(OfficialRedirectHandler(kind))
        with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
            final_url = response.geturl()
            _validate_url(final_url, kind)
            receipt.update(final_url=final_url, http_status=response.status,
                           content_type=response.headers.get("Content-Type"))
            raw = response.read(maximum + 1)
            if response.status != 200:
                raise ValueError("Official source returned a non-200 HTTP response")
            if len(raw) > maximum:
                receipt["truncated"] = True
                raise ValueError("Official response exceeded the preregistered byte bound")
            if kind == "pdf":
                validate_pdf_bytes(raw, final_url)
        receipt["status"] = "pdf_signature_verified" if kind == "pdf" else "received"
        valid = True
    except HTTPError as error:
        receipt.update(http_status=error.code, error=str(error))
        raw = error.read(maximum + 1)
        receipt["truncated"] = len(raw) > maximum
    except Exception as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        receipt["received_at"] = _now()
        if raw is not None:
            response_path = folder / f"{kind}.response"
            _write_bytes(response_path, raw)
            receipt.update(bytes=len(raw), sha256=_sha(raw), response_path=_relative(response_path))
        _write_json(folder / f"{kind}.receipt.json", receipt)
    return raw if valid else None, receipt


def select_organization(payload: list, symbol: str) -> dict:
    """Resolve the exact company code to its official catalogue key, without guessing."""
    candidate = next((c for c in CANDIDATES if c["symbol"] == symbol), None)
    if candidate is None or not isinstance(payload, list) or not 1 <= len(payload) <= 10:
        raise ValueError("Missing or oversized exact-code official organization metadata")
    matches = [row for row in payload if isinstance(row, dict) and row.get("code") == symbol]
    if len(matches) != 1 or matches[0].get("zwjc") != candidate["name"]:
        raise ValueError("Official organization identity is missing, wrong or ambiguous")
    org_id = matches[0].get("orgId")
    if not isinstance(org_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", org_id):
        raise ValueError("Unexpected official organization identifier")
    return {"symbol": symbol, "name": candidate["name"], "org_id": org_id}


def _query(candidate: dict, org_id: str) -> dict:
    symbol = candidate["symbol"]
    return {
        "pageNum": "1", "pageSize": str(MAX_METADATA_ROWS), "column": "szse",
        "tabName": "fulltext", "stock": f"{symbol},{org_id}",
        "searchkey": "2025年第一季度报告", "seDate": "2025-04-01~2025-04-30",
        "category": "", "trade": "", "sortName": "time", "sortType": "asc",
        "isHLtitle": "false",
    }


def _is_issuer_report_title(title: str, symbol: str) -> bool:
    core = title
    for prefix in sorted(ISSUER_TITLE_PREFIXES[symbol], key=len, reverse=True):
        if title.startswith(prefix):
            core = title[len(prefix):].lstrip(":：")
            break
    return bool(re.fullmatch(r"2025年(?:第一|一)季度报告(?:全文|（全文）|\(全文\))?", core))


def select_announcement(payload: dict, symbol: str, period: str) -> dict:
    """Qualify one full original Q1 report from metadata only; ambiguity fails."""
    candidate = next((c for c in CANDIDATES if c["symbol"] == symbol and c["period"] == period), None)
    if candidate is None or not isinstance(payload, dict):
        raise ValueError("Announcement is outside the fixed candidate registration")
    rows = payload.get("announcements")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_METADATA_ROWS:
        raise ValueError("Missing or oversized announcement metadata list")
    if payload.get("hasMore") or int(payload.get("totalpages") or 1) > 1:
        raise ValueError("Metadata is not complete within the single preregistered page")
    total = payload.get("totalAnnouncement")
    if total is not None and int(total) != len(rows):
        raise ValueError("Metadata total differs from the received bounded page")
    matches = []
    for row in rows:
        if not isinstance(row, dict) or row.get("secCode") != symbol or row.get("secName") != candidate["name"]:
            raise ValueError("Official announcement metadata did not match the exact company")
        title = re.sub(r"\s+", "", re.sub(r"<[^>]*>", "", html.unescape(str(row.get("announcementTitle", "")))))
        if (not _is_issuer_report_title(title, symbol)
                or re.search(r"摘要|英文|English|更正|修订|取消|提示|说明", title, re.IGNORECASE)):
            continue
        stamp = row.get("announcementTime")
        if isinstance(stamp, bool) or not re.fullmatch(r"\d{13}", str(stamp)):
            raise ValueError("Announcement publication time is not an official millisecond date")
        published = datetime.fromtimestamp(int(stamp) / 1000, timezone(timedelta(hours=8))).date().isoformat()
        if not "2025-04-01" <= published <= "2025-04-30":
            raise ValueError("Announcement publication date is outside the registered Q1 window")
        adjunct = row.get("adjunctUrl")
        if not isinstance(adjunct, str):
            raise ValueError("Official PDF attachment URL is missing")
        pdf_url = adjunct if urlsplit(adjunct).scheme else "https://static.cninfo.com.cn/" + adjunct.lstrip("/")
        _validate_url(pdf_url, "pdf")
        pdf_path = urlsplit(pdf_url).path
        announcement_id = str(row.get("announcementId", ""))
        if (not announcement_id.isdigit() or pdf_path.rsplit("/", 1)[-1].lower() != announcement_id + ".pdf"
                or pdf_path.split("/")[2] != published or str(row.get("adjunctType", "")).upper() != "PDF"):
            raise ValueError("Attachment identity/date/type does not match its announcement metadata")
        matches.append({
            "symbol": symbol, "name": candidate["name"], "period": period,
            "title": title, "pdf_url": pdf_url, "publication_date": published,
            "announcement_id": announcement_id,
        })
    if len(matches) != 1:
        raise ValueError("Fixed full report missing or ambiguous; no substitute selected")
    return matches[0]


def _load_reuse(path: str | Path | None, expected_sha: str | None):
    if path is None:
        if expected_sha is not None:
            raise ValueError("Reuse SHA supplied without a source manifest")
        return {}, None, None, None
    source = Path(path).resolve()
    if (not source.is_relative_to(SEALED_ROOT.resolve()) or source.name != "manifest.json"
            or not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)):
        raise ValueError("Reuse requires a sealed-attempt manifest and its previously recorded SHA256")
    raw = source.read_bytes()
    if _sha(raw) != expected_sha:
        raise ValueError("Previously recorded sealed manifest SHA256 changed")
    manifest = json.loads(raw)
    if manifest.get("schema") != "filing-development-sealed-v1" or manifest.get("content_accessed") is not False:
        raise ValueError("Source is not a content-unread sealed manifest")
    documents = manifest.get("documents", [])
    if (len(documents) != 3 or [{k: d.get(k) for k in ("symbol", "name", "period")} for d in documents] != list(CANDIDATES)
            or any(d.get("status") not in ("sealed", "failed") for d in documents)):
        raise ValueError("Reuse manifest changed the registered company/report identities")
    artifacts = manifest.get("artifacts", {})
    if not artifacts:
        raise ValueError("Reuse manifest lacks source artifact identities")
    for name, sha in artifacts.items():
        artifact = (PROJECT / name).resolve()
        if not artifact.is_relative_to(source.parent) or _sha(artifact.read_bytes()) != sha:
            raise ValueError("Sealed source artifact changed or escaped its original attempt")
    reusable = {}
    for document in documents:
        if document["status"] != "sealed":
            continue
        pdf = (PROJECT / document.get("pdf_path", "")).resolve()
        if (not pdf.is_relative_to(source.parent) or artifacts.get(document.get("pdf_path")) != document.get("pdf_sha256")):
            raise ValueError("Reusable PDF identity differs from the source artifact manifest")
        _validate_url(document.get("pdf_url", ""), "pdf")
        reusable[document["symbol"]] = document
    return reusable, source, expected_sha, raw


def acquire_sealed(attempt: str = "initial", *, reuse_manifest: str | Path | None = None,
                   reuse_manifest_sha256: str | None = None) -> dict:
    """Register the fixed candidates, then acquire official metadata and sealed bytes."""
    if not isinstance(attempt, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", attempt):
        raise ValueError("Unsafe attempt identifier")
    folder = _inside_project(SEALED_ROOT / attempt)
    if not folder.is_relative_to(SEALED_ROOT.resolve()):
        raise ValueError("Attempt escaped the sealed source root")
    if folder.exists():
        raise ValueError("Existing acquisition attempt retained; use a new attempt identity")
    config_raw, design_raw = CONFIG_PATH.read_bytes(), DESIGN_PATH.read_bytes()
    config = json.loads(config_raw)
    if config.get("schema") != "filing-development-design-v1" or config.get("new_evaluation_candidates") != list(CANDIDATES):
        raise ValueError("Fixed new-evaluation candidate configuration changed")
    reusable, reused_path, reused_sha, reused_raw = _load_reuse(reuse_manifest, reuse_manifest_sha256)
    folder.mkdir(parents=True, exist_ok=False)
    created = _now()
    config_sha, design_sha = _sha(config_raw), _sha(design_raw)
    _write_bytes(folder / "config.json", config_raw)
    _write_bytes(folder / "design.md", design_raw)
    if reused_raw is not None:
        _write_bytes(folder / "reused-manifest.json", reused_raw)
    new_candidates = [c for c in CANDIDATES if c["symbol"] not in reusable]
    registration = {
        "schema": "filing-development-sealed-registration-v1", "created_at": created,
        "documents": list(CANDIDATES), "config_sha256": config_sha, "design_sha256": design_sha,
        "metadata_endpoint": METADATA_URL, "organization_endpoint": ORGANIZATION_URL,
        "queries": [_query(c, "{exact_official_org_id}") for c in new_candidates],
        "organization_queries": [{"keyWord": c["symbol"], "maxNum": "5"} for c in new_candidates],
        "max_metadata_bytes": MAX_METADATA_BYTES, "max_pdf_bytes": MAX_PDF_BYTES,
        "request_timeout_seconds": REQUEST_TIMEOUT, "max_metadata_pages_per_company": 1,
        "max_organization_requests": len(new_candidates), "max_metadata_requests": len(new_candidates),
        "max_pdf_requests": len(new_candidates), "automatic_retries": 0,
        "reused_manifest_path": _relative(reused_path) if reused_path else None,
        "reused_manifest_sha256": reused_sha, "reused_symbols": sorted(reusable),
        "content_accessed": False,
        "qualification": "Official exact company/code, Chinese full original 2025Q1 report title and April publication date; PDF signature/size/host only. No PDF content identity verification.",
    }
    _write_json(folder / "preregistration.json", registration)
    documents, failures = [], []
    for candidate in CANDIDATES:
        document = {**candidate, "status": "failed"}
        dest = folder / "documents" / f"{candidate['symbol']}-{candidate['period']}"
        dest.mkdir(parents=True, exist_ok=False)
        stage = "reuse_verification" if candidate["symbol"] in reusable else "organization_request"
        try:
            if candidate["symbol"] in reusable:
                previous = reusable[candidate["symbol"]]
                raw = (PROJECT / previous["pdf_path"]).read_bytes()
                if _sha(raw) != previous["pdf_sha256"]:
                    raise ValueError("Sealed PDF changed after source-manifest verification")
                validate_pdf_bytes(raw, previous["pdf_url"])
                pdf = dest / "source.pdf"
                _write_bytes(pdf, raw)
                selected = {key: previous[key] for key in (
                    "symbol", "name", "period", "title", "pdf_url", "publication_date", "announcement_id")}
                _write_json(dest / "announcement.json", selected)
                _write_json(dest / "reuse.receipt.json", {
                    "created_at": _now(), "status": "copied_verified_sealed_bytes", "content_accessed": False,
                    "source_manifest_path": _relative(reused_path), "source_manifest_sha256": reused_sha,
                    "source_pdf_path": previous["pdf_path"], "source_pdf_sha256": previous["pdf_sha256"],
                    "pdf_sha256": _sha(raw), "new_pdf_path": _relative(pdf),
                })
                document.update(selected, status="sealed", pdf_path=_relative(pdf), pdf_sha256=_sha(raw),
                                reused_from_manifest_sha256=reused_sha)
                documents.append(document)
                continue
            org_body = urlencode({"keyWord": candidate["symbol"], "maxNum": "5"}).encode("ascii")
            org_raw, receipt = _request_bytes(ORGANIZATION_URL, dest, "organization", org_body)
            if org_raw is None:
                raise ValueError(receipt.get("error", "Official organization lookup failed"))
            stage = "organization_qualification"
            organization = select_organization(json.loads(org_raw), candidate["symbol"])
            _write_json(dest / "organization.json", organization)
            stage = "metadata_request"
            body = urlencode(_query(candidate, organization["org_id"])).encode("ascii")
            metadata_raw, receipt = _request_bytes(METADATA_URL, dest, "metadata", body)
            if metadata_raw is None:
                raise ValueError(receipt.get("error", "Official metadata request failed"))
            stage = "metadata_qualification"
            selected = select_announcement(json.loads(metadata_raw), candidate["symbol"], candidate["period"])
            selected["query_org_id"] = organization["org_id"]
            document.update(selected)
            _write_json(dest / "announcement.json", selected)
            stage = "pdf_request"
            raw, receipt = _request_bytes(selected["pdf_url"], dest, "pdf")
            if raw is None:
                raise ValueError(receipt.get("error", "Official PDF request failed"))
            pdf = dest / "source.pdf"
            _write_bytes(pdf, raw)
            document.update(status="sealed", pdf_path=_relative(pdf), pdf_sha256=_sha(raw))
        except Exception as error:
            failure = {"symbol": candidate["symbol"], "period": candidate["period"], "stage": stage,
                       "error": f"{type(error).__name__}: {error}"}
            document["failure"] = failure
            failures.append(failure)
            _write_json(dest / "failure.json", failure)
        documents.append(document)
    artifacts = {_relative(path): _sha(path.read_bytes()) for path in sorted(folder.rglob("*")) if path.is_file()}
    manifest = {
        "schema": "filing-development-sealed-v1", "created_at": created,
        "design_sha256": design_sha, "config_sha256": config_sha,
        "preregistration_sha256": _sha((folder / "preregistration.json").read_bytes()),
        "documents": documents, "artifacts": artifacts, "failures": failures, "content_accessed": False,
        "limitations": [
            "Only official announcement metadata and bounded original PDF bytes were acquired.",
            "PDF content, company identity within pages and financial values remain uninspected and unverified.",
            "No text extraction, rendering, annotation, model prediction or accuracy measurement was performed.",
            "Publication dates are not verified first-public timestamps; this is not a PIT reconstruction.",
            "Missing/ambiguous/unavailable reports remain failed without company or report replacement.",
        ],
    }
    if reused_path is not None:
        manifest.update(reused_manifest_path=_relative(reused_path), reused_manifest_sha256=reused_sha)
    _write_json(folder / "manifest.json", manifest)
    return manifest


def acquire_qualified_metadata(attempt: str = "qualified-metadata", *, source_manifest: str | Path,
                              source_manifest_sha256: str) -> dict:
    """Requalify saved issuer metadata, reuse Yili, and diagnose Midea once.

The only new catalogue query is exact 000333/official org ID, April 2025,
first-quarter category and no title search. PingAn consumes saved metadata.
There is at most one new PDF request per remaining company, with no retry.
"""
    if not isinstance(attempt, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", attempt):
        raise ValueError("Unsafe attempt identifier")
    folder = _inside_project(SEALED_ROOT / attempt)
    if not folder.is_relative_to(SEALED_ROOT.resolve()) or folder.exists():
        raise ValueError("Existing or unsafe qualification attempt retained")
    reusable, source, source_sha, source_raw = _load_reuse(source_manifest, source_manifest_sha256)
    if "600887" not in reusable:
        raise ValueError("This bounded follow-up requires the original sealed Yili PDF")
    config_raw, design_raw = CONFIG_PATH.read_bytes(), DESIGN_PATH.read_bytes()
    config = json.loads(config_raw)
    if config.get("schema") != "filing-development-design-v1" or config.get("new_evaluation_candidates") != list(CANDIDATES):
        raise ValueError("Fixed new-evaluation candidate configuration changed")
    source_artifacts = json.loads(source_raw)["artifacts"]
    cached, organizations = {}, {}
    for symbol in ("000333", "601318"):
        original = source.parent / "documents" / f"{symbol}-2025Q1"
        cached[symbol] = {}
        for kind in ("metadata", "organization"):
            path = original / f"{kind}.response"
            raw = path.read_bytes()
            if len(raw) > MAX_METADATA_BYTES or source_artifacts.get(_relative(path)) != _sha(raw):
                raise ValueError("Cached official metadata differs from its frozen artifact identity")
            cached[symbol][kind] = raw
        organizations[symbol] = select_organization(json.loads(cached[symbol]["organization"]), symbol)
    diagnostic_query = _query(CANDIDATES[0], organizations["000333"]["org_id"])
    diagnostic_query.update(searchkey="", category="category_yjdbg_szsh")
    created, config_sha, design_sha = _now(), _sha(config_raw), _sha(design_raw)
    folder.mkdir(parents=True, exist_ok=False)
    _write_bytes(folder / "config.json", config_raw)
    _write_bytes(folder / "design.md", design_raw)
    _write_bytes(folder / "source-manifest.json", source_raw)
    _write_json(folder / "preregistration.json", {
        "schema": "filing-development-sealed-registration-v1", "created_at": created,
        "documents": list(CANDIDATES), "design_sha256": design_sha, "config_sha256": config_sha,
        "source_manifest_path": _relative(source), "source_manifest_sha256": source_sha,
        "operation": "qualified_cached_issuer_metadata_and_one_Midea_title_diagnostic",
        "organizations": organizations, "metadata_endpoint": METADATA_URL, "queries": [diagnostic_query],
        "cached_metadata_sha256": {symbol: _sha(value["metadata"]) for symbol, value in cached.items()},
        "title_policy": "Exact bare or issuer-prefixed 2025年第一季度报告 / 2025年一季度报告, optionally 全文; exclude subsidiaries, summaries, English and corrections; ambiguity fails.",
        "max_organization_requests": 0, "max_metadata_requests": 1, "max_pdf_requests": 2,
        "max_metadata_pages_per_company": 1, "max_metadata_bytes": MAX_METADATA_BYTES,
        "max_pdf_bytes": MAX_PDF_BYTES, "request_timeout_seconds": REQUEST_TIMEOUT,
        "automatic_retries": 0, "content_accessed": False,
        "reused_symbols": ["600887"], "reused_pdf_sha256": reusable["600887"]["pdf_sha256"],
    })
    documents, failures = [], []
    for candidate in CANDIDATES:
        symbol = candidate["symbol"]
        document = {**candidate, "status": "failed"}
        dest = folder / "documents" / f"{symbol}-2025Q1"
        dest.mkdir(parents=True, exist_ok=False)
        stage = "reuse_verification" if symbol == "600887" else "metadata_qualification"
        try:
            if symbol == "600887":
                previous = reusable[symbol]
                raw = (PROJECT / previous["pdf_path"]).read_bytes()
                if _sha(raw) != previous["pdf_sha256"]:
                    raise ValueError("Previously sealed Yili bytes changed")
                validate_pdf_bytes(raw, previous["pdf_url"])
                pdf = dest / "source.pdf"
                _write_bytes(pdf, raw)
                selected = {key: previous[key] for key in (
                    "title", "pdf_url", "publication_date", "announcement_id")}
                document.update(selected, status="sealed", pdf_path=_relative(pdf), pdf_sha256=_sha(raw),
                                reused_from_manifest_sha256=source_sha)
                _write_json(dest / "reuse.receipt.json", {
                    "created_at": _now(), "status": "copied_verified_sealed_bytes", "content_accessed": False,
                    "source_manifest_path": _relative(source), "source_manifest_sha256": source_sha,
                    "source_pdf_path": previous["pdf_path"], "pdf_sha256": _sha(raw), "pdf_path": _relative(pdf),
                })
            else:
                _write_bytes(dest / "organization.response", cached[symbol]["organization"])
                _write_json(dest / "organization.json", organizations[symbol])
                if symbol == "000333":
                    _write_bytes(dest / "prior-metadata.response", cached[symbol]["metadata"])
                    stage = "metadata_request"
                    metadata_raw, receipt = _request_bytes(METADATA_URL, dest, "metadata",
                                                           urlencode(diagnostic_query).encode("ascii"))
                    if metadata_raw is None:
                        raise ValueError(receipt.get("error", "Single fixed metadata diagnostic failed"))
                else:
                    metadata_raw = cached[symbol]["metadata"]
                    _write_bytes(dest / "metadata.response", metadata_raw)
                    _write_json(dest / "metadata.receipt.json", {
                        "created_at": _now(), "status": "reused_verified_official_metadata", "content_accessed": False,
                        "source_manifest_path": _relative(source), "source_manifest_sha256": source_sha,
                        "metadata_sha256": _sha(metadata_raw),
                    })
                stage = "metadata_qualification"
                selected = select_announcement(json.loads(metadata_raw), symbol, candidate["period"])
                selected["query_org_id"] = organizations[symbol]["org_id"]
                document.update(selected)
                _write_json(dest / "announcement.json", selected)
                stage = "pdf_request"
                raw, receipt = _request_bytes(selected["pdf_url"], dest, "pdf")
                if raw is None:
                    raise ValueError(receipt.get("error", "Single official PDF request failed"))
                pdf = dest / "source.pdf"
                _write_bytes(pdf, raw)
                document.update(status="sealed", pdf_path=_relative(pdf), pdf_sha256=_sha(raw))
        except Exception as error:
            failure = {"symbol": symbol, "period": candidate["period"], "stage": stage,
                       "error": f"{type(error).__name__}: {error}"}
            document["failure"] = failure
            failures.append(failure)
            _write_json(dest / "failure.json", failure)
        documents.append(document)
    artifacts = {_relative(path): _sha(path.read_bytes()) for path in sorted(folder.rglob("*")) if path.is_file()}
    manifest = {
        "schema": "filing-development-sealed-v1", "created_at": created,
        "design_sha256": design_sha, "config_sha256": config_sha,
        "preregistration_sha256": _sha((folder / "preregistration.json").read_bytes()),
        "source_manifest_path": _relative(source), "source_manifest_sha256": source_sha,
        "documents": documents, "artifacts": artifacts, "failures": failures, "content_accessed": False,
        "limitations": [
            "Only official metadata, bounded signature checks and sealed PDF bytes; no text extraction, rendering, annotation or prediction.",
            "Source title identity is metadata-only and PDF content remains unread and unverified.",
            "The Midea diagnostic is one exact-company, same-April-window Q1-category query without title search; failures are retained.",
            "PingAn consumes cached official issuer metadata; Yili reuses the previously sealed bytes without a new request.",
            "Publication dates are not first-public timestamps or a PIT reconstruction.",
        ],
    }
    _write_json(folder / "manifest.json", manifest)
    return manifest


def _source_documents() -> list[dict]:
    raw = SOURCE_CORPUS.read_bytes()
    if _sha(raw) != SOURCE_CORPUS_SHA:
        raise ValueError("Frozen D29 corpus manifest changed; do not replace its source identity")
    manifest = json.loads(raw)
    documents = manifest.get("documents")
    if manifest.get("schema") != "filing-extraction-corpus-v1" or not isinstance(documents, list) or len(documents) != 6:
        raise ValueError("Expected the original six-report D29 corpus metadata")
    expected = {f"{symbol}-{period}" for symbol in COMPANIES for period in ("2024Q1", "2025Q1")}
    if {d.get("doc_id") for d in documents} != expected:
        raise ValueError("Original six-report corpus identities missing or duplicated")
    for document in documents:
        symbol, period = document["doc_id"].split("-")
        if (document.get("symbol") != symbol or document.get("period") != period
                or not isinstance(document.get("page_count"), int) or isinstance(document["page_count"], bool)
                or document["page_count"] < 1 or not document.get("title") or not document.get("pdf_path")):
            raise ValueError("Incomplete source report metadata")
        _validate_url(document.get("pdf_url", ""), "pdf")
        _inside_project(PROJECT / document["pdf_path"])
    return documents


def _review_rows(documents: list[dict]) -> list[dict]:
    rows = []
    for document in documents:
        for metric in METRICS:
            row = dict.fromkeys(COLUMNS, "")
            row.update(case_id=f"{document['doc_id']}:{metric}", doc_id=document["doc_id"],
                       company=COMPANIES[document["symbol"]], metric=metric,
                       source_url=document["pdf_url"], local_pdf=document["pdf_path"], status="unreviewed")
            rows.append(row)
    return rows


GUIDE = """# 原六报告三字段：独立人工复核填写指南

此包共 6 份原报告、18 项。所有人工答案为空，状态 unreviewed，已完成数为 0。
助手旧参考仍是待人工审核的视觉参考，本包未附参考值，也不读取或覆盖它。
本包仅覆盖原公司 600519/600036/600585 的 2024Q1 与 2025Q1；不含新封存公司。

先另存 checklist.csv 为自己的审核文件，再独立阅读 source_url 或 local_pdf 指向的完整原始 PDF。
不要先看助手参考或模型输出。source_url 是原始链接，local_pdf 是相对项目根目录的原 PDF 路径。
保留 case_id、doc_id、company、metric、source_url、local_pdf 六列身份信息，不能增删或复制行。
PDF 全文可能超过模型输入的前六页；人工应阅读足以确认金额和口径的所有页面。

## 核对口径

1. revenue：营业收入；net_profit_parent：归属于母公司/上市公司股东的净利润；
   operating_cashflow：经营活动产生的现金流量净额。先核对行名，不把相近指标当成目标。
2. 核对目标季度累计流量及“本报告期/当期”列，不抄“上年同期/上期”或增减百分比。
   manual_period 必须独立确认后填写 2024Q1 或 2025Q1；它不得从其他行自动填入。
3. 先区分合并/集团与母公司单体报表。目标为合并集团口径，manual_scope 写 consolidated。
   只找到母公司时可记 parent，但状态必须 uncertain 或 disputed，并在 notes 保留原因。
   不能只凭前页摘要推断合并范围；表头或后续报表页的范围证据也要核对并记页。
4. 归母净利润不得混用“扣除非经常性损益后的归母净利润”、总净利润、少数股东损益或同比比率。
5. 读取金额所在表的币种和单位，不让每股收益的“元/股”覆盖财务表头的“百万元”等单位。
   manual_unit 逐项填写 元/千元/万元/百万元/亿元 之一；manual_currency 在原文确认人民币后填写 CNY。
   manual_value 保留原表单位下的十进制数，不自动乘单位、不带千分位逗号/货币符号/百分号/科学计数法。
   括号负数转换为负号（如 -12.50），要区分脚注括号与负值括号；未知或无法确认不能填 0。
6. value_page 写金额所在 PDF 物理页码，从文件第一页数作 1，不用印刷页码或阅读器偏移页码。
   header_pages 记单位、期间、范围的证据物理页，可在金额页之后；多页用英文逗号分隔，如 2,8,9。
   quote 独立抄录足以定位金额/当期列及口径的简短原文；引用来自后页时在 notes 说明各页作用。

## 状态与交付

- unreviewed：未开始，所有人工列保持空白。
- in_progress：已开始，可暂留空项；有值的列仍须符合格式。
- completed：金额、单位、币种、期间、合并范围、金额页、表头页、引用、reviewer、reviewed_at 均已填写并核对。
- uncertain：证据不足，未知项留空；必须填写 reviewer、reviewed_at、notes，不能算完成。
- disputed：口径或答案有异议，保留双方原记录和说明；必须填写 reviewer、reviewed_at、notes，不能算完成。

reviewed_at 用带时区的 ISO 时间，例如 2026-11-06T15:00:00+08:00；reviewer 写实际审核人。
有分歧时分别另存带审核人/版本的文件，不删除不同意见，不覆盖助手旧参考。后续合议也需新增记录。
用 `research/.venv/Scripts/python.exe -X utf8 -m research.filing_development.preparation validate-review 审核文件.csv`
进行只读格式校验。校验只确认身份、完整性与格式，不证明财务答案或引用正确，也不写回旧参考。
未全部完成的文件始终是 pending_human_review，不能称已审核金标；本轮工程研发不等待人工填写。
"""


def prepare_human_kit(output_dir: str | Path | None = None) -> dict:
    """Create 18 blank rows from frozen source metadata; never include answers."""
    documents = _source_documents()
    folder = _inside_project(HUMAN_KIT_ROOT if output_dir is None else output_dir)
    if folder.exists():
        raise ValueError("Existing human-review kit retained; select a new output directory")
    folder.mkdir(parents=True, exist_ok=False)
    checklist = folder / "checklist.csv"
    with checklist.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(_review_rows(documents))
    with (folder / "guide.md").open("x", encoding="utf8", newline="\n") as stream:
        stream.write(GUIDE)
    manifest = {
        "schema": "filing-development-human-kit-v1", "created_at": _now(),
        "item_count": 18, "completed": 0, "status": "pending_human_review",
        "source_corpus_sha256": SOURCE_CORPUS_SHA, "source_corpus_path": _relative(SOURCE_CORPUS),
        "artifacts": {name: _sha((folder / name).read_bytes()) for name in ("checklist.csv", "guide.md")},
        "limitations": ["Blank independent review tasks, not completed human labels or expert gold.",
                        "Returned review files must be saved separately; old assistant references are never overwritten."],
    }
    _write_json(folder / "manifest.json", manifest)
    return manifest


def _page(value: str, maximum: int) -> bool:
    return bool(re.fullmatch(r"[1-9]\d*", value)) and int(value) <= maximum


def _review_errors(row: dict, period: str, maximum_page: int) -> list[str]:
    status = row["status"]
    errors = []
    if status not in REVIEW_STATUSES:
        return ["unsupported review status"]
    if status == "unreviewed" and any(row[column] for column in HUMAN_COLUMNS):
        errors.append("unreviewed rows must keep all human entries blank")
    if status == "completed":
        missing = [column for column in HUMAN_COLUMNS if column != "notes" and not row[column]]
        if missing:
            errors.append("completed row missing " + ", ".join(missing))
        if row["manual_scope"] and row["manual_scope"] != "consolidated":
            errors.append("completed target requires independently confirmed consolidated scope")
    if status in ("uncertain", "disputed") and any(not row[column] for column in ("reviewer", "reviewed_at", "notes")):
        errors.append("unresolved review requires reviewer, reviewed_at and notes")
    if row["manual_value"]:
        value = row["manual_value"]
        try:
            valid_number = bool(re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value)) and Decimal(value).is_finite()
        except InvalidOperation:
            valid_number = False
        if not valid_number:
            errors.append("manual_value must be a finite plain decimal in the reported unit")
    if row["manual_unit"] and row["manual_unit"] not in UNITS:
        errors.append("unsupported financial unit")
    if row["manual_currency"] and row["manual_currency"] != "CNY":
        errors.append("manual_currency must confirm CNY for this fixed review target")
    if row["manual_period"] and row["manual_period"] != period:
        errors.append("manual_period differs from the fixed target quarter")
    if row["manual_scope"] and row["manual_scope"] not in ("consolidated", "parent"):
        errors.append("unsupported manual scope")
    if row["value_page"] and not _page(row["value_page"], maximum_page):
        errors.append("value_page is outside the report's physical pages")
    if row["header_pages"]:
        pages = [p.strip() for p in row["header_pages"].split(",")]
        if len(set(pages)) != len(pages) or any(not _page(page, maximum_page) for page in pages):
            errors.append("header_pages must list unique in-range physical pages")
    if row["reviewed_at"]:
        try:
            instant = datetime.fromisoformat(row["reviewed_at"])
            if instant.utcoffset() is None or not row["reviewer"]:
                raise ValueError("missing timezone or reviewer")
        except ValueError:
            errors.append("reviewed_at must be an ISO timestamp with timezone and a reviewer")
    return errors


def validate_review_csv(path: str | Path) -> dict:
    """Read-only structural review; this does not assess financial correctness."""
    documents = _source_documents()
    expected = {row["case_id"]: row for row in _review_rows(documents)}
    pages = {document["doc_id"]: document["page_count"] for document in documents}
    file_path = Path(path)
    raw = file_path.read_bytes()
    # Decode once and never modify the submitted review, kit, or old references.
    with io.StringIO(raw.decode("utf-8-sig"), newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames is None or len(reader.fieldnames) != len(COLUMNS) or set(reader.fieldnames) != set(COLUMNS):
            raise ValueError("Review CSV must contain each required column exactly once")
        rows = list(reader)
    errors, seen = [], set()
    counts = dict.fromkeys(REVIEW_STATUSES, 0)
    for index, original in enumerate(rows, 2):
        if None in original or any(value is None for value in original.values()):
            errors.append(f"line {index}: malformed CSV field count")
            continue
        row = {column: original[column].strip() for column in COLUMNS}
        case_id = row["case_id"]
        if case_id not in expected or case_id in seen:
            errors.append(f"line {index}: unknown or duplicate case identity")
            continue
        seen.add(case_id)
        if any(row[column] != expected[case_id][column] for column in IDENTITY_COLUMNS):
            errors.append(f"line {index}: original case/document/source identity changed")
            continue
        row_errors = _review_errors(row, row["doc_id"].split("-")[-1], pages[row["doc_id"]])
        errors.extend(f"line {index}: {error}" for error in row_errors)
        if row["status"] in counts:
            counts[row["status"]] += 1
    if len(rows) != 18 or seen != set(expected):
        errors.append("Review must preserve all and only the original 18 distinct cases")
    if errors:
        raise ValueError("Invalid independent human review: " + "; ".join(errors))
    return {
        "schema": "filing-development-human-review-validation-v1", "validated_at": _now(),
        "item_count": len(rows), "completed": counts["completed"], "status_counts": counts,
        "status": "review_complete" if counts["completed"] == 18 else "pending_human_review",
        "review_csv_sha256": _sha(raw), "source_corpus_sha256": SOURCE_CORPUS_SHA,
        "reference_mutated": False,
        "limitations": ["Identity, completeness and format checks only; financial values, quotes and reviewer identity are not independently certified."],
    }


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("acquire-sealed")
    acquire.add_argument("--attempt", default="initial")
    acquire.add_argument("--reuse-manifest", type=Path)
    acquire.add_argument("--reuse-manifest-sha256")
    qualified = commands.add_parser("qualified-metadata")
    qualified.add_argument("--attempt", default="qualified-metadata")
    qualified.add_argument("--source-manifest", type=Path, required=True)
    qualified.add_argument("--source-manifest-sha256", required=True)
    human = commands.add_parser("human-kit")
    human.add_argument("--output-dir", type=Path)
    review = commands.add_parser("validate-review")
    review.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "acquire-sealed":
        result = acquire_sealed(args.attempt, reuse_manifest=args.reuse_manifest,
                                reuse_manifest_sha256=args.reuse_manifest_sha256)
        output = {"manifest": str(SEALED_ROOT / args.attempt / "manifest.json"),
                  "documents": [{"symbol": d["symbol"], "status": d["status"]} for d in result["documents"]],
                  "failures": len(result["failures"]), "content_accessed": result["content_accessed"]}
    elif args.command == "qualified-metadata":
        result = acquire_qualified_metadata(args.attempt, source_manifest=args.source_manifest,
                                            source_manifest_sha256=args.source_manifest_sha256)
        output = {"manifest": str(SEALED_ROOT / args.attempt / "manifest.json"),
                  "documents": [{"symbol": d["symbol"], "status": d["status"]} for d in result["documents"]],
                  "failures": len(result["failures"]), "content_accessed": result["content_accessed"]}
    elif args.command == "human-kit":
        result = prepare_human_kit(args.output_dir)
        output = {"manifest": str((args.output_dir or HUMAN_KIT_ROOT) / "manifest.json"),
                  "item_count": result["item_count"], "completed": result["completed"], "status": result["status"]}
    else:
        output = validate_review_csv(args.path)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
