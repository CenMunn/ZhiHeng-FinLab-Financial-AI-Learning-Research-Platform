import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

class RiskScoreTests(unittest.TestCase):
    def test_independent_score_publishes_only_in_temporary_project(self):
        from research.risk_budget.score import score
        from research.market.common import write_json,file_sha,digest
        keys=['train_mean','ewma','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear']
        with tempfile.TemporaryDirectory() as tmp:
            project=Path(tmp);root=project/'research/artifacts/risk-budget/run';assets=[]
            for symbol in ('600519','600036','600585','BTCUSDT','ETHUSDT'):
                specs=[];write_json(root/symbol/'dataset.json',{'symbol':symbol,'bars':[]})
                for year in (2024,2025):
                    for q in range(1,5):
                        month=(q-1)*3+1;fold=f'{year}Q{q}';folder=root/symbol/fold
                        rows=[{'signal_session':f'{year}-{month:02d}-01','decision_at':f'{year}-{month:02d}-01T07:01:00+00:00','entry_session':f'{year}-{month:02d}-02','entry_at':f'{year}-{month:02d}-02T01:30:00+00:00','exit_session':f'{year}-{month:02d}-03','exit_at':f'{year}-{month:02d}-03T01:30:00+00:00'}]
                        specs.append({'fold':fold});write_json(folder/'training.json',{'models':{k:{'name':k} for k in keys},'bounds':{},'counts':{'train':1,'early_stopping':1,'calibration':1,'evaluation':1}})
                        write_json(folder/'predictions.json',{'evaluation_labels_read':False,'models':{k:{'raw':[.0001],'calibrated':[.0001],'calibration_raw':[.0001],'raw_c':1.,'c':1.,'clipped':False,'calibration_rows':1} for k in keys}})
                        write_json(folder/'calibration.json',{'y':[.0001]});write_json(folder/'evaluation_features.json',{'rows':rows});write_json(folder/'evaluation_labels.json',{'rows':rows,'y':[.0001]})
                assets.append({'symbol':symbol,'name':symbol,'market':'crypto' if symbol.endswith('USDT') else 'ashare','status':'qualified','folds':specs})
            source={'record':{'assets':assets},'record_sha256':'c'*64,'artifact_status':'verified'};protocol={'sources':{},'environment':{},'source_report_id':'validation-'+'a'*64,'source_report_sha256':source['record_sha256']}
            write_json(root/'protocol.json',protocol);write_json(root/'source.json',source);write_json(root/'inputs.json',{'files':{}})
            for folder in root.glob('*/*Q*'):write_json(folder/'completed.json',{'inputs_sha256':file_sha(root/'inputs.json'),'files':{p.name:file_sha(p) for p in folder.glob('*.json')}})
            write_json(root/'frozen.json',{'created_at':'2026-11-05T00:00:00+00:00','protocol_sha256':digest(protocol),'inputs_sha256':file_sha(root/'inputs.json'),'files':{p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*.json')}})
            account={'metrics':{'annualized_volatility':0.},'curve':[],'trades':[],'rejections':[],'config':{}}
            with patch('research.risk_budget.score.PROJECT',project),patch('research.risk_budget.common.sources',return_value={}),patch('research.risk_budget.common.environment',return_value={}),patch('platform_app.adapters.validation_foundation_store.ValidationFoundationStore.get',return_value=source),patch('platform_app.experiments.risk_budget.simulate',return_value=account),patch('builtins.print'):
                score(root)
            publications=list((project/'backend/data/risk-budget-runs').glob('*.json'));self.assertEqual(len(publications),5)
            for p in publications:
                record=json.loads(p.read_text('utf8'))['record'];self.assertEqual(len(record['folds']),8);self.assertEqual(len(record['scenarios']['1']),8);self.assertEqual(record['shadow']['records'],0)
