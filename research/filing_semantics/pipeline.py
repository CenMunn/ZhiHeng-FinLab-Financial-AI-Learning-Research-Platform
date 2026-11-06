"""D31 prepare -> GPU predict/freeze -> score -> method freeze, no old result edits."""
import argparse
import os
import tempfile
from research.filing_semantics.common import *
from research.filing_semantics.model import run_predictions,validate_outputs,refusal,options,prompt_for
from research.filing_semantics.score import checks_for,summarize,reasons
from research.filing_extraction.download_model import verify_model

PUBLIC=PROJECT/'backend/data/filing-semantics'
DEV_REFERENCE=PROJECT/'research/artifacts/filing-development/references/development-177cc3d594b920f91ae4b52a9d544237c3261c93b2e6fcfdde01e9341fd986cc.json'
LIMITATIONS=['助手视觉参考待金融同学审计，不是专家金标；本轮无金融微调。',
 '格式、类型/列筛选和来源金额/单位复制属于规则贡献；模型只选择合格候选或拒答。',
 '期间与合并范围是给定查询约束；后页范围证据不自动加入模型前6页输入。',
 '每组仅三公司九字段，不足以证明稳定泛化；所有拒答和错误保留在分母。',
 '布局行引用由原PDF字词坐标绑定，不等同于旧D29连续文本锚定评分。',
 '网页校验离线模型资产收据，不在每次GET读取3GB权重或保证当前GPU可重跑。']

def prepare(corpus_path,attempt,reference_path=None,freeze_path=None):
    from research.filing_semantics.structure import build_cases
    corpus_path=Path(corpus_path).resolve();corpus=read(corpus_path);split=corpus['split']
    require(corpus_path.is_relative_to(ROOT.resolve()/'corpus'),'Unregistered corpus')
    frozen=verify_freeze(freeze_path) if split=='evaluation' else None
    require(split=='development' or corpus['method_freeze_sha256']==frozen['sha256'],'Corpus was not opened under this frozen method')
    require(re.fullmatch('[A-Za-z0-9_-]{1,40}',attempt),'Invalid attempt')
    verify_map(corpus['artifacts']);sources=source_files();cfg=read(CONFIG)
    require({d['symbol'] for d in corpus['documents']}==set(cfg[split+'_symbols']),'Cohort changed')
    cases=[c for d in corpus['documents'] for c in build_cases(d)]
    require(len(cases)==9 and len({c['case_id'] for c in cases})==9,'Missing/duplicate fields')
    inputs={'schema':'filing-semantics-inputs-v1','split':split,'documents':corpus['documents'],'cases':cases}
    input_path=ROOT/'inputs'/('input-'+digest(inputs)+'.json');write_json(input_path,inputs)
    reference_path=Path(reference_path or DEV_REFERENCE).resolve()
    require(reference_path.is_relative_to(PROJECT.resolve()) and reference_path.is_file(),'Reference must be independently prepared before prediction')
    require(split!='evaluation' or reference_path.is_relative_to(ROOT.resolve()/'references/evaluation'),'New-company reference root differs')
    protocol={'schema':'filing-semantics-protocol-v1','split':split,'attempt':attempt,'config':cfg,
       'sources':sources,'corpus_path':rel(corpus_path),'corpus_sha256':file_sha(corpus_path),
       'inputs_path':rel(input_path),'inputs_sha256':file_sha(input_path),
       'reference_path':rel(reference_path),'reference_sha256':file_sha(reference_path),
       'model_manifest_path':rel(MODEL),'model_manifest_sha256':file_sha(MODEL),
       'method_freeze_path':rel(freeze_path) if frozen else None,'method_freeze_sha256':frozen['sha256'] if frozen else None,
       'data_artifacts':{**corpus['artifacts'],rel(corpus_path):file_sha(corpus_path)},
       'pre_prediction_reference_access':'bytes hashed only; contents excluded from public input and prediction'}
    run=ROOT/'runs'/('filingsem-'+digest(protocol));require(not run.exists(),'Existing run retained; fresh attempt required')
    write_json(run/'protocol.json',protocol);write_json(run/'registration.json',{'registered_at':now(),'protocol_sha256':digest(protocol)})
    for name,sha in sources.items():
        target=run/'source-code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((PROJECT/name).read_bytes());require(file_sha(target)==sha,'Source changed while archiving')
    verify_run(run);print(str(run),flush=True);return run

def verify_run(run):
    from research.filing_semantics.structure import build_cases
    run=Path(run).resolve();require(run.is_relative_to(ROOT.resolve()/'runs'),'Unregistered run root')
    p=read(run/'protocol.json');require(run.name=='filingsem-'+digest(p) and read(run/'registration.json')['protocol_sha256']==digest(p),'Run identity differs')
    require(p['sources']==source_files(),'Frozen sources changed; use a new attempt')
    verify_map(p['sources']);verify_map(p['data_artifacts'])
    for name,sha in p['sources'].items():require(file_sha(run/'source-code'/name)==sha,'Archived code changed')
    for key in ('inputs','reference','model_manifest','corpus'):verify_map({p[key+'_path']:p[key+'_sha256']})
    inputs=read(PROJECT/p['inputs_path']);corpus=read(PROJECT/p['corpus_path'])
    require(inputs['documents']==corpus['documents'] and inputs['cases']==[c for d in corpus['documents'] for c in build_cases(d)],'Public inputs differ from reconstructed source layout')
    if p['split']=='evaluation':require(verify_freeze(PROJECT/p['method_freeze_path'])['sha256']==p['method_freeze_sha256'],'Method freeze differs')
    return p,inputs

def tokenizer_for(p):
    from transformers import AutoTokenizer
    return AutoTokenizer.from_pretrained((PROJECT/p['model_manifest_path']).parent,local_files_only=True,trust_remote_code=False)

def predict(run):
    run=Path(run);p,inputs=verify_run(run);require(not (run/'frozen-predictions.json').exists(),'Predictions already frozen; no overwrite')
    rule=[]
    for c in inputs['cases']:
        f=c.get('rule_field') or refusal(c['metric'])
        rule.append({'case_id':c['case_id'],'method':'structure_rule','status':'ok','field':f,
              'raw_output':json.dumps(f,ensure_ascii=False),'selected_candidate_ids':[x['candidate_id'] for x in c['candidates'] if x['field']==f and x['candidate_id'] in c['eligible_ids']],
              'input_tokens':None,'output_tokens':None,'latency_seconds':None})
    write_json(run/'structure_rule-predictions.json',{'schema':'filing-semantics-predictions-v1','method':'structure_rule',
               'created_at':now(),'inputs_sha256':p['inputs_sha256'],'predictions':rule})
    model=run_predictions(PROJECT/p['inputs_path'],PROJECT/p['model_manifest_path'],run,p['config']['generation'])
    verify_run(run);validate_outputs(model['predictions'],inputs['cases'],tokenizer_for(p))
    model_assets=verify_model(PROJECT/p['model_manifest_path'])
    write_json(run/'model-verification.json',{'verified_at':now(),'stage':'post_prediction_pre_scoring','model_manifest_sha256':p['model_manifest_sha256'],
        'files':{k:{x:v[x] for x in ('sha256','size')} for k,v in model_assets['files'].items()},'upstream_sha256':model_assets['upstream_sha256'],
        'current_assets_checked_on_request':False})
    frozen={'frozen_at':now(),'protocol_sha256':digest(p),'inputs_sha256':p['inputs_sha256'],
       'files':{m:file_sha(run/(m+'-predictions.json')) for m in METHODS},'model_verification_sha256':file_sha(run/'model-verification.json')}
    write_json(run/'frozen-predictions.json',frozen);return frozen

def verify_prediction_files(run,p):
    run=Path(run);frozen=read(run/'frozen-predictions.json')
    require(frozen['protocol_sha256']==digest(p) and frozen['inputs_sha256']==p['inputs_sha256'],'Frozen prediction identity mismatch')
    require(set(frozen['files'])==set(METHODS),'Incomplete frozen methods')
    for method in METHODS:
        require(file_sha(run/(method+'-predictions.json'))==frozen['files'][method],'Frozen prediction bytes changed')
    require(file_sha(run/'model-verification.json')==frozen['model_verification_sha256'],'Frozen model receipt changed')
    return frozen

def compute_rows(p,inputs,predictions):
    # Consume references only after the caller verifies both frozen outputs.
    ref=read(PROJECT/p['reference_path']);refs={d['doc_id']:{f['metric']:f for f in d['fields']} for d in ref['documents']}
    require(set(refs)=={d['doc_id'] for d in inputs['documents']},'Reference cohort differs')
    rows=[]
    for c in inputs['cases']:
        d=next(d for d in inputs['documents'] if d['doc_id']==c['doc_id']);r=refs[c['doc_id']][c['metric']]
        covered=any(checks_for(x['field'],'ok',r,c,d)['complete'] for x in c['candidates'])
        for m in METHODS:
            require(len(predictions[m]['predictions'])==9 and len({x['case_id'] for x in predictions[m]['predictions']})==9,'Incomplete or duplicate predictions')
            out=next(x for x in predictions[m]['predictions'] if x['case_id']==c['case_id'])
            if m=='structure_rule':require(out['field']==c['rule_field'],'Rule field changed after reconstruction')
            expected_ids=[x['candidate_id'] for x in c['candidates'] if x['candidate_id'] in c['eligible_ids'] and x['field']==out['field']]
            require(out['selected_candidate_ids']==expected_ids,'Selected candidate identity changed')
            checks=checks_for(out['field'],out['status'],r,c,d)
            rows.append({'case_id':c['case_id'],'doc_id':c['doc_id'],'metric':c['metric'],'label':LABELS[c['metric']],
                'method':m,'status':out['status'],'prediction':out['field'],'checks':checks,'reference':r,
                'error_reasons':reasons(checks,out['status']),'selected_candidate_ids':out['selected_candidate_ids'],'candidate_covered':covered,
                **{k:out[k] for k in ('input_tokens','output_tokens','latency_seconds')}})
    return rows

def score(run):
    run=Path(run);p,inputs=verify_run(run);frozen=verify_prediction_files(run,p)
    predictions={}
    for m in METHODS:
        path=run/(m+'-predictions.json');require(file_sha(path)==frozen['files'][m],'Frozen predictions changed');body=read(path)
        require(body['inputs_sha256']==p['inputs_sha256'],'Prediction input mismatch');predictions[m]=body
    validate_outputs(predictions['structure_model']['predictions'],inputs['cases'],tokenizer_for(p))
    verify_model(PROJECT/p['model_manifest_path'])
    require(file_sha(run/'model-verification.json')==frozen['model_verification_sha256'],'Model receipt changed')
    rows=compute_rows(p,inputs,predictions)
    scored={'scored_at':now(),'protocol_sha256':digest(p),'prediction_sha256':frozen['files'],
            'inputs_sha256':p['inputs_sha256'],'reference_sha256':p['reference_sha256'],'rows':rows,'metrics':summarize(rows)}
    write_json(run/'scored.json',scored)
    return publish(run,p,inputs,scored,predictions)

def atomic(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.pointer-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(body,f,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def publish(run,p,inputs,scored,predictions):
    artifacts={**p['data_artifacts'],p['inputs_path']:p['inputs_sha256'],p['reference_path']:p['reference_sha256'],p['model_manifest_path']:p['model_manifest_sha256']}
    ref=read(PROJECT/p['reference_path']);artifacts.update(ref.get('artifacts',{}))
    if p['method_freeze_path']:artifacts[p['method_freeze_path']]=file_sha(PROJECT/p['method_freeze_path'])
    for path in run.rglob('*'):
        if path.is_file():artifacts[rel(path)]=file_sha(path)
    verify_map(artifacts)
    docs=[]
    for d in inputs['documents']:
        docs.append({**{k:d[k] for k in ('doc_id','symbol','name','title','period','split','pdf_path','pdf_sha256','source_url','page_count')},'identity':read(PROJECT/d['identity_path'])})
    record={'schema':'filing-semantics-study-v1','run_id':run.name,'split':p['split'],'created_at':scored['scored_at'],
        'documents':docs,'cases':inputs['cases'],'rows':scored['rows'],'metrics':scored['metrics'],
        'methods':[{'id':'structure_rule','label':'结构规则','description':'唯一一致的合格来源金额才回答；歧义拒答。'},
                   {'id':'structure_model','label':'结构规则＋模型','description':'同一结构证据与合格候选；模型选择来源记录或拒答。'}],
        'model_details':{'model_id':p['config']['model_id'],'revision':p['config']['model_revision'],'generation':p['config']['generation'],
                         'runtime':predictions['structure_model']['runtime'],'verification':read(run/'model-verification.json')},
        'method_freeze_sha256':p['method_freeze_sha256'],'sources':p['sources'],'artifacts':artifacts,
        'prediction_sha256':scored['prediction_sha256'],'input_sha256':p['inputs_sha256'],'reference_sha256':p['reference_sha256'],
        'limitations':LIMITATIONS}
    envelope={'record':record,'sha256':digest(record)};PUBLIC.mkdir(parents=True,exist_ok=True)
    target=PUBLIC/(run.name+'.json');write_json(target,envelope)
    latest=read(PUBLIC/'latest.json') if (PUBLIC/'latest.json').exists() else {'studies':{}}
    latest['studies'][p['split']]={'file':target.name,'sha256':file_sha(target)};latest['updated_at']=now()
    atomic(PUBLIC/'latest.json',latest);print(json.dumps({'run_id':run.name,'split':p['split'],'sha256':envelope['sha256'],'metrics':scored['metrics']},ensure_ascii=False),flush=True)
    return envelope

def freeze(run,challenge_receipt):
    run=Path(run);p,inputs=verify_run(run);require(p['split']=='development','Freeze requires development run')
    scored=read(run/'scored.json');frozen=verify_prediction_files(run,p)
    require(scored['protocol_sha256']==digest(p) and scored['inputs_sha256']==p['inputs_sha256']
        and scored['reference_sha256']==p['reference_sha256'] and scored['prediction_sha256']==frozen['files'],'Scoring identity changed')
    predictions={m:read(run/(m+'-predictions.json')) for m in METHODS}
    validate_outputs(predictions['structure_model']['predictions'],inputs['cases'],tokenizer_for(p))
    expected_rows=compute_rows(p,inputs,predictions)
    require(scored['rows']==expected_rows and scored['metrics']==summarize(expected_rows),'Scored contents differ from independently recomputed frozen outputs')
    published=read(PUBLIC/(run.name+'.json'))
    require(digest(published['record'])==published['sha256'] and published['record']['artifacts'][rel(run/'scored.json')]==file_sha(run/'scored.json'),'Published scoring evidence changed')
    receipt=Path(challenge_receipt).resolve();r=read(receipt)
    require(r['status']=='passed' and r['sources']==p['sources'],'Challenges did not validate this exact method')
    files={rel(x):file_sha(x) for x in run.rglob('*') if x.is_file()}
    files.update({rel(receipt):file_sha(receipt),p['inputs_path']:p['inputs_sha256'],p['reference_path']:p['reference_sha256']})
    identity={'development_run':run.name,'sources':p['sources'],'artifacts':files,'config_sha256':file_sha(CONFIG),
        'model_manifest_sha256':p['model_manifest_sha256'],'sealed_manifest_sha256':file_sha(SEALED),
        'evaluation_cohort':read(CONFIG)['evaluation_symbols'],'reference_status':'assistant_visual_reference_pending_human_audit'}
    body={'schema':'filing-semantics-method-freeze-v1','frozen_at':now(),'sha256':digest(identity),'identity':identity}
    target=ROOT/'freezes'/(body['sha256']+'.json');write_json(target,body);verify_freeze(target);print(str(target),flush=True);return target

if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='stage',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--corpus',type=Path,required=True);prep.add_argument('--attempt',required=True);prep.add_argument('--reference',type=Path);prep.add_argument('--freeze',type=Path)
    for stage in ('predict','score','freeze'):
        cmd=sub.add_parser(stage);cmd.add_argument('--run',type=Path,required=True)
        if stage=='freeze':cmd.add_argument('--challenges',type=Path,required=True)
    a=p.parse_args()
    if a.stage=='prepare':prepare(a.corpus,a.attempt,a.reference,a.freeze)
    elif a.stage=='predict':predict(a.run)
    elif a.stage=='score':score(a.run)
    else:freeze(a.run,a.challenges)
