from datetime import datetime
from typing import Annotated,Literal
from pydantic import Field,FiniteFloat,StrictInt,StrictStr,field_validator
from platform_app.contracts.models import Contract,Hash
from platform_app.contracts.public_backtests import PublicDataset
from platform_app.contracts.market_experiments import aware_utc


class ForecastMetrics(Contract):
    rows:Annotated[StrictInt,Field(ge=1)]
    mae:Annotated[FiniteFloat,Field(ge=0)]
    rmse:Annotated[FiniteFloat,Field(ge=0)]
    bias:FiniteFloat
    mse_skill_vs_zero:FiniteFloat|None
    direction_accuracy:Annotated[FiniteFloat,Field(ge=0,le=1)]|None
    zero_actual_rows:Annotated[StrictInt,Field(ge=0)]
    neutral_prediction_rows:Annotated[StrictInt,Field(ge=0)]
    temporal_correlation:Annotated[FiniteFloat,Field(ge=-1.00000001,le=1.00000001)]|None


class ForecastModel(Contract):
    name:StrictStr
    evaluation:ForecastMetrics
    validation:ForecastMetrics
    mse_difference_interval:dict
    annual:list[dict]
    policy:dict|None=None


class ForecastResult(Contract):
    schema_version:Literal['market-forecast-result-v1']=Field(alias='schema')
    run_id:Annotated[StrictStr,Field(pattern=r'^forecast-[a-f0-9]{64}$')]
    created_at:datetime
    market:Literal['ashare','btc']
    instrument:StrictStr
    currency:Literal['CNY','USDT']
    dataset_id:StrictStr
    dataset_sha256:Hash
    dataset:PublicDataset
    config:dict
    counts:dict[str,StrictInt]
    purged:dict[str,StrictInt]
    scaler:dict
    training:dict
    models:dict[str,ForecastModel]
    benchmark:dict
    evaluation:dict
    observations:list[dict]
    environment:dict[str,StrictStr]
    code_sources:dict[str,Hash]
    artifacts:dict[str,Hash]
    artifact_directory:StrictStr
    prediction_sha256:Hash
    preparation_sha256:Hash
    training_sha256:Hash
    labels_sha256:Hash
    limitations:list[StrictStr]

    @field_validator('created_at')
    @classmethod
    def timestamp(cls,value):return aware_utc(value)
