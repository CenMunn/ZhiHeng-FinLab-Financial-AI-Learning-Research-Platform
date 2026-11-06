from hashlib import sha256
from pathlib import Path
import json,tempfile,unittest
from fastapi.testclient import TestClient
from platform_app.api.app import create_app
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict
from test_public_backtests import fixture


class ForecastStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.project=Path(self.tmp.name);self.folder=self.project/'backend/data/forecast-runs';self.folder.mkdir(parents=True)
        self.artifact=self.project/'research/artifacts/market-forecast/job/ashare';self.artifact.mkdir(parents=True)
        self.files={}
        for name in ('preparation.json','training.json','predictions.json','evaluation_labels.json'):
            (self.artifact/name).write_text('{}');self.files[name]=sha256(b'{}').hexdigest()
        data=fixture().model_dump(mode='json')
        metric={'rows':1,'mae':0.,'rmse':0.,'bias':0.,'mse_skill_vs_zero':1.,'direction_accuracy':1.,'zero_actual_rows':0,'neutral_prediction_rows':0,'temporal_correlation':None}
        self.record={'schema':'market-forecast-result-v1','market':'ashare','instrument':'600519.SS','currency':'CNY','dataset_id':data['snapshot']['snapshot_id'],
            'dataset_sha256':stable_hash(data),'dataset':data,'config':{},'counts':{'train':1,'validation':1,'evaluation':1},'purged':{},'scaler':{},'training':{},
            'models':{'zero':{'name':'零收益','evaluation':metric,'validation':metric,'annual':[],'mse_difference_interval':{}}},'benchmark':{},'evaluation':{},'observations':[],
            'environment':{},'code_sources':{},'artifacts':self.files,'artifact_directory':'research/artifacts/market-forecast/job/ashare','limitations':[],
            'preparation_sha256':self.files['preparation.json'],'training_sha256':self.files['training.json'],'prediction_sha256':self.files['predictions.json'],
            'labels_sha256':self.files['evaluation_labels.json'],'created_at':'2026-10-30T00:00:00Z'}
        self.record['run_id']='forecast-'+stable_hash({k:self.record[k] for k in ('dataset_sha256','preparation_sha256','training_sha256','prediction_sha256','labels_sha256')})
        self.path=self.folder/(self.record['run_id']+'.json');self.save()

    def tearDown(self):self.tmp.cleanup()
    def save(self):self.path.write_text(json.dumps({'sha256':stable_hash(self.record),'record':self.record}),encoding='utf8')
    def store(self):
        from platform_app.adapters.forecast_store import ForecastStore
        return ForecastStore(self.folder,self.project)

    def test_verified_read_only_api_and_missing_artifact_history(self):
        store=self.store();client=TestClient(create_app(forecast_store=store))
        self.assertEqual(client.get('/api/v1/forecasts/runs').json()[0]['run_id'],self.record['run_id'])
        response=client.get('/api/v1/forecasts/runs/'+self.record['run_id']);self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['artifact_status'],'verified');self.assertEqual(client.post('/api/v1/forecasts/train',json={}).status_code,404)
        (self.artifact/'training.json').unlink()
        self.assertEqual(store.get(self.record['run_id'])['artifact_status'],'missing')

    def test_tampering_identity_and_artifact_escape_are_rejected(self):
        store=self.store();(self.artifact/'training.json').write_text('changed')
        with self.assertRaises(DomainConflict):store.get(self.record['run_id'])
        (self.artifact/'training.json').write_text('{}');self.record['artifact_directory']='../elsewhere';self.save()
        with self.assertRaises(DomainConflict):store.get(self.record['run_id'])
        self.record['artifact_directory']='research/artifacts/market-forecast/job/ashare';self.record['run_id']='forecast-'+'a'*64;self.save()
        with self.assertRaises(DomainConflict):store.get(self.path.stem)
        with self.assertRaises(KeyError):store.get('../private')

    def test_nonfinite_metrics_do_not_become_successful_model_results(self):
        self.record['models']['zero']['evaluation']['rmse']=float('nan')
        with self.assertRaises(ValueError):self.save()


if __name__=='__main__':unittest.main()
