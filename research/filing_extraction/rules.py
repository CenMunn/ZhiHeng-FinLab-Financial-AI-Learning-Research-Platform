"""Frozen lexical current-column baseline, independent of reference labels."""
import json,re,time,unicodedata
from datetime import datetime,timezone
from pathlib import Path
from research.market.common import file_sha,write_json
from research.filing_extraction.common import METRICS,compact,financial_anchors
from research.filing_extraction.model import validate_documents

def empty(metric):return dict(metric=metric,value=None,unit=None,currency=None,period=None,scope=None,page=None,quote=None)

def extract_document(doc):
 started=time.monotonic();rows=[]
 for metric in METRICS:
  answer=empty(metric)
  for page in doc['pages']:
   text=unicodedata.normalize('NFKC',page['text'])
   for anchor in financial_anchors(text,metric):
    rawprefix=text[:anchor['start']];prefix=compact(rawprefix)
    row_prefix=compact(rawprefix[rawprefix.rfind('\n')+1:])
    if metric=='net_profit_parent' and ('扣非' in row_prefix or re.search(r'扣除.*非经常性',row_prefix)):continue
    units=[]
    for unit in re.finditer(r'(?:单位\s*[:：]?\s*(?:人民币)?|人民币)\s*(百万元|万元|亿元|元)',rawprefix):
     # A per-share row's explicit unit overrides only that row, not the table header.
     line=rawprefix[rawprefix.rfind('\n',0,unit.start())+1:unit.start()]
     if '每股' not in compact(line):units.append(unit)
    if not units or '人民币' not in text:continue
    headings=list(re.finditer(r'(合并|母公司)(?:利润表|现金流量表)',prefix))
    if headings and headings[-1].group(1)=='母公司':continue
    value=anchor['value'];unit=units[-1].group(1)
    answer=dict(metric=metric,value=str(value),unit=unit,currency='CNY',period=doc['period'],scope='consolidated',page=page['page'],quote=anchor['quote'])
    break
   if answer['value'] is not None:break
  rows.append(answer)
 return {'doc_id':doc['doc_id'],'fields':rows,'status':'ok','raw_output':json.dumps({'fields':rows},ensure_ascii=False),'latency_seconds':time.monotonic()-started,'input_tokens':None,'output_tokens':None}

def run_rules(inputs_path,output):
 inputs_path,output=Path(inputs_path),Path(output)
 if output.exists():raise ValueError('Refuse to overwrite rule predictions')
 if 'reference' in inputs_path.parts:raise ValueError('Reference is not an extractor input')
 initial=file_sha(inputs_path);source=file_sha(__file__)
 docs=validate_documents(json.loads(inputs_path.read_text('utf8')))
 result={'schema':'filing-extraction-rule-predictions-v1','created_at':datetime.now(timezone.utc).isoformat(),'inputs_sha256':initial,'source_sha256':{str(Path(__file__).resolve()):source},'predictions':[extract_document(d) for d in docs]}
 if initial!=file_sha(inputs_path) or source!=file_sha(__file__):raise ValueError('Rule input/source changed during prediction')
 write_json(output,result);return result

