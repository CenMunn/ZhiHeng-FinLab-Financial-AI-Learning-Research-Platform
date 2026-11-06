from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

from platform_app.contracts.models import CaseSnapshot, EvidenceLocator, stable_hash

REPORT_ID = "1225240687"
STOCK_CODE = "000692"
PDF_RELATIVE = Path("data/research_checklists/sources/000692_1225240687.pdf")
SOURCE_JSON_RELATIVE = Path("reports/pilot-report-app-v4/src/data.json")


def _one(rows: list[dict], **conditions) -> dict:
    selected = [row for row in rows if all(row.get(key) == value for key, value in conditions.items())]
    if len(selected) != 1:
        raise ValueError("所选财务数据缺失或存在多个匹配，无法建立唯一快照")
    return selected[0]


def _same(actual, expected, message):
    if actual != expected:
        raise ValueError(message)


def registered_pdf_path(corporate_root: Path) -> Path:
    root = corporate_root.resolve()
    path = (root / PDF_RELATIVE).resolve()
    if not path.is_relative_to(root):
        raise ValueError("来源文件超出注册范围")
    return path


def load_huitian_2025(source_json: Path, corporate_root: Path) -> CaseSnapshot:
    data = json.loads(source_json.read_bytes())
    queries = data["queries"]
    case = _one(queries["workspace_cases"]["rows"], stock_code=STOCK_CODE,
                report_id=REPORT_ID, period_kind="annual", scope="consolidated")
    metric = _one(queries["workspace_metrics"]["rows"], stock_code=STOCK_CODE,
                  report_id=REPORT_ID, period_kind="annual", metric="revenue")
    evidence = _one(queries["workspace_evidence"]["rows"], evidence_id=metric["current_evidence_id"])
    checks = {"report_id":REPORT_ID,"stock_code":STOCK_CODE,"statement_scope":"consolidated",
              "period_kind":"annual","period_role":"current","metric":"revenue","unit":"CNY",
              "value_period_start":"2025-01-01","value_period_end":"2025-12-31",
              "source_pdf_sha256":case["sha256"],"source_url":case["source_url"]}
    for field, expected in checks.items():
        _same(evidence.get(field), expected, "财务观测的来源、期间、币种或合并口径不一致")
    _same(metric["unit"], "CNY", "不支持的金额币种")
    _same(metric["current_period_start"], "2025-01-01", "只开放已适配的2025年度报告")
    _same(metric["current_period_end"], "2025-12-31", "只开放已适配的2025年度报告")
    _same(case.get("local_pdf"), PDF_RELATIVE.as_posix(), "来源PDF路径不在注册白名单中")
    with localcontext() as context:
        context.prec = 50
        original = Decimal(evidence["source_value_signed"])
        multiplier = Decimal(evidence["multiplier_to_cny"])
        normalized = Decimal(evidence["value"])
        current = Decimal(metric["current"])
        if not all(number.is_finite() for number in (original,multiplier,normalized,current)) or multiplier <= 0:
            raise ValueError("财务原值或单位倍率无效")
        _same(original*multiplier, normalized, "原始金额与规范金额换算不一致")
        _same(normalized, current, "指标值与来源观测不一致")
    pdf_path = registered_pdf_path(corporate_root)
    file_status = "missing"
    if pdf_path.is_file():
        file_status = "verified_at_load" if hashlib.sha256(pdf_path.read_bytes()).hexdigest() == case["sha256"] else "changed"
    locator = EvidenceLocator(source_id=REPORT_ID,source_url=case["source_url"],source_sha256=case["sha256"],
        value_page=int(evidence["pdf_page"]),header_pages=(int(evidence["unit_evidence_page"]),),
        printed_page=int(evidence["printed_page"]) if evidence.get("printed_page") is not None else None,
        excerpt=evidence["excerpt"],review_status=evidence["review_status"],
        availability_status=evidence["availability_review_status"],version_status=evidence["version_history_status"],
        file_status=file_status,audit_warning=case.get("audit_warning") or "当前适配器未独立复核审计意见。")
    start,end = date.fromisoformat(metric["current_period_start"]),date.fromisoformat(metric["current_period_end"])
    snapshot = CaseSnapshot(snapshot_id="pending",snapshot_sha256="0"*64,company_id=STOCK_CODE,
        company_name=case["company"],report_id=REPORT_ID,period_start=start,period_end=end,
        revenue=format(current,"f"),days=(end-start).days+1,evidence=locator,
        limitations=("惠天热电供暖业务季节性明显，年均敏感性不代表实际逐周回款。",
                     "来源数值沿用助理核对状态，尚未经独立人工验收。",
                     "历史首次公开时点与完整版本链未认证；本案例只用于当前描述性分析。"))
    identity = snapshot.model_dump(mode="json",exclude={"snapshot_id","snapshot_sha256"})
    identity["evidence"].pop("file_status")
    sha = stable_hash(identity)
    return snapshot.model_copy(update={"snapshot_id":f"huitian-2025-{sha[:16]}","snapshot_sha256":sha})
