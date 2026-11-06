import hashlib,json,tempfile,unittest
from pathlib import Path
from fastapi.testclient import TestClient
from platform_app.api.app import create_app
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict
from test_public_backtests import fixture


class RollingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.folder=self.root/'backend/data/rolling-runs';self.folder.mkdir(parents=True)
        file=self.root/'research/artifacts/rolling/job/weights.txt';file.parent.mkdir(parents=True);file.write_bytes(b'weights');self.file=file
        data=fixture().model_dump(mode='json');protocol={'fixture':True}
        identity={'market':'ashare','dataset_sha256':stable_hash(data),'protocol_sha256':stable_hash(protocol),'base_phase_sha256':'a'*64,'pretrained_phase_sha256':'b'*64}
        metric={'rows':1,'mae':0.,'rmse':0.,'bias':0.,'mse_skill_vs_zero':0.,'direction_accuracy':0.,'zero_actual_rows':0,'neutral_prediction_rows':1,'temporal_correlation':None}
        model={'name':'零收益','metrics':metric,'wins_vs_zero':0,'folds':8}
        self.record={'schema':'rolling-result-v1','run_id':'rolling-'+stable_hash(identity),'identity':identity,'created_at':'2026-10-30T00:00:00Z','market':'ashare','instrument':'600519.SS','currency':'CNY',
            'dataset_sha256':stable_hash(data),'dataset':data,'protocol':protocol,'folds':[{'fold':f'{y}Q{q}'} for y in (2024,2025) for q in (1,2,3,4)],
            'overall':{'zero':model},'policies':{},'cost_sensitivity':{},'observations':[],'pretrained':{'models':{'zero':model}},'phase_receipts':{},
            'artifacts':{file.relative_to(self.root).as_posix():hashlib.sha256(b'weights').hexdigest()},'limitations':[]}
        self.path=self.folder/(self.record['run_id']+'.json');self.save()

    def tearDown(self):self.temp.cleanup()
    def save(self):self.path.write_text(json.dumps({'sha256':stable_hash(self.record),'record':self.record}),encoding='utf8')
    def store(self):
        from platform_app.adapters.rolling_store import RollingStore
        return RollingStore(self.folder,self.root)

    def test_readonly_api_and_missing_original_artifact(self):
        store=self.store();client=TestClient(create_app(rolling_store=store))
        self.assertEqual(client.get('/api/v1/rolling/runs').json()[0]['run_id'],self.record['run_id'])
        self.assertEqual(client.get('/api/v1/rolling/runs/'+self.record['run_id']).json()['artifact_status'],'verified')
        self.assertEqual(client.post('/api/v1/rolling/train').status_code,404)
        self.file.unlink();self.assertEqual(store.get(self.record['run_id'])['artifact_status'],'missing')

    def test_wrong_lookup_and_changed_file_and_escape_fail_closed(self):
        self.file.write_text('changed')
        with self.assertRaises(DomainConflict):self.store().get(self.record['run_id'])
        self.file.write_text('weights');self.record['artifacts']={'../private':hashlib.sha256(b'weights').hexdigest()};self.save()
        with self.assertRaises(DomainConflict):self.store().get(self.record['run_id'])
        with self.assertRaises(KeyError):self.store().get('../private')


if __name__=='__main__':unittest.main()
