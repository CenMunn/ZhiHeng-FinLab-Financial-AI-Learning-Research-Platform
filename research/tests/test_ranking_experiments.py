import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest


class RankingTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('research.experiments.ranking')
        except ModuleNotFoundError:
            self.fail('Ranking experiment implementation missing')

    def row(self, split='train', q='A/2020/page_1.pdf-1'):
        return {'question_id': q, 'company_id': q.split('/')[0], 'annual_report_id': 'A/2020',
                'page_id': 'A/2020/page_1.pdf', 'split': split, 'question': 'operating cash flow',
                'candidate_scope': 'provided_page', 'serialization': 'finqa-header-aware-v1',
                'candidates': {'text_0': 'Operating cash 10', 'text_1': 'Investing cash 4', 'table_0': '2020 2019'},
                'bm25_top20': ['text_1', 'table_0', 'text_0']}

    def test_only_train_fit_ids_can_produce_pairs_and_gold_is_not_a_negative(self):
        m = self.module(); a = self.row(); b = self.row(q='B/2020/page_1.pdf-1')
        pairs = m.training_pairs([a,b], {a['question_id']: ['text_0'], b['question_id']: ['text_1']}, {a['question_id']}, 3)
        self.assertEqual(pairs, [(a['question_id'],'text_0',1.0),(a['question_id'],'text_1',0.0),(a['question_id'],'table_0',0.0)])
        with self.assertRaisesRegex(ValueError, 'train'):
            m.training_pairs([self.row(split='dev')], {a['question_id']: ['text_0']}, {a['question_id']}, 3)
        with self.assertRaises(ValueError):
            m.training_pairs([a], {a['question_id']: ['text_-1']}, {a['question_id']}, 3)

    def test_missing_recall_and_more_than_five_gold_remain_in_denominator(self):
        m=self.module(); a=self.row(split='dev'); b=self.row(split='dev',q='B/2020/page_1.pdf-1')
        b['candidates']={f'text_{i}':str(i) for i in range(6)}; b['bm25_top20']=list(b['candidates'])
        a['bm25_top20']=['text_1','table_0']
        labels={a['question_id']:['text_0'],b['question_id']:list(b['candidates'])}
        output=m.evaluate([a,b],labels,{a['question_id']:a['bm25_top20'],b['question_id']:b['bm25_top20']})
        self.assertEqual(output['summary']['questions'],2)
        self.assertEqual(output['summary']['coverage_at_5'],0)
        self.assertEqual(output['summary']['candidate_coverage_at_20'],.5)
        self.assertAlmostEqual(output['summary']['recall_at_5'],5/12)
        self.assertEqual(output['summary']['hit_at_5'],.5)
        self.assertEqual(output['summary']['gold_over_five'],1)
        self.assertEqual(output['summary']['conditional_coverage_at_5'],0)

    def test_rank_ties_are_stable_and_invalid_scores_or_injected_gold_are_rejected(self):
        m=self.module(); row=self.row()
        self.assertEqual(m.rerank(row,[1,1,2]),['text_0','text_1','table_0'])
        with self.assertRaises(ValueError): m.rerank(row,[float('nan'),0,1])
        with self.assertRaises(ValueError): m.rerank(row,[1])
        row['gold_ids']=['text_0']
        with self.assertRaisesRegex(ValueError,'whitelist'): m.validate_input(row,'train')

    def test_metrics_use_ideal_gold_and_count_absent_predictions_as_failure(self):
        m=self.module(); row=self.row(split='dev')
        out=m.evaluate([row],{row['question_id']:['text_0']},{row['question_id']:['text_1','text_0','table_0']})
        self.assertAlmostEqual(out['summary']['ndcg_at_5'],1/1.584962500721156)
        self.assertEqual(out['summary']['coverage_at_5'],1)
        failed=m.evaluate([row],{row['question_id']:['text_0']},{})
        self.assertEqual(failed['summary']['coverage_at_5'],0)
        self.assertEqual(failed['summary']['missing_predictions'],1)
        with self.assertRaises(ValueError): m.evaluate([row],{row['question_id']:['text_0']},{row['question_id']:['not_in_candidates']})

    def test_prediction_inputs_verify_hashes_and_never_require_labels(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder); (p/'inference').mkdir()
            f=p/'inference/dev.jsonl'; f.write_text(json.dumps(self.row(split='dev'))+'\n',encoding='utf8')
            (p/'manifest.json').write_text(json.dumps({'schema_version':'m2-preparation-v1','commit':m.COMMIT,
                'serialization':'finqa-header-aware-v1','test_content_accessed':False,'gold_added_to_inference_candidates':False,
                'outputs_sha256':{'inference/dev.jsonl':m.file_sha(f)}}),encoding='utf8')
            self.assertEqual(len(m.load_inputs(p,'dev')),1)
            f.write_text('{}\n')
            with self.assertRaisesRegex(ValueError,'hash'): m.load_inputs(p,'dev')
            with self.assertRaises(ValueError): m.load_inputs(p,'test')

    def test_company_bootstrap_is_paired_and_seed_reproducible(self):
        m=self.module()
        left=[{'question_id':'a','company_id':'A','coverage_at_5':0},{'question_id':'b','company_id':'A','coverage_at_5':0},{'question_id':'c','company_id':'B','coverage_at_5':0}]
        right=[{**row,'coverage_at_5':1} for row in left]
        first=m.paired_bootstrap(left,right,replicates=100,seed=42)
        self.assertEqual(first['difference'],1)
        self.assertEqual(first['ci95'],[1,1])
        self.assertEqual(first['groups'],2)
        self.assertEqual(first,m.paired_bootstrap(left,right,replicates=100,seed=42))
        right[0]['company_id']='OTHER'
        with self.assertRaises(ValueError): m.paired_bootstrap(left,right,replicates=100,seed=42)

    def test_json_sorted_keys_do_not_change_bm25_source_tie_order(self):
        m=self.module()
        row={'question':'cash','candidates':{'table_0':'unrelated','text_10':'unrelated','text_2':'unrelated','text_0':'unrelated'}}
        self.assertEqual(m.page_bm25(row),['text_0','text_2','text_10','table_0'])


if __name__=='__main__': unittest.main()
