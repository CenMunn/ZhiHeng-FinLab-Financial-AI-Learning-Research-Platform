import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research.filing_development.pipeline import project_development, validate_predictions
from research.filing_development.evidence import build_case, candidate_options
from research.filing_development.model import SYSTEM, build_prompt
from research.market.common import file_sha, digest
from research.filing_development import pipeline


class ProjectionTests(unittest.TestCase):
    def test_sealed_design_and_config_are_distinct_registered_identities(self):
        sealed_path = pipeline.ROOT/'sealed-evaluation/test/manifest.json'
        sealed = {'content_accessed': False, 'design_sha256': 'd'*64, 'config_sha256': 'c'*64,
                  'artifacts': {pipeline.rel(sealed_path.parent/'source.pdf'): 'a'*64}}
        human = {'completed': 0, 'item_count': 18, 'status': 'pending_human_review', 'artifacts': {'guide.md': 'e'*64}}
        def sha(path):
            return 'c'*64 if path == pipeline.CONFIG else 'd'*64 if Path(path).name.endswith('-design.md') else 'b'*64
        with patch.object(pipeline, 'read', side_effect=lambda path: human if Path(path) == pipeline.HUMAN else sealed), \
                patch.object(pipeline, 'file_sha', side_effect=sha), patch.object(pipeline, 'verify_files'):
            pipeline.preparation_artifacts(sealed_path)
            for key in ('config_sha256', 'design_sha256'):
                original = sealed[key]; sealed[key] = '0'*64
                with self.assertRaises(ValueError):
                    pipeline.preparation_artifacts(sealed_path)
                sealed[key] = original

    def test_projection_does_not_open_any_evaluation_page_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); docs = []
            for symbol in ('600519', '600036', '600585'):
                path = root/(symbol+'.json')
                path.write_text(json.dumps({'pdf_sha256': 'a'*64, 'pages': ['单位：元 币种：人民币\n营业收入 100 90']+['']*5}), 'utf8')
                docs.append({'doc_id': symbol+'-2024Q1', 'symbol': symbol, 'title': '合成', 'period': '2024Q1',
                             'split': 'development', 'pdf_sha256': 'a'*64, 'pages_path': path.name, 'pages_sha256': file_sha(path)})
                docs.append({'doc_id': symbol+'-2025Q1', 'symbol': symbol, 'period': '2025Q1',
                             'split': 'evaluation', 'pages_path': 'DO_NOT_OPEN_EVALUATION.json'})
            public = project_development({'documents': docs}, root)
            self.assertEqual(len(public['documents']), 3)
            self.assertEqual(len(public['cases']), 9)
            self.assertNotIn('2025', json.dumps(public))
            path.write_text('{}', 'utf8')
            with self.assertRaises(ValueError):
                project_development({'documents': docs}, root)


class PredictionValidationTests(unittest.TestCase):
    def fixture(self):
        docs = [{'doc_id': s+'-2024Q1', 'symbol': s, 'title': '合成季报', 'period': '2024Q1', 'split': 'development',
                 'pdf_sha256': 'a'*64, 'pages': [{'page': i, 'text': '单位：元 币种：人民币\n营业收入 100 90\n归属于上市公司股东的净利润 20 19\n经营活动产生的现金流量净额 10 8' if i == 1 else ''} for i in range(1, 7)]} for s in ('600519', '600036', '600585')]
        cases = [build_case(doc, metric) for doc in docs for metric in ('revenue', 'net_profit_parent', 'operating_cashflow')]
        inputs = {'documents': docs, 'cases': cases}
        rows = []
        for case in cases:
            field = case['candidates'][0]['field']; raw = candidate_options(case)[0]
            prompt = {'system': SYSTEM, 'user': build_prompt(case)}
            rows.append({'case_id': case['case_id'], 'doc_id': case['doc_id'], 'metric': case['metric'], 'method': 'single_constrained',
                         'status': 'ok', 'field': field, 'raw_output': raw, 'prompt': prompt, 'prompt_sha256': digest(prompt),
                         'allowed_options_sha256': digest(candidate_options(case))})
        return {'method': 'single_constrained', 'inputs_sha256': 'b'*64, 'model_manifest_sha256': 'c'*64, 'predictions': rows}, inputs

    def test_saved_field_and_registered_option_must_match_raw_and_prompt(self):
        body, inputs = self.fixture()
        validate_predictions(body, inputs, 'b'*64, 'c'*64)
        mutations = [('field', {**body['predictions'][0]['field'], 'value': '999'}),
                     ('prompt_sha256', 'd'*64), ('raw_output', '{}')]
        for key, value in mutations:
            changed = json.loads(json.dumps(body)); changed['predictions'][0][key] = value
            with self.assertRaises(ValueError):
                validate_predictions(changed, inputs, 'b'*64, 'c'*64)
        changed = json.loads(json.dumps(body)); changed['predictions'].pop()
        with self.assertRaises(ValueError):
            validate_predictions(changed, inputs, 'b'*64, 'c'*64)

    def test_frozen_input_and_model_binding_must_not_be_rebased(self):
        body, inputs = self.fixture()
        for input_sha, model_sha in [('d'*64, 'c'*64), ('b'*64, 'd'*64)]:
            with self.assertRaises(ValueError):
                validate_predictions(body, inputs, input_sha, model_sha)


class ModelPublicationTests(unittest.TestCase):
    def test_changed_model_assets_stop_publication_before_reference_is_read(self):
        p = {'inputs_sha256': 'b'*64, 'model_manifest_path': 'model/manifest.json',
             'model_manifest_sha256': 'c'*64, 'reference_path': 'development-reference.json'}
        run = Path('synthetic-run')
        frozen = {'protocol_sha256': digest(p), 'files': {m: 'a'*64 for m in pipeline.METHODS}}
        def fake_read(path):
            path = Path(path)
            if path.name == 'frozen-predictions.json': return frozen
            if path.name.endswith('-predictions.json'): return {'method': path.name.split('-predictions')[0]}
            raise AssertionError('Reference/result content must not be read after a model verification failure')
        with patch.object(pipeline, 'verify_run', return_value=(p, {})), patch.object(pipeline, 'read', side_effect=fake_read), \
                patch.object(pipeline, 'file_sha', return_value='a'*64), patch.object(pipeline, 'tokenizer_for'), \
                patch.object(pipeline, 'validate_predictions'), \
                patch.object(pipeline, 'verify_model', side_effect=ValueError('model asset changed'), create=True):
            with self.assertRaisesRegex(ValueError, 'model asset changed'):
                pipeline.publish(run)


if __name__ == '__main__':
    unittest.main()
