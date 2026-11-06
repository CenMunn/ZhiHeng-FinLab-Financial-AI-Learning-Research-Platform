import copy, tempfile, unittest
from datetime import datetime, timezone
from pathlib import Path
from research.forward_market.journal import register, record_prediction, settle, read_verified, digest

def stamp(s): return datetime.fromisoformat(s)

def fixture():
    snapshot={'symbol':'BTCUSDT','market':'crypto','retrieved_at':'2026-11-07T00:02:00+00:00','status':'ready','calendar':['2026-11-06','2026-11-07','2026-11-08','2026-11-09'], 'dividends':[], 'source_evidence':[],
      'bars':[{'session':'2026-11-06','open':'100','close':'101','open_at':'2026-11-06T00:00:00+00:00','close_at':'2026-11-07T00:00:00+00:00','available_at':'2026-11-07T00:02:00+00:00'}]}
    predictions={k:{'raw':.001,'calibrated':.002} for k in ('train_mean','ewma','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear')}
    return snapshot,predictions

class JournalTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    self.protocol=register(self.root,{'symbol':'BTCUSDT','market':'crypto','model_identity':'frozen','calibration':{k:2. for k in fixture()[1]}},_now=stamp('2026-11-06T01:00:00+00:00'))
 def record(self,snapshot=None,now='2026-11-07T00:03:00+00:00'):
    s,p=fixture();return record_prediction(self.root,self.protocol,snapshot or s,p,_now=stamp(now))
 def test_future_interval_and_immutable_duplicate(self):
    record=self.record();self.assertEqual(record['entry_at'],'2026-11-08T00:00:00+00:00')
    self.assertEqual(self.record(now='2026-11-07T01:00:00+00:00')['forecast_id'],record['forecast_id'])
    self.assertEqual(len(list(self.root.rglob('prediction-*.json'))),1)
 def test_pre_start_late_future_reception_and_stale_rejected(self):
    s,_=fixture();s['bars'][0]['session']='2026-11-05'
    with self.assertRaises(ValueError):self.record(s)
    for now in ['2026-11-07T00:01:00+00:00','2026-11-08T00:00:00+00:00','2026-11-12T00:03:00+00:00']:
      with self.assertRaises(ValueError):self.record(now=now)
 def test_tamper_refused(self):
    self.record();path=next(self.root.rglob('prediction-*.json'));path.write_text(path.read_text().replace('0.001','0.003'))
    with self.assertRaises(ValueError):read_verified(path)
 def test_outcome_wait_then_score_once(self):
    r=self.record();s,_=fixture()
    self.assertIsNone(settle(self.root,r,s,_now=stamp('2026-11-08T05:00:00+00:00')))
    s['retrieved_at']='2026-11-10T00:02:00+00:00'
    for day,price in [('08','100'),('09','110')]:
      s['bars'].append({'session':'2026-11-'+day,'open':price,'close':price,'available_at':'2026-11-10T00:02:00+00:00','close_at':'2026-11-10T00:00:00+00:00'})
    out=settle(self.root,r,s,_now=stamp('2026-11-10T00:03:00+00:00'))
    self.assertAlmostEqual(out['realized_variance'],0.009084030374332749)
    self.assertEqual(settle(self.root,r,s,_now=stamp('2026-11-10T01:00:00+00:00')),out)
    self.assertEqual(len(list(self.root.rglob('outcome-*.json'))),1)
 def test_dividend_excludes_entry_includes_exit(self):
    r=self.record();s,_=fixture();s['retrieved_at']='2026-11-10T00:02:00+00:00'
    for day in ['08','09']:s['bars'].append({'session':'2026-11-'+day,'open':'100','close':'100','available_at':s['retrieved_at'],'close_at':'2026-11-10T00:00:00+00:00'})
    s['dividends']=[{'session':'2026-11-08','amount':'50'},{'session':'2026-11-09','amount':'10'}]
    out=settle(self.root,r,s,_now=stamp('2026-11-10T00:03:00+00:00'))
    self.assertAlmostEqual(out['realized_variance'],0.009084030374332749)
