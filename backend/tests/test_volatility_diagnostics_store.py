import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
import test_volatility_store as parent_fixture
from platform_app.adapters.volatility_diagnostics_store import VolatilityDiagnosticsStore
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict

class DiagnosticsStoreTests(unittest.TestCase):
    def setUp(self):
        self.fixture=parent_fixture.VolatilityStoreTests();self.fixture.setUp();self.root=self.fixture.root
        self.parent=self.fixture.record
        self.folder=self.root/'backend/data/volatility-diagnostics';self.folder.mkdir(parents=True)
        self.path=self.folder/(self.parent['run_id']+'.json')
        self.source=self.root/'research/volatility_diagnostics/analysis.py';self.source.parent.mkdir(parents=True);self.source.write_text('# fixture',encoding='utf8')
        self.artifact=self.root/'research/artifacts/volatility-diagnostics/job/source.json';self.artifact.parent.mkdir(parents=True);self.artifact.write_text('{}',encoding='utf8')
        sources={self.source.relative_to(self.root).as_posix():hashlib.sha256(self.source.read_bytes()).hexdigest()}
        protocol={'fixture':True};source_sha=stable_hash(self.parent)
        metric=deepcopy(self.parent['overall']['ewma']['metrics']);one=deepcopy(metric);one['rows']=1
        coverage=lambda n:[dict(regime=str(i),name=str(i),train_rows=n if i==0 else 0,validation_rows=n if i==0 else 0,evaluation_rows=n if i==0 else 0,nonoverlap_count=n if i==0 else 0,missing_to_30=max(0,30-(n if i==0 else 0)),train_share=1. if i==0 else 0.,evaluation_share=1. if i==0 else 0.,share_change=0.) for i in range(6)]
        folds=[dict(fold=f['fold'],raw_c=1.,c=1.,clipped=False,validation_rows=1,raw=deepcopy(one),calibrated=deepcopy(one),bins=[dict(lower=None,upper=None,rows=1,prediction_mean=.001,realized_mean=.001,ratio=1.)]) for f in self.parent['folds']]
        windows=[dict(fold=o['fold'],start=o['session'],end=o['session'],rows=1,raw_qlike=-8.,calibrated_qlike=-8.,ewma_qlike=-8.,raw_delta=0.,calibrated_delta=0.,underforecast_count=0,max_realized_variance=.001) for o in self.parent['observations']]
        self.record=dict(schema='volatility-diagnostics-v1',diagnostic_id='vdiag-'+stable_hash(dict(source_record_sha256=source_sha,protocol_sha256=stable_hash(protocol),sources=sources)),source_run_id=self.parent['run_id'],source_record_sha256=source_sha,created_at='2026-11-05T00:00:00Z',market='ashare',horizon=1,protocol=protocol,sources=sources,artifacts={self.artifact.relative_to(self.root).as_posix():hashlib.sha256(self.artifact.read_bytes()).hexdigest()},models={'ewma':dict(name='EWMA',raw=metric,calibrated=deepcopy(metric),comparison=deepcopy(self.parent['overall']['ewma']['comparison']),folds=folds,windows=windows,worst_windows=deepcopy(windows[:3]))},coverage=coverage(8),coverage_folds=[dict(fold=f['fold'],regimes=coverage(1)) for f in folds],limitations=['Fixture only'])
        self.save()
    def tearDown(self): self.fixture.tearDown()
    def save(self): self.path.write_text(json.dumps(dict(record=self.record,sha256=stable_hash(self.record))),encoding='utf8')
    def store(self): return VolatilityDiagnosticsStore(self.folder,self.root,self.fixture.store())
    def test_verified_binds_source_identity(self):
        body=self.store().get(self.parent['run_id']);self.assertEqual(body['artifact_status'],'verified');self.assertEqual(body['record_sha256'],stable_hash(self.record))
    def test_no_record_is_honest_and_no_create(self):
        self.path.unlink()
        with self.assertRaises(KeyError): self.store().get(self.parent['run_id'])
        self.assertFalse(self.path.exists())
        with self.assertRaises(KeyError): self.store().get('../private')
    def test_missing_original_and_diagnostic_files_inherit(self):
        self.fixture.file.unlink();self.artifact.unlink();body=self.store().get(self.parent['run_id'])
        self.assertEqual(body['artifact_status'],'missing');self.assertEqual(len(body['missing_artifacts']),2)
    def test_changed_parent_or_artifacts_rejected(self):
        for path in (self.fixture.file,self.source,self.artifact):
            old=path.read_bytes();path.write_bytes(b'changed')
            with self.assertRaises(DomainConflict): self.store().get(self.parent['run_id'])
            path.write_bytes(old)
    def test_mutations_rejected_even_if_envelope_rehashed(self):
        original=deepcopy(self.record)
        mutations=[lambda r:r.update(source_record_sha256='a'*64),lambda r:r.update(market='btc'),lambda r:r.update(horizon=5),lambda r:r.update(diagnostic_id='vdiag-'+'f'*64),lambda r:r['models']['ewma']['folds'][0].update(c=4.),lambda r:r['models']['ewma']['windows'][0].update(rows=20),lambda r:r['models']['ewma']['raw'].update(rows=9),lambda r:r['coverage'][0].update(nonoverlap_count=9),lambda r:r.update(artifacts={'../private':'a'*64}),lambda r:r['models']['ewma']['folds'][0]['bins'][0].update(rows=0),lambda r:r['models']['ewma'].update(worst_windows=[])]
        for i,mutate in enumerate(mutations):
            with self.subTest(case=i):
                self.record=deepcopy(original);mutate(self.record);self.save()
                with self.assertRaises(DomainConflict):self.store().get(self.parent['run_id'])
    def test_readonly_endpoint(self):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        from platform_app.api.volatility import volatility_router
        app=FastAPI();app.include_router(volatility_router(self.fixture.store(),self.store()));client=TestClient(app)
        url='/api/v1/volatility/runs/'+self.parent['run_id']+'/diagnostics'
        response=client.get(url);self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store');self.assertEqual(client.post(url).status_code,405)
    def test_nonfinite_is_not_valid_json_result(self):
        self.record['models']['ewma']['raw']['qlike']=float('nan')
        self.path.write_text(json.dumps(dict(record=self.record,sha256='a'*64)),encoding='utf8')
        with self.assertRaises(DomainConflict):self.store().get(self.parent['run_id'])
