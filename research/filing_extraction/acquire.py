"""D29 fixed six public filings; text corpus contains no reference answers."""
import argparse,json,re,subprocess,sys,shutil
from datetime import datetime,timezone,date
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from research.market.common import PROJECT,file_sha,write_json

CATALOG=PROJECT/'research/artifacts/event-study/source-20261105T185411543855Z/catalog.json'
CATALOG_SHA='5cab3fc55428d9b6deeba348349bd4d2b7dd16f99c1024c249a0982ea924f131'
ROOT=PROJECT/'research/artifacts/filing-extraction'
SYMBOLS=('600519','600036','600585')
NAMES={'600519':'贵州茅台','600036':'招商银行','600585':'海螺水泥'}
MIRRORS={'600519-2024Q1':('2024-04-27','1219875828'),'600519-2025Q1':('2025-04-30','1223413786'),
 '600036-2024Q1':('2024-04-30','1219910214'),'600036-2025Q1':('2025-04-30','1223412232'),
 '600585-2024Q1':('2024-04-27','1219876082'),'600585-2025Q1':('2025-04-30','1223413869')}

def now():return datetime.now(timezone.utc).isoformat()
def catalog_metadata(source):
 return {'catalog':source['catalog'],'audit':source['audit']}
def select_documents(catalog):
 selected=[]
 for symbol in SYMBOLS:
  for period in ('2024Q1','2025Q1'):
   matches=[e for e in catalog if e['symbol']==symbol and e['report_period']==period and e['document_type']=='quarterly']
   if len(matches)!=1:raise ValueError('Fixed filing missing or duplicated')
   e=matches[0];day=date.fromisoformat(e['publication_date'])
   if day.year!=int(period[:4]) or day.month!=4:raise ValueError('Unexpected fixed Q1 publication date')
   selected.append({**e,'doc_id':symbol+'-'+period,'split':'development' if period=='2024Q1' else 'evaluation'})
 return selected
def validate_pdf(raw):
 if not raw.startswith(b'%PDF-') or len(raw)>8_000_000:raise ValueError('Not a bounded PDF; possibly access challenge')
def validate_identity(pages,symbol,period):
 text=re.sub(r'\s+','',''.join(pages[:2]))
 if NAMES[symbol] not in text or period[:4]+'年第一季度报告' not in text:raise ValueError('PDF company/report period mismatch')
def validate_unit(unit):
 if unit not in ('元','万元','百万元','亿元'):raise ValueError('Unsupported or missing financial unit')
 return unit
def extract(pdf,python):
 code='import json,sys;from pypdf import PdfReader;p=PdfReader(sys.argv[1]);print(json.dumps([x.extract_text() or "" for x in p.pages],ensure_ascii=False))'
 result=subprocess.run([str(python),'-X','utf8','-c',code,str(pdf)],capture_output=True,encoding='utf8',check=True)
 return json.loads(result.stdout)
def fetch(url,folder,label):
 received=now();receipt={'url':url,'started_at':received};raw=None
 try:
  with urlopen(Request(url,headers={'User-Agent':'FinancialLearningLab/0.1 (public report research)'}),timeout=25) as response:
   receipt.update(final_url=response.url,status=response.status,content_type=response.headers.get('Content-Type'))
   host=urlparse(response.url)
   if host.scheme!='https' or host.hostname not in ('www.sse.com.cn','static.sse.com.cn','static.cninfo.com.cn'):raise ValueError('Unexpected source redirect; not bypassing access challenge')
   raw=response.read(8_000_001)
  receipt['received_at']=now();receipt['bytes']=len(raw)
  path=folder/(label+'.response');path.write_bytes(raw);receipt['sha256']=file_sha(path)
  validate_pdf(raw);receipt['status']='pdf_received'
 except Exception as error:
  receipt.update(status='failed',received_at=now(),error=str(error));raw=None
 write_json(folder/(label+'.receipt.json'),receipt)
 return raw,receipt
def acquire(attempt,pdf_python,reuse_manifest=None):
 if not re.fullmatch(r'[a-zA-Z0-9_-]+',attempt):raise ValueError('Unsafe attempt')
 folder=ROOT/'corpus'/attempt;manifest_path=folder/'manifest.json'
 if folder.exists():raise ValueError('Existing attempt retained; select a fresh attempt')
 folder.mkdir(parents=True)
 if file_sha(CATALOG)!=CATALOG_SHA:raise ValueError('Frozen D28 source catalog changed')
 catalog=json.loads(CATALOG.read_text('utf8'));documents=[];reuse={}
 if reuse_manifest:
  reuse_manifest=Path(reuse_manifest).resolve()
  if not reuse_manifest.is_relative_to((ROOT/'corpus').resolve()):raise ValueError('Reuse manifest outside corpus')
  previous=json.loads(reuse_manifest.read_text('utf8'))
  if previous['schema']!='filing-extraction-corpus-v1':raise ValueError('Invalid reused manifest')
  for name,sha in previous['artifacts'].items():
   path=(PROJECT/name).resolve()
   if not path.is_relative_to(reuse_manifest.parent) or file_sha(path)!=sha:raise ValueError('Reused corpus artifact changed')
  reuse={d['doc_id']:d for d in previous['documents']}
 write_json(folder/'source-catalog.json',catalog_metadata(catalog))
 raw_folder=folder/'catalog-pages';raw_folder.mkdir()
 for i,name in enumerate(sorted({e['catalog_source'] for e in select_documents(catalog['catalog'])})):
  path=(PROJECT/name).resolve();expected=catalog['artifacts'][name]
  if not path.is_relative_to(CATALOG.parent.resolve()) or file_sha(path)!=expected:raise ValueError('Original announcement page changed')
  shutil.copyfile(path,raw_folder/f'page-{i+1}.json')
 try:
  for event in select_documents(catalog['catalog']):
   doc_id=event['doc_id'];dest=folder/'documents'/doc_id;dest.mkdir(parents=True)
   year_date,cnid=MIRRORS[doc_id];mirror=f'https://static.cninfo.com.cn/finalpage/{year_date}/{cnid}.PDF'
   if doc_id in reuse:
    prior=reuse[doc_id];source=PROJECT/prior['pdf_path']
    if file_sha(source)!=prior['pdf_sha256']:raise ValueError('Reused PDF changed')
    raw=source.read_bytes();pdf_url=prior['pdf_url'];receipt=json.loads((source.parent/'receipt.json').read_text('utf8'))
    receipt.update(reused_at=now(),reused_manifest_sha256=file_sha(reuse_manifest),reused_pdf_path=prior['pdf_path'])
    for old in source.parent.iterdir():
     if old.name not in ('source.pdf','pages.json','receipt.json'):shutil.copyfile(old,dest/old.name)
   elif doc_id=='600519-2024Q1':
    prior=catalog['case'];source=PROJECT/prior['pdf_path']
    if file_sha(source)!=prior['pdf_sha256']:raise ValueError('D28 PDF changed')
    raw=source.read_bytes();pdf_url=prior['pdf_url']
    receipt={'status':'copied_verified_D28','original_path':prior['pdf_path'],'original_sha256':prior['pdf_sha256'],'url':pdf_url,'received_at':now()}
   else:
    raw,receipt=fetch(event['url'],dest,'sse');pdf_url=event['url']
    if raw is None:raw,receipt=fetch(mirror,dest,'cninfo');pdf_url=mirror
    if raw is None:raise ValueError('Both fixed official sources unavailable: '+doc_id)
   validate_pdf(raw);pdf=dest/'source.pdf';pdf.write_bytes(raw);pages=extract(pdf,pdf_python)
   validate_identity(pages,event['symbol'],event['report_period'])
   pages_path=dest/'pages.json';write_json(pages_path,{'pdf_sha256':file_sha(pdf),'pages':pages})
   receipt.update(pdf_sha256=file_sha(pdf),page_count=len(pages),catalog_url=event['url'],pdf_url=pdf_url,
    original_publication_at=None,time_precision='date',note='Official alternative matched by company/period/content; byte equality with unavailable SSE PDF not asserted.')
   write_json(dest/'receipt.json',receipt)
   documents.append({'doc_id':doc_id,'symbol':event['symbol'],'title':event['title'],'period':event['report_period'],'split':event['split'],
    'event_id':event['event_id'],'publication_date':event['publication_date'],'pdf_url':pdf_url,'catalog_url':event['url'],
    'pdf_path':pdf.relative_to(PROJECT).as_posix(),'pdf_sha256':file_sha(pdf),'pages_path':pages_path.relative_to(PROJECT).as_posix(),
    'pages_sha256':file_sha(pages_path),'page_count':len(pages)})
  artifacts={p.relative_to(PROJECT).as_posix():file_sha(p) for p in folder.rglob('*') if p.is_file()}
  manifest={'schema':'filing-extraction-corpus-v1','created_at':now(),'documents':documents,'artifacts':artifacts,'source_catalog_sha256':file_sha(CATALOG),
    'limitations':['Fixed three companies and two Q1 periods are a pilot, not representative population sampling.','Only PDF first six physical pages are extractor input.','Disclosure dates are not verified first-public timestamps; current original versions are not PIT reconstruction.','Quarterly statements are unaudited.','The corpus contains original text and metadata only, not reference labels.']}
  if reuse_manifest:manifest.update(reused_manifest_path=reuse_manifest.relative_to(PROJECT).as_posix(),reused_manifest_sha256=file_sha(reuse_manifest))
  write_json(manifest_path,manifest);print(json.dumps({'manifest':str(manifest_path),'documents':len(documents),'artifacts':len(artifacts)},ensure_ascii=False))
  return manifest
 except Exception as error:
  write_json(folder/'failed.json',{'created_at':now(),'error':str(error),'completed_document_ids':[d['doc_id'] for d in documents]});raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--attempt',required=True);parser.add_argument('--pdf-python',type=Path,required=True);parser.add_argument('--reuse-manifest',type=Path);args=parser.parse_args();acquire(args.attempt,args.pdf_python,args.reuse_manifest)
