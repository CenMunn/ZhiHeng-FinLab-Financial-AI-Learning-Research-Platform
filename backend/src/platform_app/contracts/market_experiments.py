from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StrictInt, StrictStr, field_validator, model_validator
from platform_app.contracts.models import Contract, Hash, Identifier, decimal_string

UTC=timezone.utc
SHANGHAI=timezone(timedelta(hours=8))

def aware_utc(value:datetime)->datetime:
    if value.tzinfo is None or value.utcoffset() is None:raise ValueError('时间必须包含时区')
    return value.astimezone(UTC)

class MarketBar(Contract):
    session:date
    close_at:datetime
    available_at:datetime
    open:str|None
    high:str|None
    low:str|None
    close:str|None
    volume:str
    status:Literal['open','halted']='open'

    @field_validator('close_at','available_at')
    @classmethod
    def timestamps(cls,value):return aware_utc(value)

    @field_validator('open','high','low','close','volume',mode='before')
    @classmethod
    def decimals(cls,value):return None if value is None else decimal_string(value,places=8,significant=20)

    @model_validator(mode='after')
    def valid_bar(self):
        if self.available_at<self.close_at:raise ValueError('数据可用时间早于收盘')
        prices=(self.open,self.high,self.low,self.close)
        if self.status=='halted':
            if any(p is not None for p in prices) or self.volume!='0':raise ValueError('停牌必须保留空价格和零成交量')
        else:
            if any(p is None or Decimal(p)<=0 for p in prices):raise ValueError('开市价格必须为正数')
            if not Decimal(self.low)<=min(Decimal(self.open),Decimal(self.close))<=max(Decimal(self.open),Decimal(self.close))<=Decimal(self.high):raise ValueError('OHLC价格范围不一致')
        return self

class MarketSnapshot(Contract):
    schema_version:Literal['market-snapshot-v1']='market-snapshot-v1'
    snapshot_id:Identifier
    market:Literal['ashare','btc']
    instrument:Identifier
    venue:Identifier
    currency:Literal['CNY','USDT']
    source_kind:Literal['synthetic','public']
    source_uri:StrictStr
    source_license:StrictStr
    calendar_kind:Literal['synthetic','venue']
    calendar_source:StrictStr
    price_basis:Literal['raw']='raw'
    frequency:Literal['1d']='1d'
    sessions:tuple[date,...]
    bars:tuple[MarketBar,...]
    quantity_step:str
    limitations:tuple[StrictStr,...]

    @field_validator('quantity_step',mode='before')
    @classmethod
    def quantity(cls,value):
        value=decimal_string(value,places=8,significant=20)
        if Decimal(value)<=0:raise ValueError('数量步长必须为正')
        return value

    @model_validator(mode='after')
    def calendar_and_market(self):
        if not self.sessions or len(self.sessions)>10000:raise ValueError('日历样本范围为1至10000行')
        if tuple(sorted(set(self.sessions)))!=self.sessions:raise ValueError('日历必须严格递增且无重复')
        if tuple(bar.session for bar in self.bars)!=self.sessions:raise ValueError('行情与日历必须逐行对应，禁止缺失、重复或乱序')
        if self.source_kind=='public' and self.calendar_kind!='venue':raise ValueError('公开行情不得使用合成交易日历')
        if not self.source_uri or not self.calendar_source or not self.source_license:raise ValueError('来源、日历来源和许可不能为空')
        if self.market=='ashare':
            if self.currency!='CNY' or self.quantity_step!='1':raise ValueError('当前A股配置仅支持人民币普通主板整数股')
            for bar in self.bars:
                if bar.session.weekday()>4 or bar.close_at!=datetime.combine(bar.session,time(15),SHANGHAI).astimezone(UTC):raise ValueError('A股日线须对应显式交易日15:00上海时间')
        else:
            if self.currency!='USDT':raise ValueError('当前BTC配置仅支持USDT现货示例')
            for index,bar in enumerate(self.bars):
                if bar.close_at!=datetime.combine(bar.session+timedelta(days=1),time(),UTC):raise ValueError('BTC日线以UTC开日标记、次日00:00收盘')
                if index and bar.session-self.sessions[index-1]!=timedelta(days=1):raise ValueError('BTC日历必须连续，不能遗漏周末')
        return self

class CostAssumptions(Contract):
    commission_bps:str='3'
    minimum_commission:str='5'
    sell_tax_bps:str='5'
    transfer_bps:str='0.1'
    slippage_bps:str='2'
    kind:Literal['teaching_assumption']='teaching_assumption'

    @field_validator('commission_bps','sell_tax_bps','transfer_bps','slippage_bps',mode='before')
    @classmethod
    def rate(cls,value):return decimal_string(value,places=4,maximum='1000')
    @field_validator('minimum_commission',mode='before')
    @classmethod
    def minimum(cls,value):return decimal_string(value,places=8,maximum='1000000')

class FoundationConfig(Contract):
    train_count:Annotated[StrictInt,Field(ge=3,le=9998)]
    validation_count:Annotated[StrictInt,Field(ge=1,le=9998)]
    window:Annotated[StrictInt,Field(ge=2,le=120)]=3
    horizon:Annotated[StrictInt,Field(ge=1,le=20)]=1
    as_of:datetime
    seed:Annotated[StrictInt,Field(ge=0,le=2147483647)]=42
    costs:CostAssumptions

    @field_validator('as_of')
    @classmethod
    def timestamp(cls,value):return aware_utc(value)

class FoundationRequest(Contract):
    snapshot_id:Identifier
    expected_snapshot_sha256:Hash
    config:FoundationConfig
