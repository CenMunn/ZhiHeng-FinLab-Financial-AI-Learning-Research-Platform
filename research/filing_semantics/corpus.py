"""Offline PDF layout acquisition. Evaluation bytes stay closed until method-freeze."""
import argparse
import re
from pathlib import Path
from research.filing_semantics.common import *

ISSUERS={'600519':'贵州茅台酒股份有限公司','600036':'招商银行股份有限公司','600585':'安徽海螺水泥股份有限公司',
         '000333':'美的集团股份有限公司','601318':'中国平安保险（集团）股份有限公司','600887':'内蒙古伊利实业集团股份有限公司'}

def require_evaluation_gate(path):
    require(path is not None,'Evaluation requires a verified method freeze')
    try: return verify_freeze(path)
    except (KeyError,TypeError,OSError) as e: raise ValueError('Invalid method freeze') from e

def qualify_identity(doc,text):
    flat=re.sub(r'\s+','',text)
    year=doc['period'][:4]
    checks={'code':doc['symbol'] in flat,'issuer':ISSUERS[doc['symbol']] in flat,
            'period':year+'年第一季度报告' in flat or year+'年一季度报告' in flat,
            'full_report':'报告摘要' not in flat[:1800]}
    # Chinese year typography is used by the original bank report.
    if doc['symbol']=='600036' and doc['period']=='2024Q1':
        checks['period']=checks['period'] or '二○二四年第一季度报告' in flat
    return {'qualified':all(checks.values()),'checks':checks,'issuer':ISSUERS[doc['symbol']],
            'identity_excerpt':text[:3500], 'basis':'first two physical pages; code + full issuer + Q1 year + non-summary'}

def extract(split,freeze_path=None,attempt='initial'):
    require(split in ('development','evaluation'),'Unknown split')
    frozen=require_evaluation_gate(freeze_path) if split=='evaluation' else None
    require(re.fullmatch('[a-zA-Z0-9_-]{1,40}',attempt),'Invalid corpus attempt')
    origin=SEALED if split=='evaluation' else CORPUS
    if split=='evaluation':
        require(file_sha(origin)=='aee2c68b8855c5cc36ca075ab8e06f637bd67231b7b67652d77954aec12de35e','Sealed metadata changed')
    manifest=read(origin)
    selected=[d for d in manifest['documents'] if split=='evaluation' or d['split']=='development']
    symbols=['000333','601318','600887'] if split=='evaluation' else ['600519','600036','600585']
    require(len(selected)==3 and {d['symbol'] for d in selected}==set(symbols),'Fixed cohort changed')
    out=ROOT/'corpus'/split/attempt
    require(not (out/'manifest.json').exists(),'Corpus attempt exists; retain and use a fresh attempt')
    # Import only after the evaluation gate. PDF packages belong to the bundled
    # offline preparation runtime, never to the web server or model environment.
    import pypdf,pdfplumber
    documents=[];artifacts={rel(origin):file_sha(origin)}
    for d in selected:
        pdf=PROJECT/d['pdf_path']; require(file_sha(pdf)==d['pdf_sha256'],'Sealed PDF changed')
        reader=pypdf.PdfReader(pdf);texts=[p.extract_text() or '' for p in reader.pages]
        identity=qualify_identity(d,'\n'.join(texts[:2]))
        folder=out/(d['symbol']+'-'+d['period'])
        write_json(folder/'identity.json',{'checked_at':now(),**identity,'pdf_sha256':file_sha(pdf)})
        # A failed identity is retained, never silently replaced by another issuer.
        require(identity['qualified'],'PDF body identity failed for '+d['symbol'])
        require(len(texts)>=6,'Six input physical pages unavailable')
        layouts=[]
        with pdfplumber.open(pdf) as parsed:
            for i,p in enumerate(parsed.pages[:6]):
                words=[{k:w[k] for k in ('text','x0','x1','top','bottom')} for w in p.extract_words(x_tolerance=2,y_tolerance=3,keep_blank_chars=False)]
                layouts.append({'page':i+1,'width':float(p.width),'height':float(p.height),'words':words})
        write_json(folder/'all-pages.json',{'pdf_sha256':file_sha(pdf),'pages':texts})
        doc={'doc_id':d['symbol']+'-'+d['period'],'symbol':d['symbol'],'name':d.get('name',ISSUERS[d['symbol']]),
             'title':d['title'],'period':d['period'],'split':split,'pdf_path':d['pdf_path'],'pdf_sha256':d['pdf_sha256'],
             'source_url':d.get('pdf_url',d.get('source_url','')),'page_count':len(texts),
             'identity_path':rel(folder/'identity.json'),'all_pages_path':rel(folder/'all-pages.json'),
             'pages':[{'page':i+1,'text':t} for i,t in enumerate(texts[:6])],'layout_pages':layouts}
        write_json(folder/'input.json',doc);documents.append(doc)
        for p in folder.glob('*.json'): artifacts[rel(p)]=file_sha(p)
        artifacts[rel(pdf)]=file_sha(pdf)
    body={'schema':'filing-semantics-corpus-v1','split':split,'created_at':now(),
          'method_freeze_sha256':frozen['sha256'] if frozen else None,'documents':documents,'artifacts':artifacts,
          'extraction_runtime':{'pypdf':pypdf.__version__,'pdfplumber':pdfplumber.__version__}}
    write_json(out/'manifest.json',body); print(str(out/'manifest.json'),flush=True);return out/'manifest.json'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['development','evaluation'],required=True);p.add_argument('--freeze',type=Path);p.add_argument('--attempt',default='initial')
    a=p.parse_args();extract(a.split,a.freeze,a.attempt)
