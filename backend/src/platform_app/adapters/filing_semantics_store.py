"""D31 read-only publication validation; no research/model runtime import."""
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path,PurePosixPath
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict

METHODS=('structure_rule','structure_model')
CHECKS=('numeric','unit','currency','period','scope','evidence','column','complete')
LABELS={'revenue':'营业收入','net_profit_parent':'归母净利润','operating_cashflow':'经营现金流净额'}
METHOD_DESCRIPTIONS=[{'id':'structure_rule','label':'结构规则','description':'唯一一致的合格来源金额才回答；歧义拒答。'},
 {'id':'structure_model','label':'结构规则＋模型','description':'同一结构证据与合格候选；模型选择来源记录或拒答。'}]
LIMITATIONS=['助手视觉参考待金融同学审计，不是专家金标；本轮无金融微调。',
 '格式、类型/列筛选和来源金额/单位复制属于规则贡献；模型只选择合格候选或拒答。',
 '期间与合并范围是给定查询约束；后页范围证据不自动加入模型前6页输入。',
 '每组仅三公司九字段，不足以证明稳定泛化；所有拒答和错误保留在分母。',
 '布局行引用由原PDF字词坐标绑定，不等同于旧D29连续文本锚定评分。',
 '网页校验离线模型资产收据，不在每次GET读取3GB权重或保证当前GPU可重跑。']
UNITS={'元':Decimal(1),'千元':Decimal(1000),'万元':Decimal(10000),'百万元':Decimal(1000000),'亿元':Decimal(100000000)}
def independent_checks(field,status,reference,case):
    result={k:False for k in ('answered',*CHECKS)}
    result['answered']=status=='ok' and isinstance(field,dict) and field.get('value') is not None
    if not result['answered'] or reference['status']!='verified':return result
    variants=reference['variants']
    try:matches=[v for v in variants if Decimal(field['value'])*UNITS[field['unit']]==Decimal(v['value'])*UNITS[v['unit']]]
    except (ArithmeticError,KeyError,TypeError,ValueError):matches=[]
    result['numeric']=bool(matches);result['unit']=any(field['unit']==v['unit'] for v in matches)
    for key in ('currency','period','scope'):result[key]=any(field.get(key)==v.get(key) for v in variants)
    result['column']=any(c['candidate_id'] in case['eligible_ids'] and c['eligible'] and c['field']==field for c in case['candidates'])
    result['evidence']=result['column'] and any(field['page']==v['page'] and field['unit']==v['unit'] and Decimal(field['value'])==Decimal(v['value']) for v in matches)
    result['complete']=all(result[k] for k in CHECKS if k!='complete')
    return result
def independent_reasons(checks,status):
    if status!='ok':return ['未形成可读取输出：'+status]
    if not checks['answered']:return ['结构或模型拒答；保留在固定9项分母中，等待核验。']
    names={'numeric':'金额/量纲','unit':'金额与原单位配对','currency':'币种','period':'查询期间','scope':'查询合并范围','evidence':'值/页与独立参考','column':'当期金额列来源'}
    return [name+'未通过' for key,name in names.items() if not checks[key]]
def require(value):
    if not value:raise ValueError('Invalid filing semantics publication')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text('utf8'))

class FilingSemanticsStore:
    def __init__(self,folder,project):self.folder,self.project=Path(folder),Path(project).resolve()
    def path(self,name,source=False):
        require(isinstance(name,str) and ':' not in name and '\\' not in name)
        p=PurePosixPath(name);require(not p.is_absolute() and '..' not in p.parts and not any(x.startswith('.') for x in p.parts))
        full=(self.project/name).resolve();require(full.is_relative_to(self.project) and full!=self.project)
        if source:
            allowed=['research/filing_semantics/','research/configs/filing-semantics-v1.json','docs/superpowers/specs/2026-11-07-filing-semantics-design.md',
                     'research/market/common.py','research/filing_development/model.py','research/filing_development/evidence.py',
                     'research/filing_extraction/common.py','research/filing_extraction/download_model.py']
            require(any(name==a or a.endswith('/') and name.startswith(a) and p.suffix=='.py' for a in allowed))
        else:
            require(any(name.startswith(a) for a in ('research/artifacts/filing-semantics/','research/artifacts/filing-extraction/',
                'research/artifacts/filing-development/','docs/research/2026-11-07-filing-semantics')))
        return full
    def _files(self,mapping,missing,source=False):
        require(isinstance(mapping,dict) and mapping)
        for name,expected in mapping.items():
            require(isinstance(expected,str) and re.fullmatch('[a-f0-9]{64}',expected))
            path=self.path(name,source)
            if not path.is_file():missing.add(name)
            else:require(sha(path)==expected)
    def _study(self,body):
        require(body['schema']=='filing-semantics-study-v1' and body['split'] in ('development','evaluation'))
        require(re.fullmatch('filingsem-[a-f0-9]{64}',body['run_id']))
        require(len(body['documents'])==3 and len(body['cases'])==9 and len(body['rows'])==18)
        require({x['method'] for x in body['rows']}==set(METHODS))
        run='research/artifacts/filing-semantics/runs/'+body['run_id']
        protocol=read(self.project/(run+'/protocol.json'))
        require('filingsem-'+stable_hash(protocol)==body['run_id'])
        require(body['sources']==protocol['sources'] and body['split']==protocol['split'])
        require(protocol['config']==read(self.project/'research/configs/filing-semantics-v1.json'))
        require(body['methods']==METHOD_DESCRIPTIONS and body['limitations']==LIMITATIONS)
        for name,expected in protocol['sources'].items():require(body['artifacts'].get(run+'/source-code/'+name)==expected)
        for k in ('inputs','reference'):
            require(body['artifacts'].get(protocol[k+'_path'])==protocol[k+'_sha256'])
        inputs=read(self.project/protocol['inputs_path']);scored=read(self.project/(run+'/scored.json'))
        frozen=read(self.project/(run+'/frozen-predictions.json'))
        require(body['cases']==inputs['cases'] and body['rows']==scored['rows'] and body['metrics']==scored['metrics'])
        require(body['created_at']==scored['scored_at'])
        require(scored['protocol_sha256']==frozen['protocol_sha256']==stable_hash(protocol))
        require(scored['prediction_sha256']==body['prediction_sha256']==frozen['files'])
        require(body['input_sha256']==protocol['inputs_sha256'] and body['reference_sha256']==protocol['reference_sha256'])
        require(scored['inputs_sha256']==body['input_sha256'] and scored['reference_sha256']==body['reference_sha256'])
        docs={d['doc_id']:d for d in inputs['documents']};cases={c['case_id']:c for c in inputs['cases']}
        ref=read(self.project/protocol['reference_path']);refs={d['doc_id']:{f['metric']:f for f in d['fields']} for d in ref['documents']}
        require(set(refs)==set(docs))
        for row in body['rows']:
            c=cases[row['case_id']];reference=refs[c['doc_id']][c['metric']]
            require(row['reference']==reference and row['label']==LABELS[c['metric']])
            require(row['checks']==independent_checks(row['prediction'],row['status'],reference,c))
            require(row['error_reasons']==independent_reasons(row['checks'],row['status']))
            require(row['candidate_covered']==any(independent_checks(x['field'],'ok',reference,c)['complete'] for x in c['candidates']))
        require(len(cases)==9 and len(docs)==3 and {d['doc_id'] for d in body['documents']}==set(docs))
        for d in body['documents']:
            original=docs[d['doc_id']]
            for k in ('doc_id','symbol','name','title','period','split','pdf_path','pdf_sha256','source_url','page_count'):require(d[k]==original[k])
            require(d['identity']==read(self.project/original['identity_path']) and d['identity']['qualified'] is True)
            require(body['artifacts'].get(d['pdf_path'])==d['pdf_sha256'])
        for method in METHODS:
            file=run+'/'+method+'-predictions.json';require(body['artifacts'].get(file)==frozen['files'][method])
            pred=read(self.project/file);require(pred['inputs_sha256']==body['input_sha256'])
            if method=='structure_model':
                details=body['model_details'];config=protocol['config']
                require(details['runtime']==pred['runtime'] and details['generation']==pred['generation']==config['generation'])
                require(details['model_id']==config['model_id']=='Qwen/Qwen2.5-1.5B-Instruct'
                    and details['revision']==config['model_revision']=='989aa7980e4cf806f80c7fef2b1adb7bc71aa306')
                require(pred['model_manifest_sha256']==protocol['model_manifest_sha256'])
            require(len(pred['predictions'])==9 and len({r['case_id'] for r in pred['predictions']})==9)
            for out in pred['predictions']:
                case=cases[out['case_id']];row=next(r for r in body['rows'] if r['case_id']==out['case_id'] and r['method']==method)
                require(row['prediction']==out['field'] and row['status']==out['status'] and row['selected_candidate_ids']==out['selected_candidate_ids'])
                for key in ('input_tokens','output_tokens','latency_seconds'):require(row[key]==out[key])
                require(row['doc_id']==case['doc_id'] and row['metric']==case['metric'])
                if method=='structure_rule':require(out['field']==case['rule_field'])
                elif out['status']=='ok':
                    require(json.loads(out['raw_output'])==out['field'] and out['raw_output'] in out['options'])
                    require(out['field']['value'] is None or any(c['candidate_id'] in case['eligible_ids'] and c['field']==out['field'] for c in case['candidates']))
            group=[r for r in body['rows'] if r['method']==method];require(len(group)==9 and len({r['case_id'] for r in group})==9)
            expected={'method':method,'total':9,'format_valid':sum(r['status']=='ok' for r in group),'answered':sum(r['checks']['answered'] for r in group),
                      'abstained':sum(not r['checks']['answered'] for r in group),'candidate_covered':sum(r['candidate_covered'] for r in group)}
            for k in CHECKS:expected[k+'_correct']=sum(r['checks'][k] for r in group)
            require(expected==next(m for m in body['metrics'] if m['method']==method))
        receipt=run+'/model-verification.json';require(body['artifacts'].get(receipt)==frozen['model_verification_sha256'])
        require(body['model_details']['verification']==read(self.project/receipt))
        require(body['method_freeze_sha256']==protocol['method_freeze_sha256'])
        if body['split']=='evaluation':
            f=read(self.project/protocol['method_freeze_path']);require(stable_hash(f['identity'])==f['sha256']==body['method_freeze_sha256'])
    def get(self):
        empty={'artifact_status':'empty','record':None,'sha256':None,'missing_artifacts':[],'verified_artifacts':0}
        if not (self.folder/'latest.json').exists():return empty
        try:
            index=read(self.folder/'latest.json');require(set(index['studies']).issubset({'development','evaluation'}) and index['studies'])
            studies=[];missing=set();verified=set()
            for split,entry in sorted(index['studies'].items()):
                require(re.fullmatch(r'filingsem-[a-f0-9]{64}\.json',entry['file']))
                path=self.folder/entry['file']
                if not path.is_file():missing.add(str(path.relative_to(self.project)));continue
                require(sha(path)==entry['sha256']);envelope=read(path);body=envelope['record']
                require(stable_hash(body)==envelope['sha256'] and body['split']==split)
                self._files(body['artifacts'],missing);self._files(body['sources'],missing,True)
                verified.update(body['artifacts']);verified.update(body['sources']);studies.append(body)
            if missing:return {**empty,'artifact_status':'missing','missing_artifacts':sorted(missing)}
            for body in studies:self._study(body)
            record={'schema':'filing-semantics-publication-v1','created_at':index['updated_at'],'studies':studies,
                    'limitations':studies[0]['limitations']}
            return {'artifact_status':'verified','record':record,'sha256':stable_hash(record),'missing_artifacts':[],'verified_artifacts':len(verified)}
        except (OSError,ValueError,KeyError,TypeError,StopIteration,AttributeError,ArithmeticError) as error:
            raise DomainConflict('filing_semantics_changed','财务语义校验来源或封存记录不一致，暂不展示成绩。') from error
    def pdf(self,doc_id):
        body=self.get()
        if body['artifact_status']=='missing':raise DomainConflict('filing_semantics_missing','财务语义校验来源缺失，暂不打开原文。')
        for study in (body['record'] or {}).get('studies',[]):
            for doc in study['documents']:
                if doc['doc_id']==doc_id:return self.path(doc['pdf_path']).read_bytes()
        raise KeyError(doc_id)
