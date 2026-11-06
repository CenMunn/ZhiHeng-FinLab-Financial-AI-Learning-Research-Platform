"""D27 bounded public arrivals; append-only raw evidence, no historical backdating.

The now argument is a deterministic test seam, never a fabricated receipt clock.
Real downloads timestamp completion from the actual UTC clock. No model fitting.
"""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from uuid import uuid4

UTC=timezone.utc
START=date(2025,12,15)
END=date(2026,12,31)
SYMBOLS=('600519','600036','600585','BTCUSDT','ETHUSDT')
CALENDAR_URLS={2025:'https://www.sse.com.cn/disclosure/announcement/general/c/c_20241223_10767108.shtml',
               2026:'https://www.sse.com.cn/disclosure/announcement/general/c/c_20251222_10802507.shtml'}
CALENDAR_RANGES={
    2025:[((1,1),(1,1)),((1,28),(2,4)),((4,4),(4,6)),((5,1),(5,5)),((5,31),(6,2)),((10,1),(10,8))],
    2026:[((1,1),(1,3)),((2,15),(2,23)),((4,4),(4,6)),((5,1),(5,5)),((6,19),(6,21)),((9,25),(9,27)),((10,1),(10,7))],
}

def encoded(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf8')

def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def aware(value):
    if not isinstance(value,datetime) or value.tzinfo is None:raise ValueError('UTC-aware timestamp required')
    return value.astimezone(UTC)

def numeric(value,*,positive=False):
    if value is None or isinstance(value,bool):raise ValueError('Missing/boolean market value')
    try:number=Decimal(str(value))
    except InvalidOperation as exc:raise ValueError('Invalid market number') from exc
    if not number.is_finite() or (number<=0 if positive else number<0):raise ValueError('Invalid market number')
    return format(number,'f')

def parse_calendar(raw,year):
    if year not in CALENDAR_RANGES:raise ValueError('Official calendar year not implemented')
    text=re.sub(r'\s+','',html.unescape(re.sub('<[^>]*>','',raw.decode('utf8'))))
    if f'上海证券交易所{year}年部分节假日休市安排' not in text:raise ValueError('Official calendar year/title mismatch')
    found=re.findall(r'（[一二三四五六七]）[^：]*：(\d+)月(\d+)日（星期.）(?:至(\d+)月(\d+)日（星期.）)?休市',text)
    ranges=[((int(m),int(d)),(int(n or m),int(e or d))) for m,d,n,e in found]
    if ranges!=CALENDAR_RANGES[year]:raise ValueError('Official calendar content changed or incomplete')
    holidays=set()
    for first,last in ranges:
        start,end=date(year,*first),date(year,*last)
        holidays.update(start+timedelta(days=i) for i in range((end-start).days+1))
    start,end=date(year,1,1),date(year,12,31)
    return [str(day) for i in range((end-start).days+1)
            if (day:=start+timedelta(days=i)).weekday()<5 and day not in holidays]

def _bars_valid(bars):
    dates=[b['session'] for b in bars]
    if dates!=sorted(set(dates)):raise ValueError('Duplicate/unsorted sessions')
    for bar in bars:
        values={k:Decimal(numeric(bar[k],positive=k!='volume')) for k in ('open','high','low','close','volume')}
        if values['volume']<=0 or not values['low']<=min(values['open'],values['close'])<=max(values['open'],values['close'])<=values['high']:
            raise ValueError('Invalid OHLC/zero-volume bar')

def parse_tencent(raw,symbol,received):
    received=aware(received);body=json.loads(raw,parse_float=Decimal)
    if body.get('code')!=0:raise ValueError('Tencent response failure')
    try:rows=body['data']['sh'+symbol]['day']
    except (KeyError,TypeError) as exc:raise ValueError('Tencent identity/raw-day mismatch') from exc
    bars=[];all_days=[]
    for row in rows:
        if len(row)<6:raise ValueError('Incomplete Tencent row')
        day=date.fromisoformat(row[0]);all_days.append(str(day))
        opened=datetime.combine(day,time(1,30),UTC);closed=datetime.combine(day,time(7),UTC)
        if opened>received:raise ValueError('Tencent future bar')
        if closed+timedelta(minutes=1)>received:continue
        bars.append(dict(session=str(day),open=numeric(row[1],positive=True),close=numeric(row[2],positive=True),
                         high=numeric(row[3],positive=True),low=numeric(row[4],positive=True),volume=numeric(Decimal(numeric(row[5]))*100),
                         open_at=opened.isoformat(),close_at=closed.isoformat(),available_at=received.isoformat()))
    if all_days!=sorted(set(all_days)):raise ValueError('Duplicate/unsorted source rows')
    _bars_valid(bars);return bars

def parse_binance(raw,received):
    received=aware(received);rows=json.loads(raw);bars=[];all_days=[]
    if not isinstance(rows,list):raise ValueError('Binance endpoint failure')
    for row in rows:
        if not isinstance(row,list) or len(row)!=12:raise ValueError('Binance daily row shape')
        stamp=int(row[0]);opened=datetime.fromtimestamp(stamp/1000,UTC);closed=opened+timedelta(days=1)
        if opened.time()!=time() or int(row[6])!=int(closed.timestamp()*1000)-1:raise ValueError('Binance UTC daily timestamp mismatch')
        if opened>received:raise ValueError('Binance future bar')
        all_days.append(str(opened.date()))
        if closed+timedelta(minutes=1)>received:continue
        bars.append(dict(session=str(opened.date()),open=numeric(row[1],positive=True),high=numeric(row[2],positive=True),
                         low=numeric(row[3],positive=True),close=numeric(row[4],positive=True),volume=numeric(row[5]),
                         open_at=opened.isoformat(),close_at=closed.isoformat(),available_at=received.isoformat()))
    if all_days!=sorted(set(all_days)):raise ValueError('Duplicate/unsorted source rows')
    _bars_valid(bars);return bars

def parse_events(raw,symbol):
    chart=json.loads(raw,parse_float=Decimal)['chart']
    if chart.get('error') or len(chart.get('result') or [])!=1:raise ValueError('Yahoo event result unavailable')
    result=chart['result'][0];meta=result['meta']
    if meta.get('symbol')!=symbol+'.SS' or meta.get('currency')!='CNY' or meta.get('exchangeTimezoneName')!='Asia/Shanghai':raise ValueError('Yahoo identity/currency/timezone mismatch')
    dividends=[];splits=[]
    for event in result.get('events',{}).get('dividends',{}).values():
        day=datetime.fromtimestamp(int(event['date']),UTC).astimezone(timezone(timedelta(hours=8))).date()
        dividends.append({'session':str(day),'amount':numeric(event['amount'],positive=True)})
    for event in result.get('events',{}).get('splits',{}).values():
        day=datetime.fromtimestamp(int(event['date']),UTC).astimezone(timezone(timedelta(hours=8))).date()
        ratio=Decimal(numeric(event['numerator'],positive=True))/Decimal(numeric(event['denominator'],positive=True))
        splits.append({'session':str(day),'ratio':str(ratio)})
    if len({e['session'] for e in dividends})!=len(dividends):raise ValueError('Duplicate corporate events')
    return sorted(dividends,key=lambda e:e['session']),sorted(splits,key=lambda e:e['session'])

def validate_snapshot(snapshot,at):
    at=aware(at);market=snapshot['market'];bars=snapshot['bars'];calendar=snapshot['calendar']
    if market not in ('ashare','crypto'):raise ValueError('Unknown market')
    if snapshot.get('splits'):raise ValueError('Unsupported split/bonus event')
    if len(bars)<61:raise ValueError('Insufficient closed bars')
    _bars_valid(bars)
    if calendar!=sorted(set(calendar)):raise ValueError('Invalid calendar ordering')
    expected=[]
    for session in calendar:
        day=date.fromisoformat(session)
        close=datetime.combine(day,time(7),UTC) if market=='ashare' else datetime.combine(day+timedelta(days=1),time(),UTC)
        if START<=day and close+timedelta(minutes=1)<=at:expected.append(session)
    actual=[b['session'] for b in bars]
    if actual!=expected:
        missing=sorted(set(expected)-set(actual));extra=sorted(set(actual)-set(expected))
        raise ValueError(f'Calendar coverage mismatch: missing={missing[:8]}, extra={extra[:8]}')
    for bar in bars:
        if datetime.fromisoformat(bar['available_at'])>at or datetime.fromisoformat(bar['close_at'])>=at:raise ValueError('Future/unavailable bar')
    if any(e['session'] not in actual for e in snapshot.get('dividends',[])):raise ValueError('Dividend event outside closed session coverage')

def _download(url):
    request=Request(url,headers={'User-Agent':'FinancialLearningLab/0.1 (public daily research)'})
    with urlopen(request,timeout=20) as response:
        if urlparse(response.url).scheme!='https' or urlparse(response.url).netloc!=urlparse(url).netloc:raise ValueError('Unexpected source redirect')
        raw=response.read(8_000_001)
        if len(raw)>8_000_000:raise ValueError('Public response exceeds 8MB')
    return raw,datetime.now(UTC)

def _write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(value)

def acquire(symbol,output_root,*,now=None):
    if symbol not in SYMBOLS:raise ValueError('Unknown/unsafe symbol')
    started=aware(now or datetime.now(UTC));market='crypto' if symbol.endswith('USDT') else 'ashare'
    if not date(2026,1,1)<=started.date()<=END:raise ValueError('D27 source/calendar window supports 2026 only')
    root=Path(output_root).resolve()/symbol/(started.strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid4().hex[:8])
    root.mkdir(parents=True,exist_ok=False)
    body=dict(schema='forward-market-snapshot-v1',symbol=symbol,market=market,status='blocked',reasons=[],
              requested_at=started.isoformat(),retrieved_at=started.isoformat(),bars=[],dividends=[],splits=[],calendar=[],
              source_evidence=[],normalizer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              limitations=['新采集的历史上下文只代表本次收到的数据版本；不能倒填历史可用时间。',
                           '公开可访问不等于自由再分发；原始响应仅本地研究留存。'])
    evidence=body['source_evidence']
    def fetch(name,url):
        try:
            raw,received=_download(url);received=aware(received)
            if received<started:raise ValueError('Acquisition clock moved backwards')
            path=root/'raw'/name
            receipt=dict(url=url,file=str(path),sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),retrieved_at=received.isoformat())
            _write(path,raw);_write(path.with_name(path.name+'.receipt.json'),encoded(receipt));evidence.append(receipt)
            body['retrieved_at']=max(body['retrieved_at'],received.isoformat());return raw,received
        except Exception as exc:
            failure=dict(url=url,status='failed',attempted_at=datetime.now(UTC).isoformat(),error=f'{type(exc).__name__}: {exc}')
            _write(root/'raw'/(name+'.failure.json'),encoded(failure));evidence.append(failure);raise
    try:
        if market=='ashare':
            for year in (2025,2026):
                raw,_=fetch(f'sse-calendar-{year}.html',CALENDAR_URLS[year]);body['calendar']+=parse_calendar(raw,year)
            body['calendar']=[s for s in body['calendar'] if s>=str(START)]
            end=(started.astimezone(timezone(timedelta(hours=8))).date())
            url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh{symbol},day,{START},{end},640,'
            raw,received=fetch('tencent-raw-day.json',url);body['bars']=parse_tencent(raw,symbol,received)
            p1=int(datetime.combine(START,time(),UTC).timestamp());p2=int(started.timestamp())
            url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.SS?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits'
            raw,_=fetch('yahoo-events.json',url);body['dividends'],body['splits']=parse_events(raw,symbol)
            body['limitations']+=['Tencent原价日线与Yahoo公司事件；事件完整性无法由单一供应商证明。',
                '官方年度休市表决定日历；临时停市/个股停牌以缺失检查阻止预测，日历有效期止于2026-12-31。']
        else:
            p1=int(datetime.combine(START,time(),UTC).timestamp()*1000);p2=int(started.timestamp()*1000)
            url=f'https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval=1d&startTime={p1}&endTime={p2}&limit=1000'
            raw,received=fetch('binance-spot-1d.json',url);body['bars']=parse_binance(raw,received)
            body['calendar']=[str(START+timedelta(days=i)) for i in range((END-START).days+1)]
            body['limitations']+=['Binance现货USDT日线，每UTC日一个交易区间；不代表其他交易场所或永续合约。']
        received=datetime.fromisoformat(body['retrieved_at'])
        validate_snapshot(body,received);body['status']='ready'
    except Exception as exc:body['reasons'].append(f'{type(exc).__name__}: {exc}')
    body['snapshot_sha256']=canonical_sha(body);body['snapshot_path']=str(root/'snapshot.json')
    _write(root/'snapshot.json',encoded(body));return body
