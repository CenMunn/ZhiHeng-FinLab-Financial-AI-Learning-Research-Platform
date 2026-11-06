from datetime import datetime, timezone
from decimal import Decimal, localcontext
import re
from uuid import uuid4

from platform_app.adapters.scenario_store import SaveOutcome, ScenarioStore
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import CalculationRequest, CalculationResult, ComparisonRequest, ComparisonResult, DelayAssumptions, SaveScenarioRequest, SavedScenario, stable_hash
from platform_app.evidence.service import CaseService
from platform_app.risk.receivables import calculate_delay


class ScenarioService:
    def __init__(self, cases: CaseService, store: ScenarioStore):
        self.cases, self.store = cases, store

    def calculate(self, request: CalculationRequest) -> CalculationResult:
        snapshot = self.cases.get(request.snapshot_id)
        if request.expected_snapshot_sha256 != snapshot.snapshot_sha256:
            raise DomainConflict("snapshot_changed", "资料版本与请求不一致，请重新载入案例。")
        return calculate_delay(snapshot, request.assumptions)

    def save(self, request: SaveScenarioRequest, idempotency_key: str,
             project_id: str = "local") -> SaveOutcome:
        if not isinstance(idempotency_key,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",idempotency_key):
            raise ValueError("保存请求键无效")
        fingerprint = stable_hash(request.model_dump(mode="json"))
        cached = self.store.find_request(project_id,idempotency_key,fingerprint)
        if cached is not None:
            return cached
        result = self.calculate(CalculationRequest(snapshot_id=request.snapshot_id,
            expected_snapshot_sha256=request.expected_snapshot_sha256,assumptions=request.assumptions))
        if result.input_hash != request.expected_input_hash:
            raise DomainConflict("calculation_changed","计算版本已变化，请重新计算并核对结果后保存。")
        saved = SavedScenario(scenario_id=str(uuid4()),project_id=project_id,title=request.title,
                              created_at=datetime.now(timezone.utc),result=result)
        return self.store.save(saved,idempotency_key,fingerprint)

    def compare(self, request: ComparisonRequest) -> ComparisonResult:
        current = self.calculate(CalculationRequest(snapshot_id=request.snapshot_id,
            expected_snapshot_sha256=request.expected_snapshot_sha256,assumptions=request.assumptions))
        if request.reference_scenario_id is None:
            reference = calculate_delay(current.snapshot,DelayAssumptions(credit_share=request.assumptions.credit_share,delay_days="0"))
            title = "无新增回款延迟"
        else:
            saved = self.get(request.reference_scenario_id)
            reference,title = saved.result,saved.title
        if (current.snapshot.snapshot_sha256,current.formula_version,current.engine_version) != (
                reference.snapshot.snapshot_sha256,reference.formula_version,reference.engine_version):
            raise DomainConflict("comparison_basis_mismatch","资料或公式版本不同，不能直接比较资金占用差值。")
        with localcontext() as context:
            context.prec = 34
            difference = Decimal(current.occupancy_change)-Decimal(reference.occupancy_change)
        return ComparisonResult(current=current,reference=reference,reference_title=title,difference=format(difference,".2f"))

    def get(self, scenario_id: str) -> SavedScenario:
        return self.store.get(scenario_id)

    def list(self, project_id: str = "local") -> tuple[SavedScenario, ...]:
        return self.store.list(project_id)
