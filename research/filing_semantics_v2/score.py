"""Independent Decimal scoring, run only after both predictions are frozen."""
import re
import unicodedata
from decimal import Decimal
from research.filing_semantics_v2.common import require,METHODS

UNITS={'元':Decimal(1),'千元':Decimal(1000),'万元':Decimal(10000),'百万元':Decimal(1000000),'亿元':Decimal(100000000)}
def compact(text): return re.sub(r'\s+','',unicodedata.normalize('NFKC',text))
def amount(field): return Decimal(field['value'])*UNITS[field['unit']]
def checks_for(field,status,reference,case,doc):
    checks={k:False for k in ('answered','numeric','unit','currency','period','scope','evidence','column','complete')}
    checks['answered']=status=='ok' and isinstance(field,dict) and field.get('value') is not None
    if not checks['answered'] or reference['status']!='verified': return checks
    variants=reference['variants']
    try: matching=[v for v in variants if amount(v)==amount(field)]
    except (ValueError,KeyError,TypeError,ArithmeticError): matching=[]
    checks['numeric']=bool(matching);checks['unit']=any(field['unit']==v['unit'] for v in matching)
    for key in ('currency','period','scope'):checks[key]=any(field.get(key)==v.get(key) for v in variants)
    source=[c for c in case['candidates'] if c['field']==field]
    checks['column']=any(c['candidate_id'] in case['eligible_ids'] and c.get('eligible',True) for c in source)
    # Exact layout row/coordinate binding is checked during input reconstruction.
    # The independent reference still has to agree with value, unit and physical page.
    checks['evidence']=checks['column'] and any(field['page']==v['page'] and field['unit']==v['unit'] and Decimal(field['value'])==Decimal(v['value']) for v in matching)
    checks['complete']=all(checks[k] for k in ('numeric','unit','currency','period','scope','evidence','column'))
    return checks
def summarize(rows):
    result=[]
    for method in METHODS:
        group=[r for r in rows if r['method']==method];require(len(group) in (9,18),'Fixed denominator changed')
        summary={'method':method,'total':len(group),'format_valid':sum(r['status']=='ok' for r in group),
                 'answered':sum(r['checks']['answered'] for r in group),'candidate_covered':sum(r['candidate_covered'] for r in group)}
        summary['abstained']=len(group)-summary['answered']
        for k in ('numeric','unit','currency','period','scope','evidence','column','complete'):summary[k+'_correct']=sum(r['checks'][k] for r in group)
        result.append(summary)
    return result
def reasons(checks,status):
    if status!='ok': return ['未形成可读取输出：'+status]
    if not checks['answered']:return ['结构或模型拒答；保留在固定分母中，等待核验。']
    names={'numeric':'金额/量纲','unit':'金额与原单位配对','currency':'币种','period':'查询期间','scope':'查询合并范围','evidence':'值/页与独立参考','column':'当期金额列来源'}
    return [v+'未通过' for k,v in names.items() if not checks[k]]
