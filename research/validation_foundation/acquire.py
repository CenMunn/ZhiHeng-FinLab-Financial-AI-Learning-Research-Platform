"""D24 fixed public candidate acquisition; no training or application writes.

Run: research/.venv/Scripts/python.exe -m research.validation_foundation.acquire
All source bytes are local-only, immutable, SHA-bound cache pairs. An interrupted
pair is refused explicitly. Failures remain in acquisition.json; no replacements.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time as daytime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request

PROJECT = Path(__file__).resolve().parents[2]
DATA = PROJECT / 'research/artifacts/validation-data/v1'
LEGACY = PROJECT / 'backend/data/public-market'
START, END = date(2018, 1, 1), date(2025, 12, 31)
UTC = timezone.utc
CALENDAR_URL = 'https://raw.githubusercontent.com/gerrymanoim/exchange_calendars/4.11.2/exchange_calendars/exchange_calendar_xshg.py'
CANDIDATES = (
    ('600519', '贵州茅台', 'ashare', 'anchor'),
    ('600036', '招商银行', 'ashare', 'transfer'),
    ('600900', '长江电力', 'ashare', 'transfer'),
    ('600585', '海螺水泥', 'ashare', 'transfer'),
    ('600276', '恒瑞医药', 'ashare', 'transfer'),
    ('BTCUSDT', 'Bitcoin / USDT', 'crypto', 'anchor'),
    ('ETHUSDT', 'Ether / USDT', 'crypto', 'transfer'),
)
COMMON_WARNINGS = [
    '人工选择的当前存续候选组，存在选择与幸存偏差，不是历史全市场抽样。',
    '公开历史重建，不具备逐时PIT/原始接收时间；close_at后一分种available_at是教学假设。',
    '公开可访问不等于可自由再分发，腾讯/Yahoo/Binance及原提供者许可与服务条款适用；原始文件仅本地研究留存。',
    '2018–2025是已知历史，不是未知盲测；没有前瞻成绩或真实成交承诺。',
]


def now():
    return datetime.now(UTC).isoformat()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def normalization_sources():
    """Fingerprint the executed normalization boundary before any source reads."""
    paths = (
        'research/validation_foundation/acquire.py',
        'backend/src/platform_app/adapters/public_market.py',
        'backend/src/platform_app/contracts/public_backtests.py',
        'backend/src/platform_app/contracts/market_experiments.py',
        'backend/src/platform_app/contracts/models.py',
    )
    return {path: digest((PROJECT / path).read_bytes()) for path in paths}


def encoded(body):
    return (json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf8')


def atomic(path, raw, *, immutable=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and immutable:
        if path.read_bytes() != raw:
            raise ValueError('Immutable artifact differs: ' + str(path))
        return
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.partial', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def cache(root, name, url, *, supplied=None, provenance=None):
    """Validate both identity and contents on reuse; incomplete pairs fail closed."""
    path = root / 'raw' / name
    receipt_path = path.with_name(path.name + '.receipt.json')
    if path.exists() != receipt_path.exists():
        raise ValueError('Incomplete raw/receipt pair; preserve and inspect: ' + name)
    if path.exists():
        raw, receipt = path.read_bytes(), json.loads(receipt_path.read_bytes())
        if receipt.get('url') != url or receipt.get('sha256') != digest(raw) or receipt.get('file') != path.relative_to(root).as_posix():
            raise ValueError('Cache URL/SHA/path mismatch: ' + name)
        if supplied is not None and raw != supplied:
            raise ValueError('Copied source differs: ' + name)
        if provenance is not None and receipt.get('provenance') != provenance:
            raise ValueError('Copied provenance differs: ' + name)
        return raw, receipt
    raw = supplied
    if raw is None:
        last = None
        for attempt in range(2):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'FinancialLearningLab/0.1 (public daily educational research)'})
                with urllib.request.urlopen(request, timeout=15) as response:
                    raw = response.read(20_000_001)
                    if len(raw) > 20_000_000:
                        raise ValueError('Response exceeds 20 MB: ' + name)
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                if attempt == 0:
                    time.sleep(1)
        if raw is None:
            raise RuntimeError(f'Public acquisition failed after 2 attempts: {url}: {last}') from last
    receipt = {'file': path.relative_to(root).as_posix(), 'url': url, 'sha256': digest(raw), 'retrieved_at': now()}
    if provenance is not None:
        receipt['provenance'] = provenance
    # Two individually atomic files: an interruption between them is an explicit,
    # detectable partial failure, never an accepted or silently repaired cache.
    atomic(path, raw)
    atomic(receipt_path, encoded(receipt))
    return raw, receipt


def legacy_module():
    if str(PROJECT / 'backend/src') not in sys.path:
        sys.path.insert(0, str(PROJECT / 'backend/src'))
    from platform_app.adapters import public_market
    return public_market


def calendar(root):
    path = LEGACY / 'raw/xshg-4.11.2.py'
    old_receipt = json.loads(path.with_name(path.name + '.receipt.json').read_bytes())
    raw = path.read_bytes()
    if old_receipt['url'] != CALENDAR_URL or old_receipt['sha256'] != digest(raw):
        raise ValueError('Legacy fixed XSHG calendar URL/SHA mismatch')
    raw, receipt = cache(root, 'xshg-4.11.2.py', CALENDAR_URL, supplied=raw, provenance={'legacy_receipt': old_receipt})
    sessions = legacy_module().parse_xshg_calendar(raw.decode('utf8'), START, END)
    if not sessions:
        raise ValueError('Empty calendar')
    return [str(day) for day in sessions], receipt


def anchor(root, candidate):
    symbol, name, market, role = candidate
    dataset_id = 'ashare-600519-2018-2025' if symbol == '600519' else 'btc-btcusdt-2018-2025'
    old = legacy_module().load_dataset(LEGACY, dataset_id, verify_raw=True)
    path = LEGACY / (dataset_id + '.json')
    raw = path.read_bytes()
    # Copy the original envelope including all nested receipts, preserving its
    # canonical dataset SHA as well as the SHA of the exact source file bytes.
    _, receipt = cache(root, 'legacy-' + dataset_id + '.json', 'legacy-public-market:' + dataset_id,
                       supplied=raw, provenance={'source_file_sha256': digest(raw),
                       'source_dataset_sha256': json.loads(raw)['sha256'],
                       'legacy_receipts': [item.model_dump(mode='json') for item in old.receipts]})
    snapshot = old.snapshot.model_dump(mode='json')
    return {'symbol': symbol, 'name': name, 'market': market, 'role': role,
            'bars': snapshot['bars'], 'expected_sessions': snapshot['sessions'],
            'dividends': [item.model_dump(mode='json') for item in old.dividends],
            'splits': [], 'receipts': [receipt],
            'warnings': COMMON_WARNINGS + list(old.snapshot.limitations) + [old.timing_assumption,
                '锚点由旧load_dataset校验原快照及其全部原始来源；本切片只复制规范源快照，原来源收据嵌套保留。']}


def parse_tencent(raw, symbol):
    body = json.loads(raw, parse_float=Decimal)
    if body.get('code') != 0:
        raise ValueError('Tencent response code not zero')
    # Require the exact unadjusted day field and requested identity.
    rows = body['data']['sh' + symbol]['day']
    if not rows:
        raise ValueError('Empty Tencent raw day response')
    bars = []
    for row in rows:
        day = date.fromisoformat(row[0])
        close = datetime.combine(day, daytime(7), UTC)
        bars.append({'session': str(day), 'open': str(row[1]), 'close': str(row[2]),
                     'high': str(row[3]), 'low': str(row[4]),
                     'volume': str(Decimal(str(row[5])) * 100),
                     'close_at': close.isoformat(), 'available_at': (close + timedelta(minutes=1)).isoformat()})
    return bars


def parse_events(raw, symbol):
    chart = json.loads(raw, parse_float=Decimal)['chart']
    if chart.get('error') or len(chart.get('result') or []) != 1:
        raise ValueError('Yahoo has no unique chart result')
    result = chart['result'][0]
    meta = result['meta']
    if meta.get('symbol') != symbol + '.SS' or meta.get('currency') != 'CNY' or meta.get('exchangeTimezoneName') != 'Asia/Shanghai':
        raise ValueError('Yahoo event identity/currency/timezone mismatch')
    dividends, splits = [], []
    for event in result.get('events', {}).get('dividends', {}).values():
        day = datetime.fromtimestamp(int(event['date']), UTC).astimezone(timezone(timedelta(hours=8))).date()
        dividends.append({'session': str(day), 'amount': str(event['amount'])})
    for event in result.get('events', {}).get('splits', {}).values():
        day = datetime.fromtimestamp(int(event['date']), UTC).astimezone(timezone(timedelta(hours=8))).date()
        denominator = Decimal(str(event['denominator']))
        if denominator <= 0:
            raise ValueError('Invalid Yahoo split denominator')
        splits.append({'session': str(day), 'ratio': str(Decimal(str(event['numerator'])) / denominator)})
    return sorted(dividends, key=lambda item: item['session']), sorted(splits, key=lambda item: item['session'])


def ashare(root, candidate, sessions, calendar_receipt):
    symbol, name, market, role = candidate
    receipts, bars = [calendar_receipt], []
    for year in range(2018, 2026):
        url = f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh{symbol},day,{year}-01-01,{year}-12-31,640,'
        raw, receipt = cache(root, f'tencent-{symbol}-{year}-raw.json', url)
        rows = parse_tencent(raw, symbol)
        if any(not row['session'].startswith(str(year)) for row in rows):
            raise ValueError('Tencent response contains a different year')
        bars.extend(rows)
        receipts.append(receipt)
    first = int(datetime.combine(START, daytime(), UTC).timestamp())
    last = int(datetime.combine(END + timedelta(days=1), daytime(), UTC).timestamp())
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.SS?period1={first}&period2={last}&interval=1d&events=div%2Csplits'
    raw, receipt = cache(root, f'yahoo-{symbol}-2018-2025-events.json', url)
    dividends, splits = parse_events(raw, symbol)
    receipts.append(receipt)
    return {'symbol': symbol, 'name': name, 'market': market, 'role': role, 'bars': bars,
            'expected_sessions': sessions, 'dividends': dividends, 'splits': splits, 'receipts': receipts,
            'warnings': COMMON_WARNINGS + [
                'Tencent day原价OHLC；成交量手乘100为近似股数，仅作非零检查。Yahoo仅提供分红/拆股事件，无法证明完整。',
                'Yahoo事件缺少当时公告/到达与实际支付时间；不能填作已知PIT事件或假定税后分红。',
                'XSHG固定exchange_calendars 4.11.2社区日历，不是交易所直接发布的官方完整逐时档案。',
                '缺交易日/停牌不前填；拆股事件保留，交由资格模块拒绝未支持的调整。']}


def crypto_month(root, year, month):
    name = f'ETHUSDT-1d-{year}-{month:02d}.zip'
    url = 'https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1d/' + name
    raw, receipt = cache(root, name, url)
    checksum, checksum_receipt = cache(root, name + '.CHECKSUM', url + '.CHECKSUM')
    parts = checksum.decode('ascii').split()
    if len(parts) != 2 or not re.fullmatch('[0-9a-f]{64}', parts[0]) or parts[1].lstrip('*') != name or digest(raw) != parts[0]:
        raise ValueError('Binance publisher checksum/name mismatch: ' + name)
    receipt = {**receipt, 'publisher_checksum': parts[0]}
    bars = [item.model_dump(mode='json') for item in legacy_module().parse_binance_zip(raw)]
    if not bars or any(not row['session'].startswith(f'{year}-{month:02d}-') for row in bars):
        raise ValueError('Binance archive empty or wrong month: ' + name)
    return bars, [receipt, checksum_receipt]


def ether(root, candidate):
    bars, receipts, errors = [], [], []
    # At most four network workers; no simultaneous outer asset pool remains.
    def job(pair):
        try:
            return crypto_month(root, *pair), None
        except Exception as exc:
            return None, f'{pair[0]}-{pair[1]:02d}: {type(exc).__name__}: {exc}'
    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, (result, error) in enumerate(pool.map(job, [(y, m) for y in range(2018, 2026) for m in range(1, 13)]), 1):
            if error:
                errors.append(error)
            else:
                rows, items = result
                bars.extend(rows)
                receipts.extend(items)
            if index % 12 == 0:
                print(f'ETH months processed {index}/96; failures {len(errors)}', flush=True)
    if errors:
        raise ValueError('ETH monthly archive failures (all fixed months attempted): ' + ' | '.join(errors))
    symbol, name, market, role = candidate
    return {'symbol': symbol, 'name': name, 'market': market, 'role': role, 'bars': bars,
            'expected_sessions': [str(START + timedelta(days=i)) for i in range((END - START).days + 1)],
            'dividends': [], 'splits': [], 'receipts': receipts,
            'warnings': COMMON_WARNINGS + [
                'Binance ETHUSDT现货/USDT计价，每日UTC日线；不含融资、资金费率、链上费用或交易所外市场。',
                '96个月档与发布者CHECKSUM逐一核验；沿用已审计解析器兼容2025起微秒、此前毫秒时间单位。',
                'crypto分红/拆股不适用；未声称完整链上协议/分叉事件记录。']}


def acquire_all(root=DATA):
    # This records the NEW verified normalization/replay identity. It does not
    # attribute earlier downloads (whose original times stay in receipts) to
    # this code version.
    sources = normalization_sources()
    replay_started_at = now()
    root.mkdir(parents=True, exist_ok=True)
    entries = {}
    def run(candidate, callback):
        symbol = candidate[0]
        try:
            dataset = callback()
            if not dataset['bars'] or not dataset['expected_sessions']:
                raise ValueError('Missing/empty bars or calendar')
            target = root / 'datasets' / (symbol + '.json')
            raw = encoded(dataset)
            atomic(target, raw)
            entry = {'symbol': symbol, 'status': 'acquired', 'dataset_file': target.relative_to(root).as_posix(), 'dataset_sha256': digest(raw)}
        except Exception as exc:
            entry = {'symbol': symbol, 'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        return entry
    for candidate in (CANDIDATES[0], CANDIDATES[5]):
        entries[candidate[0]] = run(candidate, lambda c=candidate: anchor(root, c))
    try:
        sessions, calendar_receipt = calendar(root)
        calendar_error = None
    except Exception as exc:
        calendar_error = exc
    def stock(candidate):
        if calendar_error:
            def fail():
                raise ValueError('Missing verified calendar: ' + str(calendar_error))
            return run(candidate, fail)
        return run(candidate, lambda: ashare(root, candidate, sessions, calendar_receipt))
    with ThreadPoolExecutor(max_workers=4) as pool:
        for entry in pool.map(stock, CANDIDATES[1:5]):
            entries[entry['symbol']] = entry
    entries['ETHUSDT'] = run(CANDIDATES[6], lambda: ether(root, CANDIDATES[6]))
    if sources != normalization_sources():
        raise ValueError('Normalization source code changed during acquisition; no new manifest published')
    source_times = []
    for receipt_path in sorted((root / 'raw').glob('*.receipt.json')):
        receipt = json.loads(receipt_path.read_bytes())
        copied = bool(receipt.get('provenance'))
        item = {key: receipt[key] for key in ('file', 'url', 'sha256', 'retrieved_at')}
        item['time_kind'] = 'local_verified_copy_at' if copied else 'original_network_retrieved_at'
        originals = receipt.get('provenance', {}).get('legacy_receipts')
        if originals:
            item['original_download_receipts'] = originals
        legacy_calendar = receipt.get('provenance', {}).get('legacy_receipt')
        if legacy_calendar:
            item['original_download_receipts'] = [legacy_calendar]
        source_times.append(item)
    manifest = {'schema': 'validation-acquisition-v1', 'created_at': replay_started_at, 'start': str(START), 'end': str(END),
                'assets': [entries[c[0]] for c in CANDIDATES], 'limitations': COMMON_WARNINGS,
                'normalization_sources': sources,
                'normalization_identity_kind': 'verified_raw_normalization_replay',
                'cached_replay_allowed': True,
                'provenance_note': 'Source hashes bind this verified normalization/replay; original receipt download times predate it where shown and are not attributed retroactively to this code version.',
                'raw_source_times': source_times,
                'network_policy': {'max_workers': 4, 'timeout_seconds': 15, 'attempts': 2, 'max_response_bytes': 20_000_000}}
    previous = root / 'acquisition.json'
    if previous.exists():
        old = json.loads(previous.read_bytes())
        if {k: v for k, v in old.items() if k != 'created_at'} == {k: v for k, v in manifest.items() if k != 'created_at'}:
            return old
        # Preserve the exact prior manifest, including pre-provenance versions.
        atomic(root / 'attempts' / ('prior-' + digest(previous.read_bytes()) + '.json'), previous.read_bytes())
    # Only changed outcomes create a new journal; cache-only reruns preserve the
    # exact manifest identity and original timestamp.
    journal = root / 'attempts' / (datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    atomic(journal, encoded(manifest))
    atomic(root / 'acquisition.json', encoded(manifest), immutable=False)
    return manifest


if __name__ == '__main__':
    acquire_all()
