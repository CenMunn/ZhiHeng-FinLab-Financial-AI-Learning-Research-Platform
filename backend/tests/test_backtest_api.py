from contextlib import closing
from pathlib import Path
import json,sqlite3,tempfile,unittest
from fastapi.testclient import TestClient
from platform_app.api.app import create_app
from platform_app.contracts.models import stable_hash
from test_public_backtests import fixture,configuration


class BacktestApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)

    def tearDown(self):self.tmp.cleanup()

    def client(self,data):
        from platform_app.adapters.backtest_store import BacktestStore
        self.store=BacktestStore(self.root/'experiments.sqlite3')
        return TestClient(create_app(backtest_store=self.store,public_datasets=lambda:{data.snapshot.snapshot_id:data}))

    def test_compare_persist_replay_and_independent_history(self):
        data=fixture();client=self.client(data)
        request={'dataset_id':data.snapshot.snapshot_id,'expected_dataset_sha256':stable_hash(data.model_dump(mode='json')),'config':configuration(data).model_dump(mode='json')}
        first=client.post('/api/v1/backtests/compare',json=request)
        self.assertEqual(first.status_code,201,first.text)
        second=client.post('/api/v1/backtests/compare',json=request)
        self.assertEqual(second.status_code,200);self.assertEqual(second.json(),first.json())
        history=client.get('/api/v1/backtests/runs');self.assertEqual(len(history.json()),1)
        self.assertEqual(history.json()[0]['run_id'],first.json()['run_id'])
        standalone=TestClient(create_app(backtest_store=self.store,public_datasets=lambda:{}))
        self.assertEqual(standalone.get('/api/v1/backtests/runs/'+first.json()['run_id']).json(),first.json())

    def test_hash_conflict_validation_and_missing(self):
        data=fixture();client=self.client(data)
        req={'dataset_id':data.snapshot.snapshot_id,'expected_dataset_sha256':'a'*64,'config':configuration(data).model_dump(mode='json')}
        self.assertEqual(client.post('/api/v1/backtests/compare',json=req).status_code,409)
        req['config']['window']=True
        self.assertEqual(client.post('/api/v1/backtests/compare',json=req).status_code,422)
        self.assertEqual(client.get('/api/v1/backtests/runs/unknown').status_code,404)

    def test_new_public_run_does_not_break_empty_synthetic_history_in_shared_db(self):
        from platform_app.adapters.experiment_store import ExperimentStore
        data=fixture();client=self.client(data)
        body={'dataset_id':data.snapshot.snapshot_id,'expected_dataset_sha256':stable_hash(data.model_dump(mode='json')),'config':configuration(data).model_dump(mode='json')}
        self.assertEqual(client.post('/api/v1/backtests/compare',json=body).status_code,201)
        shared=TestClient(create_app(backtest_store=self.store,experiment_store=ExperimentStore(self.store.path),public_datasets=lambda:{}))
        self.assertEqual(shared.get('/api/v1/experiments/runs').status_code,200)
        self.assertEqual(shared.get('/api/v1/experiments/runs').json(),[])
        self.assertEqual(shared.get('/api/v1/experiments/runs/missing').status_code,404)

    def test_payload_tamper_and_lookup_id_binding(self):
        data=fixture();client=self.client(data)
        req={'dataset_id':data.snapshot.snapshot_id,'expected_dataset_sha256':stable_hash(data.model_dump(mode='json')),'config':configuration(data).model_dump(mode='json')}
        body=client.post('/api/v1/backtests/compare',json=req).json();run_id=body['run_id']
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute('UPDATE public_backtest_runs SET run_id=? WHERE run_id=?',('wrong-key',run_id));db.commit()
        self.assertEqual(client.get('/api/v1/backtests/runs/wrong-key').status_code,409)

    def test_raw_receipt_and_normalized_tamper_rejected(self):
        from platform_app.adapters.public_market import load_dataset
        data=fixture();body=data.model_dump(mode='json');body['snapshot']['snapshot_id']='ashare-600519-2018-2025'
        # The cache is registered only after all raw hashes match. No network in the loader.
        target=self.root/'ashare-600519-2018-2025.json'
        target.write_text(json.dumps({'sha256':stable_hash(body),'dataset':body}),encoding='utf8')
        with self.assertRaises(OSError):load_dataset(self.root,'ashare-600519-2018-2025')
        (self.root/'raw').mkdir();(self.root/'raw/test').write_bytes(b'changed raw response')
        with self.assertRaises(ValueError):load_dataset(self.root,'ashare-600519-2018-2025')
        self.assertEqual(load_dataset(self.root,'ashare-600519-2018-2025',verify_raw=False).snapshot.snapshot_id,'ashare-600519-2018-2025')
        body['snapshot']['bars'][0]['volume']='999'
        target.write_text(json.dumps({'sha256':'a'*64,'dataset':body}),encoding='utf8')
        with self.assertRaises(ValueError):load_dataset(self.root,'ashare-600519-2018-2025',verify_raw=False)


if __name__=='__main__':unittest.main()
