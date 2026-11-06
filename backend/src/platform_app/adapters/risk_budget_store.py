"""Verified read-only D26 publication and pure account replay adapter."""
import hashlib
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path,PurePosixPath
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from platform_app.adapters.validation_foundation_store import ValidationFoundationStore,require
from platform_app.experiments.risk_budget import simulate
ENGINE='backend/src/platform_app/experiments/risk_budget.py'
LOADED_ENGINE_PATH=Path(sys.modules[simulate.__module__].__file__).resolve()
LOADED_ENGINE_SHA=hashlib.sha256(LOADED_ENGINE_PATH.read_bytes()).hexdigest()
SOURCE='validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c'
STRATEGIES=('hold_full','fixed_risk','ewma_raw','ewma_calibrated','lightgbm_raw','lightgbm_calibrated','dlinear_raw','dlinear_calibrated')
class RiskBudgetStore:
 def __init__(self,folder,project,source_store=None):
  self.folder,self.project=Path(folder),Path(project)
  self.source=source_store or ValidationFoundationStore(self.project/'backend/data/validation-foundation',self.project)
 def get(self,run_id,*,_verification=None):
  if not re.fullmatch(r'risk-[a-f0-9]{64}',run_id):raise KeyError(run_id)
  path=self.folder/(run_id+'.json')
  if not path.exists():raise KeyError(run_id)
  try:
   require(path.resolve().is_relative_to(self.folder.resolve()))
   body=json.loads(path.read_text('utf8'));r=body['record']
   require(stable_hash(r)==body['sha256'] and r['run_id']==run_id and r['schema']=='risk-budget-result-v1')
   require(datetime.fromisoformat(r['created_at']).tzinfo is not None)
   require(r['symbol'] in {'600519','600036','600585','BTCUSDT','ETHUSDT'})
   require(r['market']==('crypto' if r['symbol'].endswith('USDT') else 'ashare') and r['annualization']==(365 if r['market']=='crypto' else 252))
   identity=dict(protocol_sha256=stable_hash(r['protocol']),source_report_sha256=r['source_report_sha256'],symbol=r['symbol'])
   require(r['identity']==identity and run_id=='risk-'+stable_hash(identity) and r['source_report_id']==SOURCE)
   require(r['dataset_sha256']==stable_hash(r['dataset']))
   require(r['dataset']['symbol']==r['symbol'] and r['dataset']['market']==r['market'])
   require([f['fold'] for f in r['folds']]==[f'{y}Q{q}' for y in (2024,2025) for q in (1,2,3,4)])
   require(bool(r['observations']) and isinstance(r['models'],dict))
   previous=None
   for row in r['observations']:
    times=[datetime.fromisoformat(row[k]) for k in ('decision_at','entry_at','exit_at')]
    require(all(t.tzinfo is not None for t in times) and times[0]<times[1]<times[2])
    require(previous is None or previous<row['signal_session']);previous=row['signal_session']
    require(row['fold'] in {f['fold'] for f in r['folds']})
    for mode in ('raw','calibrated'):
     require({'train_mean','ewma','lightgbm','dlinear'}.issubset(row[mode]))
     for value in row[mode].values():
      variance=Decimal(str(value));require(variance.is_finite() and variance>0)
   require(set(r['scenarios'])=={'0','1','2'} and all(set(v)==set(STRATEGIES) for v in r['scenarios'].values()))
   require(isinstance(r['artifacts'],dict) and bool(r['artifacts']) and isinstance(r['limitations'],list))
   verification=_verification if _verification is not None else {'sources':{},'files':{}}
   sources=verification['sources']
   if SOURCE not in sources:
    try:sources[SOURCE]=self.source.get(SOURCE)
    except KeyError:sources[SOURCE]=None
   parent=sources[SOURCE];missing=[]
   if parent is None:missing.append('source-report:'+SOURCE)
   else:
    require(parent['record_sha256']==r['source_report_sha256']);missing.extend(parent['missing_artifacts'])
   root=(self.project/'research/artifacts/risk-budget').resolve()
   for name,sha in r['artifacts'].items():
    relative=PurePosixPath(name)
    require('\\' not in name and ':' not in name and not relative.is_absolute() and '..' not in relative.parts and re.fullmatch('[a-f0-9]{64}',sha))
    artifact=(self.project/name).resolve();require(artifact!=root and artifact.is_relative_to(root))
    if not artifact.exists():missing.append(name);continue
    require(artifact.is_file());before=artifact.stat();signature=(before.st_mtime_ns,before.st_size,before.st_ctime_ns,before.st_ino)
    cached=verification['files'].get(artifact)
    if cached is None or cached[0]!=signature:
     with artifact.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
     after=artifact.stat();require(signature==(after.st_mtime_ns,after.st_size,after.st_ctime_ns,after.st_ino));verification['files'][artifact]=(signature,actual)
    else:actual=cached[1]
    require(actual==sha)
   return dict(record=r,record_sha256=body['sha256'],artifact_status='missing' if missing else 'verified',missing_artifacts=sorted(set(missing)))
  except (ValueError,KeyError,TypeError,AttributeError,OSError,ArithmeticError):
   raise DomainConflict('risk_budget_corrupt','风险预算来源、身份或产物完整性校验失败，未作为有效结果读取。') from None
 def list(self):
  if not self.folder.exists():return []
  result=[];verification={'sources':{},'files':{}}
  for path in self.folder.glob('risk-*.json'):
   body=self.get(path.stem,_verification=verification);r=body['record'];result.append({k:r[k] for k in ('run_id','created_at','symbol','name','market')}|dict(rows=len(r['observations']),artifact_status=body['artifact_status']))
  return sorted(result,key=lambda r:(datetime.fromisoformat(r['created_at']),r['run_id']),reverse=True)
 def preview(self,run_id,target_volatility,cost_multiplier):
  body=self.get(run_id);r=body['record']
  if body['artifact_status']!='verified':raise DomainConflict('risk_budget_missing','原始来源或产物缺失，无法重新计算。')
  try:
   engine=self.project/ENGINE
   with engine.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
   require(engine.resolve()==LOADED_ENGINE_PATH and actual==LOADED_ENGINE_SHA)
   require(r['protocol']['sources'][ENGINE]==actual)
  except (KeyError,OSError,ValueError):raise DomainConflict('risk_budget_engine_changed','执行引擎与原实验版本不一致，无法重新计算旧结果。') from None
  return dict(source_run_id=run_id,source_record_sha256=body['record_sha256'],config=dict(target_volatility=target_volatility,cost_multiplier=cost_multiplier),engine_sha256=actual,strategies={key:simulate(r['dataset'],r['observations'],key,target_volatility=target_volatility,cost_multiplier=cost_multiplier) for key in STRATEGIES})
