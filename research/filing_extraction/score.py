"""Score already-frozen predictions; never used by either extractor."""
import re,unicodedata
from research.filing_extraction.common import ALIASES,NUMBER,compact,number,amount,financial_anchors

def is_answer(pred):
 if not isinstance(pred,dict):return False
 value=pred.get('value')
 return isinstance(value,str) and re.fullmatch(r'-?\d+(?:\.\d+)?',value) is not None

def quoted(pred,variant,doc,metric):
 if pred.get('page')!=variant['page'] or pred.get('unit')!=variant['unit']:return False
 try:
  if number(pred['value'])!=number(variant['value']):return False
 except (ValueError,TypeError):return False
 quote=pred.get('quote');page=next((p['text'] for p in doc['pages'] if p['page']==pred.get('page')),None)
 if not isinstance(quote,str) or not quote.strip() or page is None:return False
 q=compact(quote)
 if q not in compact(page) or not any(compact(a) in q for a in ALIASES[metric]):return False
 try:
  normalized=unicodedata.normalize('NFKC',page);source=compact(normalized);reference=compact(variant['quote'])
  def spans(needle):
   return [(m.start(),m.start()+len(needle)) for m in re.finditer('(?='+re.escape(needle)+')',source)]
  predicted_spans,reference_spans=spans(q),spans(reference)
  anchors=[]
  for a in financial_anchors(normalized,metric):
   if a['value']==number(pred['value']):anchors.append((len(compact(normalized[:a['start']])),len(compact(normalized[:a['end']]))))
  # Every occurrence of a short quote must identify supported context; do not
  # accept an ambiguous repeated amount by silently choosing the favourable row.
  return bool(predicted_spans and reference_spans) and all(any(start<=a and b<=end and any(rs<=a and b<=re_ for rs,re_ in reference_spans) for a,b in anchors) for start,end in predicted_spans)
 except ValueError:return False

def score_field(pred,reference,doc,metric,status):
 answered=status=='ok' and is_answer(pred)
 checks={k:False for k in ('numeric','unit','currency','period','scope','evidence','complete')}
 checks.update(answered=answered,correct_abstention=status=='ok' and not answered and reference['status']=='unavailable')
 if not answered or reference['status']!='verified':return checks
 variants=reference['variants']
 try:
  matches=[v for v in variants if amount(pred['value'],pred.get('unit'))==amount(v['value'],v['unit'])]
 except (ValueError,TypeError):matches=[]
 checks['numeric']=bool(matches)
 checks['unit']=any(pred.get('unit')==v['unit'] for v in matches)
 for key in ('currency','period','scope'):checks[key]=any(pred.get(key)==v.get(key) for v in variants)
 checks['evidence']=any(quoted(pred,v,doc,metric) for v in variants)
 checks['complete']=all(checks[k] for k in ('numeric','unit','currency','period','scope','evidence'))
 return checks

def summarize(rows):
 result=[]
 for split,method in sorted({(r['split'],r['method']) for r in rows}):
  selected=[r for r in rows if r['split']==split and r['method']==method]
  record={'split':split,'method':method,'total':len(selected)}
  for key in ('numeric','unit','currency','period','scope','evidence','complete'):record[key+'_correct']=sum(r['checks'][key] for r in selected)
  record['answered']=sum(r['checks']['answered'] for r in selected);record['abstained']=len(selected)-record['answered']
  record['correct_abstentions']=sum(r['checks']['correct_abstention'] for r in selected)
  record['reference_verified']=sum(r['reference']['status']=='verified' for r in selected)
  record['context_complete']=sum(r['reference']['input_context_complete'] for r in selected)
  result.append(record)
 return result

ERRORS={'numeric':'金额或量纲与参考不一致','unit':'原始显示单位不一致','currency':'币种不一致或缺失','period':'期间约束不一致或缺失','scope':'合并范围约束不一致或缺失','evidence':'原文引用/物理页不支持该字段和值'}
def error_reasons(checks,status,reference):
 if status!='ok':return ['模型输出无法按冻结结构读取：'+status]
 if reference['status']!='verified':return ['参考字段未满足核验资格：'+reference['status']]
 if not checks['answered']:return ['未回答该字段；保留在固定分母']
 return [message for key,message in ERRORS.items() if not checks[key]]
