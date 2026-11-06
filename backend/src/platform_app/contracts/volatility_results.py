"""Published volatility results. No training or numerical runtime dependencies."""
from collections import Counter
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator, model_validator
from platform_app.contracts.market_experiments import aware_utc
from platform_app.contracts.models import Contract, Hash
from platform_app.contracts.public_backtests import PublicDataset

Finite = Annotated[StrictFloat, Field(allow_inf_nan=False)]
Nonnegative = Annotated[Finite, Field(ge=0)]
Count = Annotated[StrictInt, Field(ge=0)]


class VolatilityMetrics(Contract):
    rows: Count
    qlike: Finite | None
    variance_rmse: Nonnegative | None
    variance_mae: Nonnegative | None
    volatility_rmse_ann: Nonnegative | None
    calibration_ratio: Nonnegative | None
    prediction_floor_count: Count

    @model_validator(mode='after')
    def populated(self):
        values = (self.qlike, self.variance_rmse, self.variance_mae, self.volatility_rmse_ann)
        if self.prediction_floor_count > self.rows:
            raise ValueError('触底数量不能超过样本数')
        if self.rows and any(value is None for value in values):
            raise ValueError('非空样本必须提供指标')
        if not self.rows and any(value is not None for value in (*values, self.calibration_ratio)):
            raise ValueError('空样本指标必须为空，不能以零代替未知')
        return self


class VolatilityComparison(Contract):
    delta_qlike: Finite
    ci_low: Finite | None
    ci_high: Finite | None
    block: Annotated[StrictInt, Field(ge=1)]
    repeats: Annotated[StrictInt, Field(ge=1)]

    @model_validator(mode='after')
    def interval(self):
        if (self.ci_low is None) != (self.ci_high is None):
            raise ValueError('区间上下界必须同时存在')
        if self.ci_low is not None and self.ci_low > self.ci_high:
            raise ValueError('区间上下界颠倒')
        return self


class VolatilityModel(Contract):
    name: StrictStr
    metrics: VolatilityMetrics
    comparison: VolatilityComparison


class VolatilityOverall(VolatilityModel):
    wins_vs_ewma: Count
    folds: Annotated[StrictInt, Field(ge=1, le=8)]

    @model_validator(mode='after')
    def wins(self):
        if self.wins_vs_ewma > self.folds:
            raise ValueError('胜出季度数超过总季度数')
        return self


class VolatilityFold(Contract):
    fold: StrictStr
    bounds: dict
    counts: dict[str, Count]
    purged: dict[str, Count]
    regime_thresholds: dict
    models: dict[str, VolatilityModel]
    training: dict


class VolatilityRegimeModel(Contract):
    name: StrictStr
    metrics: VolatilityMetrics | None
    comparison: VolatilityComparison | None


class VolatilityRegime(Contract):
    name: StrictStr
    rows: Count
    sufficient: StrictBool
    models: dict[str, VolatilityRegimeModel]


class VolatilityObservation(Contract):
    session: date
    fold: StrictStr
    regime: StrictStr
    realized_variance: Nonnegative
    predictions: dict[str, Annotated[Finite, Field(ge=1e-10)]]
    label_end: date


class VolatilityResult(Contract):
    schema_version: Literal['volatility-result-v1'] = Field(alias='schema')
    run_id: Annotated[StrictStr, Field(pattern=r'^volatility-[a-f0-9]{64}$')]
    identity: dict[str, StrictStr]
    created_at: datetime
    market: Literal['ashare', 'btc']
    instrument: StrictStr
    currency: Literal['CNY', 'USDT']
    horizon: Literal[1, 5]
    annualization: Literal[252, 365]
    dataset_sha256: Hash
    dataset: PublicDataset
    protocol: dict
    folds: list[VolatilityFold]
    overall: dict[str, VolatilityOverall]
    regimes: dict[str, VolatilityRegime]
    observations: list[VolatilityObservation]
    artifacts: Annotated[dict[str, Hash], Field(min_length=1)]
    limitations: list[StrictStr]
    phase_receipts: dict

    @field_validator('created_at')
    @classmethod
    def timestamp(cls, value):
        return aware_utc(value)

    @model_validator(mode='after')
    def coherent(self):
        expected = [f'{year}Q{quarter}' for year in (2024, 2025) for quarter in (1, 2, 3, 4)]
        if [fold.fold for fold in self.folds] != expected:
            raise ValueError('必须保留唯一有序的全部八季度')
        if self.annualization != (252 if self.market == 'ashare' else 365):
            raise ValueError('年化天数与市场不符')
        models = set(self.overall)
        if 'ewma' not in models or not self.observations:
            raise ValueError('必须保留EWMA对照与实际预测')
        sessions = [row.session for row in self.observations]
        if sessions != sorted(set(sessions)):
            raise ValueError('预测日期必须唯一有序')
        by_fold = Counter(row.fold for row in self.observations)
        by_regime = Counter(row.regime for row in self.observations)
        if set(by_fold) != set(expected) or not set(by_regime).issubset(self.regimes):
            raise ValueError('预测缺少季度或市况归属')
        for row in self.observations:
            quarter = f'{row.session.year}Q{(row.session.month-1)//3+1}'
            if set(row.predictions) != models or row.label_end <= row.session or row.fold != quarter:
                raise ValueError('预测模型、标签成熟时间或季度归属错配')
        for model in self.overall.values():
            if model.metrics.rows != len(self.observations) or model.folds != 8:
                raise ValueError('总体样本数或季度数错配')
        for fold in self.folds:
            if set(fold.models) != models or any(m.metrics.rows != by_fold[fold.fold] for m in fold.models.values()):
                raise ValueError('季度模型或样本数错配')
            if fold.counts.get('evaluation') != by_fold[fold.fold]:
                raise ValueError('季度评估样本数错配')
        for key, regime in self.regimes.items():
            if set(regime.models) != models or regime.rows != by_regime[key] or regime.sufficient != (regime.rows >= 30):
                raise ValueError('市况模型、样本数或充分性错配')
            for model in regime.models.values():
                if regime.rows == 0:
                    if model.metrics is not None or model.comparison is not None:
                        raise ValueError('空市况必须保留空指标与空比较')
                elif model.metrics is None or model.metrics.rows != regime.rows or model.comparison is None:
                    raise ValueError('市况指标样本数错配')
        return self
