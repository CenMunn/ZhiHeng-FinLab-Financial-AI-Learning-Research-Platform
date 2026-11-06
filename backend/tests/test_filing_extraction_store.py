import copy, hashlib, json, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from platform_app.adapters.filing_extraction_store import FilingExtractionStore
from platform_app.api.filing_extraction import filing_extraction_router
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash


class FilingExtractionStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.folder = self.root/'backend/data/filing-extraction'
        self.folder.mkdir(parents=True)
        self.pdf = self.root/'research/artifacts/filing-extraction/report.pdf'
        self.pdf.parent.mkdir(parents=True); self.pdf.write_bytes(b'%PDF-synthetic-fixture')
        name = self.pdf.relative_to(self.root).as_posix(); sha = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        sources = {'research/filing_extraction/score.py':'a'*64}
        protocol = {'schema':'filing-extraction-protocol-v1','sources':sources,'inputs_sha256':'b'*64,'reference_sha256':'c'*64,'design':{'model_id':'synthetic/model','model_revision':'f'*40}}
        docs=[]; rows=[]
        for period,split in [('2024Q1','development'),('2025Q1','evaluation')]:
            for symbol in ['600519','600036','600585']:
                doc_id=symbol+'-'+period
                docs.append(dict(doc_id=doc_id,symbol=symbol,name='合成公司',title='合成季报',period=period,split=split,pdf_path=name,pdf_sha256=sha,pdf_url='https://example.org/report.pdf',input_pages=[1,2,3,4,5,6],input_sha256='b'*64,coverage={}))
                for method in ['rule','model']:
                    for metric in ['revenue','net_profit_parent','operating_cashflow']:
                        value=dict(metric=metric,value='12.30',unit='万元',currency='CNY',period=period,scope='consolidated',page=2,quote='合成指标 12.30')
                        checks={k:True for k in ['numeric','unit','currency','period','scope','evidence','complete','answered']}; checks['correct_abstention']=False
                        rows.append(dict(doc_id=doc_id,split=split,metric=metric,label='合成指标',method=method,prediction=value,status='ok',reference=dict(status='verified',variants=[value],input_context_complete=True,notes=[]),checks=checks,error_reasons=[]))
        metrics=[dict(split=split,method=method,total=9,answered=9,abstained=0,numeric_correct=9,unit_correct=9,currency_correct=9,period_correct=9,scope_correct=9,evidence_correct=9,complete_correct=9,correct_abstentions=0,reference_verified=9,context_complete=9) for split in ['development','evaluation'] for method in ['rule','model']]
        self.record=dict(schema='filing-extraction-publication-v1',run_id='filing-'+stable_hash(protocol),created_at='2026-11-06T00:00:00Z',protocol=protocol,sources=sources,artifacts={name:sha},documents=docs,methods=[dict(id='rule',label='规则',description='合成'),dict(id='model',label='模型',description='合成',model_id='synthetic/model',revision='f'*40)],metrics=metrics,rows=rows,limitations=['合成夹具'],reference_status='assistant_visual_reference_pending_human_audit',model_status='completed',input_sha256='b'*64,reference_sha256='c'*64,prediction_sha256={'rule':'d'*64,'model':'e'*64},model_details={})
        self.store=FilingExtractionStore(self.folder,self.root)

    def save(self):
        (self.folder/'latest.json').write_text(json.dumps(dict(record=self.record,sha256=stable_hash(self.record))),encoding='utf8')

    def test_empty_verified_and_allowlisted_pdf(self):
        self.assertEqual(self.store.get()['artifact_status'],'empty'); self.save()
        self.assertEqual(self.store.get()['artifact_status'],'verified')
        self.assertEqual(self.store.document('600519-2024Q1'),self.pdf.read_bytes())
        with self.assertRaises(KeyError): self.store.document('../report.pdf')

    def test_changed_missing_and_escaped_sources(self):
        self.save(); self.pdf.write_bytes(b'changed')
        with self.assertRaises(DomainConflict): self.store.get()
        self.pdf.unlink(); self.assertEqual(self.store.get()['artifact_status'],'missing')
        with self.assertRaises(DomainConflict): self.store.document('600519-2024Q1')
        self.record['artifacts']={'../outside':'a'*64}; self.save()
        with self.assertRaises(DomainConflict): self.store.get()

    def test_identity_document_hash_and_source_binding(self):
        for mutation in [lambda r:r.update(run_id='filing-other'),lambda r:r['documents'][0].update(pdf_sha256='f'*64),lambda r:r.update(sources={'changed':'f'*64})]:
            old=copy.deepcopy(self.record); mutation(self.record); self.save()
            with self.assertRaises(DomainConflict): self.store.get()
            self.record=old

    def test_metrics_cannot_exclude_failed_rows(self):
        self.record['metrics'][0]['total']=8; self.save()
        with self.assertRaises(DomainConflict): self.store.get()
        self.record['metrics'][0]['total']=9; self.record['rows'][0]['checks']['numeric']=False; self.save()
        with self.assertRaises(DomainConflict): self.store.get()

    def test_duplicate_and_misassigned_rows_rejected(self):
        old=copy.deepcopy(self.record); self.record['rows'][1]=copy.deepcopy(self.record['rows'][0]); self.save()
        with self.assertRaises(DomainConflict): self.store.get()
        self.record=old; self.record['rows'][0]['split']='evaluation'; self.save()
        with self.assertRaises(DomainConflict): self.store.get()

    def test_get_and_document_do_not_mutate_publication(self):
        self.save(); before=(self.folder/'latest.json').read_bytes()
        app=FastAPI(); app.include_router(filing_extraction_router(self.store)); client=TestClient(app)
        response=client.get('/api/v1/filing-extraction'); self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'no-store')
        response=client.get('/api/v1/filing-extraction/document',params={'doc_id':'600519-2024Q1'})
        self.assertEqual(response.status_code,200); self.assertTrue(response.headers['content-type'].startswith('application/pdf'))
        self.assertEqual(client.post('/api/v1/filing-extraction').status_code,405)
        self.assertEqual((self.folder/'latest.json').read_bytes(),before)

    def test_input_reference_and_model_labels_cannot_escape_protocol(self):
        for mutate in [lambda r:r.update(input_sha256='f'*64),lambda r:r.update(reference_sha256='f'*64),lambda r:r['methods'][1].update(model_id='other/model'),lambda r:r['methods'][1].update(revision='e'*40)]:
            old=copy.deepcopy(self.record); mutate(self.record); self.save()
            with self.assertRaises(DomainConflict): self.store.get()
            self.record=old

    def test_relabelled_document_and_inconsistent_success_rejected(self):
        self.record['documents'][0]['doc_id']='renamed'
        for row in self.record['rows']:
            if row['doc_id']=='600519-2024Q1': row['doc_id']='renamed'
        self.save()
        with self.assertRaises(DomainConflict): self.store.get()
        self.record['documents'][0]['doc_id']='600519-2024Q1'
        for row in self.record['rows']:
            if row['doc_id']=='renamed': row['doc_id']='600519-2024Q1'
        self.record['rows'][0]['checks']['numeric']=False
        self.record['metrics'][0]['numeric_correct']=8
        self.save()
        with self.assertRaises(DomainConflict): self.store.get()
        self.record['rows'][0]['checks']['numeric']=True
        self.record['metrics'][0]['numeric_correct']=9
        self.record['rows'][0]['status']='invalid_output'; self.save()
        with self.assertRaises(DomainConflict): self.store.get()
