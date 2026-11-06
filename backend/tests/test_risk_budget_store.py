import json,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import Mock,patch
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict
from platform_app.adapters.risk_budget_store import RiskBudgetStore,STRATEGIES,ENGINE,SOURCE
class RiskBudgetTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.folder=self.root/'runs';self.folder.mkdir()
  self.file=self.root/'research/artifacts/risk-budget/job/input.json';self.file.parent.mkdir(parents=True);self.file.write_text('{}')
  self.engine=self.root/ENGINE;self.engine.parent.mkdir(parents=True);self.engine.write_text('# test')
  sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
  for key,value in (('LOADED_ENGINE_PATH',self.engine.resolve()),('LOADED_ENGINE_SHA',sha(self.engine))):
   guard=patch('platform_app.adapters.risk_budget_store.'+key,value);guard.start();self.addCleanup(guard.stop)
  protocol={'sources':{ENGINE:sha(self.engine)}};identity={'protocol_sha256':stable_hash(protocol),'source_report_sha256':'a'*64,'symbol':'600519'}
  account={'metrics':{},'curve':[],'trades':[],'rejections':[],'config':{}}
  self.r=dict(schema='risk-budget-result-v1',identity=identity,run_id='risk-'+stable_hash(identity),protocol=protocol,created_at='2026-11-05T00:00:00Z',symbol='600519',name='茅台',market='ashare',annualization=252,source_report_id=SOURCE,source_report_sha256='a'*64,dataset={'symbol':'600519'},models={},folds=[],observations=[],scenarios={str(i):{k:account for k in STRATEGIES} for i in range(3)},artifacts={self.file.relative_to(self.root).as_posix():sha(self.file)},limitations=['test'],shadow={'status':'pending','records':0})
  self.r['dataset']['market']='ashare';self.r['dataset_sha256']=stable_hash(self.r['dataset'])
  self.r['folds']=[{'fold':f'{y}Q{q}'} for y in (2024,2025) for q in (1,2,3,4)]
  self.r['observations']=[dict(signal_session='2024-01-02',decision_at='2024-01-02T07:01:00Z',entry_at='2024-01-03T01:30:00Z',exit_at='2024-01-04T01:30:00Z',fold='2024Q1',raw={k:.01 for k in ('train_mean','ewma','lightgbm','dlinear')},calibrated={k:.01 for k in ('train_mean','ewma','lightgbm','dlinear')})]
  self.source=Mock();self.source.get.return_value={'record_sha256':'a'*64,'missing_artifacts':[]}
  self.store=RiskBudgetStore(self.folder,self.root,self.source);self.save()
 def save(self): (self.folder/(self.r['run_id']+'.json')).write_text(json.dumps({'record':self.r,'sha256':stable_hash(self.r)}),encoding='utf8')
 def tearDown(self):self.tmp.cleanup()
 def test_verified_missing_changed_and_archive_binding(self):
  self.assertEqual(self.store.get(self.r['run_id'])['artifact_status'],'verified');self.source.get.assert_called_with(SOURCE)
  self.file.unlink();self.assertEqual(self.store.get(self.r['run_id'])['artifact_status'],'missing')
  self.file.write_text('changed')
  with self.assertRaises(DomainConflict):self.store.get(self.r['run_id'])
 def test_path_and_source_identity_rejected(self):
  self.r['artifacts']={'research/artifacts/other/file':'a'*64};self.save()
  with self.assertRaises(DomainConflict):self.store.get(self.r['run_id'])
  with self.assertRaises(KeyError):self.store.get('../private')
 def test_list_deduplicates_only_within_request(self):
  self.r['protocol']['version']=2;self.r['identity']['protocol_sha256']=stable_hash(self.r['protocol']);self.r['run_id']='risk-'+stable_hash(self.r['identity']);self.save()
  self.assertEqual(len(self.store.list()),2);self.assertEqual(self.source.get.call_count,1)
  self.store.list();self.assertEqual(self.source.get.call_count,2)
 def test_preview_refuses_missing_or_changed_engine(self):
  self.file.unlink()
  with self.assertRaises(DomainConflict):self.store.preview(self.r['run_id'],'0.1',1)
  self.file.write_text('{}');self.engine.write_text('changed')
  with self.assertRaises(DomainConflict):self.store.preview(self.r['run_id'],'0.1',1)
 def test_preview_calls_only_engine_and_does_not_write(self):
  before=(self.folder/(self.r['run_id']+'.json')).read_bytes()
  with patch('platform_app.adapters.risk_budget_store.simulate',return_value={'metrics':{}}) as engine:
   body=self.store.preview(self.r['run_id'],'0.20',2)
  self.assertEqual(engine.call_count,8);self.assertEqual(body['source_record_sha256'],stable_hash(self.r));self.assertEqual(set(body['strategies']),set(STRATEGIES));self.assertEqual(before,(self.folder/(self.r['run_id']+'.json')).read_bytes())
 def test_api_rejects_invalid_parameters(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from platform_app.api.risk_budget import risk_budget_router
  app=FastAPI();app.include_router(risk_budget_router(self.store));client=TestClient(app)
  url='/api/v1/risk-budget/runs/'+self.r['run_id']+'/preview'
  for data in ({'target_volatility':'0.04','cost_multiplier':1},{'target_volatility':'NaN','cost_multiplier':1},{'target_volatility':.1,'cost_multiplier':1},{'target_volatility':'0.10','cost_multiplier':True},{'target_volatility':'0.10','cost_multiplier':3}):
   self.assertEqual(client.post(url,json=data).status_code,422)

 def test_rehashed_dataset_time_and_prediction_corruption_refused(self):
  from copy import deepcopy
  original=deepcopy(self.r)
  for mutate in (lambda r:r['dataset'].update(symbol='BTCUSDT'),lambda r:r['folds'].pop(),lambda r:r['observations'][0].update(entry_at='2024-01-02T00:00:00Z'),lambda r:r['observations'][0]['raw'].update(ewma=0)):
   self.r=deepcopy(original);mutate(self.r);self.save()
   with self.assertRaises(DomainConflict):self.store.get(self.r['run_id'])

 def test_missing_original_never_replaced_by_current_source(self):
  self.source.get.side_effect=KeyError('archive missing')
  result=self.store.get(self.r['run_id']);self.assertEqual(result['artifact_status'],'missing');self.assertIn('source-report:'+SOURCE,result['missing_artifacts'])
  with self.assertRaises(DomainConflict):self.store.preview(self.r['run_id'],'0.10',1)
 def test_changed_original_archive_refused(self):
  self.source.get.return_value['record_sha256']='b'*64
  with self.assertRaises(DomainConflict):self.store.get(self.r['run_id'])
 def test_endpoint_read_no_store_and_preview_identity(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from platform_app.api.risk_budget import risk_budget_router
  app=FastAPI();app.include_router(risk_budget_router(self.store));client=TestClient(app);url='/api/v1/risk-budget/runs/'+self.r['run_id']
  response=client.get(url);self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')
  with patch('platform_app.adapters.risk_budget_store.simulate',return_value={'metrics':{}}):
   response=client.post(url+'/preview',json={'target_volatility':'0.10','cost_multiplier':1})
  self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store');self.assertEqual(response.json()['source_record_sha256'],stable_hash(self.r))

 def test_stale_loaded_engine_refused_even_when_disk_matches_record(self):
  with patch('platform_app.adapters.risk_budget_store.LOADED_ENGINE_SHA','0'*64):
   with self.assertRaises(DomainConflict):self.store.preview(self.r['run_id'],'0.10',1)
