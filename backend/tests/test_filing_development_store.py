"""Synthetic publication tests: no research environment, models or private data."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from platform_app.adapters.filing_development_store import FilingDevelopmentStore
from platform_app.api.filing_development import filing_development_router
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash


METHODS = ('baseline_rule', 'baseline_model', 'single_free', 'single_constrained')
METRICS = ('revenue', 'net_profit_parent', 'operating_cashflow')
BASELINE_PATH = 'backend/data/filing-extraction/filing-eea0bd9c4721f14a19f11b8fc49245c00ca9f57347509b787f53658e0c01d3cc.json'


class FilingDevelopmentStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.folder = self.root / 'backend/data/filing-development'
        self.folder.mkdir(parents=True)
        self.artifacts = {}
        self.put('research/filing_development/pipeline.py', 'synthetic source')
        self.sources = {'research/filing_development/pipeline.py': self.sha('research/filing_development/pipeline.py')}
        self.docs = [dict(doc_id=symbol+'-2024Q1', symbol=symbol, name='合成公司', period='2024Q1', split='development', pdf_url='https://static.cninfo.com.cn/finalpage/synthetic.PDF', input_pages=[1,2,3,4,5,6]) for symbol in ('600519','600036','600585')]
        rows = []
        for doc in self.docs:
            for method in METHODS:
                for metric in METRICS:
                    pred = dict(metric=metric,value='12.30',unit='万元',currency='CNY',period='2024Q1',scope='consolidated',page=2,quote='合成指标 12.30')
                    checks = {k: True for k in ('numeric','unit','currency','period','scope','evidence','complete','answered')}; checks['correct_abstention'] = False
                    variant={key:value for key,value in pred.items() if key!='metric'}; variant.update(unit_evidence_pages=[1,2],scope_evidence_pages=[2,5])
                    rows.append(dict(case_id=doc['doc_id']+'/'+metric,doc_id=doc['doc_id'],metric=metric,label='合成指标',method=method,status='ok',prediction=pred,checks=checks,error_reasons=[],reference=dict(status='verified',variants=[variant],input_context_complete=True,notes=['合成参考']),candidate_count=2 if method.startswith('single_') else None,candidate_covered=True if method.startswith('single_') else None,input_tokens=100,output_tokens=20,latency_seconds=0.5))
        self.put('research/artifacts/filing-development/inputs.json', {'cases':'synthetic'})
        self.put('research/artifacts/filing-development/reference.json', {'reference':'synthetic'})
        model_files={name:{'sha256':hashlib.sha256(name.encode()).hexdigest(),'size':100} for name in ('LICENSE','README.md','config.json','generation_config.json','merges.txt','model.safetensors','tokenizer.json','tokenizer_config.json','vocab.json')}
        self.put('research/artifacts/filing-development/model-manifest.json', {'model_id':'synthetic/model','revision':'f'*40,'files':model_files})
        baseline_rows = []
        for row in rows:
            if row['method'].startswith('baseline_'):
                baseline_rows.append({**copy.deepcopy(row),'method':row['method'].replace('baseline_',''),'split':'development'})
        baseline = dict(schema='filing-extraction-publication-v1',run_id=PurePosixPath(BASELINE_PATH).stem,documents=copy.deepcopy(self.docs),rows=baseline_rows)
        self.put(BASELINE_PATH,dict(record=baseline,sha256=stable_hash(baseline)))
        pin=patch('platform_app.adapters.filing_development_store.BASELINE_RECORD_SHA256',stable_hash(baseline),create=True); pin.start(); self.addCleanup(pin.stop)
        human_dir = 'docs/research/human-review/2026-11-06/'
        stream=io.StringIO(); columns=['case_id','doc_id','company','metric','source_url','local_pdf','manual_value','manual_unit','manual_currency','manual_period','manual_scope','value_page','header_pages','quote','status','reviewer','reviewed_at','notes']; writer=csv.DictWriter(stream,fieldnames=columns); writer.writeheader()
        for period in ('2024Q1','2025Q1'):
            for symbol in ('600519','600036','600585'):
                for metric in METRICS:
                    doc_id=symbol+'-'+period; writer.writerow(dict(case_id=doc_id+':'+metric,doc_id=doc_id,company='合成公司',metric=metric,source_url='https://example.org/synthetic.pdf',local_pdf='research/artifacts/filing-extraction/synthetic.pdf',status='unreviewed'))
        self.put(human_dir+'checklist.csv',stream.getvalue())
        self.put(human_dir+'guide.md','# 合成填写规范\n未填写，不代表完成核验。')
        self.put(human_dir+'manifest.json',dict(item_count=18,completed=0,status='pending_human_review',artifacts={name:self.sha(human_dir+name) for name in ('checklist.csv','guide.md')}))
        sealed_docs=[]
        for symbol in ('000333','601318','600887'):
            pdf='research/artifacts/filing-development/sealed-evaluation/initial/'+symbol+'.pdf'; self.put(pdf,'%PDF-synthetic-'+symbol)
            sealed_docs.append(dict(symbol=symbol,name='合成封存公司',period='2025Q1',status='sealed',pdf_url='https://static.cninfo.com.cn/finalpage/synthetic.PDF',pdf_path=pdf,pdf_sha256=self.sha(pdf)))
        sealed = dict(content_accessed=False,status='sealed',documents=sealed_docs)
        sealed_path='research/artifacts/filing-development/sealed-evaluation/initial/manifest.json'
        self.put(sealed_path,sealed)
        generation=dict(max_input_tokens=4096,max_new_tokens=384,dtype='bfloat16',do_sample=False,seed=0,batch_size=1)
        protocol = dict(schema='filing-development-protocol-v1',sources=self.sources,inputs_sha256=self.sha('research/artifacts/filing-development/inputs.json'),reference_sha256=self.sha('research/artifacts/filing-development/reference.json'),model_manifest_path='research/artifacts/filing-development/model-manifest.json',model_manifest_sha256=self.sha('research/artifacts/filing-development/model-manifest.json'),baseline_path=BASELINE_PATH,baseline_file_sha256=self.sha(BASELINE_PATH),design={'model_id':'synthetic/model','model_revision':'f'*40,'generation':generation})
        run_id='filingdev-'+stable_hash(protocol); run='research/artifacts/filing-development/runs/'+run_id
        pred_sha={}
        for method in METHODS[2:]:
            name=run+'/'+method+'-predictions.json'
            outputs=[{**{key:copy.deepcopy(row[key]) for key in ('case_id','doc_id','metric','method','status','input_tokens','output_tokens','latency_seconds','candidate_count')},'field':copy.deepcopy(row['prediction']),'raw_output':json.dumps(row['prediction'],ensure_ascii=False),'token_ids':[1]*row['output_tokens']} for row in rows if row['method']==method]
            self.put(name,dict(schema='filing-development-predictions-v1',method=method,inputs_sha256=protocol['inputs_sha256'],model_manifest_sha256=protocol['model_manifest_sha256'],model_id='synthetic/model',revision='f'*40,generation=generation,runtime={},predictions=outputs)); pred_sha[method]=self.sha(name)
        metrics = [dict(method=m,total=9,format_valid=9,answered=9,numeric_correct=9,unit_correct=9,currency_correct=9,period_correct=9,scope_correct=9,evidence_correct=9,complete_correct=9,correct_abstentions=0,candidate_covered=9 if m.startswith('single_') else None) for m in METHODS]
        scoring_path=run+'/scored-rows.json'; self.put(scoring_path,dict(schema='filing-development-scoring-v1',protocol_sha256=stable_hash(protocol),prediction_sha256=pred_sha,inputs_sha256=protocol['inputs_sha256'],reference_sha256=protocol['reference_sha256'],rows=rows,metrics=metrics))
        verification_path=run+'/model-verification.json'; self.put(verification_path,dict(schema='filing-development-model-verification-v1',model_id='synthetic/model',revision='f'*40,model_manifest_sha256=protocol['model_manifest_sha256'],verified_at='2026-11-05T23:59:00Z',stage='post_prediction_pre_scoring',files=model_files))
        verification=dict(receipt_path=verification_path,verified_at='2026-11-05T23:59:00Z',stage='post_prediction_pre_scoring',current_assets_checked_on_request=False)
        self.record = dict(schema='filing-development-publication-v1',run_id=run_id,created_at='2026-11-06T00:00:00Z',protocol=protocol,sources=self.sources,artifacts=self.artifacts,input_sha256=protocol['inputs_sha256'],reference_sha256=protocol['reference_sha256'],prediction_sha256=pred_sha,scoring_path=scoring_path,documents=self.docs,methods=[dict(id=m,label=m,description='合成夹具') for m in METHODS],metrics=metrics,rows=rows,model_details=dict(model_id='synthetic/model',revision='f'*40,generation=copy.deepcopy(generation),runtime={},verification=verification),baseline=dict(record_sha256=stable_hash(baseline),run_id=baseline['run_id']),new_evaluation=dict(manifest_path=sealed_path,**sealed),human_review=dict(manifest_path=human_dir+'manifest.json',checklist_path=human_dir+'checklist.csv',guide_path=human_dir+'guide.md',item_count=18,completed=0,status='pending_human_review'),limitations=['合成开发测试，不是新评估'])
        self.store = FilingDevelopmentStore(self.folder, self.root)

    def put(self,name,body):
        path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(body,ensure_ascii=False) if not isinstance(body,str) else body,encoding='utf8')
        if name.startswith(('research/artifacts/','backend/data/filing-extraction/','docs/research/human-review/')):
            self.artifacts[name]=self.sha(name)

    def sha(self,name):
        return hashlib.sha256((self.root/name).read_bytes()).hexdigest()

    def save(self):
        (self.folder/'latest.json').write_text(json.dumps(dict(record=self.record,sha256=stable_hash(self.record)),ensure_ascii=False),encoding='utf8')

    def change_prediction(self,mutate):
        name='research/artifacts/filing-development/runs/'+self.record['run_id']+'/single_free-predictions.json'
        body=json.loads((self.root/name).read_text('utf8')); mutate(body); self.put(name,body)
        self.record['prediction_sha256']['single_free']=self.sha(name)
        score_path=self.record['scoring_path']; scored=json.loads((self.root/score_path).read_text('utf8')); scored['prediction_sha256']=self.record['prediction_sha256']; self.put(score_path,scored); self.save()

    def reject(self,mutate):
        original=copy.deepcopy(self.record); mutate(self.record); self.save()
        with self.assertRaises(DomainConflict): self.store.get()
        self.record=original

    def test_empty_then_verified_with_four_fixed_denominators(self):
        self.assertEqual(self.store.get(),dict(record=None,record_sha256=None,artifact_status='empty',missing_artifacts=[]))
        self.save(); response=self.store.get(); self.assertEqual(response['artifact_status'],'verified'); self.assertEqual(len(response['record']['rows']),36)

    def test_every_get_rechecks_source_code_and_artifacts(self):
        self.save(); self.store.get()
        (self.root/'research/filing_development/pipeline.py').write_text('changed',encoding='utf8')
        with self.assertRaises(DomainConflict): self.store.get()
        (self.root/'research/filing_development/pipeline.py').unlink()
        self.assertIn('research/filing_development/pipeline.py',self.store.get()['missing_artifacts'])
        (self.root/('research/artifacts/filing-development/runs/'+self.record['run_id']+'/single_free-predictions.json')).write_text('changed',encoding='utf8')
        with self.assertRaises(DomainConflict): self.store.get()

    def test_missing_artifact_and_review_refuse_download(self):
        self.save(); name=self.record['human_review']['checklist_path']; (self.root/name).unlink()
        self.assertEqual(self.store.get()['artifact_status'],'missing')
        with self.assertRaises(DomainConflict): self.store.review('guide')

    def test_path_traversal_private_files_and_extra_archive_rejected(self):
        for name in ('../outside.json','C:/outside.json','research/artifacts/filing-development/../../private.json','research/artifacts/filing-development\\outside.json','backend/data/filing-extraction/latest.json','backend/data/private.sqlite3'):
            self.reject(lambda r:r['artifacts'].update({name:'a'*64}))
        self.reject(lambda r:r['sources'].update({'.env':'a'*64}))

    def test_protocol_identity_and_required_hashes_rejected(self):
        self.reject(lambda r:r.update(run_id='filingdev-forged'))
        self.reject(lambda r:r.update(input_sha256='f'*64))
        self.reject(lambda r:r.update(reference_sha256='f'*64))
        self.reject(lambda r:r['prediction_sha256'].update(single_free='f'*64))
        self.reject(lambda r:r['sources'].update({'changed.py':'f'*64}))

    def test_model_labels_and_new_output_limits_bind_to_frozen_design(self):
        for mutate in [lambda r:r['model_details'].update(model_id='another/model'),lambda r:r['model_details'].update(revision='e'*40),lambda r:r['model_details']['generation'].update(max_new_tokens=999)]:
            self.reject(mutate)
        def field(r): return next(row for row in r['rows'] if row['method']=='single_free')
        self.reject(lambda r:field(r)['prediction'].update(quote='字'*161))
        self.reject(lambda r:field(r).update(input_tokens=4097))
        self.reject(lambda r:field(r).update(output_tokens=385))

    def test_only_fixed_development_documents_and_unique_36_rows(self):
        self.reject(lambda r:r['documents'][0].update(period='2025Q1',split='evaluation'))
        self.reject(lambda r:r['documents'][0].update(symbol='000333'))
        self.reject(lambda r:r['rows'].__setitem__(1,copy.deepcopy(r['rows'][0])))
        self.reject(lambda r:r['rows'][0].update(case_id='other/revenue'))
        self.reject(lambda r:r['rows'][0].update(split='evaluation'))

    def test_scores_recomputed_without_excluding_format_failures(self):
        self.reject(lambda r:r['metrics'][0].update(total=8))
        self.reject(lambda r:r['metrics'][0].update(format_valid=8))
        self.reject(lambda r:r['rows'][0]['checks'].update(numeric=False))
        self.reject(lambda r:r['rows'][0].update(status='invalid_output'))
        self.reject(lambda r:r['metrics'][2].update(candidate_covered=8))

    def test_new_rows_must_match_registered_prediction_artifact(self):
        def mutate(body):
            body['predictions'][0]['field']['value']='99'; body['predictions'][0]['raw_output']=json.dumps(body['predictions'][0]['field'])
        self.change_prediction(mutate)
        with self.assertRaises(DomainConflict): self.store.get()

    def test_ok_field_must_match_strict_raw_json_without_cleaning(self):
        self.change_prediction(lambda b:b['predictions'][0].update(raw_output='```json\n'+b['predictions'][0]['raw_output']+'\n```'))
        with self.assertRaises(DomainConflict): self.store.get()

    def test_scored_artifact_must_match_embedded_rows_metrics_and_identity(self):
        name=self.record['scoring_path']; body=json.loads((self.root/name).read_text('utf8')); body['rows'][0]['checks']['numeric']=False; self.put(name,body); self.save()
        with self.assertRaises(DomainConflict): self.store.get()

    def test_missing_scored_artifact_is_not_verified(self):
        self.save(); (self.root/self.record['scoring_path']).unlink(); self.assertEqual(self.store.get()['artifact_status'],'missing')

    def test_reference_and_baseline_results_cannot_be_rewritten(self):
        self.reject(lambda r:r['rows'][0]['reference']['variants'][0].update(value='99'))
        self.reject(lambda r:r['rows'][0]['prediction'].update(value='99'))
        self.reject(lambda r:r['baseline'].update(record_sha256='f'*64))

    def test_production_baseline_hash_does_not_reaccept_another_archive(self):
        self.save()
        with patch('platform_app.adapters.filing_development_store.BASELINE_RECORD_SHA256','4340739bbebb77de426fd2538d9848e56df4ce436c9b4fa2fe7454232611514c',create=True):
            with self.assertRaises(DomainConflict): self.store.get()

    def test_archived_model_verification_binds_all_manifest_file_hashes(self):
        self.save(); self.assertEqual(self.store.get()['artifact_status'],'verified')
        name=self.record['model_details']['verification']['receipt_path']; body=json.loads((self.root/name).read_text('utf8')); body['files']['model.safetensors']['sha256']='f'*64; self.put(name,body); self.save()
        with self.assertRaises(DomainConflict): self.store.get()

    def test_model_verification_cannot_claim_current_assets_were_checked(self):
        self.reject(lambda r:r['model_details']['verification'].update(current_assets_checked_on_request=True))

    def test_original_reference_variant_schema_retains_header_and_scope_pages(self):
        self.save(); body=self.store.get(); variant=body['record']['rows'][0]['reference']['variants'][0]
        self.assertNotIn('metric',variant); self.assertEqual(variant['scope_evidence_pages'],[2,5]); self.assertEqual(variant['unit_evidence_pages'],[1,2])
        for key,value in [('unit_evidence_pages',['2']),('scope_evidence_pages',[0]),('scope_evidence_pages',[2,2])]:
            self.reject(lambda r:r['rows'][0]['reference']['variants'][0].update({key:value}))

    def test_sealed_metadata_and_pending_human_review_must_stay_honest(self):
        self.reject(lambda r:r['new_evaluation'].update(content_accessed=True))
        self.reject(lambda r:r['new_evaluation']['documents'][0].update(value='99'))
        self.reject(lambda r:r['human_review'].update(completed=18,status='completed'))
        self.reject(lambda r:r['human_review'].update(checklist_path='../../private.csv'))
        self.reject(lambda r:r['new_evaluation']['documents'][0].update(pdf_path='research/artifacts/filing-development/missing.pdf'))

    def test_blank_human_manifest_cannot_mask_filled_csv(self):
        name=self.record['human_review']['checklist_path']; path=self.root/name
        rows=list(csv.DictReader(io.StringIO(path.read_text('utf8')))); rows[0]['manual_value']='99'
        stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
        self.put(name,stream.getvalue())
        manifest_name=self.record['human_review']['manifest_path']; manifest=json.loads((self.root/manifest_name).read_text('utf8')); manifest['artifacts']['checklist.csv']=self.sha(name); self.put(manifest_name,manifest)
        self.save()
        with self.assertRaises(DomainConflict): self.store.get()

    def test_review_bytes_and_readonly_routes_no_store_mutation(self):
        self.save(); before=(self.folder/'latest.json').read_bytes()
        app=FastAPI(); app.include_router(filing_development_router(self.store)); client=TestClient(app)
        response=client.get('/api/v1/filing-development'); self.assertEqual(response.status_code,200); self.assertEqual(response.headers['cache-control'],'no-store')
        for file,media in [('checklist','text/csv'),('guide','text/markdown')]:
            response=client.get('/api/v1/filing-development/review',params={'file':file}); self.assertEqual(response.status_code,200); self.assertTrue(response.headers['content-type'].startswith(media)); self.assertIn('attachment;',response.headers['content-disposition'])
        self.assertEqual(client.get('/api/v1/filing-development/review',params={'file':'../../private'}).status_code,422)
        self.assertEqual(client.post('/api/v1/filing-development').status_code,405)
        self.assertEqual((self.folder/'latest.json').read_bytes(),before)

    def test_review_source_disappearing_between_check_and_read_is_conflict(self):
        self.save(); original_get=self.store.get
        def checked_then_removed():
            body=original_get(); (self.root/self.record['human_review']['guide_path']).unlink(); return body
        with patch.object(self.store,'get',side_effect=checked_then_removed):
            with self.assertRaises(DomainConflict): self.store.review('guide')


if __name__=='__main__': unittest.main()
