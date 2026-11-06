"""D28 bounded SSE announcement audit; publication dates are not receipt timestamps."""
import argparse,json,math,re,subprocess,sys,time
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode,urlparse
from urllib.request import Request,urlopen
from research.market.common import PROJECT,digest,file_sha,write_json

SYMBOLS=('600519','600036','600585')
BEGIN,END='2024-01-01','2025-12-31'
ENDPOINT='https://query.sse.com.cn/security/stock/queryCompanyBulletin.do'
CASE_PDF_MIRROR='https://static.cninfo.com.cn/finalpage/2024-04-27/1219875828.PDF'
LIMITATIONS=[
 '当前官方历史目录快照，不是当时收到的PIT记录，也不能证明历史所有修订均完整保留。',
 'SSEDATE仅日期；ADDDATE为目录系统入库字段，不等于首次公开时间，publication_at留空。',
 '所有日期精度事件保守映射至披露日期之后的首个交易日；可能遗漏披露当日真实反应。',
 '按披露日期2024–2025取样，报告所属年度另列；不是2024–2025财务期间全报告集合。',
 '摘要、翻译、更正与正文分别保留；目录关系不代表已经获取和核对全部PDF内容。',
 '仅固定茅台2024Q1正文下载与规则抽取，没有运行语言模型或计算模型抽取准确率。',
]

def now():return datetime.now(timezone.utc).isoformat()

def normalize(row,symbol):
    if row.get('SECURITY_CODE')!=symbol or symbol not in SYMBOLS:raise ValueError('Announcement stock mismatch')
    day=row.get('SSEDATE','')[:10]
    if not re.fullmatch(r'\d{4}-\d\d-\d\d',day) or not BEGIN<=day<=END:raise ValueError('Publication date outside protocol')
    datetime.fromisoformat(day)
    source_path=row.get('URL','')
    if not source_path.startswith('/disclosure/listedinfo/announcement/') or '..' in source_path or not source_path.lower().endswith('.pdf'):raise ValueError('Unexpected official PDF path')
    title=row['TITLE'].strip();heading=row.get('BULLETIN_HEADING','');kind=row.get('BULLETIN_TYPE','')
    match=re.search(r'(20\d{2})\s*年(?:度)?\s*(第一季度|第三季度|半年度|中期|年度)?\s*报告',title)
    if not match:return None
    year,period=match.group(1),match.group(2) or '年度'
    suffix={'第一季度':'Q1','第三季度':'Q3','半年度':'H1','中期':'H1','年度':'FY'}[period]
    correction=any(word in title for word in ('更正','修订','更新后','补充公告'))
    translation=any(word in title for word in ('英文','英语'))
    summary='摘要' in title
    if heading!='定期报告' and not correction and not translation:return None
    doc_type='correction' if correction else 'summary' if summary else 'quarterly' if suffix in ('Q1','Q3') else 'semiannual' if suffix=='H1' else 'annual'
    qualification='excluded_translation' if translation else 'review_revision' if correction else 'excluded_summary' if summary else 'qualified_date_only'
    url='https://www.sse.com.cn'+source_path
    identity=dict(symbol=symbol,publication_date=day,title=title,url=url)
    return {**identity,'event_id':'event-'+digest(identity),'publication_at':None,'time_precision':'date',
            'report_period':year+suffix,'document_type':doc_type,'version_status':'revision_listing' if correction else 'original_listing_unverified',
            'qualification':qualification,'raw_added_at':row.get('ADDDATE'),'source_heading':heading,'source_type':kind,
            'publication_time_note':'SSEDATE日期；ADDDATE入库字段未当作公开时刻。','related_event_ids':[]}

def link_versions(catalog):
    for event in catalog:
        event['related_event_ids']=sorted(e['event_id'] for e in catalog if e['symbol']==event['symbol'] and e['report_period']==event['report_period'] and e['event_id']!=event['event_id'])

def verify_page(body,page,expected_total):
    meta=body['pageHelp'];rows=body['result'];total=int(meta['total'])
    if int(meta['pageNo'])!=page or int(meta['pageSize'])!=100 or not isinstance(rows,list):raise ValueError('Pagination identity mismatch')
    if total<=0 or total>3000 or int(meta['pageCount'])!=math.ceil(total/100):raise ValueError('Unbounded or empty announcement query')
    if expected_total is not None and total!=expected_total:raise ValueError('Announcement directory changed during pagination')
    if len(rows)!=min(100,max(0,total-(page-1)*100)):raise ValueError('Incomplete announcement page')
    return total

METRICS=(('revenue','营业收入'),('net_profit_parent','归属于上市公司股东的净利润'),('operating_cashflow','经营活动产生的现金流量净额'))

def extract_metrics(pages):
    result=[]
    for key,label in METRICS:
        found=[]
        for index,text in enumerate(pages):
            compact=re.sub(r'\s+','',text)
            # Summary table first occurrence, original report current-period first numeric column.
            pattern=re.escape(label)+r'(-?\d[\d,]*\.\d{2})'
            for match in re.finditer(pattern,compact):
                if '单位：元' not in compact and '单位:元' not in compact:continue
                if '人民币' not in compact:continue
                value=str(Decimal(match.group(1).replace(',','')))
                found.append(dict(metric=key,label=label,value=value,unit='元',currency='CNY',period='2024Q1',
                     scope='consolidated',page=index+1,excerpt=compact[max(0,match.start()-40):match.end()+45],
                     unit_evidence='单位：元 币种：人民币',method='rule',verification='rule_extracted_pending_visual_review',
                     confidence='exact_named_row_first_current_period_column'))
        if not found:raise ValueError('Missing unambiguous current-period summary metric: '+key)
        result.append(found[0])
    return result

def fetch(url,path,*,limit=12_000_000):
    request=Request(url,headers={'Referer':'https://www.sse.com.cn/','User-Agent':'Mozilla/5.0 FinancialLearningLab public research'})
    started=now()
    try:
        with urlopen(request,timeout=30) as response:
            if urlparse(response.url).scheme!='https' or urlparse(response.url).hostname!=urlparse(url).hostname:raise ValueError('Unexpected redirect')
            raw=response.read(limit+1)
            if len(raw)>limit:raise ValueError('Response exceeds bounded size')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(raw)
        receipt={'url':url,'requested_at':started,'retrieved_at':now(),'bytes':len(raw),'sha256':file_sha(path),'file':path.relative_to(PROJECT).as_posix()}
        write_json(path.with_name(path.name+'.receipt.json'),receipt)
        return raw,receipt
    except Exception as error:
        write_json(path.with_name(path.name+'.failure.json'),{'url':url,'attempted_at':started,'error':str(error)[:500]});raise

def extract_pdf(path,python,output):
    code="import json,sys;from pypdf import PdfReader;r=PdfReader(sys.argv[1]);print(json.dumps([p.extract_text() for p in r.pages],ensure_ascii=False))"
    run=subprocess.run([str(python),'-X','utf8','-c',code,str(path)],capture_output=True,text=True,encoding='utf8',check=True)
    pages=json.loads(run.stdout)
    cover=re.sub(r'\s+','',pages[0])
    if not all(label in cover for label in ('600519','贵州茅台','2024年第一季度报告')):raise ValueError('PDF identity differs from fixed case')
    write_json(output/'pages.json',{'pages':pages,'extractor':'pypdf','pdf_sha256':file_sha(path)})
    evidence=extract_metrics(pages)
    for fact in evidence:
        required='合并现金流量表' if fact['metric']=='operating_cashflow' else '合并利润表'
        starts=[i for i,t in enumerate(pages) if required in re.sub(r'\s+','',t)]
        if len(starts)!=1:raise ValueError('Missing or ambiguous consolidated statement header')
        first=starts[0];last=len(pages)-1
        for i in range(first+1,len(pages)):
            compact=re.sub(r'\s+','',pages[i])
            if any(h in compact for h in ('合并资产负债表','合并利润表','合并现金流量表','母公司资产负债表','母公司利润表','母公司现金流量表')):
                last=i;break
        fact['scope_header_page']=first+1
        fact['corroborating_pages']=[i+1 for i in range(first,last+1) if fact['value'] in re.sub(r'[\s,]','',pages[i])]
        if not fact['corroborating_pages']:raise ValueError('Cannot corroborate consolidated scope for '+fact['metric'])
    # Independent render is preserved for a human/agent visual check.
    selected=sorted({e['page'] for e in evidence}|{e['scope_header_page'] for e in evidence}|{p for e in evidence for p in e['corroborating_pages']})
    render="import sys,pdfplumber; p=pdfplumber.open(sys.argv[1]); [(p.pages[int(n)-1].to_image(resolution=140).save(sys.argv[2]+'/page-'+n+'.png')) for n in sys.argv[3:]]"
    subprocess.run([str(python),'-X','utf8','-c',render,str(path),str(output),*[str(p) for p in selected]],capture_output=True,text=True,encoding='utf8',check=True)
    return evidence,len(pages),selected

def acquire(output=None,pdf_python=None):
    root=Path(output) if output else PROJECT/'research/artifacts/event-study'/('source-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    if not root.resolve().is_relative_to((PROJECT/'research/artifacts/event-study').resolve()):raise ValueError('Output root outside D28')
    root.mkdir(parents=True,exist_ok=False)
    write_json(root/'protocol.json',{'symbols':SYMBOLS,'publication_range':[BEGIN,END],'selected_case':{'symbol':'600519','report_period':'2024Q1'},'created_at':now(),'source_sha256':file_sha(__file__)})
    with (root/'sources.py').open('xb') as f:f.write(Path(__file__).read_bytes())
    catalog=[];audit=[]
    for symbol in SYMBOLS:
        seen=set();total=None;page=1;rows=[];receipts=[]
        while total is None or len(rows)<total:
            params={'isPagination':'true','productId':symbol,'keyWord':'','securityType':'0101,120100,020100,020200,120200','reportType2':'','reportType':'ALL','beginDate':BEGIN,'endDate':END,'pageHelp.pageSize':100,'pageHelp.pageNo':page,'pageHelp.beginPage':page,'pageHelp.cacheSize':1,'pageHelp.endPage':page}
            raw,receipt=fetch(ENDPOINT+'?'+urlencode(params),root/symbol/f'page-{page}.json');body=json.loads(raw)
            total=verify_page(body,page,total);receipts.append(receipt)
            for row in body['result']:
                ident=(row['TITLE'],row['SSEDATE'],row['URL'])
                if ident in seen:raise ValueError('Repeated announcement across pages')
                seen.add(ident);rows.append(row);event=normalize(row,symbol)
                if event:event['catalog_source']=receipt['file'];event['catalog_source_sha256']=receipt['sha256'];catalog.append(event)
            page+=1
        audit.append({'symbol':symbol,'all_announcement_count':total,'pages':page-1,'received_count':len(rows),'complete_pagination':len(rows)==total,'sources':receipts})
        print(json.dumps(audit[-1]|{'sources':len(receipts)},ensure_ascii=False),flush=True)
    link_versions(catalog);catalog.sort(key=lambda e:(e['symbol'],e['publication_date'],e['title']))
    for item in audit:
        mine=[r for r in catalog if r['symbol']==item['symbol']];item['catalog_count']=len(mine);item['full_report_count']=sum(r['qualification']=='qualified_date_only' for r in mine)
        item['qualification_counts']=dict(Counter(r['qualification'] for r in mine))
        expected={f'{year}{quarter}' for year in (2024,2025) for quarter in ('Q1','H1','Q3')}|{'2023FY','2024FY'}
        present={r['report_period'] for r in mine if r['qualification']=='qualified_date_only'}
        item['expected_full_periods']=sorted(expected);item['missing_full_periods']=sorted(expected-present)
    cases=[r for r in catalog if r['symbol']=='600519' and r['report_period']=='2024Q1' and r['qualification']=='qualified_date_only']
    if len(cases)!=1:raise ValueError('Deterministic case missing or ambiguous; no replacement')
    event=cases[0];folder=root/'case';path=folder/'report.pdf'
    try:raw,pdf_receipt=fetch(event['url'],path)
    except Exception:
        # Explicit same-document official disclosure mirror. No challenge bypass.
        path=folder/'cninfo-report.pdf';raw,pdf_receipt=fetch(CASE_PDF_MIRROR,path)
    if not raw.startswith(b'%PDF'):raise ValueError('Official case response is not PDF')
    evidence,count,selected=extract_pdf(path,pdf_python or sys.executable,folder)
    case={'event_id':event['event_id'],'symbol':event['symbol'],'report_period':event['report_period'],'pdf_path':path.relative_to(PROJECT).as_posix(),'pdf_sha256':file_sha(path),'pdf_url':pdf_receipt['url'],'catalog_pdf_url':event['url'],'page_count':count,'evidence':evidence,'visual_review_pages':selected,'pdf_source':pdf_receipt,'mirror_note':'官方SSE目录URL保留；若SSE附件不可访问则使用固定CNinfo官方同文并核验证券代码/标题/报告期。','model_extraction_status':'not_run','accuracy_status':'no_labeled_benchmark'}
    result={'schema':'event-source-catalog-v1','created_at':now(),'catalog':catalog,'audit':audit,'case':case,'limitations':LIMITATIONS,
            'artifacts':{p.relative_to(PROJECT).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file()}}
    write_json(root/'catalog.json',result);print('CATALOG '+str(root/'catalog.json'),flush=True);return root/'catalog.json'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--pdf-python',type=Path);a=p.parse_args();acquire(a.output,a.pdf_python)
