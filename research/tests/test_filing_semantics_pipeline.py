import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class BoundaryTests(unittest.TestCase):
    def test_prediction_bytes_cannot_be_reapproved_by_method_freeze(self):
        from research.filing_semantics.pipeline import verify_prediction_files
        from research.market.common import file_sha,digest
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p={'inputs_sha256':'a'*64}
            files={}
            for method in ('structure_rule','structure_model'):
                path=root/(method+'-predictions.json');path.write_text('{}','utf8');files[method]=file_sha(path)
            receipt=root/'model-verification.json';receipt.write_text('{}','utf8')
            frozen={'protocol_sha256':digest(p),'inputs_sha256':'a'*64,'files':files,'model_verification_sha256':file_sha(receipt)}
            (root/'frozen-predictions.json').write_text(json.dumps(frozen),'utf8')
            verify_prediction_files(root,p)
            (root/'structure_model-predictions.json').write_text('CHANGED AFTER SCORE','utf8')
            with self.assertRaises(ValueError):verify_prediction_files(root,p)
            (root/'structure_model-predictions.json').write_text('{}','utf8');receipt.write_text('[]','utf8')
            with self.assertRaises(ValueError):verify_prediction_files(root,p)

    def test_evaluation_is_closed_until_verified_method_freeze(self):
        from research.filing_semantics.corpus import require_evaluation_gate
        with self.assertRaisesRegex(ValueError, 'freeze'):
            require_evaluation_gate(None)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'freeze.json'; p.write_text('{}', 'utf8')
            with self.assertRaises(ValueError): require_evaluation_gate(p)

    def test_body_identity_requires_code_issuer_and_period_not_child_company(self):
        from research.filing_semantics.corpus import qualify_identity
        d = {'symbol':'601318','name':'中国平安','period':'2025Q1'}
        good = '证券代码：601318 中国平安保险（集团）股份有限公司 2025年第一季度报告'
        self.assertTrue(qualify_identity(d,good)['qualified'])
        for bad in ['证券代码：000001 平安银行股份有限公司 2025年第一季度报告',
                    '证券代码：601318 中国平安 2024年第一季度报告',
                    '证券代码：601318 中国平安 2025年第一季度报告摘要']:
            self.assertFalse(qualify_identity(d,bad)['qualified'])

    def test_json_options_have_identical_key_order_and_only_eligible_candidates(self):
        from research.filing_semantics.model import options
        field = dict(metric='revenue',value='100',unit='元',currency='CNY',period='2024Q1',scope='consolidated',page=1,quote='营业收入 100')
        case = {'metric':'revenue','candidates':[{'candidate_id':1,'field':field},{'candidate_id':2,'field':{**field,'value':'90'}}], 'eligible_ids':[1]}
        choices = options(case)
        self.assertEqual(len(choices),2)
        self.assertEqual([list(json.loads(c)) for c in choices],[list(field),list(field)])
        self.assertEqual([json.loads(c)['value'] for c in choices],['100',None])

    def test_prediction_validation_rejects_modified_raw_selection_and_prompt(self):
        from research.filing_semantics.model import options, prompt_for, validate_outputs
        field = dict(metric='revenue',value='100',unit='元',currency='CNY',period='2024Q1',scope='consolidated',page=1,quote='营业收入 100')
        case = {'case_id':'x/revenue','doc_id':'x','metric':'revenue','query':{'period':'2024Q1'},'candidates':[{'candidate_id':1,'field':field}], 'blocks':[], 'eligible_ids':[1]}
        row = {'case_id':case['case_id'],'field':field,'raw_output':options(case)[0], 'status':'ok','prompt':prompt_for(case),'options':options(case),'token_ids':[]}
        validate_outputs([row],[case])
        for key,value in [('field',{**field,'value':'999'}),('raw_output','{}'),('prompt',{})]:
            changed={**row,key:value}
            with self.assertRaises(ValueError): validate_outputs([changed],[case])

    def test_scoring_never_runs_before_prediction_freeze(self):
        from research.filing_semantics.pipeline import score
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises((ValueError,FileNotFoundError)):
                score(Path(tmp))

    def test_source_change_is_rejected_not_rebased(self):
        from research.filing_semantics.common import verify_map
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); p=root/'x.json';p.write_text('{}','utf8')
            from research.market.common import file_sha
            old={p.name:file_sha(p)};verify_map(old,project=root)
            p.write_text('[]','utf8')
            with self.assertRaises(ValueError): verify_map(old,project=root)
            with self.assertRaises(ValueError): verify_map({'../outside.json':'a'*64},project=root)

if __name__=='__main__': unittest.main()
