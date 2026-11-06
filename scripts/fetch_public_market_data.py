"""Acquire the frozen teaching datasets. Run with backend's Python; no API keys.

PYTHONPATH=backend/src python scripts/fetch_public_market_data.py
Raw responses stay ignored by Git. Existing cache is checked, never silently refreshed.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as daytime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'backend/src'))
from platform_app.adapters.public_market import parse_xshg_calendar, parse_yahoo_dividends, parse_tencent_chart, parse_binance_zip
from platform_app.contracts.market_experiments import MarketSnapshot
from platform_app.contracts.public_backtests import SourceReceipt, PublicDataset, BlockObservation
from platform_app.contracts.models import stable_hash

UTC=timezone.utc
ROOT=PROJECT/'backend/data/public-market'
START=date(2018,1,1);END=date(2025,12,31)
CALENDAR='https://raw.githubusercontent.com/gerrymanoim/exchange_calendars/4.11.2/exchange_calendars/exchange_calendar_xshg.py'
TIMING='历史重建行情；收盘后1分钟可用是教学假设，不是历史发布/接收时间凭据。'


def fetch(url:str,name:str):
    path=ROOT/'raw'/name;meta=path.with_suffix(path.suffix+'.receipt.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and meta.exists():
        raw=path.read_bytes();receipt=SourceReceipt.model_validate_json(meta.read_bytes())
        if receipt.url!=url or receipt.sha256!=hashlib.sha256(raw).hexdigest():raise ValueError('缓存来源或哈希变化，需人工检查：'+name)
        return raw,receipt
    if path.exists() or meta.exists():raise ValueError('缓存写入不完整，需人工检查：'+name)
    last=None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'FinancialLearningLab/0.1 (public daily educational research)'}),timeout=25) as response:
                raw=response.read(20_000_001)
                if len(raw)>20_000_000:raise ValueError('来源响应超过20MB')
            receipt=SourceReceipt(url=url,retrieved_at=datetime.now(UTC),sha256=hashlib.sha256(raw).hexdigest(),file='raw/'+name)
            path.write_bytes(raw);meta.write_text(receipt.model_dump_json(indent=2),encoding='utf8')
            return raw,receipt
        except (urllib.error.URLError,TimeoutError) as exc:
            last=exc;time.sleep(2**attempt)
    raise RuntimeError('公开来源下载失败：'+url) from last


def save(dataset):
    body=dataset.model_dump(mode='json');digest=stable_hash(body)
    target=ROOT/(dataset.snapshot.snapshot_id+'.json')
    payload=json.dumps({'sha256':digest,'dataset':body},ensure_ascii=False,indent=2)
    if target.exists() and target.read_text(encoding='utf8')!=payload:raise ValueError('已登记快照不能覆盖：'+str(target))
    target.write_text(payload,encoding='utf8')
    print(json.dumps({'dataset':dataset.snapshot.snapshot_id,'sha256':digest,'quality':dataset.quality},ensure_ascii=False),flush=True)


def ashare():
    raw,cal=fetch(CALENDAR,'xshg-4.11.2.py')
    sessions=parse_xshg_calendar(raw.decode('utf8'),START,END)
    start=int(datetime.combine(START,daytime(),UTC).timestamp());end=int(datetime.combine(END+timedelta(days=1),daytime(),UTC).timestamp())
    url=f'https://query1.finance.yahoo.com/v8/finance/chart/600519.SS?period1={start}&period2={end}&interval=1d&events=div%2Csplits'
    raw,prices=fetch(url,'yahoo-600519-2018-2025.json')
    dividends=parse_yahoo_dividends(raw,sessions)
    yahoo=json.loads(raw)['chart']['result'][0];q=yahoo['indicators']['quote'][0]
    invalid=[str(datetime.fromtimestamp(t,UTC).date()) for i,t in enumerate(yahoo['timestamp'])
             if any(q[k][i] is None for k in ('open','high','low','close')) or not q['low'][i]<=min(q['open'][i],q['close'][i])<=max(q['open'][i],q['close'][i])<=q['high'][i]]
    bars=[];receipts=[cal,prices]
    for year in range(2018,2026):
        quote_url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,{year}-01-01,{year}-12-31,640,'
        raw,receipt=fetch(quote_url,f'tencent-600519-{year}-raw.json');receipts.append(receipt)
        bars.extend(parse_tencent_chart(raw,tuple(d for d in sessions if d.year==year)))
    yahoo_by_day={str(datetime.fromtimestamp(t,UTC).date()):{k:q[k][i] for k in ('open','high','low','close')} for i,t in enumerate(yahoo['timestamp'])}
    differences=sum(1 for bar in bars if str(bar.session) not in yahoo_by_day or any(yahoo_by_day[str(bar.session)][k] is None or abs(Decimal(str(yahoo_by_day[str(bar.session)][k]))-Decimal(getattr(bar,k)))>Decimal('.011') for k in ('open','high','low','close')))
    limitations=(TIMING,'单一现存股票教学案例；不能外推市场表现，存在选择和幸存偏差。',
                  '原价OHLC用腾讯公开day字段、分红/拆股事件用Yahoo；均非交易所逐时档案，不能证明事件完整。腾讯成交量手乘100为近似股数，仅作非零检查。',
                  '分红在除息日确认为不可再投资的应收；没有支付日、个人分红税和真实券商费率。',
                  '日历为exchange_calendars 4.11.2社区XSHG休市表，不是直接获取的官方交易日历。',
                  '仅普通主板T+1/100股买入和10%保守开盘过滤的教学子集；不模拟竞价排队、流动性或完整涨跌停规则。')
    snapshot=MarketSnapshot(snapshot_id='ashare-600519-2018-2025',market='ashare',instrument='600519.SS',venue='XSHG',currency='CNY',source_kind='public',source_uri='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
        source_license='公开可访问不等于自由再分发；遵循腾讯、Yahoo及原提供者条款，原文件仅本地留存。',calendar_kind='venue',calendar_source=CALENDAR,
        sessions=sessions,bars=tuple(bars),quantity_step='1',limitations=limitations)
    save(PublicDataset(snapshot=snapshot,receipts=tuple(receipts),dividends=dividends,timing_assumption=TIMING,
        quality={'expected_sessions':len(sessions),'actual_bars':len(bars),'missing':0,'duplicates':0,'dividend_events':len(dividends),'split_events':0,
                 'start':str(START),'end':str(END),'calendar_version':'exchange_calendars 4.11.2; XSHG','availability':'assumed_not_vintage',
                 'rejected_yahoo_ohlc_dates':invalid,'cross_vendor_different_ohlc_rows_over_0011':differences,'primary_quotes':'Tencent day (unadjusted)','corporate_events':'Yahoo dividends/splits'}))


def month(item):
    year,month=item;tag=f'{year}-{month:02d}';name=f'BTCUSDT-1d-{tag}.zip'
    url='https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1d/'+name
    raw,receipt=fetch(url,name);checksum,checkreceipt=fetch(url+'.CHECKSUM',name+'.CHECKSUM')
    published=checksum.decode('ascii').split()[0]
    if receipt.sha256!=published:raise ValueError('Binance发布者校验失败：'+name)
    receipt=receipt.model_copy(update={'publisher_checksum':published})
    bars=parse_binance_zip(raw)
    if any(b.session.year!=year or b.session.month!=month for b in bars):raise ValueError('归档月份不匹配')
    return bars,(receipt,checkreceipt)


def block(day):
    # Leave an explicit hour before close. Header time is not a first-seen receipt.
    observed=datetime.combine(day+timedelta(days=1),daytime(),UTC)-timedelta(hours=1)
    requested=int(observed.timestamp());receipts=[]
    for _ in range(4):
        name='block-'+str(requested)+'.json'
        cached=(ROOT/'raw'/name).exists()
        raw,receipt=fetch('https://mempool.space/api/v1/mining/blocks/timestamp/'+str(requested),name)
        if not cached:time.sleep(.5) # bounded four workers, small daily responses
        receipts.append(receipt);body=json.loads(raw)
        block_at=datetime.fromisoformat(body['timestamp'].replace('Z','+00:00'))
        if block_at<=observed:
            if observed-block_at>timedelta(hours=6):raise ValueError('区块观察过旧，不作插值')
            return BlockObservation(session=day,observed_at=observed,block_at=block_at,height=body['height'],block_hash=body['hash']),tuple(receipts)
        requested-=3600 # closest may be later than cutoff: retry earlier, never consume future block
    raise ValueError('无法取得观察时点之前的区块')


def btc():
    bars=[];receipts=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(rows,items) in enumerate(pool.map(month,[(y,m) for y in range(2018,2026) for m in range(1,13)])):
            bars.extend(rows);receipts.extend(items)
            if (i+1)%12==0:print(f'BTC verified months {i+1}/96',flush=True)
    sessions=tuple(START+timedelta(days=i) for i in range((END-START).days+1))
    blocks=[];first=date(2023,12,30);days=[first+timedelta(days=i) for i in range((END-first).days+1)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,(point,items) in enumerate(pool.map(block,days)):
            blocks.append(point);receipts.extend(items)
            if (i+1)%50==0:print(f'BTC block observations {i+1}/{len(days)}',flush=True)
    limitations=(TIMING,'仅Binance BTCUSDT现货，计价USDT而非美元；不含融资、杠杆、永续资金费率或链上交易费用。',
                  '区块高度是历史接口按区块头时间重建，不是当时节点接收日志；每日收盘前1小时取样，可能滞后，拒绝未来或超过6小时的块。',
                  '狼波的3/4上行、1/4下行及减半居中是待验证假设；本评估段只有一次减半，不能证明四年规律或顶部日期准确性。',
                  '数量步长0.00001、费率和1分钟行情延迟均为教学假设，不是历史交易所过滤器或实际可成交承诺。')
    snapshot=MarketSnapshot(snapshot_id='btc-btcusdt-2018-2025',market='btc',instrument='BTCUSDT',venue='BINANCE-SPOT',currency='USDT',source_kind='public',
        source_uri='https://data.binance.vision/',source_license='遵循Binance数据条款与mempool服务条款；原始归档仅本地留存，不推定行情可自由再分发。',
        calendar_kind='venue',calendar_source='Binance UTC spot 1d calendar: every UTC date, weekends included',sessions=sessions,bars=tuple(bars),quantity_step='0.00001',limitations=limitations)
    save(PublicDataset(snapshot=snapshot,receipts=tuple(receipts),blocks=tuple(blocks),timing_assumption=TIMING,
        quality={'expected_sessions':len(sessions),'actual_bars':len(bars),'missing':0,'duplicates':0,'verified_monthly_archives':96,
                 'block_observations':len(blocks),'block_start':str(first),'start':str(START),'end':str(END),'availability':'assumed_not_vintage'}))


if __name__=='__main__':
    ROOT.mkdir(parents=True,exist_ok=True)
    ashare();btc()
