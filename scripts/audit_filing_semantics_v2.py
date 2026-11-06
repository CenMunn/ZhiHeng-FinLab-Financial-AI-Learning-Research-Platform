"""Independent offline D32 publication arithmetic and immutable-byte audit."""
import json,hashlib,sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
P=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text('utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
U={'元':Decimal(1),'千元':Decimal(1000),'万元':Decimal(10000),'百万元':Decimal(1000000),'亿元':Decimal(100000000)}
def amount(f):return Decimal(f['value'])*U[f['unit']]
def checks(f,status,ref,c):
 b={k:False for k in ('answered','numeric','unit','currency','period','scope','evidence','column','complete')}
 b['answered']=status=='ok' and isinstance(f,dict) and f.get('value') is not None
 if not b['answered'] or ref['status']!='verified':return b
 try:matches=[v for v in ref['variants'] if amount(v)==amount(f)]
 except (KeyError,TypeError,ArithmeticError,ValueError):matches=[]
 b['numeric']=bool(matches);b['unit']=any(v['unit']==f['unit'] for v in matches)
 for k in ('currency','period','scope'):b[k]=any(v.get(k)==f.get(k) for v in ref['variants'])
 b['column']=any(v['field']==f and v['candidate_id'] in c['eligible_ids'] and v['eligible'] for v in c['candidates'])
 b['evidence']=b['column'] and any(v['page']==f['page'] and v['unit']==f['unit'] and Decimal(v['value'])==Decimal(f['value']) for v in matches)
 b['complete']=all(b[k] for k in ('numeric','unit','currency','period','scope','evidence','column'))
 return b
out={'checked_at':datetime.now(timezone.utc).isoformat(),'status':'passed','studies':[],'reference_limitation':'Assistant visual references pending human audit; missing currencies remain None, never inferred CNY.'}
index=read(P/'backend/data/filing-semantics-v2/latest.json')
for split,e in index['studies'].items():
 path=P/'backend/data/filing-semantics-v2'/e['file'];assert sha(path)==e['sha256'];env=read(path);s=env['record'];assert digest(s)==env['sha256']
 n=18 if split=='development' else 9;assert len(s['rows'])==2*n
 for name,h in {**s['sources'],**s['artifacts']}.items():assert sha(P/name)==h,name
 run=P/'research/artifacts/filing-semantics-v2/runs'/s['run_id'];pr=read(run/'protocol.json');fr=read(run/'frozen-predictions.json');sc=read(run/'scored.json');reg=read(run/'registration.json')
 assert s['run_id']=='filingsem-'+digest(pr)
 assert reg['registered_at']<=fr['frozen_at']<=sc['scored_at']
 assert sha(P/pr['inputs_path'])==pr['inputs_sha256'];assert sha(P/pr['reference_path'])==pr['reference_sha256']
 refs={d['doc_id']:{f['metric']:f for f in d['fields']} for d in read(P/pr['reference_path'])['documents']};cases={c['case_id']:c for c in s['cases']}
 for m,h in fr['files'].items():assert sha(run/(m+'-predictions.json'))==h
 for row in s['rows']:
  c=cases[row['case_id']];ref=refs[c['doc_id']][c['metric']];assert row['reference']==ref;assert checks(row['prediction'],row['status'],ref,c)==row['checks'];assert row['candidate_covered']==any(checks(v['field'],'ok',ref,c)['complete'] for v in c['candidates'])
 for summary in s['metrics']:
  rows=[r for r in s['rows'] if r['method']==summary['method']];assert len(rows)==n
  expected={'method':summary['method'],'total':n,'format_valid':sum(r['status']=='ok' for r in rows),'answered':sum(r['checks']['answered'] for r in rows),'abstained':sum(not r['checks']['answered'] for r in rows),'candidate_covered':sum(r['candidate_covered'] for r in rows)}
  for k in ('numeric','unit','currency','period','scope','evidence','column','complete'):expected[k+'_correct']=sum(r['checks'][k] for r in rows)
  assert summary==expected
 if split=='evaluation':
  assert pr['method_freeze_path'];freeze=read(P/pr['method_freeze_path']);assert freeze['frozen_at']<=read(P/pr['corpus_path'])['created_at']<=reg['registered_at']
 out['studies'].append({'split':split,'run_id':s['run_id'],'rows':2*n,'booleans':2*n*9,'sources':len(s['sources']),'artifacts':len(s['artifacts']),'metrics':s['metrics'],'time_order':'passed'})
print(json.dumps(out,ensure_ascii=False,indent=2))
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
