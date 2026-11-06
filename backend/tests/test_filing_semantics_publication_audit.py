"""Source-backed D31 tamper challenges; temporary copies never alter live data."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from platform_app.adapters.filing_semantics_store import FilingSemanticsStore, sha
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash

PROJECT = Path(__file__).resolve().parents[2]
PUBLICATION = Path('backend/data/filing-semantics/filingsem-03152f928655832e3dc3f37c0a3395ca17d1c724bf95ffe0e1261fd8c7a19995.json')


@unittest.skipUnless((PROJECT/PUBLICATION).exists(), 'Archived D31 development publication unavailable')
class PublicationTamperAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.body = json.loads((PROJECT/PUBLICATION).read_text('utf8'))['record']
        for name in {**self.body['artifacts'], **self.body['sources']}:
            target = self.root/name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT/name, target)
        self.store = FilingSemanticsStore(self.root/'backend/data/filing-semantics', self.root)
        self.publish(self.body)
        self.assertEqual(self.store.get()['artifact_status'], 'verified')

    def publish(self, body):
        folder = self.root/PUBLICATION.parent
        folder.mkdir(parents=True, exist_ok=True)
        path = self.root/PUBLICATION
        path.write_text(json.dumps({'record':body, 'sha256':stable_hash(body)}, ensure_ascii=False), 'utf8')
        (folder/'latest.json').write_text(json.dumps({'studies':{'development':{'file':path.name,'sha256':sha(path)}},'updated_at':'audit'}), 'utf8')

    def test_runtime_is_bound_to_frozen_model_prediction(self):
        changed = copy.deepcopy(self.body)
        changed['model_details']['runtime']['parameters'] = 999
        changed['model_details']['revision'] = 'forged-revision'
        self.publish(changed)
        with self.assertRaises(DomainConflict):
            self.store.get()

    def test_method_description_and_limitations_cannot_claim_training(self):
        changed = copy.deepcopy(self.body)
        changed['methods'][1]['description'] = 'Expert-audited fine-tuning with independently proven reasoning gains'
        changed['limitations'] = ['No limitations; expert gold labels']
        self.publish(changed)
        with self.assertRaises(DomainConflict):
            self.store.get()

    def test_reference_in_rehashed_scoring_is_bound_to_original_reference(self):
        changed = copy.deepcopy(self.body)
        changed['rows'][0]['reference']['variants'][0]['value'] = '999'
        scored_name = 'research/artifacts/filing-semantics/runs/'+changed['run_id']+'/scored.json'
        scored_path = self.root/scored_name
        scored = json.loads(scored_path.read_text('utf8'))
        scored['rows'] = changed['rows']
        scored_path.write_text(json.dumps(scored, ensure_ascii=False), 'utf8')
        changed['artifacts'][scored_name] = sha(scored_path)
        self.publish(changed)
        with self.assertRaises(DomainConflict):
            self.store.get()

    def test_rehashed_checks_are_recomputed_from_original_prediction_and_reference(self):
        changed = copy.deepcopy(self.body)
        changed['rows'][0]['checks']['numeric'] = False
        changed['rows'][0]['checks']['complete'] = False
        method = changed['rows'][0]['method']
        metric = next(m for m in changed['metrics'] if m['method']==method)
        metric['numeric_correct'] -= 1
        metric['complete_correct'] -= 1
        scored_name = 'research/artifacts/filing-semantics/runs/'+changed['run_id']+'/scored.json'
        scored_path = self.root/scored_name
        scored = json.loads(scored_path.read_text('utf8'))
        scored['rows'], scored['metrics'] = changed['rows'], changed['metrics']
        scored_path.write_text(json.dumps(scored, ensure_ascii=False), 'utf8')
        changed['artifacts'][scored_name] = sha(scored_path)
        self.publish(changed)
        with self.assertRaises(DomainConflict):
            self.store.get()

    def test_rehashed_error_reasons_agree_with_original_checks(self):
        changed = copy.deepcopy(self.body)
        changed['rows'][0]['error_reasons'] = ['invented_financial_failure']
        scored_name = 'research/artifacts/filing-semantics/runs/'+changed['run_id']+'/scored.json'
        scored_path = self.root/scored_name
        scored = json.loads(scored_path.read_text('utf8'))
        scored['rows'] = changed['rows']
        scored_path.write_text(json.dumps(scored, ensure_ascii=False), 'utf8')
        changed['artifacts'][scored_name] = sha(scored_path)
        self.publish(changed)
        with self.assertRaises(DomainConflict):
            self.store.get()

    def test_row_token_and_latency_metadata_match_original_prediction(self):
        changed = copy.deepcopy(self.body)
        row = next(r for r in changed['rows'] if r['method']=='structure_model')
        row['input_tokens'], row['output_tokens'], row['latency_seconds'] = 1, 1, 0
        scored_name = 'research/artifacts/filing-semantics/runs/'+changed['run_id']+'/scored.json'
        scored_path = self.root/scored_name
        scored = json.loads(scored_path.read_text('utf8'))
        scored['rows'] = changed['rows']
        scored_path.write_text(json.dumps(scored, ensure_ascii=False), 'utf8')
        changed['artifacts'][scored_name] = sha(scored_path)
        self.publish(changed)
        with self.assertRaises(DomainConflict):
            self.store.get()


if __name__ == '__main__':
    unittest.main()
