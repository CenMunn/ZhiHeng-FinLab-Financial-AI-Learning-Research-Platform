import unittest
from research.filing_extraction.acquire import select_documents, validate_pdf, validate_identity, validate_unit, catalog_metadata

class FilingSourcesTests(unittest.TestCase):
 def test_catalog_copy_excludes_previous_extracted_case_labels(self):
  source={'catalog':[{'event_id':'x'}],'audit':[{'symbol':'s'}],'case':{'evidence':[{'value':'123'}]},'artifacts':{'private':'hash'}}
  value=catalog_metadata(source)
  self.assertEqual(value,{'catalog':source['catalog'],'audit':source['audit']})
 def catalog(self):
  return [{'symbol':s,'report_period':p,'document_type':'quarterly','publication_date':p[:4]+'-04-30','title':'季度报告','event_id':s+p} for s in ('600519','600036','600585') for p in ('2024Q1','2025Q1')]
 def test_exact_six_documents_and_date_eligibility(self):
  rows=select_documents(self.catalog());self.assertEqual(len(rows),6)
  self.assertEqual({r['split'] for r in rows},{'development','evaluation'})
  changed=self.catalog();changed[0]['publication_date']='2026-04-30'
  with self.assertRaises(ValueError):select_documents(changed)
 def test_missing_duplicate_or_unexpected_candidate_not_substituted(self):
  for rows in (self.catalog()[:-1],self.catalog()+[self.catalog()[0]]):
   with self.assertRaises(ValueError):select_documents(rows)
 def test_challenge_and_oversized_pdf_refused(self):
  validate_pdf(b'%PDF-1.7\ntest')
  for raw in (b'<html>challenge</html>',b'%PDF'+b'x'*8_000_000):
   with self.assertRaises(ValueError):validate_pdf(raw)
 def test_document_identity_must_match_company_and_period(self):
  validate_identity(['招商银行股份有限公司 2025年第一季度报告'],'600036','2025Q1')
  for symbol,period in [('600585','2025Q1'),('600036','2024Q1')]:
   with self.assertRaises(ValueError):validate_identity(['招商银行股份有限公司 2025年第一季度报告'],symbol,period)
 def test_only_explicit_supported_units(self):
  for unit in ('元','万元','百万元','亿元'):self.assertEqual(validate_unit(unit),unit)
  for unit in ('人民币','千元','unknown',''):
   with self.assertRaises(ValueError):validate_unit(unit)
