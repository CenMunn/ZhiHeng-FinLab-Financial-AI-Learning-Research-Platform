import unittest
import tempfile,json
from unittest.mock import patch
from pathlib import Path
import numpy as np
from research.volatility_diagnostics.analysis import fit_scale,reliability_bins,failure_windows,coverage_rows
from research.volatility_diagnostics.publish import publish

class DiagnosticTests(unittest.TestCase):
    def test_evaluation_shock_does_not_refit_scale_or_bin_edges(self):
        from research.volatility_diagnostics.runner import diagnose
        from research.market.common import write_json,file_sha
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'source/btc/h1/2025Q1';folder.mkdir(parents=True)
            rows=[{'signal_session':f'2025-01-0{i}','label_start':f'2025-01-0{i+1}','label_end':f'2025-01-0{i+1}'} for i in range(1,5)]
            part={'rows':rows,'x':[[0.]*60]*4,'y':[2.]*4}
            for n in ('train','validation','evaluation_features'):write_json(folder/(n+'.json'),part)
            write_json(folder/'predictions.json',{'ewma':{'validation':[1.]*4,'evaluation':[1.]*4}})
            r={'market':'btc','horizon':1,'annualization':365,'folds':[{'fold':'2025Q1','regime_thresholds':{'low':0.,'high':0.}}],'artifacts':{p.relative_to(root).as_posix():file_sha(p) for p in folder.glob('*.json')},'overall':{'ewma':{'name':'EWMA'}},'observations':[{'session':row['signal_session'],'fold':'2025Q1','predictions':{'ewma':1.},'realized_variance':1.} for row in rows]}
            with patch('research.volatility_diagnostics.runner.PROJECT',root):
                first=diagnose({'record':r})[0]['ewma']['folds'][0]
                for o in r['observations']:o['realized_variance']=100.
                second=diagnose({'record':r})[0]['ewma']['folds'][0]
            self.assertEqual(first['c'],2.);self.assertEqual(first['c'],second['c'])
            self.assertEqual([b['upper'] for b in first['bins']],[b['upper'] for b in second['bins']])
            self.assertNotEqual(first['calibrated'],second['calibrated'])

    def test_publish_preserves_versions_and_idempotency(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);r={'source_run_id':'volatility-'+'a'*64,'diagnostic_id':'vdiag-'+'b'*64}
            publish(folder,r);publish(folder,r)
            second={**r,'diagnostic_id':'vdiag-'+'c'*64};publish(folder,second)
            self.assertEqual(len(list((folder/'versions').glob('*.json'))),2)
            self.assertEqual(json.loads((folder/(r['source_run_id']+'.json')).read_text())['record'],second)
    def test_scale_qlike_optimum_and_clipping(self):
        self.assertEqual(fit_scale([2.,4.],[1.,2.]),{'raw_c':2.,'c':2.,'clipped':False,'validation_rows':2})
        self.assertEqual(fit_scale([0.,0.],[1.,1.])['c'],.25)
        self.assertTrue(fit_scale([100.],[1.])['clipped'])
        with self.assertRaises(ValueError):fit_scale([1.],[float('nan')])

    def test_bins_validation_boundaries_ties_and_empty(self):
        bins=reliability_bins([1.,1.,1.],[.5,1.,3.],[0.,2.,4.])
        self.assertEqual(sum(b['rows'] for b in bins),3)
        self.assertEqual(len(bins),2)
        empty=reliability_bins([1.,2.,3.,4.,5.],[100.],[2.])
        self.assertTrue(any(b['rows']==0 and b['ratio'] is None for b in empty))

    def test_windows_fixed_with_tail_and_boundary(self):
        rows=[{'session':str(i),'realized_variance':2.,'predictions':{'x':1.,'ewma':2.}} for i in range(43)]
        windows=failure_windows(rows,'x',2.,'Q1')
        self.assertEqual([w['rows'] for w in windows],[20,20,3])
        self.assertAlmostEqual(windows[0]['calibrated_delta'],0.)
        self.assertTrue(all(w['fold']=='Q1' for w in windows))

    def test_coverage_zero_and_overlapping_labels(self):
        rows=[{'label_start':f'2025-01-{i:02d}','label_end':f'2025-01-{i+4:02d}'} for i in range(1,11)]
        x=np.zeros((10,60));parts={k:{'x':x,'rows':rows} for k in ('train','validation','evaluation')}
        coverage=coverage_rows(parts,[0.,0.])
        low=next(v for v in coverage if v['regime']=='low_up')
        self.assertEqual(low['evaluation_rows'],10);self.assertEqual(low['nonoverlap_count'],2)
        self.assertEqual(low['missing_to_30'],20)
        self.assertEqual(next(v for v in coverage if v['regime']=='high_down')['evaluation_rows'],0)
