import unittest,tempfile,json,hashlib
from pathlib import Path
from copy import deepcopy
from unittest.mock import Mock
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict

KEYS=['train_mean','hist20','ewma','garch','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear']
class FiveAssetTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.folder=self.root/'records';self.folder.mkdir()
  self.artifact=self.root/'research/artifacts/five-asset/job/frozen.json';self.artifact.parent.mkdir(parents=True);self.artifact.write_text('{}')
  self.source=Mock();self.source.get.return_value=dict(record_sha256='a'*64,artifact_status='verified',missing_artifacts=[])
  metric=dict(rows=1,qlike=-8.,variance_rmse=0.,variance_mae=0.,volatility_rmse_ann=0.,calibration_ratio=1.,prediction_floor_count=0)
  comparison=dict(delta_qlike=0.,ci_low=0.,ci_high=0.,block=20,repeats=2000,method='fixture')
  model=dict(name='fixture',raw=metric,calibrated=metric,raw_vs_ewma=comparison,calibrated_vs_ewma=comparison,calibrated_vs_raw=comparison)
  folds=[];obs=[]
  for y in [2024,2025]:
   for q in [1,2,3,4]:
    f=f'{y}Q{q}';day=f'{y}-{(q-1)*3+1:02d}-02';models={k:deepcopy(model)|dict(c=1.,raw_c=1.,clipped=False,calibration_rows=1) for k in KEYS}
    bounds=dict(train=['2018-01-01','2022-12-31'],early_stopping=['2023-01-01','2023-06-30'],calibration=['2023-07-01','2023-12-31'],evaluation=[day,day[:-2]+'28'])
    folds.append(dict(fold=f,bounds=bounds,counts={k:1 for k in bounds},models=models,training={}))
    obs.append(dict(session=day,label_end=day[:-2]+'03',fold=f,regime='low_up',realized_variance=.01,raw={k:.01 for k in KEYS},calibrated={k:.01 for k in KEYS}))
  overall={k:deepcopy(model)|dict(wins_raw=0,wins_calibrated=0,folds=8) for k in KEYS}
  for m in overall.values():m['raw']['rows']=m['calibrated']['rows']=8
  regimes={'low_up':dict(name='low',rows=8,sufficient=False,models=deepcopy(overall))}
  protocol={'fixture':True};identity=dict(protocol_sha256=stable_hash(protocol),source_report_sha256='a'*64,symbol='600519',horizon='1')
  self.r=dict(schema='five-asset-result-v1',run_id='five-'+stable_hash(identity),identity=identity,created_at='2026-11-05T00:00:00Z',symbol='600519',name='fixture',market='ashare',horizon=1,annualization=252,source_report_id='validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c',source_report_sha256='a'*64,protocol=protocol,overall=overall,folds=folds,regimes=regimes,observations=obs,artifacts={self.artifact.relative_to(self.root).as_posix():hashlib.sha256(b'{}').hexdigest()},limitations=['fixture only'])
  self.save()
 def save(self):
  (self.folder/(self.r['run_id']+'.json')).write_text(json.dumps(dict(record=self.r,sha256=stable_hash(self.r))),'utf8')
 def store(self):
  from platform_app.adapters.five_asset_store import FiveAssetStore
  return FiveAssetStore(self.folder,self.root,self.source)
 def test_verified_original_source_and_readonly_api(self):
  from fastapi import FastAPI
  from fastapi.testclient import TestClient
  from platform_app.api.five_asset import five_asset_router
  app=FastAPI();app.include_router(five_asset_router(self.store()));c=TestClient(app)
  response=c.get('/api/v1/five-asset/runs');self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store');self.assertEqual(response.json()[0]['rows'],8)
  self.assertEqual(c.get('/api/v1/five-asset/runs/'+self.r['run_id']).json()['artifact_status'],'verified');self.assertEqual(c.post('/api/v1/five-asset/runs').status_code,405)
  self.source.get.assert_called_with(self.r['source_report_id'])
 def test_missing_and_changed_artifacts_and_source(self):
  self.artifact.unlink();self.source.get.return_value.update(artifact_status='missing',missing_artifacts=['original-source'])
  body=self.store().get(self.r['run_id']);self.assertEqual(body['artifact_status'],'missing');self.assertIn('original-source',body['missing_artifacts'])
  self.artifact.write_text('changed')
  with self.assertRaises(DomainConflict):self.store().get(self.r['run_id'])
  self.artifact.write_text('{}');self.source.get.return_value['record_sha256']='b'*64
  with self.assertRaises(DomainConflict):self.store().get(self.r['run_id'])
 def test_rehashed_corruption_rejected(self):
  original=deepcopy(self.r)
  mutations=[lambda r:r.update(symbol='ETHUSDT'),lambda r:r['folds'].pop(),lambda r:r['observations'][0]['raw'].update(ewma=0),lambda r:r['overall']['ewma']['raw'].update(rows=7),lambda r:r['folds'][0]['counts'].update(evaluation=3),lambda r:r['overall']['ewma']['calibrated_vs_raw'].update(ci_low=1,ci_high=0),lambda r:r['observations'][0]['raw'].pop('garch'),lambda r:r.update(artifacts={'research/artifacts/volatility/x':'a'*64}),lambda r:r['regimes']['low_up'].update(sufficient=True),lambda r:r['folds'][0]['counts'].update(calibration=-1),lambda r:r['folds'][0]['bounds']['calibration'].__setitem__(0,'2023-06-30')]
  for mutate in mutations:
   self.r=deepcopy(original);mutate(self.r);self.save()
   with self.assertRaises(DomainConflict):self.store().get(self.r['run_id'])
 def test_invalid_lookup_and_empty_no_writes(self):
  with self.assertRaises(KeyError):self.store().get('../private')
  self.assertEqual(type(self.store())(self.root/'absent',self.root,self.source).list(),[]);self.assertFalse((self.root/'absent').exists())

 def test_absent_original_source_is_missing_not_current_replacement(self):
  self.source.get.side_effect=KeyError('original')
  body=self.store().get(self.r['run_id']);self.assertEqual(body['record'],self.r)
  self.assertEqual(body['artifact_status'],'missing');self.assertIn('source-report:'+self.r['source_report_id'],body['missing_artifacts'])
 def test_empty_regime_is_null_and_cannot_claim_zero_metrics(self):
  model=dict(name='empty',raw=None,calibrated=None,raw_vs_ewma=None,calibrated_vs_ewma=None,calibrated_vs_raw=None)
  self.r['regimes']['empty']=dict(name='empty',rows=0,sufficient=False,models={k:deepcopy(model) for k in KEYS});self.save()
  self.assertIsNone(self.store().get(self.r['run_id'])['record']['regimes']['empty']['models']['ewma']['raw'])
  self.r['regimes']['empty']['models']['ewma']['raw']={};self.save()
  with self.assertRaises(DomainConflict):self.store().get(self.r['run_id'])

 def test_catalog_latest_uses_actual_timestamp_across_offsets(self):
  latest=self.r['run_id'];self.r['created_at']='2026-11-05T07:00:00+08:00'
  self.r['protocol']['another_version']=True
  self.r['identity']['protocol_sha256']=stable_hash(self.r['protocol'])
  self.r['run_id']='five-'+stable_hash(self.r['identity']);self.save()
  self.assertEqual(self.store().list()[0]['run_id'],latest)

 def second_version(self):
  self.r['protocol']['second_version']=True;self.r['identity']['protocol_sha256']=stable_hash(self.r['protocol']);self.r['run_id']='five-'+stable_hash(self.r['identity']);self.save()
 def test_list_deduplicates_shared_verification_but_new_requests_are_fresh(self):
  from unittest.mock import patch
  self.second_version();store=self.store()
  with patch('platform_app.adapters.five_asset_store.hashlib.file_digest',wraps=hashlib.file_digest) as hashed:
   self.assertEqual(len(store.list()),2);self.assertEqual(hashed.call_count,1);self.assertEqual(self.source.get.call_count,1)
   store.get(self.r['run_id']);self.assertEqual(hashed.call_count,2)
   self.artifact.write_text('changed')
   with self.assertRaises(DomainConflict):store.list()
   with self.assertRaises(DomainConflict):store.get(self.r['run_id'])
 def test_list_still_compares_each_expected_sha(self):
  self.second_version();self.r['artifacts']={next(iter(self.r['artifacts'])):'f'*64};self.save()
  with self.assertRaises(DomainConflict):self.store().list()
 def test_shared_file_changed_during_list_is_rehashed_and_rejected(self):
  from unittest.mock import patch
  self.second_version();original=hashlib.file_digest
  def change_after_first(stream,kind):
   result=original(stream,kind);self.artifact.write_text('changed after hash');return result
  with patch('platform_app.adapters.five_asset_store.hashlib.file_digest',side_effect=change_after_first):
   with self.assertRaises(DomainConflict):self.store().list()

 def test_stat_change_between_records_rehashes_shared_file(self):
  from unittest.mock import patch
  self.second_version();store=self.store();read=store.get;calls=0
  def between(*args,**kwargs):
   nonlocal calls
   body=read(*args,**kwargs);calls+=1
   if calls==1:self.artifact.write_text('changed between records')
   return body
  with patch.object(store,'get',side_effect=between),patch('platform_app.adapters.five_asset_store.hashlib.file_digest',wraps=hashlib.file_digest) as hashed:
   with self.assertRaises(DomainConflict):store.list()
   self.assertEqual(hashed.call_count,2)
