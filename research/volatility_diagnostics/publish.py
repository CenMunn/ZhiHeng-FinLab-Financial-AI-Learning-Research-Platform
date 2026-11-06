"""Immutable versions and atomically selected latest diagnosis per source run."""
import json,os,re
from research.market.common import digest,write_json

def publish(folder,record):
    folder.mkdir(parents=True,exist_ok=True);did=record['diagnostic_id'];run=record['source_run_id']
    if not re.fullmatch(r'vdiag-[a-f0-9]{64}',did) or not re.fullmatch(r'volatility-[a-f0-9]{64}',run):raise ValueError('非法诊断身份')
    body={'record':record,'sha256':digest(record)};pointer=folder/(run+'.json')
    if pointer.exists():
        old=json.loads(pointer.read_text('utf8'));oid=old['record']['diagnostic_id']
        if not re.fullmatch(r'vdiag-[a-f0-9]{64}',oid) or old['sha256']!=digest(old['record']):raise ValueError('已有诊断摘要变化，拒绝覆盖')
        write_json(folder/'versions'/(oid+'.json'),old)
    write_json(folder/'versions'/(did+'.json'),body)
    tmp=folder/(run+'.'+did+'.tmp');write_json(tmp,body);os.replace(tmp,pointer)
