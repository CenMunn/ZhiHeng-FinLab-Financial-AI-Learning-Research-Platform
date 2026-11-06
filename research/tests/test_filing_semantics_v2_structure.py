import unittest
from research.tests.test_filing_semantics_structure import doc
from research.filing_semantics_v2.structure import build_cases

class V2Tests(unittest.TestCase):
 def test_inline_unit(self):
  d=doc([[(0,'币种：人民币')],[(200,'本报告期')],[(0,'营业收入（千元）'),(200,'2')]])
  self.assertEqual(build_cases(d)[0]['rule_field']['unit'],'千元')
 def test_numeric_year_header(self):
  d=doc([[(0,'单位：元 币种：人民币')],[(200,'2024'),(240,'年1-3月')],[(0,'营业收入'),(200,'2')]])
  self.assertEqual(build_cases(d)[0]['rule_field']['value'],'2')

 def test_dates_are_not_flow_headers(self):
  for header in ('2024年3月31日','2024','2024年12月31日'):
   d=doc([[(0,'单位：元 币种：人民币')],[(200,header)],[(0,'营业收入'),(200,'2')]])
   self.assertIsNone(build_cases(d)[0]['rule_field']['value'])
 def test_explicit_foreign_inline_refuses(self):
  d=doc([[(0,'币种：美元')],[(200,'本报告期')],[(0,'营业收入（千元）'),(200,'2')]])
  self.assertIsNone(build_cases(d)[0]['rule_field']['value'])
 def test_inline_percentage_per_share_refuses(self):
  for label in ('营业收入每股（元/股）','营业收入增长（%）'):
   d=doc([[(0,'单位：元 币种：人民币')],[(200,'本报告期')],[(0,label),(200,'2')]])
   self.assertIsNone(build_cases(d)[0]['rule_field']['value'])
 def test_conflicting_inline_units_refuses(self):
  d=doc([[(0,'币种：人民币')],[(200,'本报告期')],[(0,'营业收入（千元）（万元）'),(200,'2')]])
  self.assertIsNone(build_cases(d)[0]['rule_field']['value'])

 def test_inline_unit_does_not_leak(self):
  d=doc([[(0,'币种：人民币')],[(200,'本报告期')],[(0,'营业收入（千元）'),(200,'2')],[(0,'归属于上市公司股东的净利润'),(200,'3')]])
  self.assertIsNone(build_cases(d)[1]['rule_field']['value'])

 def test_inline_currency_does_not_leak(self):
  d=doc([[(200,'本报告期')],[(0,'营业收入（人民币千元）'),(200,'2')],[(0,'归属于上市公司股东的净利润（千元）'),(200,'3')]])
  self.assertIsNone(build_cases(d)[1]['rule_field']['value'])
 def test_conflicting_currency_refuses(self):
  d=doc([[(0,'单位：元 币种：人民币，美元')],[(200,'本报告期')],[(0,'营业收入'),(200,'2')]])
  self.assertIsNone(build_cases(d)[0]['rule_field']['value'])
