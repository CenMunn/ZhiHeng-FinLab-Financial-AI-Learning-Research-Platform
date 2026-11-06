import copy,json,tempfile,unittest,hashlib
from pathlib import Path
from research.filing_extraction.model import build_prompt,parse_output,validate_documents
from research.filing_extraction.download_model import verify_file,validate_range,retained_range_path,retained_prefix

class FilingModelTests(unittest.TestCase):
 def fields(self):
  return [{'metric':m,'value':'-12.34','unit':'百万元','currency':'CNY','period':'2024Q1','scope':'consolidated','page':2,'quote':'经营活动产生的现金流量净额 -12.34'} for m in ('revenue','net_profit_parent','operating_cashflow')]
 def doc(self):
  return {'doc_id':'600519-2024Q1','symbol':'600519','title':'季度报告','period':'2024Q1','split':'development','pdf_sha256':'a'*64,'pages':[{'page':1,'text':'完整第一页内容'}, {'page':2,'text':'单位：百万元，人民币。收入12.34'}]}
 def test_exact_decimal_string_negative_and_null_are_preserved(self):
  fields=self.fields();fields[1].update({k:None for k in fields[1] if k!='metric'})
  self.assertEqual(parse_output(json.dumps({'fields':fields})),fields)
 def test_schema_rejects_missing_duplicate_extra_and_nonfinite(self):
  rows=self.fields()
  malformed=[rows[:2],rows+[rows[0]], [rows[0],rows[0],rows[2]]]
  for key,value in [('value',float('nan')),('value',12.34),('value','1,000'),('page',True),('unit','美元'),('scope','unknown'),('quote',[])]:
   wrong=copy.deepcopy(rows);wrong[0][key]=value;malformed.append(wrong)
  wrong=copy.deepcopy(rows);wrong[0]['confidence']=1;malformed.append(wrong)
  for value in malformed:
   with self.assertRaises(ValueError):parse_output(json.dumps({'fields':value}))
  for raw in ['```json\n'+json.dumps({'fields':rows})+'\n```',json.dumps({'fields':rows,'note':'fixed'}),'{"fields":[],"fields":[]}']:
   with self.assertRaises(ValueError):parse_output(raw)
 def test_prompt_contains_every_page_and_constraints_without_answers(self):
  doc=self.doc();prompt=build_prompt(doc)
  self.assertIn('完整第一页内容',prompt);self.assertIn('单位：百万元',prompt);self.assertIn('2024Q1',prompt)
  self.assertIn('未知',prompt);self.assertNotIn('gold',prompt)
 def test_inputs_forbid_label_fields_duplicate_docs_and_silent_page_loss(self):
  doc=self.doc();self.assertEqual(validate_documents({'schema':'filing-extraction-inputs-v1','documents':[doc]}),[doc])
  for key,value in [('reference',{'value':'12'}),('pdf_sha256','x'),('pages',[{'page':2,'text':'bad'}])]:
   wrong=copy.deepcopy(doc);wrong[key]=value
   with self.assertRaises(ValueError):build_prompt(wrong)
  with self.assertRaises(ValueError):validate_documents({'schema':'filing-extraction-inputs-v1','documents':[doc,doc]})
 def test_upstream_and_local_file_identity_rejects_tampering(self):
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'config.json';raw=b'{}';path.write_bytes(raw)
   spec={'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'blob_id':hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),'lfs_sha256':None}
   verify_file(path,spec);path.write_bytes(b'[]')
   with self.assertRaises(ValueError):verify_file(path,spec)
   path.write_bytes(raw);spec['blob_id']='0'*40
   with self.assertRaises(ValueError):verify_file(path,spec)
 def test_range_resume_requires_exact_status_interval_and_size(self):
  validate_range(206,'bytes 100-199/1000',100,199,1000,100)
  for status,header,size in [(200,'bytes 100-199/1000',100),(206,'bytes 0-99/1000',100),(206,'bytes 100-199/999',100),(206,'bytes 100-199/1000',99)]:
   with self.assertRaises(ValueError):validate_range(status,header,100,199,1000,size)
 def test_range_recovery_reuses_only_complete_candidate_and_keeps_partial(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);base=root/'100-199.bin';base.write_bytes(b'x'*40)
   path,reused=retained_range_path(root,100,199);self.assertFalse(reused);self.assertNotEqual(path,base);self.assertEqual(base.stat().st_size,40)
   path.write_bytes(b'y'*100)
   again,reused=retained_range_path(root,100,199);self.assertTrue(reused);self.assertEqual(path,again)
   self.assertEqual(base.read_bytes(),b'x'*40)
 def test_range_prefix_selects_largest_valid_fragment_without_mutation(self):
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory);a=folder/'100-199.bin';a.write_bytes(b'a'*40)
   b=folder/'100-199.retry-1.bin';b.write_bytes(b'b'*70)
   c=folder/'100-199.retry-2.bin';c.write_bytes(b'c'*101)
   self.assertEqual(retained_prefix(folder,100,199),b)
   self.assertEqual(a.stat().st_size,40);self.assertEqual(b.stat().st_size,70)

if __name__=='__main__':unittest.main()
