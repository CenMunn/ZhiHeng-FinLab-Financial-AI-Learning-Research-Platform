from pathlib import Path
from contextlib import closing
import sqlite3
import tempfile
import unittest

from test_receivables import fixture


class ScenarioTests(unittest.TestCase):
    def setUp(self):
        from platform_app.adapters.scenario_store import ScenarioStore
        from platform_app.evidence.service import CaseService
        from platform_app.risk.scenario_service import ScenarioService
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"scenarios.sqlite3"
        self.store=ScenarioStore(self.path)
        self.case=fixture()
        self.service=ScenarioService(CaseService((self.case,)),self.store)

    def tearDown(self): self.tmp.cleanup()

    def request(self,delay="15",title="回款延迟15天",**extra):
        from platform_app.contracts.models import SaveScenarioRequest
        from platform_app.contracts.models import DelayAssumptions
        from platform_app.risk.receivables import calculate_delay
        assumptions=DelayAssumptions(credit_share="0.8",delay_days=delay)
        return SaveScenarioRequest(snapshot_id=self.case.snapshot_id,expected_snapshot_sha256=self.case.snapshot_sha256,
            assumptions=assumptions,expected_input_hash=calculate_delay(self.case,assumptions).input_hash,title=title,**extra)

    def test_save_reopen_and_canonical_retry(self):
        first=self.service.save(self.request(),"key-1")
        again=self.service.save(self.request(delay="15.00"),"key-1")
        self.assertFalse(first.replayed);self.assertTrue(again.replayed)
        self.assertEqual(first.scenario,again.scenario)
        self.assertEqual(self.service.get(first.scenario.scenario_id),first.scenario)
        self.assertEqual(first.scenario.result.occupancy_change,"120000.00")
        self.assertEqual(len(self.service.list()),1)

    def test_key_conflict_and_project_scope(self):
        from platform_app.contracts.errors import DomainConflict
        first=self.service.save(self.request(),"key-1")
        for changed in (self.request(delay="20"),self.request(title="改名")):
            with self.assertRaises(DomainConflict): self.service.save(changed,"key-1")
        other=self.service.save(self.request(),"key-1",project_id="another")
        self.assertNotEqual(first.scenario.scenario_id,other.scenario.scenario_id)
        self.assertEqual(len(self.service.list()),1)

    def test_missing_snapshot_mismatched_hash_and_forged_result(self):
        from platform_app.contracts.errors import DomainConflict
        from platform_app.contracts.models import SaveScenarioRequest
        from pydantic import ValidationError
        bad=self.request().model_dump(mode="json");bad["expected_snapshot_sha256"]="c"*64
        with self.assertRaises(DomainConflict): self.service.save(SaveScenarioRequest(**bad),"key-1")
        bad=self.request().model_dump(mode="json");bad["result"]={"occupancy_change":"1.00"}
        with self.assertRaises(ValidationError): SaveScenarioRequest(**bad)
        bad=self.request().model_dump(mode="json");bad["snapshot_id"]="unknown"
        with self.assertRaises(KeyError): self.service.save(SaveScenarioRequest(**bad),"key-1")

    def test_transaction_rolls_back_when_idempotency_insert_fails(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER block_save BEFORE INSERT ON idempotency BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.service.save(self.request(),"key-1")
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM scenarios").fetchone()[0],0)

    def test_old_result_and_retry_survive_case_service_replacement(self):
        from platform_app.evidence.service import CaseService
        from platform_app.risk.scenario_service import ScenarioService
        saved=self.service.save(self.request(),"key-1")
        restarted=ScenarioService(CaseService(()),self.store)
        self.assertEqual(restarted.get(saved.scenario.scenario_id).result.occupancy_change,"120000.00")
        self.assertEqual(restarted.save(self.request(),"key-1").scenario,saved.scenario)

    def test_invalid_key_does_not_create_record(self):
        for key in ("", "x"*129,"key\ninvalid"):
            with self.assertRaises(ValueError): self.service.save(self.request(),key)
        self.assertEqual(self.service.list(),())


if __name__ == "__main__": unittest.main()
