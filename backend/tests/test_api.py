from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from test_case_adapter import source_fixture


class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from platform_app.api.app import create_app
        from platform_app.adapters.corporate_risk import load_huitian_2025
        from platform_app.adapters.scenario_store import ScenarioStore
        from platform_app.evidence.service import CaseService
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        source,self.pdf,_=source_fixture(self.root)
        self.case=load_huitian_2025(source,self.root)
        self.db=self.root/"scenarios.sqlite3"
        app=create_app(cases=CaseService((self.case,)),store=ScenarioStore(self.db),corporate_root=self.root)
        self.client=TestClient(app,raise_server_exceptions=False)
        self.body={"snapshot_id":self.case.snapshot_id,"expected_snapshot_sha256":self.case.snapshot_sha256,
                   "assumptions":{"credit_share":"0.8","delay_days":"15"}}

    def tearDown(self): self.client.close();self.tmp.cleanup()

    def save_body(self, **updates):
        body={**self.body,**updates}
        calculation=self.client.post('/api/v1/risk/receivables-delay',json={key:value for key,value in body.items() if key!='title'}).json()
        return {**body,'expected_input_hash':calculation['input_hash']}

    def test_health_case_and_calculation(self):
        self.assertEqual(self.client.get('/api/v1/health').status_code,200)
        self.assertEqual(len(self.client.get('/api/v1/cases').json()),1)
        self.assertEqual(self.client.get('/api/v1/cases/'+self.case.snapshot_id).json()['revenue'],'2103585508.31')
        response=self.client.post('/api/v1/risk/receivables-delay',json=self.body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['occupancy_change'],'69158975.62')

    def test_strict_requests_version_conflict_and_not_found(self):
        response=self.client.post('/api/v1/risk/receivables-delay',json={**self.body,"revenue":"1"})
        self.assertEqual(response.status_code,422)
        response=self.client.post('/api/v1/risk/receivables-delay',json={**self.body,"assumptions":{"credit_share":0.8,"delay_days":"15"}})
        self.assertEqual(response.status_code,422)
        response=self.client.post('/api/v1/risk/receivables-delay',json={**self.body,"expected_snapshot_sha256":"a"*64})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['code'],'snapshot_changed')
        self.assertEqual(self.client.get('/api/v1/cases/unknown').status_code,404)

    def test_save_replay_list_and_reopen(self):
        body=self.save_body(title="情景A");headers={'Idempotency-Key':'api-key-1'}
        first=self.client.post('/api/v1/scenarios',json=body,headers=headers)
        self.assertEqual(first.status_code,201)
        again=self.client.post('/api/v1/scenarios',json=body,headers=headers)
        self.assertEqual(again.status_code,200)
        self.assertEqual(first.json(),again.json())
        self.assertEqual(len(self.client.get('/api/v1/scenarios').json()),1)
        self.assertEqual(self.client.get('/api/v1/scenarios/'+first.json()['scenario_id']).json(),first.json())
        changed=self.client.post('/api/v1/scenarios',json={**body,'title':'情景B'},headers=headers)
        self.assertEqual(changed.status_code,409)

    def test_invalid_save_key_and_storage_failure(self):
        body=self.save_body(title='情景A')
        self.assertEqual(self.client.post('/api/v1/scenarios',json=body).status_code,422)
        with closing(sqlite3.connect(self.db)) as connection,connection:
            connection.execute("CREATE TRIGGER block_save BEFORE INSERT ON idempotency BEGIN SELECT RAISE(ABORT,'failure'); END")
        failed=self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'api-key-1'})
        self.assertEqual(failed.status_code,500)
        self.assertEqual(failed.json()['code'],'storage_error')
        self.assertNotIn(str(self.root),failed.text)
        self.assertEqual(self.client.get('/api/v1/scenarios').json(),[])

    def test_registered_pdf_integrity_and_path_isolation(self):
        source_url='/api/v1/sources/1225240687?expected_sha256='+self.case.evidence.source_sha256
        response=self.client.get(source_url)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.headers['content-type'].startswith('application/pdf'))
        self.pdf.write_bytes(b'changed')
        self.assertEqual(self.client.get(source_url).status_code,409)
        self.assertEqual(self.client.get('/api/v1/sources/unregistered?expected_sha256='+self.case.evidence.source_sha256).status_code,404)

    def test_old_saved_source_never_serves_new_registered_bytes(self):
        import hashlib
        from fastapi.testclient import TestClient
        from platform_app.api.app import create_app
        from platform_app.adapters.scenario_store import ScenarioStore
        from platform_app.evidence.service import CaseService
        old_sha=self.case.evidence.source_sha256
        self.pdf.write_bytes(b'%PDF-new registered version')
        new_sha=hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        updated=self.case.model_copy(update={'evidence':self.case.evidence.model_copy(update={'source_sha256':new_sha})})
        path='/api/v1/sources/1225240687'
        with TestClient(create_app(cases=CaseService((updated,)),store=ScenarioStore(self.db),corporate_root=self.root)) as client:
            self.assertEqual(client.get(path,params={'expected_sha256':old_sha}).status_code,409)
            self.assertEqual(client.get(path+'/status',params={'expected_sha256':old_sha}).json()['status'],'changed')
            self.assertEqual(client.get(path+'/status',params={'expected_sha256':new_sha}).json()['status'],'available')
            self.assertEqual(client.get(path,params={'expected_sha256':new_sha}).content,self.pdf.read_bytes())
            self.pdf.unlink()
            self.assertEqual(client.get(path+'/status',params={'expected_sha256':old_sha}).json()['status'],'missing')
            self.assertEqual(client.get(path,params={'expected_sha256':old_sha}).status_code,404)
            self.assertEqual(client.get(path).status_code,422)

    def test_authoritative_comparison_baseline_saved_reference_and_version_guard(self):
        body=self.save_body(title='参照情景',assumptions={'credit_share':'0.5','delay_days':'15'})
        saved=self.client.post('/api/v1/scenarios',json=body,headers={'Idempotency-Key':'compare-ref'}).json()
        baseline=self.client.post('/api/v1/risk/receivables-compare',json=self.body)
        self.assertEqual(baseline.status_code,200)
        self.assertEqual(baseline.json()['difference'],baseline.json()['current']['occupancy_change'])
        compared=self.client.post('/api/v1/risk/receivables-compare',json={**self.body,'reference_scenario_id':saved['scenario_id']})
        self.assertEqual(compared.status_code,200)
        self.assertEqual(compared.json()['reference_title'],'参照情景')
        self.assertEqual(compared.json()['difference'],'25934615.86')
        import json
        payload=saved.copy();payload['result']['engine_version']='different-engine'
        with closing(sqlite3.connect(self.db)) as connection,connection:
            connection.execute('UPDATE scenarios SET payload_json=? WHERE scenario_id=?',(json.dumps(payload),saved['scenario_id']))
        self.assertEqual(self.client.post('/api/v1/risk/receivables-compare',json={**self.body,'reference_scenario_id':saved['scenario_id']}).status_code,409)

    def test_history_survives_missing_or_invalid_current_source_configuration(self):
        from fastapi.testclient import TestClient
        from platform_app.api.app import create_app
        from platform_app.adapters.scenario_store import ScenarioStore
        from platform_app.adapters.corporate_risk import SOURCE_JSON_RELATIVE
        saved=self.client.post('/api/v1/scenarios',json=self.save_body(title='保留情景'),headers={'Idempotency-Key':'history'}).json()
        for invalid in (None,'{broken','{"queries":{"workspace_cases":{"rows":[null]}}}'):
            if invalid:
                source=self.root/SOURCE_JSON_RELATIVE
                source.parent.mkdir(parents=True,exist_ok=True)
                source.write_text(invalid,encoding='utf-8')
            else:
                (self.root/SOURCE_JSON_RELATIVE).unlink(missing_ok=True)
            with TestClient(create_app(store=ScenarioStore(self.db),corporate_root=self.root)) as client:
                self.assertEqual(client.get('/api/v1/health').json()['source_status'],'unavailable')
                self.assertEqual(client.get('/api/v1/cases').json(),[])
                self.assertEqual(client.get('/api/v1/scenarios/'+saved['scenario_id']).json(),saved)
                self.assertEqual(client.post('/api/v1/scenarios',json=self.save_body(title='保留情景'),headers={'Idempotency-Key':'history'}).json(),saved)

    def test_save_rejects_displayed_calculation_version_mismatch(self):
        body=self.save_body(title='版本保护')
        response=self.client.post('/api/v1/scenarios',json={**body,'expected_input_hash':'a'*64},headers={'Idempotency-Key':'old-result'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['code'],'calculation_changed')
        self.assertEqual(self.client.get('/api/v1/scenarios').json(),[])


if __name__ == '__main__': unittest.main()
