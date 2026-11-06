import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from research.five_asset.score import summarize,verify_calibration

class FiveScoreTests(unittest.TestCase):
    def test_full_scorer_temporary_ten_records(self):
        from research.five_asset.score import score
        from research.market.common import write_json,file_sha,digest
        keys=['train_mean','hist20','ewma','garch','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear']
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp);root=project/'research/artifacts/five-asset/run';root.mkdir(parents=True)
            assets=[]
            for symbol in ('600519','600036','600585','BTCUSDT','ETHUSDT'):
                specs=[]
                for year in (2024,2025):
                    for q in range(1,5):
                        month=(q-1)*3+1;fold=f'{year}Q{q}';rows=[{'signal_session':f'{year}-{month:02d}-{i:02d}','label_end':f'{year}-{month:02d}-{i+5:02d}'} for i in (1,2)]
                        specs.append({'fold':fold,'bounds':{},'horizons':[{'horizon':h,'counts':{'train':2,'early_stopping':2,'calibration':2,'evaluation':2}} for h in (1,5)]})
                        for h in (1,5):
                            folder=root/symbol/fold/f'h{h}'
                            write_json(folder/'training.json',{'models':{k:{'name':k} for k in keys}})
                            write_json(folder/'predictions.json',{'evaluation_labels_read':False,'models':{k:{'raw':[.0001]*2,'calibrated':[.0001]*2,'calibration_raw':[.0001]*2,'raw_c':1.,'c':1.,'clipped':False,'calibration_rows':2} for k in keys}})
                            write_json(folder/'train.json',{'x':[[.01]*60]*2});write_json(folder/'calibration.json',{'y':[.0001]*2})
                            write_json(folder/'evaluation_features.json',{'rows':rows,'x':[[.01]*60]*2});write_json(folder/'evaluation_labels.json',{'rows':rows,'y':[.0001]*2})
                assets.append({'symbol':symbol,'name':symbol,'market':'crypto' if symbol.endswith('USDT') else 'ashare','status':'qualified','folds':specs})
            source={'record':{'assets':assets},'record_sha256':'c'*64,'artifact_status':'verified'}
            protocol={'sources':{},'environment':{},'source_report_id':'validation-'+'a'*64,'source_report_sha256':source['record_sha256']}
            write_json(root/'protocol.json',protocol);write_json(root/'source.json',source);write_json(root/'inputs.json',{'files':{}})
            for folder in root.glob('*/*/h*'):
                write_json(folder/'completed.json',{'inputs_sha256':file_sha(root/'inputs.json'),'files':{p.name:file_sha(p) for p in folder.glob('*.json')}})
            write_json(root/'frozen.json',{'created_at':'2026-11-05T00:00:00+00:00','protocol_sha256':digest(protocol),'inputs_sha256':file_sha(root/'inputs.json'),'files':{p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*.json')}})
            with patch('research.five_asset.score.PROJECT',project),patch('research.five_asset.common.sources',return_value={}),patch('research.five_asset.common.environment',return_value={}),patch('platform_app.adapters.validation_foundation_store.ValidationFoundationStore.get',return_value=source),patch('builtins.print'):
                score(root)
            publications=list((project/'backend/data/five-asset-runs').glob('*.json'));self.assertEqual(len(publications),10)
            for p in publications:
                r=json.loads(p.read_text(encoding='utf8'))['record'];self.assertEqual(len(r['folds']),8);self.assertEqual(r['overall']['ewma']['raw_vs_ewma']['delta_qlike'],0.)
    def test_raw_calibrated_comparisons_share_rows(self):
        rows=[{'fold':'2024Q1','realized_variance':float(i+1),'raw':{'ewma':1.,'x':2.},'calibrated':{'ewma':2.,'x':float(i+1)}} for i in range(10)]
        m=summarize(rows,{'ewma':'EWMA','x':'model'},252)
        self.assertLess(m['x']['calibrated_vs_raw']['delta_qlike'],0)
        self.assertEqual(m['x']['raw']['rows'],10)
        self.assertEqual(m['ewma']['raw_vs_ewma']['delta_qlike'],0.)
        empty=summarize([],{'ewma':'EWMA'},252)
        self.assertIsNone(empty['ewma']['raw'])

    def test_calibration_bound_to_independent_segment(self):
        p={'calibration_raw':[1.,2.],'raw':[2.,3.],'calibrated':[4.,6.],'c':2.,'raw_c':2.,'clipped':False,'calibration_rows':2}
        verify_calibration(p,[2.,4.])
        with self.assertRaises(ValueError):verify_calibration({**p,'c':3.},[2.,4.])
        with self.assertRaises(ValueError):verify_calibration({**p,'calibrated':[9.,9.]},[2.,4.])
