"""Read-only independent-validation preparation publication. No research imports."""
import hashlib
import json
import re
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash

SYMBOLS = {'600519','600036','600900','600585','600276','BTCUSDT','ETHUSDT'}
SEGMENTS = ('train','early_stopping','calibration','evaluation')
FOLDS = [f'{year}Q{quarter}' for year in (2024,2025) for quarter in (1,2,3,4)]

def require(value):
    if not value: raise ValueError('Invalid validation foundation publication')

def count(value):
    require(type(value) is int and value >= 0)

def strings(value):
    require(isinstance(value,list) and all(isinstance(s,str) for s in value))

def validate(record):
    require(record['schema']=='validation-foundation-v1')
    require(datetime.fromisoformat(record['created_at']).tzinfo is not None)
    require(isinstance(record['protocol'],dict) and bool(record['protocol']))
    require(record['protocol_sha256']==stable_hash(record['protocol']))
    require(record['report_id']=='validation-'+stable_hash({k:record[k] for k in ('protocol_sha256','assets','artifacts')}))
    strings(record['limitations']);require(bool(record['limitations']))
    assets=record['assets'];require(isinstance(assets,list) and len(assets)==7 and {a['symbol'] for a in assets}==SYMBOLS)
    for asset in assets:
        require(asset['market']==('crypto' if asset['symbol'].endswith('USDT') else 'ashare'))
        require(isinstance(asset['name'],str) and isinstance(asset['role'],str))
        require(asset['status'] in ('qualified','rejected'));count(asset['rows'])
        strings(asset['issues']);strings(asset['warnings'])
        require(not asset['issues'] if asset['status']=='qualified' else bool(asset['issues']))
        for key in ('expected','missing','extra'):count(asset['coverage'][key])
        for key in ('dividends','splits'):count(asset['events'][key])
        require(isinstance(asset['source_receipts'],list) and all(isinstance(r,dict) for r in asset['source_receipts']))
        for receipt in asset['source_receipts']:
            name=receipt['file'];require(isinstance(name,str))
            relative=PurePosixPath(name)
            require('\\' not in name and ':' not in name and not relative.is_absolute() and '..' not in relative.parts)
            require(record['artifacts'].get('research/artifacts/validation-data/v1/'+name)==receipt['sha256'])
            require(isinstance(receipt['url'],str) and datetime.fromisoformat(receipt['retrieved_at']).tzinfo is not None)
        folds=asset['folds'];require(isinstance(folds,list))
        require([f['fold'] for f in folds]==FOLDS if asset['status']=='qualified' else not folds)
        for fold in folds:
            previous=None
            require(set(fold['bounds'])==set(SEGMENTS))
            for segment in SEGMENTS:
                pair=fold['bounds'][segment];require(isinstance(pair,list) and len(pair)==2)
                start,end=map(date.fromisoformat,pair);require(start<=end and (previous is None or previous<start));previous=end
            require([h['horizon'] for h in fold['horizons']]==[1,5])
            for horizon in fold['horizons']:
                for group in ('counts','purged'):
                    require(set(horizon[group])==set(SEGMENTS))
                    for n in horizon[group].values():count(n)

class ValidationFoundationStore:
    def __init__(self, folder, project):self.folder,self.project=Path(folder),Path(project)
    def get(self, report_id=None):
        if report_id is not None and not re.fullmatch(r'validation-[a-f0-9]{64}', report_id):raise KeyError(report_id)
        path=self.folder/'latest.json' if report_id is None else self.folder/'versions'/(report_id+'.json')
        if not path.exists():raise KeyError('validation-foundation')
        try:
            require(path.resolve().is_relative_to(self.folder.resolve()))
            body=json.loads(path.read_text('utf8'));record=body['record']
            require(stable_hash(record)==body['sha256']);validate(record)
            require(report_id is None or record['report_id']==report_id)
            require(isinstance(record['artifacts'],dict) and bool(record['artifacts']))
            missing=[]
            roots=[(self.project/'research/artifacts'/name).resolve() for name in ('validation-data','validation-foundation')]
            for name,sha in record['artifacts'].items():
                require(isinstance(name,str) and isinstance(sha,str) and re.fullmatch('[a-f0-9]{64}',sha))
                relative=PurePosixPath(name)
                require('\\' not in name and ':' not in name and not relative.is_absolute() and '..' not in relative.parts)
                artifact=(self.project/name).resolve()
                require(any(artifact!=root and artifact.is_relative_to(root) for root in roots))
                if not artifact.exists():missing.append(name)
                else:
                    require(artifact.is_file())
                    with artifact.open('rb') as stream:require(hashlib.file_digest(stream,'sha256').hexdigest()==sha)
            return dict(record=record,record_sha256=body['sha256'],artifact_status='missing' if missing else 'verified',missing_artifacts=sorted(missing))
        except (ValueError,KeyError,TypeError,AttributeError,OSError,OverflowError):
            raise DomainConflict('validation_foundation_corrupt','数据资格与四段准备报告完整性校验失败，未作为有效记录读取。') from None
