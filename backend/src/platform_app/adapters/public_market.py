"""Pure parsers and hash-checked offline catalogue. No network on HTTP requests."""
import ast
import csv
import hashlib
import io
import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import zipfile
from platform_app.contracts.market_experiments import MarketBar
from platform_app.contracts.public_backtests import Dividend, PublicDataset
from platform_app.contracts.models import stable_hash

UTC=timezone.utc
IDS=('ashare-600519-2018-2025','btc-btcusdt-2018-2025')


def number(value):
    if value is None or isinstance(value,bool):raise ValueError('公开行情存在空值/布尔数值')
    return format(Decimal(str(value)).quantize(Decimal('.00000001'),rounding=ROUND_HALF_UP),'f').rstrip('0').rstrip('.') if Decimal(str(value)) else '0'


def parse_xshg_calendar(source:str,start:date,end:date)->tuple[date,...]:
    if not date(1991,1,1)<=start<=end<=date(2025,12,31):raise ValueError('固定日历版本只登记1991–2025')
    holidays=None
    for node in ast.parse(source).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='precomputed_shanghai_holidays' for t in node.targets):
            if isinstance(node.value,ast.Call) and node.value.args:
                holidays={date.fromisoformat(day) for day in ast.literal_eval(node.value.args[0])}
    if not holidays:raise ValueError('未找到固定版本的XSHG休市表')
    return tuple(start+timedelta(days=i) for i in range((end-start).days+1)
                 if (start+timedelta(days=i)).weekday()<5 and start+timedelta(days=i) not in holidays)


def yahoo_body(raw:bytes):
    body=json.loads(raw,parse_float=Decimal)['chart']
    if body.get('error') or len(body.get('result') or [])!=1:raise ValueError('行情响应没有唯一结果')
    data=body['result'][0];meta=data['meta']
    if meta.get('symbol')!='600519.SS' or meta.get('currency')!='CNY' or meta.get('exchangeTimezoneName')!='Asia/Shanghai':raise ValueError('股票身份/币种/时区不一致')
    events=data.get('events',{})
    if events.get('splits'):raise ValueError('首版未实现拆股账户处理，禁止继续')
    return data


def parse_yahoo_dividends(raw:bytes,sessions:tuple[date,...]):
    data=yahoo_body(raw)
    dividends=tuple(sorted((Dividend(session=datetime.fromtimestamp(event['date'],UTC).astimezone(timezone(timedelta(hours=8))).date(),amount=number(event['amount'])) for event in data.get('events',{}).get('dividends',{}).values()),key=lambda x:x.session))
    if len({d.session for d in dividends})!=len(dividends) or not {d.session for d in dividends}<=set(sessions):raise ValueError('分红事件不属于日历或重复')
    return dividends


def parse_yahoo_chart(raw:bytes,sessions:tuple[date,...]):
    data=yahoo_body(raw)
    quote=data['indicators']['quote'][0];stamps=data['timestamp']
    if any(len(quote.get(k,[]))!=len(stamps) for k in ('open','high','low','close','volume')):raise ValueError('行情列长度不一致')
    bars=[]
    for i,stamp in enumerate(stamps):
        day=datetime.fromtimestamp(stamp,UTC).astimezone(timezone(timedelta(hours=8))).date()
        close=datetime.combine(day,time(7),UTC)
        bars.append(MarketBar(session=day,close_at=close,available_at=close+timedelta(minutes=1),
                              **{k:number(quote[k][i]) for k in ('open','high','low','close','volume')}))
    if tuple(b.session for b in bars)!=sessions:raise ValueError('行情与独立交易日历不一致：缺失/多余/重复/乱序，停止回测')
    return tuple(bars),parse_yahoo_dividends(raw,sessions)


def parse_tencent_chart(raw:bytes,sessions:tuple[date,...]):
    data=json.loads(raw,parse_float=Decimal)
    if data.get('code')!=0:raise ValueError('腾讯行情查询失败')
    rows=data['data']['sh600519']['day'];bars=[]
    for row in rows:
        day=date.fromisoformat(row[0]);close=datetime.combine(day,time(7),UTC)
        bars.append(MarketBar(session=day,close_at=close,available_at=close+timedelta(minutes=1),
            open=number(row[1]),close=number(row[2]),high=number(row[3]),low=number(row[4]),volume=number(Decimal(str(row[5]))*100)))
    if tuple(b.session for b in bars)!=sessions:raise ValueError('腾讯原始行情与独立XSHG日历不一致')
    return tuple(bars)


def parse_binance_zip(raw:bytes)->tuple[MarketBar,...]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files=archive.infolist()
        if len(files)!=1 or files[0].file_size>1000000:raise ValueError('日线归档格式/大小异常')
        rows=list(csv.reader(io.StringIO(archive.read(files[0]).decode('utf8'))))
    bars=[]
    for row in rows:
        if len(row)!=12:raise ValueError('Binance日线必须有12列')
        stamp=int(row[0]);unit=1000000 if stamp>=10**14 else 1000
        opened=datetime.fromtimestamp(stamp/unit,UTC)
        if opened.time()!=time():raise ValueError('Binance日线不是UTC零点开始')
        close=opened+timedelta(days=1)
        if int(row[6])!=int(close.timestamp())*unit-1:raise ValueError('Binance收盘时间/单位异常')
        bars.append(MarketBar(session=opened.date(),close_at=close,available_at=close+timedelta(minutes=1),
                              open=row[1],high=row[2],low=row[3],close=row[4],volume=row[5]))
    if tuple(sorted(set(b.session for b in bars)))!=tuple(b.session for b in bars):raise ValueError('Binance重复或乱序行情')
    return tuple(bars)


def load_dataset(root:Path,dataset_id:str,*,verify_raw=True)->PublicDataset:
    if dataset_id not in IDS:raise KeyError(dataset_id)
    body=json.loads((root/(dataset_id+'.json')).read_text(encoding='utf8'))
    dataset=PublicDataset.model_validate(body['dataset'])
    if body['sha256']!=stable_hash(dataset.model_dump(mode='json')) or dataset.snapshot.snapshot_id!=dataset_id:raise ValueError('数据快照校验失败')
    if verify_raw:
        for receipt in dataset.receipts:
            target=(root/receipt.file).resolve()
            if not target.is_relative_to(root.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest()!=receipt.sha256:raise ValueError('原始来源文件校验失败')
            if receipt.publisher_checksum and receipt.publisher_checksum!=receipt.sha256:raise ValueError('发布者校验不一致')
    return dataset
