import unittest
from research.filing_extraction.rules import extract_document

class FilingRuleTests(unittest.TestCase):
 def doc(self,text):return {'doc_id':'600036-2025Q1','symbol':'600036','title':'2025年第一季度报告','period':'2025Q1','split':'evaluation','pdf_sha256':'a'*64,'pages':[{'page':1,'text':text}]}
 def test_million_parentheses_current_column_and_aliases(self):
  doc=self.doc('本集团 2025年1-3月 上年同期（人民币百万元）\n营业收入 2,100 2,200\n归属于本行股东的净利润 800 900\n经营活动产生的现金流量净额 (123,456) 12,000')
  result=extract_document(doc);rows={r['metric']:r for r in result['fields']}
  self.assertEqual(rows['revenue']['value'],'2100');self.assertEqual(rows['operating_cashflow']['value'],'-123456')
  self.assertEqual(rows['net_profit_parent']['unit'],'百万元');self.assertEqual(rows['revenue']['period'],'2025Q1')
 def test_no_unit_or_wrong_profit_name_is_not_invented(self):
  rows=extract_document(self.doc('营业收入 100\n净利润 50'))['fields']
  self.assertTrue(all(x['value'] is None for x in rows))
 def test_zero_and_parent_company_only(self):
  rows=extract_document(self.doc('单位：元 币种：人民币\n营业收入 0.00 10.00'))['fields'];self.assertEqual(rows[0]['value'],'0.00')
  rows=extract_document(self.doc('母公司利润表 单位：元 币种：人民币\n营业收入 100.00 10.00'))['fields'];self.assertIsNone(rows[0]['value'])
 def test_negative_decimal_and_quoted_source(self):
  result=extract_document(self.doc('单位：人民币万元\n经营活动产生的现金流量净额 -12.30 9.0'))
  row=next(x for x in result['fields'] if x['metric']=='operating_cashflow');self.assertEqual(row['value'],'-12.30');self.assertIn('-12.30',row['quote'])
 def test_declared_footnote_is_not_negative_amount_and_per_share_unit_is_local(self):
  doc=self.doc('本集团（人民币百万元，特别注明除外）\n营业收入 100 90\n基本每股收益(人民币元)(1) 1.2 1.1\n经营活动产生的现金流量净额 (2) (1,234) (2,345)\n注：\n(2) 经营现金流量变动说明')
  row=next(x for x in extract_document(doc)['fields'] if x['metric']=='operating_cashflow')
  self.assertEqual((row['value'],row['unit']),('-1234','百万元'));self.assertIn('(1,234)',row['quote'])
 def test_nonrecurring_adjusted_profit_is_not_parent_net_profit(self):
  result=extract_document(self.doc('单位：元 币种：人民币\n扣除非经常性损益后归属于本行股东的净利润 100 90'))
  self.assertIsNone(next(x for x in result['fields'] if x['metric']=='net_profit_parent')['value'])

