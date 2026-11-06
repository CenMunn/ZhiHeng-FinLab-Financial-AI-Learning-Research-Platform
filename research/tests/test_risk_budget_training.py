import copy
import json
import math
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


def dataset(market='ashare', n=100):
    bars=[]
    for i in range(n):
        day=datetime(2024,1,1,tzinfo=timezone.utc)+timedelta(days=i)
        close=day+timedelta(hours=7) if market=='ashare' else day+timedelta(days=1)
        bars.append(dict(session=day.date().isoformat(),open=str(100+i),close=str(200+i),
                         close_at=close.isoformat(),available_at=(close+timedelta(minutes=1)).isoformat()))
    return dict(market=market,bars=bars,dividends=[{'session':bars[62]['session'],'amount':'2'}])


class RiskBudgetTrainingTests(unittest.TestCase):
    def test_target_uses_executable_open_interval_and_exit_dividend(self):
        from research.risk_budget.data import make_rows
        for market,entry,exit in [('ashare',61,62),('crypto',62,63)]:
            d=dataset(market);rows,history=make_rows(d);r=rows[0]
            dividend=2 if exit==62 else 0
            self.assertAlmostEqual(r['target'],math.log((100+exit+dividend)/(100+entry))**2)
            self.assertEqual(r['entry_session'],d['bars'][entry]['session'])
            self.assertEqual(r['exit_session'],d['bars'][exit]['session'])
            self.assertEqual(r['x'],history[1:61])
            self.assertAlmostEqual(r['x'][-1],math.log(160/159))
            self.assertLess(datetime.fromisoformat(r['decision_at']),datetime.fromisoformat(r['entry_at']))

    def test_prefix_delay_and_future_mutation(self):
        from research.risk_budget.data import make_rows
        d=dataset();before,_=make_rows(d)
        mutated=copy.deepcopy(d);mutated['bars'][70]['open']='9999'
        after,_=make_rows(mutated)
        self.assertEqual(before[0],after[0])
        d['bars'][1]['available_at']='2024-03-15T07:01:00+00:00'
        rows,_=make_rows(d)
        self.assertTrue(all(r['signal_session']>='2024-03-15' for r in rows))

    def test_partition_purges_cross_boundary_entry_exit_and_late_labels(self):
        from research.risk_budget.data import make_rows,partition
        rows,_=make_rows(dataset('crypto'))
        bounds={'evaluation':['2024-03-01','2024-03-10']}
        parts,purged=partition(rows,bounds)
        self.assertGreater(purged['evaluation'],0)
        self.assertTrue(all(r['exit_session']<='2024-03-10' for r in parts['evaluation']))
        delayed=copy.deepcopy(rows);delayed[0]['label_available_at']='2025-01-01T00:00:00+00:00'
        p,_=partition(delayed,bounds)
        self.assertNotIn(delayed[0],p['evaluation'])

    def test_calibration_and_loader_separation(self):
        from research.risk_budget.train import calibrate
        from research.risk_budget.pipeline import calibration_features,load_role
        self.assertEqual(calibrate([1.,2.],[10.,20.],[3.])['calibrated'],[12.])
        self.assertEqual(calibrate([1.],[0.],[1e-10])['calibrated'],[1e-10])
        with self.assertRaises(ValueError):calibrate([0.],[1.],[1.])
        with self.assertRaises(ValueError):calibrate([1.],[-1.],[1.])
        with self.assertRaises(ValueError):load_role(Path('.'),'evaluation_labels')
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'calibration.json').write_text('{"rows":[],"x":[],"y":INVALID}',encoding='utf8')
            self.assertEqual(calibration_features(Path(t)),{'rows':[],'x':[]})

    def test_completed_guard_is_file_sha_and_checks_tampering(self):
        from research.risk_budget.pipeline import run_unit
        from research.market.common import write_json,file_sha
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);write_json(root/'inputs.json',{'files':{}})
            folder=root/'BTCUSDT'/'2024Q1';write_json(folder/'receipt.json',{'steps':1})
            write_json(folder/'completed.json',dict(inputs_sha256=file_sha(root/'inputs.json'),files={'receipt.json':file_sha(folder/'receipt.json')}))
            run_unit(root,'BTCUSDT','2024Q1')
            (folder/'receipt.json').write_text('{}')
            with self.assertRaises(ValueError):run_unit(root,'BTCUSDT','2024Q1')

    def test_fit_rejects_labels_in_inference_and_overlapping_roles(self):
        import numpy as np
        from research.risk_budget.train import fit_models
        history=np.arange(200,dtype=float)/1000
        indices=[[60,61],[70,71],[80,81],[90,91]]
        parts=[{'x':[history[i-59:i+1].tolist() for i in ids]} for ids in indices]
        for p in parts[:2]:p['y']=[.001,.002]
        with tempfile.TemporaryDirectory() as t:
            contaminated=copy.deepcopy(parts);contaminated[2]['y']=[.1,.2]
            with self.assertRaisesRegex(ValueError,'exclude labels'):
                fit_models(*contaminated,history_returns=history,indices=indices,lead=3,folder=Path(t)/'a')
            overlapping=[[60,61],[63,64],[80,81],[90,91]]
            parts[1]['x']=[history[i-59:i+1].tolist() for i in overlapping[1]]
            with self.assertRaisesRegex(ValueError,'overlap'):
                fit_models(*parts,history_returns=history,indices=overlapping,lead=3,folder=Path(t)/'b')

    def test_ewma_uses_only_matured_open_history(self):
        import numpy as np
        from research.volatility.models import ewma_forecast
        from research.risk_budget.data import make_rows
        d=dataset();rows,history=make_rows(d);expected=history[1]**2
        for u in history[2:61]:expected=.94*expected+.06*u*u
        actual=ewma_forecast(history,[60])[0]
        self.assertAlmostEqual(actual,expected)
        d['bars'][61]['open']='9000';_,future_mutation=make_rows(d)
        self.assertEqual(actual,ewma_forecast(future_mutation,[60])[0])
        self.assertNotEqual(actual,float(np.mean(np.square(rows[0]['x']))))

    def test_source_archive_exact_bytes_and_bounded_manifest(self):
        from research.risk_budget.common import archive_sources,verify
        from research.market.common import PROJECT,file_sha
        name='research/risk_budget/data.py'
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);manifest=archive_sources(root,{name:file_sha(PROJECT/name)})
            self.assertEqual((root/'source-code'/name).read_bytes(),(PROJECT/name).read_bytes())
            verify(root,manifest)
            with self.assertRaises(ValueError):verify(root,{'../escape':'0'*64})
            (root/'source-code'/name).write_text('tampered')
            with self.assertRaises(ValueError):verify(root,manifest)

if __name__=='__main__':unittest.main()
