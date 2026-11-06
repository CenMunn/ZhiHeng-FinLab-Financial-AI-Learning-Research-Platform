"""Offline public-data backtests; separate from synthetic foundation-v1 records."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from platform_app.contracts.models import Contract, Hash, Identifier, decimal_string
from platform_app.contracts.market_experiments import MarketSnapshot, CostAssumptions, aware_utc


class SourceReceipt(Contract):
    url: StrictStr
    retrieved_at: datetime
    sha256: Hash
    file: StrictStr
    publisher_checksum: Hash | None = None

    @field_validator('retrieved_at')
    @classmethod
    def timestamp(cls, value):return aware_utc(value)

    @field_validator('url')
    @classmethod
    def https(cls,value):
        if not value.startswith('https://'):raise ValueError('公开来源必须使用HTTPS')
        return value

    @field_validator('file')
    @classmethod
    def relative_path(cls,value):
        from pathlib import PurePosixPath
        if '\\' in value or ':' in value or PurePosixPath(value).is_absolute() or '..' in PurePosixPath(value).parts:
            raise ValueError('来源文件必须为目录内相对路径')
        return value


class Dividend(Contract):
    session:date
    amount:str

    @field_validator('amount',mode='before')
    @classmethod
    def positive(cls,value):
        value=decimal_string(value,places=8,significant=20)
        if Decimal(value)<=0:raise ValueError('每股分红必须大于零')
        return value


class BlockObservation(Contract):
    session:date
    observed_at:datetime
    block_at:datetime
    height:Annotated[StrictInt,Field(ge=0,le=10000000)]
    block_hash:Hash

    @field_validator('observed_at','block_at')
    @classmethod
    def timestamp(cls,value):return aware_utc(value)

    @model_validator(mode='after')
    def not_future(self):
        if self.block_at>self.observed_at:raise ValueError('区块不能来自观察时点之后')
        return self


class PublicDataset(Contract):
    schema_version:Literal['public-dataset-v1']='public-dataset-v1'
    snapshot:MarketSnapshot
    receipts:tuple[SourceReceipt,...]
    dividends:tuple[Dividend,...]=()
    blocks:tuple[BlockObservation,...]=()
    timing_assumption:StrictStr
    quality:dict

    @model_validator(mode='after')
    def consistency(self):
        if self.snapshot.source_kind!='public':raise ValueError('回测需要登记的公开数据')
        if not self.receipts:raise ValueError('缺少公开数据凭据')
        for rows in (self.dividends,self.blocks):
            days=tuple(row.session for row in rows)
            if tuple(sorted(set(days)))!=days or not set(days)<=set(self.snapshot.sessions):raise ValueError('事件必须唯一、有序、属于快照日历')
        for point in self.blocks:
            bar=self.snapshot.bars[self.snapshot.sessions.index(point.session)]
            if point.observed_at>bar.close_at:raise ValueError('高度观察不能晚于当日收盘')
        if any(b.height<a.height for a,b in zip(self.blocks,self.blocks[1:])):raise ValueError('高度必须不下降')
        if self.snapshot.market=='btc' and self.dividends:raise ValueError('BTC现货没有股息')
        if self.snapshot.market=='ashare' and self.blocks:raise ValueError('股票不接受区块特征')
        return self


class BacktestConfig(Contract):
    start:date=date(2024,1,1)
    end:date=date(2025,12,31)
    window:Annotated[StrictInt,Field(ge=2,le=120)]=20
    initial_cash:str
    costs:CostAssumptions

    @field_validator('initial_cash',mode='before')
    @classmethod
    def cash(cls,value):
        value=decimal_string(value,places=2,maximum='100000000')
        if Decimal(value)<100:raise ValueError('起始现金至少100报价币')
        return value

    @model_validator(mode='after')
    def dates(self):
        if self.start>self.end:raise ValueError('开始日期不能晚于结束日期')
        return self


class BacktestRequest(Contract):
    dataset_id:Identifier
    expected_dataset_sha256:Hash
    config:BacktestConfig
