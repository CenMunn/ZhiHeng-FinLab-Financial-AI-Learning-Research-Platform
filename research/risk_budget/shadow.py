"""Append-only forecast evidence. No live adapter or historical backdating."""
import json,math,re
from pathlib import Path
from datetime import datetime,timezone,date,timedelta
from decimal import Decimal
from research.market.common import digest,file_sha,write_json

START='2026-11-06'

def register(folder,run_id,protocol_sha256):
    if not re.fullmatch(r'risk-[a-f0-9]{64}',run_id):raise ValueError('非法前瞻模型版本')
    folder=Path(folder)/run_id
    body={'source_run_id':run_id,'protocol_sha256':protocol_sha256,'start':START,'status':'pending','records':0,
        'scope':'registry and append validation only; live data/inference not connected; no actual forward scores'}
    write_json(folder/'registry.json',body)
    return {**body,'registry_file':str(folder/'registry.json'),'registry_sha256':file_sha(folder/'registry.json')}

def append_prediction(folder,record,inputs,allowed_model_hashes,*,_now=None):
    now=_now or datetime.now(timezone.utc);run=record['source_run_id'];registry=Path(folder)/run/'registry.json'
    if not re.fullmatch(r'risk-[a-f0-9]{64}',run) or not registry.exists():raise ValueError('未注册的前瞻版本')
    meta=json.loads(registry.read_text('utf8'))
    if meta['source_run_id']!=run or meta['start']!=START:raise ValueError('注册版本变化')
    signal=date.fromisoformat(record['signal_session']);decision=datetime.fromisoformat(record['decision_at']);entry=datetime.fromisoformat(record['entry_at']);available=datetime.fromisoformat(inputs['available_at'])
    if any(v.tzinfo is None for v in (now,decision,entry,available)):raise ValueError('前瞻时间必须含时区')
    if str(signal)<START or inputs['feature_asof']!=str(signal) or not available<=decision<=now<entry or now-available>timedelta(days=4):raise ValueError('不接受过期输入/补记历史预测/未来输入或已错过的成交')
    if record['input_sha256']!=digest(inputs) or record['model_sha256'] not in allowed_model_hashes:raise ValueError('输入/模型摘要不符')
    if record['model_key'] not in ('ewma','lightgbm','dlinear') or record['mode'] not in ('raw','calibrated'):raise ValueError('未登记前瞻方法')
    if not math.isfinite(record['variance']) or record['variance']<=0 or not Decimal(0)<=Decimal(record['target_weight'])<=Decimal(1):raise ValueError('前瞻风险/仓位非法')
    context={k:record[k] for k in ('source_run_id','model_key','mode','signal_session')}
    body={'created_at':now.isoformat(),'forecast':record,'inputs':inputs,'sha256':digest({'forecast':record,'inputs':inputs})}
    path=registry.parent/('prediction-'+digest(context)+'.json')
    write_json(path,body);return path
