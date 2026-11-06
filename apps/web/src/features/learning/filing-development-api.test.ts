import {afterEach,describe,expect,it,vi} from 'vitest';
import {developmentReason,developmentReport,readFilingDevelopment,readFilingReview,reviewDownloadUrl,validateFilingDevelopment,type DevelopmentEnvelope} from './filing-development-api';

function fixture():DevelopmentEnvelope {
 const methods=['baseline_rule','baseline_model','single_free','single_constrained'] as const;
 const documents=['600519','600036','600585'].map(symbol=>({doc_id:symbol+'-2024Q1',symbol,name:'合成公司',period:'2024Q1' as const,split:'development' as const,pdf_url:'https://example.org/synthetic.pdf',input_pages:[1,2,3,4,5,6]}));
 const rows=documents.flatMap(d=>methods.flatMap(method=>['revenue','net_profit_parent','operating_cashflow'].map(metric=>({case_id:d.doc_id+'/'+metric,doc_id:d.doc_id,metric,label:'合成字段',method,status:'ok' as const,prediction:{metric,value:'12.30',unit:'万元',currency:'CNY',period:'2024Q1',scope:'consolidated',page:2,quote:'合成字段 12.30'},reference:{status:'verified' as const,variants:[{value:'12.30',unit:'万元',currency:'CNY',period:'2024Q1',scope:'consolidated',page:2,quote:'合成字段 12.30',unit_evidence_pages:[1,2],scope_evidence_pages:[2,5]}],input_context_complete:true,notes:['合成测试参考']},checks:{numeric:true,unit:true,currency:true,period:true,scope:true,evidence:true,complete:true,answered:true,correct_abstention:false},error_reasons:[],candidate_count:method.startsWith('single_')?2:null,candidate_covered:method.startsWith('single_')?true:null,input_tokens:100,output_tokens:20,latency_seconds:.5}))));
 return {record_sha256:'a'.repeat(64),artifact_status:'verified',missing_artifacts:[],record:{schema:'filing-development-publication-v1',run_id:'filingdev-synthetic-ui-only',created_at:'2026-11-06T00:00:00Z',documents,methods:methods.map(id=>({id,label:id,description:'合成测试，不是真实成绩'})),rows,metrics:methods.map(method=>({method,total:9,format_valid:9,answered:9,numeric_correct:9,unit_correct:9,currency_correct:9,period_correct:9,scope_correct:9,evidence_correct:9,complete_correct:9,correct_abstentions:0,candidate_covered:method.startsWith('single_')?9:null})),sources:{'research/filing_development/pipeline.py':'b'.repeat(64)},artifacts:{'research/artifacts/filing-development/synthetic.json':'c'.repeat(64)},model_details:{model_id:'synthetic/model',revision:'f'.repeat(40),generation:{},runtime:{},verification:{receipt_path:'research/artifacts/filing-development/runs/filingdev-synthetic-ui-only/model-verification.json',verified_at:'2026-11-05T23:59:00Z',stage:'post_prediction_pre_scoring',current_assets_checked_on_request:false}},baseline:{record_sha256:'d'.repeat(64),run_id:'filing-synthetic'},new_evaluation:{manifest_path:'research/artifacts/filing-development/sealed-evaluation/initial/manifest.json',status:'sealed',content_accessed:false,documents:['000333','601318','600887'].map(symbol=>({symbol,name:'合成封存公司',period:'2025Q1',status:'sealed'}))},human_review:{manifest_path:'docs/research/human-review/synthetic/manifest.json',checklist_path:'docs/research/human-review/synthetic/checklist.csv',guide_path:'docs/research/human-review/synthetic/guide.md',item_count:18,completed:0,status:'pending_human_review'},limitations:['合成开发夹具，不是新评估']}};
}

afterEach(()=>vi.unstubAllGlobals());
describe('D30 readonly publication client',()=>{
 it('accepts fixed development rows and coherent counts',()=>expect(validateFilingDevelopment(fixture()).record?.rows).toHaveLength(36));
 it('preserves original reference pages without adding a prediction metric',()=>{
  const body=fixture(),variant=validateFilingDevelopment(body).record!.rows[0].reference.variants[0];expect(variant).not.toHaveProperty('metric');expect(variant).toMatchObject({unit_evidence_pages:[1,2],scope_evidence_pages:[2,5]});
  for(const pages of [[0],[2,2],['2']]){const changed=fixture();(changed.record!.rows[0].reference.variants[0] as unknown as Record<string,unknown>).scope_evidence_pages=pages;expect(()=>validateFilingDevelopment(changed)).toThrow();}
 });
 it('accepts explicit empty and missing states without presenting them as verified',()=>{
  expect(validateFilingDevelopment({record:null,record_sha256:null,artifact_status:'empty',missing_artifacts:[]}).record).toBeNull();
  const body=fixture();body.artifact_status='missing';body.missing_artifacts=['missing.json'];expect(validateFilingDevelopment(body).artifact_status).toBe('missing');
 });
 it('rejects another split, companies, duplicated rows and forged denominators',()=>{
  for(const mutate of [(b:DevelopmentEnvelope)=>b.record!.documents[0].period='2025Q1' as '2024Q1',(b:DevelopmentEnvelope)=>b.record!.documents[0].symbol='000333',(b:DevelopmentEnvelope)=>b.record!.rows[1]=structuredClone(b.record!.rows[0]),(b:DevelopmentEnvelope)=>b.record!.metrics[0].total=8]){const body=fixture();mutate(body);expect(()=>validateFilingDevelopment(body)).toThrow();}
 });
 it('recomputes summary values and rejects contradictory format and checks',()=>{
  for(const mutate of [(b:DevelopmentEnvelope)=>b.record!.metrics[0].numeric_correct=8,(b:DevelopmentEnvelope)=>b.record!.metrics[2].candidate_covered=8,(b:DevelopmentEnvelope)=>b.record!.rows[0].checks.numeric=false,(b:DevelopmentEnvelope)=>b.record!.rows[0].status='invalid_output']){const body=fixture();mutate(body);expect(()=>validateFilingDevelopment(body)).toThrow();}
 });
 it('requires all new-company entries sealed or failed, content unopened and human work pending',()=>{
  for(const mutate of [(b:DevelopmentEnvelope)=>b.record!.new_evaluation.content_accessed=true as false,(b:DevelopmentEnvelope)=>b.record!.human_review.completed=18,(b:DevelopmentEnvelope)=>b.record!.new_evaluation.documents[0].symbol='600519']){const body=fixture();mutate(body);expect(()=>validateFilingDevelopment(body)).toThrow();}
 });
 it('does not claim current model assets were rechecked for a page request',()=>{
  const body=fixture();(body.record!.model_details as unknown as Record<string,unknown>).verification={receipt_path:'synthetic-receipt.json',verified_at:'2026-11-06T00:00:00Z',stage:'post_prediction_pre_scoring',current_assets_checked_on_request:true};expect(()=>validateFilingDevelopment(body)).toThrow();
 });
 it('does not turn invalid output into a numeric error in a reusable report',()=>{
  const body=fixture(),r=body.record!;for(const row of r.rows.filter(row=>row.method==='single_free')){row.status='invalid_output';row.prediction=null;for(const key of Object.keys(row.checks))row.checks[key]=false;row.error_reasons=['synthetic invalid JSON'];}
  const score=r.metrics.find(m=>m.method==='single_free')!;for(const key of ['format_valid','answered','numeric_correct','unit_correct','currency_correct','period_correct','scope_correct','evidence_correct','complete_correct'] as const)score[key]=0;
  validateFilingDevelopment(body);const report=developmentReport(body);expect(report).toContain('未形成可核验记录');expect(report).toContain('未能核验');expect(report).toContain('不代表模型未识别出任何数字');expect(report).toContain('2024开发验证，共9字段；不是新评估');expect(report).toContain(body.record_sha256);expect(report).toContain('待人工核验：0/18');expect(report).not.toContain('example.org');
 });
 it('explains a failed amount/unit pair without asserting the unit name is wrong',()=>{
  const body=fixture(),r=body.record!,row=r.rows.find(v=>v.method==='single_constrained')!;row.prediction!.value='11.30';row.checks.numeric=false;row.checks.unit=false;row.checks.complete=false;row.error_reasons=['原始显示单位不一致'];const score=r.metrics.find(v=>v.method==='single_constrained')!;score.numeric_correct=8;score.unit_correct=8;score.complete_correct=8;
  expect(row.prediction!.unit).toBe(row.reference.variants[0].unit);validateFilingDevelopment(body);expect(developmentReason(row.error_reasons[0])).toBe('金额与原单位的配对未通过');const report=developmentReport(body);expect(report).toContain('单位项按金额/原单位配对核验');expect(report).toContain('金额与原单位的配对未通过');expect(report).not.toContain('原始显示单位不一致');expect(row.error_reasons[0]).toBe('原始显示单位不一致');
 });
 it('downloads only fixed checklist and guide endpoints',()=>{
  expect(reviewDownloadUrl('checklist')).toBe('/api/v1/filing-development/review?file=checklist');expect(reviewDownloadUrl('guide')).toBe('/api/v1/filing-development/review?file=guide');
 });
 it('validates review download responses before creating a file',async()=>{
  const fetcher=vi.fn().mockResolvedValueOnce(new Response('item_id,value\n1,\n',{status:200}));vi.stubGlobal('fetch',fetcher);
  expect(await (await readFilingReview('checklist')).text()).toContain('item_id');expect(fetcher).toHaveBeenCalledWith(reviewDownloadUrl('checklist'),expect.objectContaining({cache:'no-store'}));
  fetcher.mockResolvedValueOnce(new Response(JSON.stringify({message:'人工包来源已变化'}),{status:409}));await expect(readFilingReview('guide')).rejects.toThrow('人工包来源已变化');
 });
 it('uses no-store and propagates backend or transport errors',async()=>{
  const fetcher=vi.fn().mockResolvedValue({ok:true,json:async()=>fixture()});vi.stubGlobal('fetch',fetcher);await readFilingDevelopment();expect(fetcher).toHaveBeenCalledWith('/api/v1/filing-development',expect.objectContaining({cache:'no-store'}));
  fetcher.mockResolvedValueOnce({ok:false,json:async()=>({message:'来源已经变化'})});await expect(readFilingDevelopment()).rejects.toThrow('来源已经变化');
  fetcher.mockRejectedValueOnce(new TypeError('offline'));await expect(readFilingDevelopment()).rejects.toThrow('暂不可用');
 });
 it('rejects a late response after its context was aborted',async()=>{
  let release!:(v:unknown)=>void;vi.stubGlobal('fetch',()=>new Promise(resolve=>{release=resolve;}));const controller=new AbortController(),pending=readFilingDevelopment(controller.signal);controller.abort();release({ok:true,json:async()=>fixture()});await expect(pending).rejects.toMatchObject({name:'AbortError'});
 });
});
