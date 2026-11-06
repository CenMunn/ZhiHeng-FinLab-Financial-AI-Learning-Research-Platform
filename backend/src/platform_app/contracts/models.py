from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, localcontext
import hashlib
import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

SCHEMA_VERSION = "1"
FORMULA_VERSION = "receivables-delay-v1"
ENGINE_VERSION = "decimal34-halfup-v1"
Hash = Annotated[StrictStr, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[StrictStr, Field(min_length=1, max_length=160)]


def decimal_string(value: object, *, places: int, maximum: str | None = None,
                   significant: int | None = None) -> str:
    if not isinstance(value, str) or len(value) > 32 or not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", value, flags=re.ASCII):
        raise ValueError("请使用不含指数或空格的十进制字符串")
    if "." in value and len(value.split(".")[1]) > places:
        raise ValueError(f"最多支持{places}位小数")
    number = Decimal(value)
    if number < 0 or (maximum is not None and number > Decimal(maximum)):
        raise ValueError("参数超出支持范围")
    with localcontext() as context:
        context.prec = 50
        if significant is not None and len(number.normalize().as_tuple().digits) > significant:
            raise ValueError(f"最多支持{significant}位有效数字")
    if number == 0:
        return "0"
    fixed = format(number, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def stable_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceLocator(Contract):
    source_id: Identifier
    source_url: StrictStr
    source_sha256: Hash
    value_page: Annotated[StrictInt, Field(ge=1)]
    header_pages: tuple[Annotated[StrictInt, Field(ge=1)], ...] = ()
    printed_page: StrictInt | None = None
    excerpt: StrictStr
    review_status: StrictStr
    availability_status: StrictStr
    version_status: StrictStr
    file_status: Literal["verified_at_load", "missing", "changed", "synthetic"] = "missing"
    audit_warning: StrictStr = ""

    @field_validator("source_url")
    @classmethod
    def http_source(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("来源必须使用HTTPS链接")
        return value


class CaseSnapshot(Contract):
    snapshot_id: Identifier
    snapshot_sha256: Hash
    company_id: Identifier
    company_name: StrictStr
    report_id: Identifier
    period_start: date
    period_end: date
    currency: Literal["CNY"] = "CNY"
    scope: Literal["consolidated"] = "consolidated"
    revenue: str
    days: Annotated[StrictInt, Field(ge=1, le=366)]
    evidence: EvidenceLocator
    limitations: tuple[StrictStr, ...]
    source_kind: Literal["public", "synthetic"] = "public"

    @field_validator("revenue", mode="before")
    @classmethod
    def revenue_decimal(cls, value: object) -> str:
        return decimal_string(value, places=6, significant=18)

    @model_validator(mode="after")
    def period_days(self) -> CaseSnapshot:
        if self.period_end < self.period_start or (self.period_end-self.period_start).days+1 != self.days:
            raise ValueError("报告期间与天数不一致")
        return self


class DelayAssumptions(Contract):
    credit_share: str
    delay_days: str

    @field_validator("credit_share", mode="before")
    @classmethod
    def share_decimal(cls, value: object) -> str:
        return decimal_string(value, places=6, maximum="1")

    @field_validator("delay_days", mode="before")
    @classmethod
    def delay_decimal(cls, value: object) -> str:
        return decimal_string(value, places=2, maximum="90")


class CalculationRequest(Contract):
    snapshot_id: Identifier
    expected_snapshot_sha256: Hash
    assumptions: DelayAssumptions


class ComparisonRequest(CalculationRequest):
    reference_scenario_id: Identifier | None = None


class CurvePoint(Contract):
    delay_days: str
    occupancy_change: str


class CalculationResult(Contract):
    schema_version: str = SCHEMA_VERSION
    formula_version: str = FORMULA_VERSION
    engine_version: str = ENGINE_VERSION
    input_hash: Hash
    snapshot: CaseSnapshot
    assumptions: DelayAssumptions
    occupancy_change: str
    cash_equivalent_change: str
    unrounded_occupancy_change: str
    formula: str
    limitations: tuple[StrictStr, ...]
    sensitivity_curve: tuple[CurvePoint, ...]


class SaveScenarioRequest(CalculationRequest):
    expected_input_hash: Hash
    title: Annotated[StrictStr, Field(min_length=1, max_length=80)]

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请输入情景名称")
        return value.strip()


class SavedScenario(Contract):
    scenario_id: Identifier
    project_id: Identifier
    title: str
    created_at: datetime
    result: CalculationResult

    @field_validator("created_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("保存时间必须包含时区")
        return value


class ComparisonResult(Contract):
    current: CalculationResult
    reference: CalculationResult
    reference_title: str
    difference: str
