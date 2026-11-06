"""D32 paths, immutable source identities and safe local verification."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from research.market.common import PROJECT, digest, file_sha, write_json

ROOT=PROJECT/'research/artifacts/filing-semantics-v2'
CONFIG=PROJECT/'research/configs/filing-semantics-v2.json'
SPEC=PROJECT/'docs/superpowers/specs/2026-11-07-filing-semantics-v2-design.md'
MODEL=PROJECT/'research/artifacts/filing-extraction/model/989aa7980e4cf806f80c7fef2b1adb7bc71aa306/manifest.json'
SEALED=PROJECT/'research/artifacts/filing-semantics-v2/sealed-evaluation/registered/manifest.json'
CORPUS=PROJECT/'research/artifacts/filing-extraction/corpus/v2/manifest.json'
METHODS=('structure_rule','structure_model')
METRICS=('revenue','net_profit_parent','operating_cashflow')
LABELS=dict(revenue='营业收入',net_profit_parent='归母净利润',operating_cashflow='经营现金流净额')
def read(path): return json.loads(Path(path).read_text('utf8'))
def now(): return datetime.now(timezone.utc).isoformat()
def rel(path): return Path(path).resolve().relative_to(PROJECT.resolve()).as_posix()
def require(condition,message='D32 identity or boundary mismatch'):
    if not condition: raise ValueError(message)
def verify_map(mapping,project=PROJECT):
    project=Path(project).resolve()
    require(isinstance(mapping,dict) and mapping,'Empty identity map')
    for name,sha in mapping.items():
        p=PurePosixPath(name)
        require(not p.is_absolute() and '..' not in p.parts and ':' not in name and '\\' not in name and re.fullmatch('[a-f0-9]{64}',sha),'Unsafe artifact path')
        path=(project/name).resolve()
        require(path.is_relative_to(project) and path.is_file() and file_sha(path)==sha,'Missing or changed: '+name)
def source_files():
    files=[*Path(__file__).parent.glob('*.py'),CONFIG,SPEC,PROJECT/'research/market/common.py',
           PROJECT/'research/filing_development/model.py',PROJECT/'research/filing_development/evidence.py',
           PROJECT/'research/filing_extraction/common.py',PROJECT/'research/filing_extraction/download_model.py']
    return {rel(p):file_sha(p) for p in sorted(files)}
def verify_freeze(path):
    path=Path(path).resolve()
    require(path.is_relative_to(ROOT.resolve()/'freezes'),'Unregistered method freeze')
    body=read(path);identity=body['identity']
    require(body['schema']=='filing-semantics-method-freeze-v1' and body['sha256']==digest(identity),'Invalid method freeze')
    require(path.stem==body['sha256'],'Method freeze filename differs')
    require(identity['sources']==source_files(),'Method sources changed after freeze')
    verify_map(identity['sources']);verify_map(identity['artifacts'])
    return body
