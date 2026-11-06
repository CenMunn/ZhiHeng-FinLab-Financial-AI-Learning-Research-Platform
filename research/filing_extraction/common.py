"""D29 public-input boundary and exact financial-value helpers."""
import json,re,unicodedata
from decimal import Decimal
from pathlib import Path,PurePosixPath
from research.market.common import PROJECT,file_sha,digest,write_json

ROOT=PROJECT/'research/artifacts/filing-extraction'
CONFIG=PROJECT/'research/configs/filing-extraction-v1.json'
METRICS=('revenue','net_profit_parent','operating_cashflow')
LABELS={'revenue':'营业收入','net_profit_parent':'归母净利润','operating_cashflow':'经营现金流净额'}
ALIASES={'revenue':('营业收入',),
 'net_profit_parent':('归属于上市公司股东的净利润','归属于本行股东的净利润','归属于母公司股东的净利润','归属于母公司所有者的净利润','归属母公司股东的净利润'),
 'operating_cashflow':('经营活动产生的现金流量净额','经营活动现金流量净额')}
UNITS={'元':Decimal(1),'万元':Decimal(10000),'百万元':Decimal(1000000),'亿元':Decimal(100000000)}
NAMES={'600519':'贵州茅台','600036':'招商银行','600585':'海螺水泥'}
NUMBER=r'\(?-?\d[\d,]*(?:\.\d+)?\)?'

def compact(text):return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))
def number(token):
 token=compact(token).replace(',','')
 if token.startswith('(') and token.endswith(')'):token='-'+token[1:-1]
 if not re.fullmatch(r'-?\d+(?:\.\d+)?',token):raise ValueError('Invalid decimal amount')
 return Decimal(token)
def amount(value,unit):
 if not isinstance(value,str) or not re.fullmatch(r'-?\d+(?:\.\d+)?',value) or unit not in UNITS:raise ValueError('Unknown amount or unit')
 return Decimal(value)*UNITS[unit]
def financial_anchors(text,metric):
 """Pair a named field with its first amount, skipping only declared note markers."""
 text=unicodedata.normalize('NFKC',text)
 aliases=['\\s*'.join(map(re.escape,alias)) for alias in ALIASES[metric]]
 pattern='(?:'+'|'.join(aliases)+')\\s*(?:为|实现|:|人民币|约|共|计|达|\\s)*('+NUMBER+')'
 for match in re.finditer(pattern,text):
  token=match.group(1);end=match.end()
  note=re.fullmatch(r'\(([1-9])\)',token)
  if note and re.search(r'注\s*[:：]',text) and re.search(r'(?m)^\s*\('+note.group(1)+r'\)\s*[^\d\s]',text):
   following=re.match(r'\s*('+NUMBER+')',text[end:])
   if not following:continue
   token=following.group(1);end+=following.end()
  yield {'start':match.start(),'end':end,'value':number(token),'quote':text[match.start():end]}
def rel(path):return Path(path).resolve().relative_to(PROJECT.resolve()).as_posix()

def verify_artifacts(mapping,*,project=PROJECT):
 project=Path(project).resolve();allowed=(project/'research/artifacts/filing-extraction').resolve()
 if not isinstance(mapping,dict) or not mapping:raise ValueError('Empty evidence manifest')
 for name,sha in mapping.items():
  p=PurePosixPath(name)
  if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Unsafe artifact identity')
  path=(project/name).resolve()
  if not path.is_relative_to(allowed) or not path.is_file() or file_sha(path)!=sha:raise ValueError('Missing or changed artifact: '+name)

def make_inputs(documents,texts):
 keys=('doc_id','symbol','title','period','split','pdf_sha256')
 return {'schema':'filing-extraction-inputs-v1','documents':[{**{k:d[k] for k in keys},'pages':[{'page':i+1,'text':t} for i,t in enumerate(texts[d['doc_id']][:6])]} for d in documents]}

def load_corpus(path):
 path=Path(path).resolve()
 if not path.is_relative_to(ROOT.resolve()/'corpus'):raise ValueError('Not a public corpus manifest')
 body=json.loads(path.read_text('utf8'));verify_artifacts(body['artifacts'])
 if body['schema']!='filing-extraction-corpus-v1':raise ValueError('Corpus schema mismatch')
 docs=body['documents'];expected={s+'-'+p for s in NAMES for p in ('2024Q1','2025Q1')}
 if len(docs)!=6 or {d['doc_id'] for d in docs}!=expected:raise ValueError('Fixed sample changed')
 texts={}
 for d in docs:
  if d['doc_id']!=d['symbol']+'-'+d['period'] or d['split']!=('development' if d['period']=='2024Q1' else 'evaluation'):raise ValueError('Split identity mismatch')
  for key in ('pdf','pages'):
   if body['artifacts'].get(d[key+'_path'])!=d[key+'_sha256']:raise ValueError('Document is not bound to manifest')
  pagebody=json.loads((PROJECT/d['pages_path']).read_text('utf8'))
  if pagebody['pdf_sha256']!=d['pdf_sha256'] or len(pagebody['pages'])!=d['page_count'] or not all(isinstance(t,str) for t in pagebody['pages']):raise ValueError('Page text identity mismatch')
  if len(pagebody['pages'])<6:raise ValueError('Fixed six-page input missing')
  texts[d['doc_id']]=pagebody['pages']
 return body,make_inputs(docs,texts)

