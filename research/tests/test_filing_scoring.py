import copy,unittest
from research.filing_extraction.score import score_field,summarize

class FilingScoringTests(unittest.TestCase):
 def fixture(self):
  quote='营业收入 1,234.50'
  pred={'metric':'revenue','value':'1234.50','unit':'百万元','currency':'CNY','period':'2025Q1','scope':'consolidated','page':2,'quote':quote}
  ref={'status':'verified','variants':[dict(pred,scope_evidence_pages=[2],unit_evidence_pages=[2])],'input_context_complete':True,'notes':''}
  doc={'pages':[{'page':1,'text':'2025年第一季度报告'},{'page':2,'text':'本集团 单位：人民币百万元 本期 上期\n'+quote+' 1200.00\n总净利润 50.00'}]}
  return pred,ref,doc
 def test_exact_decimal_and_grounded_full_record(self):
  p,r,d=self.fixture();self.assertTrue(score_field(p,r,d,'revenue','ok')['complete'])
  p['value']='1234500000';p['unit']='元'
  result=score_field(p,r,d,'revenue','ok');self.assertTrue(result['numeric']);self.assertFalse(result['unit']);self.assertFalse(result['complete'])
 def test_wrong_period_scope_currency_and_page_are_separate(self):
  for key,value in [('period','2024Q1'),('scope','parent'),('currency',None),('page',1)]:
   p,r,d=self.fixture();p[key]=value;result=score_field(p,r,d,'revenue','ok')
   self.assertTrue(result['numeric']);self.assertFalse(result['complete']);self.assertFalse(result['evidence' if key=='page' else key])
 def test_quote_must_occur_and_support_label_and_number(self):
  for quote in ('本集团','总净利润 50.00','营业收入 999.00','这是营业收入1,234.50'):
   p,r,d=self.fixture();p['quote']=quote;self.assertFalse(score_field(p,r,d,'revenue','ok')['evidence'])
 def test_paired_precision_variant_cannot_cross_pages(self):
  p,r,d=self.fixture();r['variants'].append(dict(p,value='1235',page=1,quote='营业收入 1235'))
  d['pages'][0]['text']+='\n营业收入 1235';p['value']='1235'
  self.assertFalse(score_field(p,r,d,'revenue','ok')['complete'])
 def test_zero_is_answer_and_null_is_abstention(self):
  p,r,d=self.fixture();p.update(value='0',quote='营业收入 0');r['variants']=[dict(p)];d['pages'][1]['text']='营业收入 0'
  self.assertTrue(score_field(p,r,d,'revenue','ok')['complete']);p['value']=None
  self.assertFalse(score_field(p,r,d,'revenue','ok')['answered'])
  r.update(status='unavailable',variants=[])
  self.assertTrue(score_field(p,r,d,'revenue','ok')['correct_abstention'])
 def test_invalid_status_and_nonfinite_cannot_be_success(self):
  p,r,d=self.fixture();self.assertFalse(score_field(p,r,d,'revenue','invalid_output')['complete'])
  p['value']='NaN';self.assertFalse(score_field(p,r,d,'revenue','ok')['answered'])
 def test_fixed_denominator_keeps_abstention_and_bad_output(self):
  p,r,d=self.fixture();ok=score_field(p,r,d,'revenue','ok');bad=score_field(None,r,d,'revenue','invalid_output')
  rows=[{'split':'evaluation','method':'model','checks':c,'reference':r} for c in (ok,bad,bad)]
  metrics=summarize(rows)[0];self.assertEqual((metrics['total'],metrics['complete_correct'],metrics['abstained']),(3,1,2))
 def test_unrelated_number_in_real_quote_is_not_field_evidence(self):
  p,r,d=self.fixture();p.update(value='20',unit='元',quote='营业收入 10（上年） 其他收入 20。')
  r['variants']=[dict(p,quote='营业收入 20（本期）')];d['pages'][1]['text']=p['quote']+'\n营业收入 20（本期）'
  result=score_field(p,r,d,'revenue','ok');self.assertTrue(result['numeric']);self.assertFalse(result['evidence']);self.assertFalse(result['complete'])
 def test_same_value_in_wrong_period_context_is_not_valid_quote(self):
  p,r,d=self.fixture();p.update(value='20',unit='元',quote='上年营业收入 20')
  r['variants']=[dict(p,quote='本期营业收入 20')];d['pages'][1]['text']='上年营业收入 20\n本期营业收入 20'
  self.assertFalse(score_field(p,r,d,'revenue','ok')['evidence'])
  p['quote']='营业收入 20'
  self.assertFalse(score_field(p,r,d,'revenue','ok')['evidence'])
  p['quote']='本期营业收入 20'
  self.assertTrue(score_field(p,r,d,'revenue','ok')['evidence'])

