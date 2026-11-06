from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
from typing import Annotated

from fastapi import FastAPI, Header, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from platform_app.adapters.corporate_risk import load_huitian_2025, registered_pdf_path, SOURCE_JSON_RELATIVE, REPORT_ID
from platform_app.adapters.scenario_store import ScenarioStore
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import CaseSnapshot, CalculationRequest, CalculationResult, ComparisonRequest, ComparisonResult, SaveScenarioRequest, SavedScenario, SCHEMA_VERSION
from platform_app.evidence.service import CaseService
from platform_app.risk.scenario_service import ScenarioService
from platform_app.integrations.committee import integration_status
from platform_app.adapters.experiment_store import ExperimentStore
from platform_app.api.experiments import experiment_router
from platform_app.adapters.backtest_store import BacktestStore
from platform_app.api.backtests import backtest_router
from platform_app.adapters.forecast_store import ForecastStore
from platform_app.api.forecasts import forecast_router
from platform_app.adapters.rolling_store import RollingStore
from platform_app.api.rolling import rolling_router
from platform_app.adapters.volatility_store import VolatilityStore
from platform_app.api.volatility import volatility_router
from platform_app.adapters.volatility_diagnostics_store import VolatilityDiagnosticsStore
from platform_app.adapters.validation_foundation_store import ValidationFoundationStore
from platform_app.api.validation_foundation import validation_foundation_router

from platform_app.adapters.five_asset_store import FiveAssetStore
from platform_app.api.five_asset import five_asset_router

from platform_app.adapters.risk_budget_store import RiskBudgetStore
from platform_app.api.risk_budget import risk_budget_router
from platform_app.adapters.forward_store import ForwardStore
from platform_app.api.forward import forward_router
from platform_app.adapters.event_study_store import EventStudyStore
from platform_app.api.event_study import event_study_router
from platform_app.adapters.filing_extraction_store import FilingExtractionStore
from platform_app.api.filing_extraction import filing_extraction_router
from platform_app.adapters.filing_development_store import FilingDevelopmentStore
from platform_app.api.filing_development import filing_development_router
from platform_app.adapters.filing_semantics_store import FilingSemanticsStore
from platform_app.api.filing_semantics import filing_semantics_router
from platform_app.api.filing_semantics_v2 import filing_semantics_v2_router
from platform_app.adapters.filing_semantics_v2_store import FilingSemanticsV2Store

PROJECT = Path(__file__).resolve().parents[4]


def create_app(*, cases: CaseService | None = None, store: ScenarioStore | None = None,
               corporate_root: Path | None = None, experiment_store:ExperimentStore|None=None,
               backtest_store:BacktestStore|None=None,public_datasets=None,forecast_store:ForecastStore|None=None,rolling_store:RollingStore|None=None,
               volatility_store:VolatilityStore|None=None, volatility_diagnostics_store:VolatilityDiagnosticsStore|None=None,
               validation_foundation_store:ValidationFoundationStore|None=None, five_asset_store:FiveAssetStore|None=None, risk_budget_store:RiskBudgetStore|None=None, forward_store:ForwardStore|None=None, event_study_store:EventStudyStore|None=None, filing_extraction_store:FilingExtractionStore|None=None, filing_development_store:FilingDevelopmentStore|None=None) -> FastAPI:
    corporate_root = corporate_root or PROJECT.parent / "corporate-risk"
    if cases is None:
        try:
            cases = CaseService((load_huitian_2025(corporate_root/SOURCE_JSON_RELATIVE,corporate_root),))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ArithmeticError):
            # History owns its snapshots and stays readable when live input fails.
            cases = CaseService(())
    store = store or ScenarioStore(PROJECT/"backend/data/scenarios.sqlite3")
    service = ScenarioService(cases,store)
    app = FastAPI(title="财务风险研究台",version="0.1.0")
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=["127.0.0.1","localhost","testserver"])
    app.include_router(experiment_router(experiment_store or ExperimentStore(PROJECT/'backend/data/experiments.sqlite3')))
    app.include_router(backtest_router(backtest_store or BacktestStore(PROJECT/'backend/data/experiments.sqlite3'),PROJECT/'backend/data/public-market',public_datasets))
    app.include_router(forecast_router(forecast_store or ForecastStore(PROJECT/'backend/data/forecast-runs',PROJECT)))
    app.include_router(rolling_router(rolling_store or RollingStore(PROJECT/'backend/data/rolling-runs',PROJECT)))
    volatility_store = volatility_store or VolatilityStore(PROJECT/'backend/data/volatility-runs',PROJECT)
    app.include_router(volatility_router(volatility_store, volatility_diagnostics_store or VolatilityDiagnosticsStore(PROJECT/'backend/data/volatility-diagnostics',PROJECT,volatility_store)))

    validation_foundation_store = validation_foundation_store or ValidationFoundationStore(PROJECT/'backend/data/validation-foundation',PROJECT)
    app.include_router(validation_foundation_router(validation_foundation_store))
    app.include_router(five_asset_router(five_asset_store or FiveAssetStore(PROJECT/'backend/data/five-asset-runs',PROJECT,validation_foundation_store)))

    app.include_router(risk_budget_router(risk_budget_store or RiskBudgetStore(PROJECT/'backend/data/risk-budget-runs',PROJECT,validation_foundation_store)))
    app.include_router(forward_router(forward_store or ForwardStore(PROJECT/'backend/data/forward-market',PROJECT)))
    app.include_router(event_study_router(event_study_store or EventStudyStore(PROJECT/'backend/data/event-study',PROJECT)))
    app.include_router(filing_extraction_router(filing_extraction_store or FilingExtractionStore(PROJECT/'backend/data/filing-extraction',PROJECT)))
    app.include_router(filing_development_router(filing_development_store or FilingDevelopmentStore(PROJECT/'backend/data/filing-development',PROJECT)))
    app.include_router(filing_semantics_v2_router(FilingSemanticsV2Store(PROJECT/'backend/data/filing-semantics-v2',PROJECT)))
    app.include_router(filing_semantics_router(FilingSemanticsStore(PROJECT/'backend/data/filing-semantics',PROJECT)))

    @app.get('/api/v1/integrations/committee')
    def committee_status():
        return JSONResponse(content=integration_status(PROJECT), headers={'Cache-Control':'no-store'})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = [{"field":".".join(str(item) for item in error["loc"]),"message":error["msg"]}
                  for error in exc.errors()]
        return JSONResponse(status_code=422,content={"code":"invalid_input","message":"参数有误，请检查输入值和范围。","fields":fields})

    @app.exception_handler(DomainConflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409,content={"code":exc.code,"message":str(exc)})

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse(status_code=404,content={"code":"not_found","message":"未找到所选案例、情景或来源。"})

    @app.exception_handler(ValueError)
    async def invalid_value(request, exc):
        return JSONResponse(status_code=422,content={"code":"invalid_input","message":str(exc)})

    @app.exception_handler(sqlite3.Error)
    async def storage_error(request, exc):
        return JSONResponse(status_code=500,content={"code":"storage_error","message":"情景保存失败，请保留当前参数后重试。"})

    @app.get("/api/v1/health")
    def health():
        return {"status":"ready" if cases.list() else "history_only","source_status":"available" if cases.list() else "unavailable",
                "schema_version":SCHEMA_VERSION,"model_status":"not_trained"}

    @app.get("/api/v1/cases",response_model=tuple[CaseSnapshot,...])
    def list_cases():
        return cases.list()

    @app.get("/api/v1/cases/{snapshot_id}",response_model=CaseSnapshot)
    def get_case(snapshot_id: str):
        return cases.get(snapshot_id)

    @app.post("/api/v1/risk/receivables-delay",response_model=CalculationResult)
    def calculate(body: CalculationRequest):
        return service.calculate(body)

    @app.post("/api/v1/risk/receivables-compare",response_model=ComparisonResult)
    def compare(body: ComparisonRequest):
        return service.compare(body)

    @app.post("/api/v1/scenarios",response_model=SavedScenario,status_code=201)
    def save(body: SaveScenarioRequest,response: Response,
             idempotency_key: Annotated[str,Header(alias="Idempotency-Key")]):
        outcome = service.save(body,idempotency_key)
        response.status_code = 200 if outcome.replayed else 201
        return outcome.scenario

    @app.get("/api/v1/scenarios",response_model=tuple[SavedScenario,...])
    def list_scenarios():
        return service.list()

    @app.get("/api/v1/scenarios/{scenario_id}",response_model=SavedScenario)
    def get_scenario(scenario_id: str):
        return service.get(scenario_id)

    def source_bytes(source_id: str):
        if source_id != REPORT_ID:
            raise KeyError(source_id)
        path = registered_pdf_path(corporate_root)
        try:
            return path.read_bytes()
        except OSError:
            return None

    @app.get("/api/v1/sources/{source_id}/status")
    def source_status(source_id: str, expected_sha256: Annotated[str,Query(pattern=r"^[0-9a-f]{64}$")]):
        content = source_bytes(source_id)
        status = "missing" if content is None else "available" if hashlib.sha256(content).hexdigest() == expected_sha256 else "changed"
        return JSONResponse(content={"status":status},headers={"Cache-Control":"no-store"})

    @app.get("/api/v1/sources/{source_id}")
    def source_pdf(source_id: str, expected_sha256: Annotated[str,Query(pattern=r"^[0-9a-f]{64}$")]):
        content = source_bytes(source_id)
        if content is None:
            raise KeyError(source_id)
        if hashlib.sha256(content).hexdigest() != expected_sha256:
            raise DomainConflict("source_changed","原文件已变化，无法把当前文件作为保存时的原文。")
        return Response(content,media_type="application/pdf",headers={"Content-Disposition":f'inline; filename="report-{source_id}.pdf"',
            "X-Content-Type-Options":"nosniff","Cache-Control":"no-store"})

    return app
