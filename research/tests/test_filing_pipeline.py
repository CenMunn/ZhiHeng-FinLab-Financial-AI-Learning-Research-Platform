import copy,json,unittest
from research.filing_extraction.pipeline import validate_reference,validate_predictions,check_prediction_binding,validate_reference_provenance,source_files
from pathlib import Path
from research.filing_extraction.common import ROOT,rel

class FilingPipelineTests(unittest.TestCase):
 def test_shared_hash_io_dependency_is_in_frozen_sources(self):
  self.assertIn('research/market/common.py',source_files())
 def fixtures(self):
  fields=[{'metric':m,'value':'100','unit':'元','currency':'CNY','period':'2025Q1','scope':'consolidated','page':1,'quote':label+' 100'} for m,label in [('revenue','营业收入'),('net_profit_parent','归属于本行股东的净利润'),('operating_cashflow','经营活动产生的现金流量净额')]]
  doc={'doc_id':'600036-2025Q1','period':'2025Q1','pdf_sha256':'a'*64,'pages':[{'page':1,'text':'\n'.join(f['quote'] for f in fields)}]}
  refs={'schema':'filing-extraction-reference-v1','status':'assistant_visual_reference_pending_human_audit','documents':[{'doc_id':doc['doc_id'],'pdf_sha256':doc['pdf_sha256'],'fields':[{'metric':f['metric'],'status':'verified','variants':[dict(f)],'input_context_complete':True,'notes':''} for f in fields]}]}
  prediction={'predictions':[{'doc_id':doc['doc_id'],'fields':fields,'status':'ok','raw_output':json.dumps({'fields':fields})}]}
  return {'documents':[doc]},refs,prediction
 def test_reference_is_bound_to_input_identity_and_quote(self):
  inputs,refs,_=self.fixtures();validate_reference(refs,inputs)
  refs['documents'][0]['pdf_sha256']='b'*64
  with self.assertRaises(ValueError):validate_reference(refs,inputs)
 def test_reference_outside_input_or_wrong_unit_fails(self):
  for key,value in [('page',7),('unit','千元'),('quote','营业收入 200')]:
   inputs,refs,_=self.fixtures();refs['documents'][0]['fields'][0]['variants'][0][key]=value
   with self.assertRaises(ValueError):validate_reference(refs,inputs)
 def test_predictions_cannot_drop_duplicate_or_replace_document(self):
  inputs,_,pred=self.fixtures();validate_predictions(pred,inputs)
  pred['predictions'].append(copy.deepcopy(pred['predictions'][0]))
  with self.assertRaises(ValueError):validate_predictions(pred,inputs)
 def test_failed_output_kept_but_not_smuggled_as_success(self):
  inputs,_,pred=self.fixtures();pred['predictions'][0].update(status='invalid_output',fields=[],raw_output='broken JSON');validate_predictions(pred,inputs)
  pred['predictions'][0]['fields']=[{'metric':'revenue','value':'100'}]
  with self.assertRaises(ValueError):validate_predictions(pred,inputs)
 def test_structured_values_cannot_diverge_from_saved_raw_output(self):
  inputs,_,pred=self.fixtures();pred['predictions'][0]['fields'][0]['value']='999'
  with self.assertRaises(ValueError):validate_predictions(pred,inputs)
 def test_stale_inputs_model_or_code_cannot_be_reaccepted(self):
  protocol={'inputs_sha256':'a'*64,'model_manifest_sha256':'b'*64,'sources':{'research/filing_extraction/model.py':'c'*64}}
  pred={'inputs_sha256':'a'*64,'model_manifest_sha256':'b'*64,'source_sha256':{'research/filing_extraction/model.py':'c'*64}}
  check_prediction_binding(pred,protocol,'model')
  for key in ('inputs_sha256','model_manifest_sha256'):
   changed=copy.deepcopy(pred);changed[key]='d'*64
   with self.assertRaises(ValueError):check_prediction_binding(changed,protocol,'model')
  pred['source_sha256']['research/filing_extraction/model.py']='d'*64
  with self.assertRaises(ValueError):check_prediction_binding(pred,protocol,'model')
 def test_reference_corpus_and_reviewed_images_must_be_bound(self):
  _,refs,_=self.fixtures();path=ROOT/'reference/synthetic/references.json';doc=refs['documents'][0]
  doc['reviewed_pages']=[1]
  for field in doc['fields']:
   field['variants'][0].update(scope_evidence_pages=[1],unit_evidence_pages=[1])
  refs.update(corpus_manifest_sha256='a'*64,artifacts={rel(path.parent/doc['doc_id']/'page-1.png'):'b'*64})
  corpus={'documents':[{'doc_id':doc['doc_id'],'page_count':2}]}
  validate_reference_provenance(refs,corpus,'a'*64,path)
  with self.assertRaises(ValueError):validate_reference_provenance(refs,corpus,'c'*64,path)
  refs['artifacts']={}
  with self.assertRaises(ValueError):validate_reference_provenance(refs,corpus,'a'*64,path)

