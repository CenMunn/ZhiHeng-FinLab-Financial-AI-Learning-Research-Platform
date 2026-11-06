from datetime import date
import unittest
import numpy as np


class RollingTests(unittest.TestCase):
    def test_fixed_model_files_and_frozen_phase_are_verified_not_reblessed(self):
        import tempfile
        from pathlib import Path
        from research.rolling.acquire import verify_model_files,REVISION
        from research.rolling.common import verify_files,file_sha
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);files={}
            for name in ('README.md','config.json','generation_config.json','model.safetensors'):
                (root/name).write_bytes(b'original');files[name]={'sha256':file_sha(root/name)}
            receipt={'revision':REVISION,'files':files};verify_model_files(receipt,root)
            frozen={'model.safetensors':file_sha(root/'model.safetensors')}
            (root/'model.safetensors').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_model_files(receipt,root)
            with self.assertRaises(ValueError):verify_files(root,frozen)
            (root/'model.safetensors').unlink()
            with self.assertRaises(ValueError):verify_model_files(receipt,root)

    def test_quarter_boundaries_are_cash_and_capital_does_not_reset(self):
        from datetime import timedelta
        from decimal import Decimal
        from research.rolling.score import continuous_policy
        from platform_app.experiments.samples import sample_snapshots
        from platform_app.contracts.public_backtests import PublicDataset
        s=sample_snapshots()[1];body=s.model_dump(mode='json');body.update(source_kind='public',calendar_kind='venue',source_uri='https://example.org/test',calendar_source='test dates')
        data=PublicDataset.model_validate({'snapshot':body,'receipts':[{'url':'https://example.org/test','retrieved_at':'2026-10-30T00:00:00Z','sha256':'a'*64,'file':'raw/test'}], 'timing_assumption':'test','quality':{}})
        def row(i):return {'signal_session':str(s.sessions[i]),'decision_at':(s.bars[i].close_at+timedelta(minutes=1)).isoformat(),
            'entry_session':str(s.sessions[i+2]),'exit_session':str(s.sessions[i+3])}
        folds=[{'rows':[row(3),row(4)],'predictions':{'test':[1,1]}},{'rows':[row(8),row(9)],'predictions':{'test':[1,1]}}]
        policy=continuous_policy(data,folds,'test',0)
        self.assertEqual(len(policy['trades']),4)
        for point in policy['curve']:
            if point['session'] in (str(s.sessions[8]),str(s.sessions[9])):self.assertEqual(point['quantity'],'0')
        cash=Decimal('10000')
        for trade in policy['trades']:cash+=(1 if trade['side']=='sell' else -1)*Decimal(trade['notional'])-Decimal(trade['costs']['total'])
        self.assertEqual(cash,Decimal(policy['curve'][-1]['cash']))

    def test_readout_stats_are_train_only_and_cache_is_input_bound(self):
        import tempfile,json
        from pathlib import Path
        from research.rolling.pretrained import readout,cache
        from research.market.common import file_sha
        x=np.array([[0.,1.],[1.,2.],[2.,3.]])
        _,a=readout(x,[0,1,2],np.zeros((2,2)))
        _,b=readout(x,[0,1,2],np.ones((2,2))*999)
        self.assertEqual(a,b)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);np.savez_compressed(root/'chronos.npz',features=np.zeros((2,3)))
            (root/'chronos.json').write_text(json.dumps({'sha256':file_sha(root/'chronos.npz'),'context_sha256':'wrong'}))
            from unittest.mock import patch
            with patch('research.rolling.pretrained.acquire',return_value={'revision':'fixture','files':{'model.safetensors':{'sha256':'a'*64},'config.json':{'sha256':'b'*64}}}):
                with self.assertRaises(ValueError):cache(root,np.ones((2,60)))

    def test_quarter_fold_and_purge_mature_labels(self):
        from research.rolling.data import fold_specs,partition
        spec=fold_specs()[1]
        self.assertEqual(spec['evaluation'],['2024-04-01','2024-06-30'])
        self.assertEqual(spec['validation'],['2023-04-01','2024-03-31'])
        self.assertEqual(spec['train'],['2018-01-01','2023-03-31'])
        rows=[{'signal_session':'2023-03-29','entry_session':'2023-03-30','exit_session':'2023-03-31','label_available_at':'2023-04-01T00:01:00+00:00'},
              {'signal_session':'2023-03-30','entry_session':'2023-03-31','exit_session':'2023-04-03','label_available_at':'2023-04-03T07:01:00+00:00'},
              {'signal_session':'2024-04-01','entry_session':'2024-04-02','exit_session':'2024-04-03','label_available_at':'2024-04-03T07:01:00+00:00'}]
        split,purged=partition(rows,spec)
        self.assertEqual(len(split['train']),1);self.assertEqual(purged['train'],1);self.assertEqual(len(split['evaluation']),1)
        rows[0]['label_available_at']='2023-04-01T00:02:00+00:00'
        self.assertEqual(len(partition(rows,spec)[0]['train']),0)

    def test_future_prices_do_not_change_features(self):
        import sys
        from pathlib import Path
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend/src'))
        from platform_app.experiments.samples import sample_snapshots
        from platform_app.contracts.market_experiments import MarketSnapshot
        from research.rolling.data import engineered
        data=sample_snapshots()[1];before=engineered(data.bars,(),10,lookback=5)
        raw=data.model_dump(mode='json')
        for key in ('open','high','low','close'):raw['bars'][-1][key]='9999'
        changed=MarketSnapshot.model_validate(raw)
        self.assertEqual(before,engineered(changed.bars,(),10,lookback=5))
        self.assertEqual(len(before),8)

    def test_drift_and_block_permutation_handle_constant_and_alignment(self):
        from research.rolling.diagnostics import psi,block_permute
        self.assertEqual(psi(np.ones(30),np.ones(10))['status'],'constant_train')
        self.assertAlmostEqual(psi(np.arange(100),np.arange(100))['psi'],0)
        x=np.c_[np.arange(60),np.arange(60)*2,np.ones(60)]
        p=block_permute(x,[0,1],seed=42,block=10)
        np.testing.assert_allclose(p[:,1],p[:,0]*2);np.testing.assert_allclose(p[:,2],x[:,2])
        self.assertEqual(sorted(p[:,0]),list(range(60)))


if __name__=='__main__':unittest.main()
