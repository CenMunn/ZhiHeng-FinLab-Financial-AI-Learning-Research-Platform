import unittest
from research.event_study.sources import normalize, link_versions, extract_metrics, verify_page

def row(title='贵州茅台2024年第一季度报告',day='2024-04-27',kind='第一季度季报',heading='定期报告'):
 return {'TITLE':title,'SSEDATE':day,'SECURITY_CODE':'600519','URL':'/disclosure/listedinfo/announcement/c/new/'+day+'/600519_test.pdf','BULLETIN_TYPE':kind,'BULLETIN_HEADING':heading,'ADDDATE':'2024-04-26 18:29:13'}

class SourceTests(unittest.TestCase):
 def test_date_not_system_ingestion_time(self):
  r=normalize(row(),'600519');self.assertEqual(r['publication_date'],'2024-04-27');self.assertIsNone(r['publication_at']);self.assertEqual(r['time_precision'],'date');self.assertEqual(r['report_period'],'2024Q1')
 def test_report_period_is_not_publication_year(self):
  r=normalize(row('贵州茅台2023年年度报告','2024-04-03','年报'),'600519');self.assertEqual(r['report_period'],'2023FY');self.assertEqual(r['publication_date'],'2024-04-03')
 def test_summary_translation_and_board_resolution_not_full(self):
  self.assertEqual(normalize(row('贵州茅台2024年年度报告摘要',kind='年报摘要'),'600519')['document_type'],'summary')
  self.assertEqual(normalize(row('贵州茅台2024年年度报告（英文版）',kind='其它',heading='临时公告'),'600519')['qualification'],'excluded_translation')
  self.assertIsNone(normalize(row('关于审议2024年第一季度报告的董事会决议',kind='其它',heading='临时公告'),'600519'))
 def test_wrong_stock_date_and_url_refused(self):
  for change in [{'SECURITY_CODE':'600036'},{'SSEDATE':'2026-01-01'},{'URL':'https://evil.example/report.pdf'}]:
   r=row();r.update(change)
   with self.assertRaises(ValueError):normalize(r,'600519')
 def test_revision_links_without_inventing_original_time(self):
  a=normalize(row(),'600519');b=normalize(row('贵州茅台关于2024年第一季度报告的更正公告','2024-05-01',kind='其它',heading='临时公告'),'600519')
  link_versions([a,b]);self.assertIn(a['event_id'],b['related_event_ids']);self.assertEqual(b['qualification'],'review_revision');self.assertIsNone(a['publication_at'])
 def test_page_total_and_duplicate_detection(self):
  data={'pageHelp':{'total':1,'pageCount':1,'pageNo':1,'pageSize':100},'result':[row()]};self.assertEqual(verify_page(data,1,None),1)
  with self.assertRaises(ValueError):verify_page(data,2,1)
  with self.assertRaises(ValueError):verify_page(data,1,2)
 def test_metrics_keep_sign_unit_scope_and_current_period(self):
  pages=['2024 年第一季度报告\n单位：元 币种：人民币\n营业收入 45,775,725,790.75 18.11\n归属于上市公司股东的净利润 24,065,325,188.34 15.73\n经营活动产生的现金流量净额 -9,999,999.50 -200.00']
  result=extract_metrics(pages)
  self.assertEqual(result[0]['value'],'45775725790.75');self.assertEqual(result[2]['value'],'-9999999.50');self.assertEqual(result[2]['scope'],'consolidated');self.assertEqual(result[0]['unit'],'元');self.assertEqual(result[0]['page'],1)
 def test_ambiguous_or_missing_units_refused(self):
  with self.assertRaises(ValueError):extract_metrics(['营业收入 12.50'])
