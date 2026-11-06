from decimal import Decimal, ROUND_HALF_UP, localcontext

from platform_app.contracts.models import (
    CaseSnapshot, CalculationResult, CurvePoint, DelayAssumptions,
    ENGINE_VERSION, FORMULA_VERSION, SCHEMA_VERSION, stable_hash,
)


def canonical_input(snapshot: CaseSnapshot, assumptions: DelayAssumptions) -> dict:
    data = snapshot.model_dump(mode="json")
    # Runtime file availability is not part of the immutable financial input.
    data["evidence"].pop("file_status", None)
    return {"schema_version": SCHEMA_VERSION, "formula_version": FORMULA_VERSION,
            "engine_version": ENGINE_VERSION, "snapshot": data,
            "assumptions": assumptions.model_dump(mode="json")}


def _occupancy(snapshot: CaseSnapshot, share: str, delay: str) -> Decimal:
    return Decimal(snapshot.revenue)*Decimal(share)*Decimal(delay)/Decimal(snapshot.days)


def calculate_delay(snapshot: CaseSnapshot, assumptions: DelayAssumptions) -> CalculationResult:
    with localcontext() as context:
        context.prec = 34
        context.rounding = ROUND_HALF_UP
        raw = _occupancy(snapshot, assumptions.credit_share, assumptions.delay_days)
        amount = raw.quantize(Decimal("0.01"))
        equivalent = -amount if amount != 0 else Decimal("0.00")
        days = sorted({Decimal(str(day)) for day in range(0, 91, 15)} | {Decimal(assumptions.delay_days)})
        points = tuple(CurvePoint(delay_days=format(day, "f"),
                       occupancy_change=format(_occupancy(snapshot, assumptions.credit_share, str(day))
                                               .quantize(Decimal("0.01")), ".2f")) for day in days)
        return CalculationResult(input_hash=stable_hash(canonical_input(snapshot, assumptions)),
            snapshot=snapshot, assumptions=assumptions, occupancy_change=format(amount, ".2f"),
            cash_equivalent_change=format(equivalent, ".2f"), unrounded_occupancy_change=format(raw, "f"),
            formula="应收占款变化 = 报告期收入 × 假设赊销比例 × 回款延迟天数 ÷ 报告期间天数",
            limitations=snapshot.limitations + ("均匀销售与稳定经营结构假设下的稳态估算，不代表逐周现金预测或已实现收款。",
                "暂不考虑税费、折扣、退货和客户违约；显示到分不代表估计准确到分。"),
            sensitivity_curve=points)
