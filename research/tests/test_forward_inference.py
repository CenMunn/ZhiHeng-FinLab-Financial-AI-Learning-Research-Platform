import copy
import json
import math
import unittest
from datetime import date, timedelta
from pathlib import Path


class ForwardInferenceTests(unittest.TestCase):
    def test_frozen_latest_fold_reproduces_saved_predictions_without_fitting(self):
        from research.forward_market.inference import load_bundle, predict
        for symbol in ('600519', '600036', '600585', 'BTCUSDT', 'ETHUSDT'):
            bundle = load_bundle(symbol)
            self.assertEqual(bundle['fold'], '2025Q4')
            root = Path(bundle['root'])
            history = json.loads((root/symbol/'history.json').read_text('utf8'))
            features = json.loads((root/symbol/'2025Q4/evaluation_features.json').read_text('utf8'))
            saved = json.loads((root/symbol/'2025Q4/predictions.json').read_text('utf8'))['models']
            for index in (0, len(features['rows'])-1):
                row = features['rows'][index]
                actual = predict(bundle, history[:row['history_index']+1])
                self.assertEqual(len(actual['raw']), 7)
                for mode in ('raw', 'calibrated'):
                    for model in saved:
                        expected = saved[model][mode][index]
                        self.assertAlmostEqual(actual[mode][model], expected,
                                               delta=max(1e-10, abs(expected)*2e-6))

    def test_bundle_metadata_tampering_and_truncated_history_rejected(self):
        from research.forward_market.inference import load_bundle, predict, verify_bundle, _digest
        bundle = load_bundle('BTCUSDT')
        changed = copy.deepcopy(bundle)
        changed['calibration']['dlinear'] = 9.0
        with self.assertRaisesRegex(ValueError, 'bundle'):
            verify_bundle(changed)
        changed=copy.deepcopy(bundle)
        changed['model_files'].pop(next(iter(changed['model_files'])))
        changed['bundle_sha256']=_digest({k:v for k,v in changed.items() if k!='bundle_sha256'})
        with self.assertRaisesRegex(ValueError, 'bundle'):
            verify_bundle(changed)
        for values in ([0.]+[.01]*60, [0., float('nan')], [0.]*60):
            with self.assertRaises(ValueError):
                predict(bundle, values)
        with self.assertRaises(ValueError):
            load_bundle('INVALID')

    def fixture(self):
        start = date(2025, 10, 31)
        bars = [dict(session=(start+timedelta(days=i)).isoformat(), open=str(100+i)) for i in range(62)]
        dataset = dict(symbol='BTCUSDT', market='crypto', bars=bars, dividends=[])
        history = [0.]+[math.log(float(bars[i]['open'])/float(bars[i-1]['open'])) for i in range(1,len(bars))]
        new = [dict(session='2026-01-01',open='162'), dict(session='2026-01-02',open='163')]
        for bar in bars+new:
            bar['available_at'] = bar['session']+'T23:59:00+00:00'
        snapshot = dict(symbol='BTCUSDT',market='crypto',status='ready',bars=copy.deepcopy(bars[-3:]+new),
                        dividends=[],splits=[],calendar=[b['session'] for b in bars[-3:]+new],
                        retrieved_at='2026-01-03T00:00:00+00:00')
        return dataset,history,snapshot

    def test_history_extends_all_intervening_sessions_without_resetting_ewma(self):
        from research.forward_market.inference import _merge_history
        d,h,s=self.fixture()
        joined=_merge_history(d,h,s,'2026-01-02')
        self.assertEqual(joined[:len(h)],h)
        self.assertEqual(len(joined),len(h)+2)
        self.assertAlmostEqual(joined[-1],math.log(163/162))
        shorter=_merge_history(d,h,s,'2026-01-01')
        self.assertEqual(len(shorter),len(h)+1)

    def test_history_rejects_gap_duplicate_overlap_revision_split_and_future_availability(self):
        from research.forward_market.inference import _merge_history
        d,h,s=self.fixture()
        cases=[]
        t=copy.deepcopy(s);t['bars']=[b for b in t['bars'] if b['session']!='2026-01-01'];cases.append(t)
        t=copy.deepcopy(s);t['bars'].append(t['bars'][-1]);cases.append(t)
        t=copy.deepcopy(s);t['bars'][0]['open']='999';cases.append(t)
        t=copy.deepcopy(s);t['splits']=[{'session':'2026-01-01','ratio':'2'}];cases.append(t)
        t=copy.deepcopy(s);t['bars'][-1]['available_at']='2026-01-04T00:00:00Z';cases.append(t)
        t=copy.deepcopy(s);t['calendar'].remove('2026-01-01');cases.append(t)
        t=copy.deepcopy(s);t['dividends']=[{'session':d['bars'][-1]['session'],'amount':'1'}];cases.append(t)
        t=copy.deepcopy(s);t['status']='blocked';cases.append(t)
        for invalid in cases:
            with self.assertRaises(ValueError): _merge_history(d,h,invalid,'2026-01-02')


if __name__=='__main__':unittest.main()
