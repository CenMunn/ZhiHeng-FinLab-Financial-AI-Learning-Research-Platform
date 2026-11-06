from copy import deepcopy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from fastapi.testclient import TestClient
from platform_app.api.app import create_app
from platform_app.adapters.experiment_store import ExperimentStore
from platform_app.adapters.scenario_store import ScenarioStore
from platform_app.evidence.service import CaseService

class ExperimentApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.path=root/'experiments.sqlite3';self.store=ExperimentStore(self.path)
        self.client=TestClient(create_app(cases=CaseService(()),store=ScenarioStore(root/'m1.sqlite3'),experiment_store=self.store),raise_server_exceptions=False)
        self.samples=self.client.get('/api/v1/experiments/snapshots').json()
        sample=self.samples[0]
        self.body={'snapshot_id':sample['snapshot_id'],'expected_snapshot_sha256':sample['snapshot_sha256'],'config':sample['default_config']}
    def tearDown(self):self.client.close();self.tmp.cleanup()

    def test_registry_and_new_store_stay_separate_from_original_business_data(self):
        self.assertEqual(len(self.samples),2)
        self.assertEqual(self.client.get('/api/v1/experiments/runs').json(),[])
        self.assertFalse(self.path.exists())
        self.assertEqual(self.client.get('/api/v1/experiments/snapshots/../../env').status_code,404)

    def test_both_samples_save_reopen_replay_and_preserve_full_snapshot(self):
        for sample in self.samples:
            body={'snapshot_id':sample['snapshot_id'],'expected_snapshot_sha256':sample['snapshot_sha256'],'config':sample['default_config']}
            response=self.client.post('/api/v1/experiments/foundation',json=body)
            self.assertEqual(response.status_code,201,response.text)
            record=response.json();run_id=record['run_id']
            self.assertEqual(record['snapshot']['source_kind'],'synthetic')
            self.assertEqual(record['result']['cost_example']['currency'],sample['currency'])
            self.assertEqual(record,self.client.get('/api/v1/experiments/runs/'+run_id).json())
            replay=self.client.post('/api/v1/experiments/foundation',json=body)
            self.assertEqual(replay.status_code,200);self.assertEqual(replay.json(),record)
        self.assertEqual(len(self.client.get('/api/v1/experiments/runs').json()),2)

    def test_input_changes_create_new_record_and_bad_hash_never_saves(self):
        first=self.client.post('/api/v1/experiments/foundation',json=self.body).json()
        changed=deepcopy(self.body);changed['config']['window']=4
        second=self.client.post('/api/v1/experiments/foundation',json=changed).json()
        self.assertNotEqual(first['run_id'],second['run_id'])
        bad={**self.body,'expected_snapshot_sha256':'a'*64}
        self.assertEqual(self.client.post('/api/v1/experiments/foundation',json=bad).status_code,409)
        self.assertEqual(len(self.client.get('/api/v1/experiments/runs').json()),2)

    def test_invalid_parameter_failures_leave_no_success_records(self):
        for change in [{'train_count':100},{'train_count':True},{'window':1},{'as_of':'2026-09-21T00:00:00'}]:
            body=deepcopy(self.body);body['config'].update(change)
            self.assertEqual(self.client.post('/api/v1/experiments/foundation',json=body).status_code,422)
        self.assertEqual(self.client.get('/api/v1/experiments/runs').json(),[])

    def test_valid_payload_cannot_be_substituted_under_another_run_key(self):
        first=self.client.post('/api/v1/experiments/foundation',json=self.body).json()
        changed=deepcopy(self.body);changed['config']['window']=4
        second=self.client.post('/api/v1/experiments/foundation',json=changed).json()
        with closing(sqlite3.connect(self.path)) as db,db:
            payload,digest=db.execute('SELECT payload,digest FROM experiment_runs WHERE run_id=?',(second['run_id'],)).fetchone()
            db.execute('UPDATE experiment_runs SET payload=?,digest=? WHERE run_id=?',(payload,digest,first['run_id']))
        self.assertEqual(self.client.get('/api/v1/experiments/runs/'+first['run_id']).status_code,409)
        self.assertEqual(self.client.get('/api/v1/experiments/runs').status_code,409)

    def test_corrupted_record_is_rejected_and_storage_failure_does_not_save(self):
        record=self.client.post('/api/v1/experiments/foundation',json=self.body).json()
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("UPDATE experiment_runs SET payload='{}'")
        self.assertEqual(self.client.get('/api/v1/experiments/runs/'+record['run_id']).status_code,409)
        self.assertEqual(self.client.get('/api/v1/experiments/runs').status_code,409)
        blocked=ExperimentStore(Path(self.tmp.name)/'directory');blocked.path.mkdir()
        self.assertRaises(sqlite3.Error,blocked.save,record['snapshot'],record['result'])

if __name__=='__main__':unittest.main()
