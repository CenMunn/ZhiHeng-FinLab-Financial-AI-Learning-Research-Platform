"""Verified D28 publication, bounded preview, allowlisted source document."""
import hashlib,json,re,sys
from datetime import datetime,date
from pathlib import Path,PurePosixPath
from platform_app.contracts.models import stable_hash
from platform_app.contracts.errors import DomainConflict
from platform_app.experiments.event_study import analyze

ENGINE='backend/src/platform_app/experiments/event_study.py'
LOADED_ENGINE=Path(sys.modules[analyze.__module__].__file__).resolve()
LOADED_ENGINE_SHA=hashlib.sha256(LOADED_ENGINE.read_bytes()).hexdigest()
def current_engine_sha():return hashlib.sha256(LOADED_ENGINE.read_bytes()).hexdigest()
def require(value):
 if not value:raise ValueError('Invalid event study publication')

class EventStudyStore:
 def __init__(self,folder,project):self.folder,self.project=Path(folder),Path(project)
 def get(self):
  path=self.folder/'latest.json'
  if not path.exists():return dict(record=None,record_sha256=None,artifact_status='empty',missing_artifacts=[])
  try:
   require(path.resolve().is_relative_to(self.folder.resolve()))
   body=json.loads(path.read_text('utf8'));r=body['record'];require(stable_hash(r)==body['sha256'])
   protocol=r['protocol']
   require(r['schema']=='event-study-publication-v1' and r['run_id']=='event-'+stable_hash(protocol))
   require(protocol['schema']=='event-study-protocol-v1' and protocol['fixed_case']=='600519/2024Q1')
   require(protocol['catalog_publication_range']==['2024-01-01','2025-12-31'] and protocol['symbols']==['600519','600036','600585'])
   require(protocol['estimation_offsets']==[-130,-21] and protocol['event_window_default']==[-5,5] and protocol['window_preview_each_side']==[1,10])
   require(datetime.fromisoformat(r['created_at']).tzinfo is not None)
   require(isinstance(r['catalog'],list) and r['catalog'] and len({e['event_id'] for e in r['catalog']})==len(r['catalog']))
   for event in r['catalog']:
    require(event['symbol'] in {'600519','600036','600585'} and isinstance(event['title'],str))
    date.fromisoformat(event['publication_date']);require(event['time_precision'] in {'date','minute','second'})
   case=r['case'];require(case['event_id'] in {e['event_id'] for e in r['catalog']} and isinstance(case['evidence'],list))
   chosen=next(e for e in r['catalog'] if e['event_id']==case['event_id'])
   require(chosen['symbol']=='600519' and chosen['report_period']=='2024Q1')
   require(isinstance(r['analysis'],dict) and isinstance(r['stock'],dict) and isinstance(r['benchmark'],dict))
   require(r['analysis']['event_id']==case['event_id'] and r['analysis']['symbol']==chosen['symbol'])
   require(r['analysis']['config']['pre']==5 and r['analysis']['config']['post']==5)
   require(isinstance(r['limitations'],list) and isinstance(r['extraction_evaluation'],dict))
   require(isinstance(r['sources'],dict) and r['sources']==protocol['sources'] and re.fullmatch('[a-f0-9]{64}',r['sources'][ENGINE]))
   require(isinstance(r['artifacts'],dict) and r['artifacts'])
   require(r['artifacts'].get(case['pdf_path'])==case['pdf_sha256'])
   root=(self.project/'research/artifacts/event-study').resolve();missing=[]
   for name,sha in r['artifacts'].items():
    relative=PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts and '\\' not in name and ':' not in name and re.fullmatch('[a-f0-9]{64}',sha))
    artifact=(self.project/name).resolve();require(artifact!=root and artifact.is_relative_to(root))
    if not artifact.exists():missing.append(name);continue
    require(artifact.is_file())
    with artifact.open('rb') as source:require(hashlib.file_digest(source,'sha256').hexdigest()==sha)
   return dict(record=r,record_sha256=body['sha256'],artifact_status='missing' if missing else 'verified',missing_artifacts=missing)
  except (ValueError,KeyError,TypeError,AttributeError,OSError,ArithmeticError):
   raise DomainConflict('event_study_corrupt','公告实验记录或来源完整性校验失败，未展示为有效结果。') from None
 def complete(self):
  body=self.get()
  if body['artifact_status']!='verified':raise DomainConflict('event_study_missing','公告实验来源尚未齐备，暂不能计算或打开原文。')
  return body
 def preview(self,pre,post,source_record_sha256):
  body=self.complete();r=body['record']
  if source_record_sha256!=body['record_sha256']:raise DomainConflict('event_study_version','公告实验版本已变化，请刷新后重新计算。')
  if current_engine_sha()!=LOADED_ENGINE_SHA or r['sources'][ENGINE]!=LOADED_ENGINE_SHA:
   raise DomainConflict('event_study_engine','计算引擎与发布版本不一致，无法重算旧结果。')
  event=next(e for e in r['catalog'] if e['event_id']==r['case']['event_id'])
  return dict(source_record_sha256=body['record_sha256'],engine_sha256=LOADED_ENGINE_SHA,analysis=analyze(r['stock'],r['benchmark'],event,pre=pre,post=post))
 def document(self,event_id):
  body=self.complete();case=body['record']['case']
  if event_id!=case['event_id']:raise KeyError(event_id)
  data=(self.project/case['pdf_path']).read_bytes()
  if hashlib.sha256(data).hexdigest()!=case['pdf_sha256']:raise DomainConflict('event_study_document','原文在读取期间变化。')
  return data
