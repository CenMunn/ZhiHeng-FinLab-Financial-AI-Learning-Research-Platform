"""Read-only five-asset publications. Never imports the research/training runtime."""
import hashlib
import json
import math
import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.volatility_results import VolatilityMetrics, VolatilityComparison
from platform_app.adapters.validation_foundation_store import ValidationFoundationStore, require

KEYS={'train_mean','hist20','ewma','garch','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear'}
FOLDS=[f'{y}Q{q}' for y in (2024,2025) for q in (1,2,3,4)]
SOURCE='validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c'
def finite(value, minimum=None):
    require(type(value) in (int,float) and math.isfinite(value) and (minimum is None or value>=minimum))
def model(value, rows):
    require(isinstance(value['name'],str))
    for mode in ('raw','calibrated'):
        m=value[mode]
        if rows==0:require(m is None)
        else:
            require(isinstance(m,dict))
            parsed=VolatilityMetrics.model_validate({k:m[k] for k in VolatilityMetrics.model_fields})
            require(parsed.rows==rows)
    for key in ('raw_vs_ewma','calibrated_vs_ewma','calibrated_vs_raw'):
        c=value[key]
        if rows==0:require(c is None)
        else:
            require(isinstance(c,dict));VolatilityComparison.model_validate({k:c[k] for k in VolatilityComparison.model_fields})
def validate(r):
    require(r['schema']=='five-asset-result-v1' and datetime.fromisoformat(r['created_at']).tzinfo is not None)
    require(r['symbol'] in {'600519','600036','600585','BTCUSDT','ETHUSDT'})
    require(r['market']==('crypto' if r['symbol'].endswith('USDT') else 'ashare'))
    require(type(r['horizon']) is int and r['horizon'] in (1,5) and r['annualization']==(252 if r['market']=='ashare' else 365))
    require(r['source_report_id']==SOURCE and isinstance(r['name'],str))
    identity=dict(protocol_sha256=stable_hash(r['protocol']),source_report_sha256=r['source_report_sha256'],symbol=r['symbol'],horizon=str(r['horizon']))
    require(r['identity']==identity and r['run_id']=='five-'+stable_hash(identity))
    require(set(r['overall'])==KEYS and [f['fold'] for f in r['folds']]==FOLDS)
    rows=r['observations'];require(isinstance(rows,list) and bool(rows))
    dates=[date.fromisoformat(row['session']) for row in rows];require(dates==sorted(set(dates)))
    by_fold=Counter();by_regime=Counter()
    for row,day in zip(rows,dates):
        require(row['fold']==f'{day.year}Q{(day.month-1)//3+1}' and row['fold'] in FOLDS)
        require(date.fromisoformat(row['label_end'])>day and row['regime'] in r['regimes'])
        finite(row['realized_variance'],0)
        for mode in ('raw','calibrated'):
            require(set(row[mode])==KEYS)
            for p in row[mode].values():finite(p,1e-10)
        by_fold[row['fold']]+=1;by_regime[row['regime']]+=1
    require(set(by_fold)==set(FOLDS))
    for m in r['overall'].values():
        model(m,len(rows));require(m['folds']==8)
        for k in ('wins_raw','wins_calibrated'):require(type(m[k]) is int and 0<=m[k]<=8)
    for f in r['folds']:
        require(set(f['models'])==KEYS and f['counts']['evaluation']==by_fold[f['fold']])
        require(isinstance(f['bounds'],dict) and isinstance(f['training'],dict))
        segments={'train','early_stopping','calibration','evaluation'}
        require(set(f['bounds'])==segments and set(f['counts'])==segments)
        previous=None
        for segment in ('train','early_stopping','calibration','evaluation'):
            pair=f['bounds'][segment];require(isinstance(pair,list) and len(pair)==2)
            start,end=map(date.fromisoformat,pair);require(start<=end and (previous is None or previous<start));previous=end
            require(type(f['counts'][segment]) is int and f['counts'][segment]>0)
        lo,hi=map(date.fromisoformat,f['bounds']['evaluation'])
        require(all(lo<=date.fromisoformat(row['session'])<=hi for row in rows if row['fold']==f['fold']))
        for m in f['models'].values():
            model(m,by_fold[f['fold']]);finite(m['c'],.25);require(m['c']<=4);finite(m['raw_c'],0)
            require(type(m['clipped']) is bool and type(m['calibration_rows']) is int and m['calibration_rows']==f['counts']['calibration'])
    for key,g in r['regimes'].items():
        require(type(g['rows']) is int and g['rows']==by_regime[key] and type(g['sufficient']) is bool and g['sufficient']==(g['rows']>=30) and set(g['models'])==KEYS)
        for m in g['models'].values():model(m,g['rows'])
    require(isinstance(r['limitations'],list) and bool(r['limitations']) and all(isinstance(s,str) for s in r['limitations']))
    require(isinstance(r['artifacts'],dict) and bool(r['artifacts']))

class FiveAssetStore:
    def __init__(self,folder,project,source_store=None):
        self.folder,self.project=Path(folder),Path(project)
        self.source=source_store or ValidationFoundationStore(self.project/'backend/data/validation-foundation',self.project)
    def get(self,run_id,*,_verification=None):
        if not re.fullmatch(r'five-[a-f0-9]{64}',run_id):raise KeyError(run_id)
        path=self.folder/(run_id+'.json')
        if not path.exists():raise KeyError(run_id)
        try:
            require(path.resolve().is_relative_to(self.folder.resolve()))
            body=json.loads(path.read_text('utf8'));r=body['record']
            require(stable_hash(r)==body['sha256'] and r['run_id']==run_id);validate(r)
            # Context exists only for this list call; individual GETs always recheck.
            verification=_verification if _verification is not None else {'sources':{},'files':{}}
            sources=verification['sources']
            if r['source_report_id'] not in sources:
                try:sources[r['source_report_id']]=self.source.get(r['source_report_id'])
                except KeyError:sources[r['source_report_id']]=None
            source=sources[r['source_report_id']]
            missing=[]
            if source is None:missing.append('source-report:'+r['source_report_id'])
            else:
                require(source['record_sha256']==r['source_report_sha256']);missing.extend(source['missing_artifacts'])
            root=(self.project/'research/artifacts/five-asset').resolve()
            for name,sha in r['artifacts'].items():
                relative=PurePosixPath(name)
                require('\\' not in name and ':' not in name and not relative.is_absolute() and '..' not in relative.parts and re.fullmatch('[a-f0-9]{64}',sha))
                artifact=(self.project/name).resolve();require(artifact!=root and artifact.is_relative_to(root))
                if not artifact.exists():missing.append(name)
                else:
                    require(artifact.is_file())
                    before=artifact.stat()
                    signature=(before.st_mtime_ns,before.st_size,before.st_ctime_ns,before.st_ino)
                    cached=verification['files'].get(artifact)
                    if cached is None or cached[0]!=signature:
                        with artifact.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
                        after=artifact.stat()
                        require(signature==(after.st_mtime_ns,after.st_size,after.st_ctime_ns,after.st_ino))
                        verification['files'][artifact]=(signature,actual)
                    else:actual=cached[1]
                    require(actual==sha)
            return dict(record=r,record_sha256=body['sha256'],artifact_status='missing' if missing else 'verified',missing_artifacts=sorted(set(missing)))
        except (ValueError,KeyError,TypeError,AttributeError,OSError,OverflowError):
            raise DomainConflict('five_asset_corrupt','五标的实验来源、身份或产物完整性校验失败，未作为有效结果读取。') from None
    def list(self):
        if not self.folder.exists():return []
        result=[];verification={'sources':{},'files':{}}
        for path in self.folder.glob('five-*.json'):
            body=self.get(path.stem,_verification=verification);r=body['record']
            result.append({k:r[k] for k in ('run_id','created_at','symbol','name','market','horizon')}|dict(rows=len(r['observations']),artifact_status=body['artifact_status']))
        return sorted(result,key=lambda r:(datetime.fromisoformat(r['created_at']),r['run_id']),reverse=True)
