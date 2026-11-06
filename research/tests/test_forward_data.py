import copy
import hashlib
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from research.forward_market.data import (acquire, parse_calendar, parse_binance,
    parse_tencent, parse_events, validate_snapshot, canonical_sha, CALENDAR_RANGES)

UTC=timezone.utc

def calendar_html(year):
    parts=[f'上海证券交易所{year}年部分节假日休市安排']
    for i,((m,d),(n,e)) in enumerate(CALENDAR_RANGES[year]):
        end='' if (m,d)==(n,e) else f'至{n}月{e}日（星期一）'
        parts.append(f'（{"一二三四五六七"[i]}）节日：{m}月{d}日（星期一）{end}休市')
    return ''.join(parts).encode()

def crypto_rows(start=date(2025,12,15),count=326):
    return [[int(datetime.combine(start+timedelta(days=i),datetime.min.time(),UTC).timestamp()*1000),
             '100','102','98','101','12',int(datetime.combine(start+timedelta(days=i+1),datetime.min.time(),UTC).timestamp()*1000)-1,'0',0,'0','0','0'] for i in range(count)]

class ForwardDataTests(unittest.TestCase):
    def test_official_calendar_holidays_weekends_and_future_year_guard(self):
        days=parse_calendar(calendar_html(2026),2026)
        self.assertNotIn('2026-02-23',days)
        self.assertIn('2026-02-24',days)
        self.assertNotIn('2026-09-25',days)
        self.assertIn('2026-11-06',days)
        with self.assertRaises(ValueError):parse_calendar(calendar_html(2026).replace(b'2026',b'2027'),2026)
        with self.assertRaises(ValueError):parse_calendar(calendar_html(2026).replace('2月23日'.encode(),'2月22日'.encode()),2026)

    def test_binance_closed_bars_arrival_time_and_ongoing_candle(self):
        at=datetime(2026,11,5,18,tzinfo=UTC)
        rows=crypto_rows(count=326)
        bars=parse_binance(json.dumps(rows).encode(),at)
        self.assertEqual(bars[-1]['session'],'2026-11-04')
        self.assertTrue(all(b['available_at']==at.isoformat() for b in bars))
        self.assertTrue(all(datetime.fromisoformat(b['close_at'])<at for b in bars))
        rows[0][6]+=1
        with self.assertRaises(ValueError):parse_binance(json.dumps(rows).encode(),at)

    def test_tencent_identity_raw_prices_duplicates_and_future(self):
        at=datetime(2026,11,5,18,tzinfo=UTC)
        raw={'code':0,'data':{'sh600519':{'day':[['2026-11-05','100','101','102','98','12']]}}}
        bars=parse_tencent(json.dumps(raw).encode(),'600519',at)
        self.assertEqual(bars[0]['volume'],'1200')
        self.assertEqual(bars[0]['available_at'],at.isoformat())
        with self.assertRaises(ValueError):parse_tencent(json.dumps(raw).encode(),'600036',at)
        raw['data']['sh600519']['day']*=2
        with self.assertRaises(ValueError):parse_tencent(json.dumps(raw).encode(),'600519',at)

    def test_events_identity_splits_and_invalid_values(self):
        stamp=int(datetime(2026,6,1,1,30,tzinfo=UTC).timestamp())
        raw={'chart':{'error':None,'result':[{'meta':{'symbol':'600519.SS','currency':'CNY','exchangeTimezoneName':'Asia/Shanghai'},'events':{'dividends':{'a':{'date':stamp,'amount':10}}}}]}}
        div,splits=parse_events(json.dumps(raw).encode(),'600519')
        self.assertEqual(div,[{'session':'2026-06-01','amount':'10'}]);self.assertEqual(splits,[])
        raw['chart']['result'][0]['events']['dividends']['a']['amount']=-1
        with self.assertRaises(ValueError):parse_events(json.dumps(raw).encode(),'600519')

    def test_calendar_missing_session_and_stale_tail_fail_closed(self):
        at=datetime(2026,11,5,18,tzinfo=UTC)
        bars=parse_binance(json.dumps(crypto_rows()).encode(),at)
        days=[str(date(2025,12,15)+timedelta(days=i)) for i in range(382)]
        body={'market':'crypto','bars':bars,'calendar':days,'dividends':[],'splits':[],'retrieved_at':at.isoformat()}
        validate_snapshot(body,at)
        for index in (100,-1):
            broken=copy.deepcopy(body);broken['bars'].pop(index)
            with self.assertRaises(ValueError):validate_snapshot(broken,at)
        broken=copy.deepcopy(body);broken['splits']=[{'session':'2026-06-01','ratio':'2'}]
        with self.assertRaises(ValueError):validate_snapshot(broken,at)

    def test_acquire_archives_raw_receipts_ready_and_failure_snapshot(self):
        at=datetime(2026,11,5,18,tzinfo=UTC)
        raw=json.dumps(crypto_rows()).encode()
        with tempfile.TemporaryDirectory() as temp,patch('research.forward_market.data._download',return_value=(raw,at)):
            snapshot=acquire('BTCUSDT',Path(temp),now=at)
            self.assertEqual(snapshot['status'],'ready')
            evidence=snapshot['source_evidence'][0]
            self.assertEqual(hashlib.sha256(Path(evidence['file']).read_bytes()).hexdigest(),evidence['sha256'])
            self.assertEqual(snapshot['snapshot_sha256'],canonical_sha({k:v for k,v in snapshot.items() if k not in ('snapshot_sha256','snapshot_path')}))
            second=acquire('BTCUSDT',Path(temp),now=at)
            self.assertNotEqual(snapshot['snapshot_path'],second['snapshot_path'])
        with tempfile.TemporaryDirectory() as temp,patch('research.forward_market.data._download',side_effect=TimeoutError('fixture timeout')):
            failed=acquire('BTCUSDT',Path(temp),now=at)
            self.assertEqual(failed['status'],'blocked');self.assertTrue(failed['reasons'])
            self.assertTrue(Path(failed['snapshot_path']).exists())

    def test_invalid_symbol_before_writing_or_network(self):
        with tempfile.TemporaryDirectory() as temp,patch('research.forward_market.data._download') as download:
            with self.assertRaises(ValueError):acquire('../bad',Path(temp))
            download.assert_not_called();self.assertEqual(list(Path(temp).iterdir()),[])

if __name__=='__main__':unittest.main()
