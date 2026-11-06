from datetime import datetime
from typing import Annotated,Literal
from pydantic import Field,StrictInt,StrictStr,field_validator,model_validator
from platform_app.contracts.models import Contract,Hash
from platform_app.contracts.market_experiments import aware_utc
from platform_app.contracts.public_backtests import PublicDataset
from platform_app.contracts.forecast_results import ForecastMetrics


class RollingModel(Contract):
    name:StrictStr
    metrics:ForecastMetrics
    wins_vs_zero:Annotated[StrictInt,Field(ge=0)]
    folds:Annotated[StrictInt,Field(ge=1,le=8)]


class RollingResult(Contract):
    schema_version:Literal['rolling-result-v1']=Field(alias='schema')
    run_id:Annotated[StrictStr,Field(pattern=r'^rolling-[a-f0-9]{64}$')]
    identity:dict[str,StrictStr]
    created_at:datetime
    market:Literal['ashare','btc']
    instrument:StrictStr
    currency:Literal['CNY','USDT']
    dataset_sha256:Hash
    dataset:PublicDataset
    protocol:dict
    folds:list[dict]
    overall:dict[str,RollingModel]
    policies:dict
    cost_sensitivity:dict
    observations:list[dict]
    pretrained:dict
    phase_receipts:dict
    artifacts:dict[str,Hash]
    limitations:list[StrictStr]

    @field_validator('created_at')
    @classmethod
    def timestamp(cls,value):return aware_utc(value)

    @model_validator(mode='after')
    def quarters(self):
        if [f.get('fold') for f in self.folds]!=[f'{year}Q{q}' for year in (2024,2025) for q in (1,2,3,4)]:raise ValueError('滚动折必须唯一有序并覆盖已登记八季')
        for model in self.pretrained.get('models',{}).values():RollingModel.model_validate(model)
        return self
