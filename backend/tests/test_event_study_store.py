import copy, hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from platform_app.adapters.event_study_store import EventStudyStore, ENGINE, LOADED_ENGINE_SHA
from platform_app.api.event_study import event_study_router
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict

class EventStoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.folder=self.root/'backend/data/event-study';self.folder.mkdir(parents=True)
  self.pdf=self.root/'research/artifacts/event-study/case.pdf';self.pdf.parent.mkdir(parents=True);self.pdf.write_bytes(b'%PDF-test')
  self.artifact=self.pdf.relative_to(self.root).as_posix()
  self.record={'schema':'event-study-publication-v1','run_id':'event-test','created_at':'2026-11-06T00:00:00+00:00',
   'catalog':[{'event_id':'case','symbol':'600519','title':'2024Q1','report_period':'2024Q1','publication_date':'2024-04-27','time_precision':'date','publication_at':None,'url':'https://www.sse.com.cn/case.pdf'}],
   'case':{'event_id':'case','pdf_path':self.artifact,'pdf_sha256':hashlib.sha256(self.pdf.read_bytes()).hexdigest(),'evidence':[]},
   'stock':{},'benchmark':{},'analysis':{'event_id':'case','symbol':'600519','config':{'pre':5,'post':5}},'artifacts':{self.artifact:hashlib.sha256(self.pdf.read_bytes()).hexdigest()},'sources':{ENGINE:LOADED_ENGINE_SHA},'limitations':[],
   'extraction_evaluation':{'rule':'rule extraction','model':'not_run','gold':'not_established'}}
  self.record['protocol']={'schema':'event-study-protocol-v1','fixed_case':'600519/2024Q1','catalog_publication_range':['2024-01-01','2025-12-31'],'symbols':['600519','600036','600585'],'estimation_offsets':[-130,-21],'event_window_default':[-5,5],'window_preview_each_side':[1,10],'sources':self.record['sources']}
  self.record['run_id']='event-'+stable_hash(self.record['protocol'])
  self.store=EventStudyStore(self.folder,self.root)
 def save(self):
  self.sha=stable_hash(self.record);(self.folder/'latest.json').write_text(json.dumps({'record':self.record,'sha256':self.sha}),encoding='utf8')
 def test_empty_and_verified_pdf(self):
  self.assertEqual(self.store.get()['artifact_status'],'empty');self.save()
  self.assertEqual(self.store.get()['artifact_status'],'verified');self.assertEqual(self.store.document('case'),b'%PDF-test')
  with self.assertRaises(KeyError):self.store.document('../case.pdf')
 def test_tamper_missing_and_unsafe_path(self):
  self.save();self.pdf.write_bytes(b'changed')
  with self.assertRaises(DomainConflict):self.store.get()
  self.pdf.unlink();self.assertEqual(self.store.get()['artifact_status'],'missing')
  with self.assertRaises(DomainConflict):self.store.document('case')
  self.record['artifacts']={'../escape':'a'*64};self.save()
  with self.assertRaises(DomainConflict):self.store.get()
 def test_pdf_must_be_bound_to_artifact_manifest(self):
  self.record['case']['pdf_sha256']='b'*64;self.save()
  with self.assertRaises(DomainConflict):self.store.get()
 def test_internal_identity_and_case_binding_cannot_be_relabelled(self):
  for mutate in [lambda r:r.update(run_id='event-'+'a'*64),lambda r:r['analysis'].update(symbol='600036'),lambda r:r.update(sources={ENGINE:'a'*64})]:
   old=copy.deepcopy(self.record);mutate(self.record);self.save()
   with self.assertRaises(DomainConflict):self.store.get()
   self.record=old
 def test_preview_binds_version_and_loaded_engine(self):
  self.save()
  with self.assertRaises(DomainConflict):self.store.preview(5,5,'a'*64)
  with patch('platform_app.adapters.event_study_store.current_engine_sha',return_value=LOADED_ENGINE_SHA),patch('platform_app.adapters.event_study_store.analyze',return_value={'calculated':True}) as call:
   result=self.store.preview(2,3,self.sha);self.assertEqual(result['analysis'],{'calculated':True});self.assertEqual(call.call_args.kwargs,{'pre':2,'post':3})
  with patch('platform_app.adapters.event_study_store.current_engine_sha',return_value='b'*64):
   with self.assertRaises(DomainConflict):self.store.preview(5,5,self.sha)
 def test_request_validation_and_no_source_write(self):
  self.save();app=FastAPI();app.include_router(event_study_router(self.store));client=TestClient(app)
  before=(self.folder/'latest.json').read_bytes()
  for value in [0,11,True,'5',2.5]:
   response=client.post('/api/v1/event-study/preview',json={'pre':value,'post':5,'source_record_sha256':self.sha});self.assertEqual(response.status_code,422)
  with patch('platform_app.adapters.event_study_store.current_engine_sha',return_value=LOADED_ENGINE_SHA),patch('platform_app.adapters.event_study_store.analyze',return_value={'calculated':True}):
   self.assertEqual(client.post('/api/v1/event-study/preview',json={'pre':2,'post':3,'source_record_sha256':self.sha}).status_code,200)
  self.assertEqual((self.folder/'latest.json').read_bytes(),before)
