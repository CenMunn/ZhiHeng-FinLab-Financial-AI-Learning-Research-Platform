import json,tempfile,unittest
from pathlib import Path
from research.filing_extraction.common import verify_artifacts,make_inputs
from research.market.common import file_sha

class FilingInputTests(unittest.TestCase):
 def test_rejects_changed_and_escaped_artifacts(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);folder=root/'research/artifacts/filing-extraction';folder.mkdir(parents=True);p=folder/'a.json';p.write_text('{}')
   mapping={p.relative_to(root).as_posix():file_sha(p)};verify_artifacts(mapping,project=root)
   p.write_text('changed')
   with self.assertRaises(ValueError):verify_artifacts(mapping,project=root)
   with self.assertRaises(ValueError):verify_artifacts({'../bad':'a'*64},project=root)
 def test_first_six_exact_pages_no_reference_or_extra_fields(self):
  docs=[{'doc_id':'600519-2024Q1','symbol':'600519','title':'Q1','period':'2024Q1','split':'development','pdf_sha256':'a'*64}]
  result=make_inputs(docs,{'600519-2024Q1':['page'+str(i) for i in range(1,9)]})
  row=result['documents'][0];self.assertEqual(row['pages'][-1],{'page':6,'text':'page6'});self.assertEqual(set(row),set(docs[0])|{'pages'})

