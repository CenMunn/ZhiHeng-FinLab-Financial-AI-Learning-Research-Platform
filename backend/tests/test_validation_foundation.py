import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from platform_app.adapters.validation_foundation_store import ValidationFoundationStore
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash

SYMBOLS = ['600519','600036','600900','600585','600276','BTCUSDT','ETHUSDT']
class ValidationFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.folder=self.root/'backend/data/validation-foundation';self.folder.mkdir(parents=True)
        self.artifact=self.root/'research/artifacts/validation-foundation/protocol.json';self.artifact.parent.mkdir(parents=True);self.artifact.write_text('{}')
        bounds=dict(train=['2018-01-01','2022-12-31'],early_stopping=['2023-01-01','2023-06-30'],calibration=['2023-07-01','2023-12-31'],evaluation=['2024-01-01','2024-03-31'])
        assets=[]
        for symbol in SYMBOLS:
            assets.append(dict(symbol=symbol,name=symbol,market='crypto' if symbol.endswith('USDT') else 'ashare',role='candidate',status='rejected',rows=0,issues=['fixture only'],warnings=[],coverage=dict(expected=0,missing=0,extra=0),events=dict(dividends=0,splits=0),folds=[],source_receipts=[]))
        self.record=dict(schema='validation-foundation-v1',created_at='2026-11-05T00:00:00Z',protocol=dict(prospective_start='2026-11-06'),protocol_sha256='',assets=assets,artifacts={self.artifact.relative_to(self.root).as_posix():hashlib.sha256(self.artifact.read_bytes()).hexdigest()},limitations=['Isolated fixture, not research evidence'])
        self.bounds=bounds;self.save()
    def save(self, identity=True):
        if identity:
            self.record['protocol_sha256']=stable_hash(self.record['protocol'])
            self.record['report_id']='validation-'+stable_hash({k:self.record[k] for k in ('protocol_sha256','assets','artifacts')})
        (self.folder/'latest.json').write_text(json.dumps(dict(record=self.record,sha256=stable_hash(self.record))),encoding='utf8')
    def store(self):return ValidationFoundationStore(self.folder,self.root)
    def test_reads_all_candidates_and_verifies_artifacts(self):
        body=self.store().get();self.assertEqual(body['artifact_status'],'verified');self.assertEqual(body['record_sha256'],stable_hash(self.record));self.assertEqual(len(body['record']['assets']),7)
    def test_absent_publication_does_not_create(self):
        (self.folder/'latest.json').unlink()
        with self.assertRaises(KeyError):self.store().get()
        self.assertFalse((self.folder/'latest.json').exists())
    def test_missing_artifacts_marked_and_changed_refused(self):
        self.artifact.unlink();self.assertEqual(self.store().get()['missing_artifacts'],list(self.record['artifacts']))
        self.artifact.write_text('changed')
        with self.assertRaises(DomainConflict):self.store().get()
    def test_rehashed_illegal_paths_identity_and_candidates_rejected(self):
        original=deepcopy(self.record)
        mutations=[lambda r:r.update(report_id='validation-'+'f'*64),lambda r:r.update(protocol_sha256='a'*64),lambda r:r['assets'].pop(),lambda r:r['assets'][0].update(rows=-1),lambda r:r['assets'][0].update(market='btc'),lambda r:r['assets'][0].update(status='qualified'),lambda r:r.update(artifacts={'research/artifacts/validation-foundation/../private.json':'a'*64}),lambda r:r.update(artifacts={'research/artifacts/other/file.json':'a'*64}),lambda r:r.update(artifacts={'D:/secret':'a'*64})]
        for i,mutation in enumerate(mutations):
            with self.subTest(i=i):
                self.record=deepcopy(original);mutation(self.record);self.save(identity=i not in (0,1))
                with self.assertRaises(DomainConflict):self.store().get()
    def test_overlapping_segments_rejected_after_valid_rehash(self):
        asset=self.record['assets'][0];asset.update(status='qualified',issues=[],rows=1000)
        bounds=deepcopy(self.bounds);bounds['calibration'][0]='2023-06-30'
        asset['folds']=[dict(fold=f'{y}Q{q}',bounds=deepcopy(bounds),horizons=[dict(horizon=h,counts={k:1 for k in bounds},purged={k:0 for k in bounds}) for h in (1,5)]) for y in (2024,2025) for q in (1,2,3,4)]
        self.save()
        with self.assertRaises(DomainConflict):self.store().get()
    def test_readonly_endpoint(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from platform_app.api.validation_foundation import validation_foundation_router
        app=FastAPI();app.include_router(validation_foundation_router(self.store()));client=TestClient(app);url='/api/v1/validation-foundation/report'
        response=client.get(url);self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store');self.assertEqual(client.post(url).status_code,405)

    def test_receipt_cannot_reference_untracked_or_external_source(self):
        self.record['assets'][0]['source_receipts']=[dict(file='../private.json',sha256='a'*64,url='fixture',retrieved_at='2026-11-05T00:00:00Z')]
        self.save()
        with self.assertRaises(DomainConflict):self.store().get()
    def test_envelope_tampering_rejected(self):
        path=self.folder/'latest.json';body=json.loads(path.read_text('utf8'));body['record']['assets'][0]['rows']=42;path.write_text(json.dumps(body),encoding='utf8')
        with self.assertRaises(DomainConflict):self.store().get()

    def test_original_version_remains_readable_after_latest_changes(self):
        original=self.record['report_id'];versions=self.folder/'versions';versions.mkdir()
        (versions/(original+'.json')).write_bytes((self.folder/'latest.json').read_bytes())
        self.record['protocol']['new_version']=True;self.save()
        self.assertNotEqual(self.store().get()['record']['report_id'],original)
        self.assertEqual(self.store().get(original)['record']['report_id'],original)
        with self.assertRaises(KeyError):self.store().get('../latest')
        wrong='validation-'+'f'*64
        (versions/(wrong+'.json')).write_bytes((versions/(original+'.json')).read_bytes())
        with self.assertRaises(DomainConflict):self.store().get(wrong)
