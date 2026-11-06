import copy,tempfile,unittest
from pathlib import Path
from research.event_study.pipeline import committee_facts,verify_artifacts
from research.market.common import file_sha

class EventPublicationTests(unittest.TestCase):
 def case(self):
    return {'pdf_sha256':'a'*64,'evidence':[{'metric':'operating_cashflow','label':'经营活动产生的现金流量净额','value':'-12.34','unit':'万元','period':'2024Q1','scope':'consolidated','page':2,'excerpt':'本报告期 合并 人民币万元 -12.34'}]}
 def test_committee_contract_keeps_signed_value_unit_period_and_source(self):
    row=committee_facts(self.case())[0]
    self.assertEqual((row['value'],row['unit'],row['period'],row['scope']),('-12.34','万元','2024-03-31','consolidated'))
    self.assertEqual(row['year'],2024);self.assertFalse(row['annualFlow']);self.assertEqual(row['page'],2)
    self.assertIn('a'*64,row['sourceId']);self.assertEqual(row['currency'],'人民币')
 def test_unknown_scope_nonfinite_and_unsupported_period_refused(self):
    for key,value in [('scope','unknown'),('value','NaN'),('period','unknown'),('page',0)]:
      case=self.case();case['evidence'][0][key]=value
      with self.assertRaises(ValueError):committee_facts(case)
 def test_missing_modified_or_escaped_artifact_not_reregistered(self):
    with tempfile.TemporaryDirectory() as t:
      root=Path(t);p=root/'research/artifacts/event-study/a.json';p.parent.mkdir(parents=True);p.write_text('{}')
      mapping={p.relative_to(root).as_posix():file_sha(p)};verify_artifacts(root,mapping)
      p.write_text('changed')
      with self.assertRaises(ValueError):verify_artifacts(root,mapping)
      with self.assertRaises(ValueError):verify_artifacts(root,{'../outside':'a'*64})
