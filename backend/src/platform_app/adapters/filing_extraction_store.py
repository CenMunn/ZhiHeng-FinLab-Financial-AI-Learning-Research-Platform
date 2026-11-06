"""Read-only D29 result publication; no inference, label generation, or training."""
import hashlib
import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict

METRICS = {'revenue','net_profit_parent','operating_cashflow'}
CHECKS = ('numeric','unit','currency','period','scope','evidence','complete','answered','correct_abstention')


def require(value):
    if not value:
        raise ValueError('Invalid filing extraction publication')


def valid_hash(value):
    return isinstance(value,str) and re.fullmatch('[a-f0-9]{64}',value)


class FilingExtractionStore:
    def __init__(self, folder, project):
        self.folder, self.project = Path(folder), Path(project)

    def get(self):
        path = self.folder/'latest.json'
        if not path.exists():
            return dict(record=None,record_sha256=None,artifact_status='empty',missing_artifacts=[])
        try:
            require(path.resolve().is_relative_to(self.folder.resolve()))
            body=json.loads(path.read_text('utf8')); r=body['record']; protocol=r['protocol']
            require(stable_hash(r)==body['sha256'])
            require(r['schema']=='filing-extraction-publication-v1')
            require(protocol['schema']=='filing-extraction-protocol-v1' and r['run_id']=='filing-'+stable_hash(protocol))
            require(datetime.fromisoformat(r['created_at']).tzinfo is not None)
            require(isinstance(r['sources'],dict) and r['sources'] and r['sources']==protocol['sources'])
            require(all(valid_hash(v) for v in r['sources'].values()))
            require(r['reference_status']=='assistant_visual_reference_pending_human_audit' and r['model_status']=='completed')
            require(all(valid_hash(r[k]) for k in ('input_sha256','reference_sha256')))
            require(r['input_sha256']==protocol['inputs_sha256'] and r['reference_sha256']==protocol['reference_sha256'])
            require(set(r['prediction_sha256'])=={'rule','model'} and all(valid_hash(v) for v in r['prediction_sha256'].values()))
            docs=r['documents']; require(isinstance(docs,list) and len(docs)==6)
            require(len({d['doc_id'] for d in docs})==6)
            require({(d['symbol'],d['period'],d['split']) for d in docs}=={(symbol,period,split) for symbol in ('600519','600036','600585') for period,split in [('2024Q1','development'),('2025Q1','evaluation')]})
            require({m['id'] for m in r['methods']}=={'rule','model'} and len(r['methods'])==2)
            model=next(m for m in r['methods'] if m['id']=='model')
            require(model['model_id']==protocol['design']['model_id'] and model['revision']==protocol['design']['model_revision'])
            for d in docs:
                require(isinstance(d['doc_id'],str) and isinstance(d['title'],str) and isinstance(d['name'],str))
                require(d['doc_id']==d['symbol']+'-'+d['period'])
                require(d['input_pages']==[1,2,3,4,5,6] and valid_hash(d['input_sha256']))
                require(r['artifacts'].get(d['pdf_path'])==d['pdf_sha256'])
            by_id={d['doc_id']:d for d in docs}; rows=r['rows']
            require(len(rows)==36 and {(v['doc_id'],v['metric'],v['method']) for v in rows}=={(d['doc_id'],metric,method) for d in docs for metric in METRICS for method in ('rule','model')})
            for row in rows:
                require(row['split']==by_id[row['doc_id']]['split'])
                require(row['status'] in ('ok','invalid_output','input_too_long','error'))
                require(all(type(row['checks'][key]) is bool for key in CHECKS))
                require(row['checks']['complete']==all(row['checks'][key] for key in CHECKS[:6]))
                require(row['status']=='ok' or not (row['checks']['answered'] or row['checks']['complete']))
                require(row['reference']['status'] in ('verified','unavailable','ambiguous'))
                require(type(row['reference']['input_context_complete']) is bool and isinstance(row['reference']['variants'],list))
                require(isinstance(row['error_reasons'],list) and all(isinstance(v,str) for v in row['error_reasons']))
                pred=row['prediction']
                if pred is not None:
                    require(isinstance(pred,dict) and pred['metric']==row['metric'])
                    if pred['value'] is not None:
                        require(isinstance(pred['value'],str) and re.fullmatch(r'-?\d+(\.\d+)?',pred['value']) and Decimal(pred['value']).is_finite())
            summary=r['metrics']; require(len(summary)==4 and {(s['split'],s['method']) for s in summary}=={(split,method) for split in ('development','evaluation') for method in ('rule','model')})
            for s in summary:
                group=[row for row in rows if row['split']==s['split'] and row['method']==s['method']]
                counts={'total':len(group),'answered':sum(row['checks']['answered'] for row in group),'abstained':sum(not row['checks']['answered'] for row in group),'correct_abstentions':sum(row['checks']['correct_abstention'] for row in group),'reference_verified':sum(row['reference']['status']=='verified' for row in group),'context_complete':sum(row['reference']['input_context_complete'] for row in group)}
                counts.update({key+'_correct':sum(row['checks'][key] for row in group) for key in CHECKS[:7]})
                require(all(type(s[k]) is int and s[k]==v for k,v in counts.items()))
            require(isinstance(r['limitations'],list) and all(isinstance(v,str) for v in r['limitations']))
            artifacts=r['artifacts']; require(isinstance(artifacts,dict) and artifacts)
            root=(self.project/'research/artifacts/filing-extraction').resolve(); missing=[]
            for name,sha in artifacts.items():
                relative=PurePosixPath(name)
                require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in name and ':' not in name and valid_hash(sha))
                artifact=(self.project/name).resolve(); require(artifact!=root and artifact.is_relative_to(root))
                if not artifact.exists():
                    missing.append(name); continue
                require(artifact.is_file())
                with artifact.open('rb') as source:
                    require(hashlib.file_digest(source,'sha256').hexdigest()==sha)
            return dict(record=r,record_sha256=body['sha256'],artifact_status='missing' if missing else 'verified',missing_artifacts=missing)
        except (ValueError,KeyError,TypeError,AttributeError,OSError,ArithmeticError):
            raise DomainConflict('filing_extraction_corrupt','字段抽取记录或来源完整性校验失败，未展示为有效成绩。') from None

    def document(self, doc_id):
        body=self.get()
        if body['artifact_status']!='verified':
            raise DomainConflict('filing_extraction_missing','字段核验所需来源尚未齐备，暂不能打开原文。')
        doc=next((d for d in body['record']['documents'] if d['doc_id']==doc_id),None)
        if doc is None:
            raise KeyError(doc_id)
        data=(self.project/doc['pdf_path']).read_bytes()
        if hashlib.sha256(data).hexdigest()!=doc['pdf_sha256']:
            raise DomainConflict('filing_extraction_document','原文在读取期间发生变化。')
        return data
