"""Freeze public inputs and method outputs, then independently score D29."""
import argparse,json,os,re,tempfile
from datetime import datetime,timezone
from pathlib import Path
from research.market.common import PROJECT,file_sha,digest,write_json
from research.filing_extraction.common import ROOT,CONFIG,METRICS,LABELS,NAMES,UNITS,rel,load_corpus,verify_artifacts
from research.filing_extraction.model import parse_output
from research.filing_extraction.score import score_field,summarize,error_reasons,quoted

def now():return datetime.now(timezone.utc).isoformat()
def source_files():return {rel(p):file_sha(p) for p in sorted([*Path(__file__).parent.glob('*.py'),PROJECT/'research/market/common.py'])}
def require(value,message):
 if not value:raise ValueError(message)

def validate_reference(reference,inputs):
 require(reference['schema']=='filing-extraction-reference-v1' and reference['status']=='assistant_visual_reference_pending_human_audit','Reference status mismatch')
 docs={d['doc_id']:d for d in inputs['documents']};refs=reference['documents']
 require(len(refs)==len(docs) and {d['doc_id'] for d in refs}==set(docs),'Reference document set differs')
 for item in refs:
  doc=docs[item['doc_id']];require(item['pdf_sha256']==doc['pdf_sha256'],'Reference PDF differs')
  require(len(item['fields'])==3 and {f['metric'] for f in item['fields']}==set(METRICS),'Reference field set differs')
  for field in item['fields']:
   require(field['status'] in ('verified','unavailable','ambiguous') and type(field['input_context_complete']) is bool,'Invalid reference qualification')
   require(isinstance(field['variants'],list),'Invalid variants')
   if field['status']=='verified':require(bool(field['variants']),'Verified field has no evidence')
   for variant in field['variants']:
    require(variant['unit'] in UNITS and variant['currency']=='CNY' and variant['period']==doc['period'] and variant['scope']=='consolidated','Reference target differs')
    require(quoted(variant,variant,doc,field['metric']),'Reference quote/value not grounded in shared input: '+doc['doc_id']+'/'+field['metric'])

def validate_predictions(body,inputs):
 docs={d['doc_id'] for d in inputs['documents']};rows=body['predictions']
 require(len(rows)==len(docs) and {r['doc_id'] for r in rows}==docs,'Prediction document set differs')
 for row in rows:
  require(row['status'] in ('ok','invalid_output','input_too_long','error'),'Unknown prediction status')
  if row['status']=='ok':
   parse_output(json.dumps({'fields':row['fields']}))
   require(parse_output(row['raw_output'])==row['fields'],'Structured predictions differ from raw generation')
  else:
   require(row['fields']==[],'Failed output contains accepted predictions')
   if row['status']=='invalid_output':
    try:parse_output(row['raw_output'])
    except ValueError:pass
    else:raise ValueError('Valid output incorrectly labelled as invalid')

def validate_reference_provenance(reference,corpus,corpus_sha,reference_path):
 require(reference['corpus_manifest_sha256']==corpus_sha,'Reference corpus differs')
 docs={d['doc_id']:d for d in corpus['documents']};expected=set()
 for item in reference['documents']:
  pages=item['reviewed_pages'];doc=docs[item['doc_id']]
  require(isinstance(pages,list) and pages==sorted(set(pages)) and all(type(p) is int and 1<=p<=doc['page_count'] for p in pages),'Invalid reviewed page set')
  expected.update(rel(Path(reference_path).parent/item['doc_id']/f'page-{p}.png') for p in pages)
  for field in item['fields']:
   evidence_pages=set()
   for variant in field['variants']:
    require(bool(variant['unit_evidence_pages']) and bool(variant['scope_evidence_pages']),'Missing context evidence')
    evidence_pages.update([variant['page'],*variant['unit_evidence_pages'],*variant['scope_evidence_pages']])
   require(evidence_pages<=set(pages),'Evidence page was not reviewed')
   require(not field['input_context_complete'] or bool(evidence_pages) and evidence_pages<=set(range(1,7)),'Context coverage overclaimed')
 require(set(reference['artifacts'])==expected,'Reviewed page image manifest differs')

def check_prediction_binding(body,protocol,method):
 require(body['inputs_sha256']==protocol['inputs_sha256'],'Prediction input mismatch')
 if method=='model':require(body['model_manifest_sha256']==protocol['model_manifest_sha256'],'Prediction model mismatch')
 require(bool(body['source_sha256']),'Missing prediction source fingerprint')
 bound={}
 for name,sha in body['source_sha256'].items():
  path=Path(name);name=rel(path) if path.is_absolute() else path.as_posix()
  require(protocol['sources'].get(name)==sha,'Prediction code mismatch');bound[name]=sha
 require('research/filing_extraction/'+('model.py' if method=='model' else 'rules.py') in bound,'Missing extractor fingerprint')

def prepare(corpus_path,reference_path,model_path,attempt):
 require(re.fullmatch(r'[a-zA-Z0-9_-]{1,40}',attempt),'Invalid attempt')
 corpus_path,reference_path,model_path=map(lambda p:Path(p).resolve(),(corpus_path,reference_path,model_path))
 require(reference_path.is_relative_to(ROOT.resolve()/'reference') and model_path.is_relative_to(ROOT.resolve()/'model'),'Input manifest path outside owned roots')
 corpus,inputs=load_corpus(corpus_path);config=json.loads(CONFIG.read_text('utf8'))
 require(config['input_physical_pages']==6 and config['symbols']==['600519','600036','600585'] and config['metrics']==list(METRICS),'Frozen design mismatch')
 # Only hash the sealed reference here; extractors never receive its content.
 reference_sha=file_sha(reference_path);model=json.loads(model_path.read_text('utf8'))
 require(model['model_id']==config['model_id'] and model['revision']==config['model_revision'],'Model identity mismatch')
 require(model['files']['model.safetensors']['sha256']==config['model_weight_sha256'],'Model weight identity mismatch')
 sources=source_files()
 protocol={'schema':'filing-extraction-protocol-v1','attempt':attempt,'design':config,'design_sha256':file_sha(CONFIG),
  'corpus_path':rel(corpus_path),'corpus_sha256':file_sha(corpus_path),'reference_path':rel(reference_path),'reference_sha256':reference_sha,
  'model_manifest_path':rel(model_path),'model_manifest_sha256':file_sha(model_path),'inputs_sha256':None,'sources':sources}
 # Serialized bytes are produced once and then shared unchanged by both methods.
 public=ROOT/'inputs'/('inputs-'+digest(inputs)+'.json');write_json(public,inputs)
 protocol.update(inputs_path=rel(public),inputs_sha256=file_sha(public))
 run_id='filing-'+digest(protocol);run=ROOT/'runs'/run_id
 write_json(run/'protocol.json',protocol)
 for name,sha in sources.items():
  path=run/'source-code'/name;path.parent.mkdir(parents=True,exist_ok=True);raw=(PROJECT/name).read_bytes()
  require(file_sha(PROJECT/name)==sha,'Source changed before registration')
  if path.exists():require(path.read_bytes()==raw,'Old code snapshot changed')
  else:
   with path.open('xb') as stream:stream.write(raw)
 write_json(run/'design.json',config)
 design_source=run/'design-source.json';raw=CONFIG.read_bytes()
 require(file_sha(CONFIG)==protocol['design_sha256'],'Design source changed during registration')
 if design_source.exists():require(design_source.read_bytes()==raw,'Design source snapshot changed')
 else:
  with design_source.open('xb') as stream:stream.write(raw)
 registration=run/'registration.json'
 if not registration.exists():write_json(registration,{'run_id':run_id,'registered_at':now(),'protocol_sha256':digest(protocol),'reference_status':'sealed_before_predictions'})
 verify_run(run)
 print(json.dumps({'run_id':run_id,'run_path':str(run),'input_path':str(public),'reference_sha256':reference_sha},ensure_ascii=False),flush=True)
 return run

def verify_run(run):
 run=Path(run).resolve();require(run.is_relative_to(ROOT.resolve()/'runs'),'Unsafe run path')
 protocol=json.loads((run/'protocol.json').read_text('utf8'));require(run.name=='filing-'+digest(protocol),'Run identity mismatch')
 require(json.loads((run/'registration.json').read_text('utf8'))['protocol_sha256']==digest(protocol),'Registration differs')
 for pathkey,shakey in [('corpus_path','corpus_sha256'),('reference_path','reference_sha256'),('model_manifest_path','model_manifest_sha256'),('inputs_path','inputs_sha256')]:
  path=PROJECT/protocol[pathkey];require(path.resolve().is_relative_to(ROOT.resolve()) and file_sha(path)==protocol[shakey],'Frozen input changed: '+pathkey)
 for name,sha in protocol['sources'].items():
  require(file_sha(PROJECT/name)==sha and file_sha(run/'source-code'/name)==sha,'Frozen source changed: '+name)
 corpus,inputs=load_corpus(PROJECT/protocol['corpus_path'])
 require(json.loads((PROJECT/protocol['inputs_path']).read_text('utf8'))==inputs,'Shared inputs differ from source PDF text')
 require(json.loads((run/'design.json').read_text('utf8'))==protocol['design'],'Design snapshot differs')
 require(file_sha(run/'design-source.json')==protocol['design_sha256'] and json.loads((run/'design-source.json').read_text('utf8'))==protocol['design'],'Original design bytes differ')
 return protocol,corpus,inputs

def freeze_predictions(run):
 run=Path(run);protocol,_,inputs=verify_run(run);files={}
 for method in ('rule','model'):
  path=run/(method+'-predictions.json');body=json.loads(path.read_text('utf8'))
  validate_predictions(body,inputs);check_prediction_binding(body,protocol,method);files[path.name]=file_sha(path)
 stage=run/'frozen-predictions.json'
 if stage.exists():
  old=json.loads(stage.read_text('utf8'));require(old['protocol_sha256']==digest(protocol) and old['files']==files,'Existing frozen outputs changed')
 else:write_json(stage,{'frozen_at':now(),'protocol_sha256':digest(protocol),'files':files})
 return files

def predict(run):
 from research.filing_extraction.rules import run_rules
 from research.filing_extraction.model import run_model
 run=Path(run);protocol,_,inputs=verify_run(run)
 if (run/'frozen-predictions.json').exists():return freeze_predictions(run)
 for method in ('rule','model'):
  output=run/(method+'-predictions.json')
  if not output.exists():
   if method=='rule':run_rules(PROJECT/protocol['inputs_path'],output)
   else:run_model(PROJECT/protocol['inputs_path'],output,PROJECT/protocol['model_manifest_path'])
  body=json.loads(output.read_text('utf8'));validate_predictions(body,inputs);check_prediction_binding(body,protocol,method);verify_run(run)
 return freeze_predictions(run)

def atomic_latest(path,body):
 path.parent.mkdir(parents=True,exist_ok=True);fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.filing-')
 try:
  with os.fdopen(fd,'w',encoding='utf8') as stream:
   json.dump(body,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
  os.replace(temp,path)
 finally:Path(temp).unlink(missing_ok=True)

def publish(run):
 run=Path(run);protocol,corpus,inputs=verify_run(run)
 frozen=json.loads((run/'frozen-predictions.json').read_text('utf8'));require(frozen['protocol_sha256']==digest(protocol),'Frozen output protocol differs')
 require(set(frozen['files'])=={'rule-predictions.json','model-predictions.json'},'Output stage incomplete')
 bodies={}
 for method in ('rule','model'):
  path=run/(method+'-predictions.json');require(file_sha(path)==frozen['files'][path.name],'Frozen predictions changed')
  body=json.loads(path.read_text('utf8'));validate_predictions(body,inputs);check_prediction_binding(body,protocol,method);bodies[method]=body
 # First reference content read in the production pipeline occurs after output freezing.
 reference_path=PROJECT/protocol['reference_path'];reference=json.loads(reference_path.read_text('utf8'))
 validate_reference(reference,inputs);validate_reference_provenance(reference,corpus,protocol['corpus_sha256'],reference_path);verify_artifacts(reference['artifacts'])
 refs={d['doc_id']:d for d in reference['documents']};rows=[]
 for doc in inputs['documents']:
  refdoc=refs[doc['doc_id']]
  for metric in METRICS:
   ref=next(f for f in refdoc['fields'] if f['metric']==metric)
   for method in ('rule','model'):
    output=next(r for r in bodies[method]['predictions'] if r['doc_id']==doc['doc_id']);pred=next((f for f in output['fields'] if f['metric']==metric),None)
    checks=score_field(pred,ref,doc,metric,output['status'])
    rows.append({'doc_id':doc['doc_id'],'split':doc['split'],'metric':metric,'label':LABELS[metric],'method':method,'prediction':pred,'status':output['status'],'reference':ref,'checks':checks,'error_reasons':error_reasons(checks,output['status'],ref)})
 documents=[]
 for d in corpus['documents']:
  doc=next(x for x in inputs['documents'] if x['doc_id']==d['doc_id']);ref=refs[d['doc_id']]
  documents.append({**d,'name':NAMES[d['symbol']],'input_pages':[p['page'] for p in doc['pages']],'input_sha256':digest(doc),'coverage':{'reference_verified':sum(f['status']=='verified' for f in ref['fields']),'context_complete':sum(f['input_context_complete'] for f in ref['fields'])}})
 artifacts={**corpus['artifacts'],**reference['artifacts']}
 for path in [PROJECT/protocol['corpus_path'],reference_path,PROJECT/protocol['model_manifest_path'],PROJECT/protocol['inputs_path']]+[p for p in run.rglob('*') if p.is_file()]:artifacts[rel(path)]=file_sha(path)
 verify_artifacts(artifacts)
 model=bodies['model'];run_id=run.name;archive=PROJECT/'backend/data/filing-extraction'/(run_id+'.json')
 created=now() if not archive.exists() else json.loads(archive.read_text('utf8'))['record']['created_at']
 record={'schema':'filing-extraction-publication-v1','run_id':run_id,'created_at':created,'protocol':protocol,'sources':protocol['sources'],'artifacts':artifacts,'documents':documents,
  'methods':[{'id':'rule','label':'固定规则抽取','description':'字段别名＋当期首列＋原文单位；拒绝不明确匹配。'},
   {'id':'model','label':'本地预训练指令模型','description':'冻结Qwen2.5-1.5B-Instruct；未进行金融微调。','model_id':model['model_id'],'revision':model['revision']}],
  'metrics':summarize(rows),'rows':rows,'reference_status':reference['status'],'model_status':'completed',
  'input_sha256':protocol['inputs_sha256'],'reference_sha256':protocol['reference_sha256'],'prediction_sha256':{m:frozen['files'][m+'-predictions.json'] for m in bodies},
  'model_details':{k:model[k] for k in ('model_id','revision','generation','runtime','model_manifest_sha256')},
  'limitations':['固定三公司各两份季报，开发/评估各9字段；同公司跨年先导，不代表公司外泛化，字段不是独立统计样本。',
   '双方使用相同PDF前6物理页文本；不是OCR、全文检索或收益预测，输入不足与输出失败都保留。',
   '参考由助手逐页核对，仍待金融同学/人工复核，不能称专家金标准或人类标注一致率。',
   '期间与合并范围是查询约束，相关分数只表示口径一致性；部分工业报告的合并范围需前6页之外的报表确认。',
   '完整正确要求原金额/单位/币种/期间/范围和有效原文引用均正确；固定分母包含拒答、缺页和格式失败，不作显著胜负结论。',
   '官方固定模型可能见过公开历史材料，发布日期与固定版本不能证明无预训练重叠。',
   'Qwen本轮仅进行冻结推理，没有微调或付费API；规则不会补写模型答案。',
   '接口校验发布证据、输入、原始输出与离线模型校验收据，不在每次网页请求中重复加载或散列3GB权重。']}
 verify_run(run);verify_artifacts(artifacts)
 envelope={'record':record,'sha256':digest(record)};write_json(archive,envelope);atomic_latest(archive.parent/'latest.json',envelope)
 print(json.dumps({'run_id':run_id,'record_sha256':envelope['sha256'],'metrics':record['metrics']},ensure_ascii=False),flush=True)
 return envelope

if __name__=='__main__':
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='stage',required=True)
 p=sub.add_parser('prepare');p.add_argument('--corpus',type=Path,required=True);p.add_argument('--reference',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--attempt',required=True)
 for stage in ('predict','freeze-predictions','publish'):
  p=sub.add_parser(stage);p.add_argument('--run',type=Path,required=True)
 args=parser.parse_args()
 if args.stage=='prepare':prepare(args.corpus,args.reference,args.model,args.attempt)
 elif args.stage=='predict':predict(args.run)
 elif args.stage=='freeze-predictions':freeze_predictions(args.run)
 else:publish(args.run)
