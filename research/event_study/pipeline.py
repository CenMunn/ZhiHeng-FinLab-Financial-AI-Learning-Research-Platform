"""Publish a fixed public announcement teaching case; no model calls or account writes."""
import argparse,json,os,re,sys,tempfile
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path,PurePosixPath
from research.market.common import PROJECT,digest,file_sha,write_json

ROOT=PROJECT/'research/artifacts/event-study'

def verify_artifacts(project, mapping):
    project=Path(project).resolve();allowed=project/'research/artifacts/event-study'
    if not mapping:raise ValueError('缺少来源产物')
    for name,expected in mapping.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:raise ValueError('来源路径越界')
        path=(project/name).resolve()
        if not path.is_relative_to(allowed.resolve()) or not path.is_file() or file_sha(path)!=expected:raise ValueError('来源缺失或摘要变化：'+name)

def committee_facts(case):
    """Match the existing public Fact contract without touching its authenticated store."""
    rows=[];sha=case['pdf_sha256']
    if not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('PDF摘要非法')
    for row in case['evidence']:
        try:value=Decimal(row['value'])
        except (InvalidOperation,TypeError):raise ValueError('金额非法') from None
        period=row['period'];page=row['page']
        if (not value.is_finite() or row['scope'] not in ('consolidated','parent') or
            not re.fullmatch(r'20\d{2}(Q[1-4]|H[12]|FY)',period) or type(page) is not int or page<1 or
            row['unit'] not in ('元','万元','百万元','亿元')):raise ValueError('证据单位/范围/期间/页码不明确')
        period_end=period[:4] if period.endswith('FY') else period[:4]+'-'+{'Q1':'03-31','Q2':'06-30','Q3':'09-30','Q4':'12-31','H1':'06-30','H2':'12-31'}[period[4:]]
        rows.append({'sourceId':f'D28:{sha}:P{page}:{row["metric"]}','page':page,'label':row['label'],
                     'year':int(period[:4]),'period':period_end,'scope':row['scope'],'unit':row['unit'],'value':row['value'],
                     'currency':'人民币','annualFlow':period.endswith('FY'),'quote':row['excerpt']})
    return rows

def validate_derived(source,source_path,market,market_path):
    """Embedded summaries must reproduce the pinned source and dataset files."""
    from research.event_study.sources import normalize,link_versions,extract_metrics,verify_page
    for manifest in (source,market):verify_artifacts(PROJECT,manifest['artifacts'])
    def read_pinned(path,mapping):
        path=Path(path).resolve();name=path.relative_to(PROJECT.resolve()).as_posix()
        if mapping.get(name)!=file_sha(path):raise ValueError('派生字段缺少绑定的输入文件')
        return json.loads(path.read_text('utf8'))
    if set(market['stocks'])!={'600519','600036','600585'}:raise ValueError('行情样本集合变化')
    for symbol,value in {**market['stocks'],'000300':market['benchmark']}.items():
        if read_pinned(Path(market_path).parent/'datasets'/(symbol+'.json'),market['artifacts'])!=value:raise ValueError('清单内行情不等于已绑定数据集')
    catalog=[]
    if {a['symbol'] for a in source['audit']}!={'600519','600036','600585'} or len(source['audit'])!=3:raise ValueError('目录审计标的不完整')
    for audit in source['audit']:
        total=None;received=0;seen=set()
        for page,receipt in enumerate(audit['sources'],1):
            if source['artifacts'].get(receipt['file'])!=receipt['sha256']:raise ValueError('目录来源摘要不符')
            body=read_pinned(PROJECT/receipt['file'],source['artifacts']);total=verify_page(body,page,total)
            for row in body['result']:
                key=(row['TITLE'],row['SSEDATE'],row['URL'])
                if key in seen:raise ValueError('目录分页重复')
                seen.add(key);received+=1;event=normalize(row,audit['symbol'])
                if event:
                    event.update(catalog_source=receipt['file'],catalog_source_sha256=receipt['sha256']);catalog.append(event)
        if received!=total or received!=audit['received_count'] or total!=audit['all_announcement_count']:raise ValueError('目录分页计数不符')
    link_versions(catalog);catalog.sort(key=lambda e:(e['symbol'],e['publication_date'],e['title']))
    if catalog!=source['catalog']:raise ValueError('公告目录派生字段与原响应不符')
    case=source['case'];pages=read_pinned(Path(source_path).parent/'case/pages.json',source['artifacts'])
    if pages['pdf_sha256']!=case['pdf_sha256'] or len(pages['pages'])!=case['page_count']:raise ValueError('文本提取与PDF身份不符')
    extracted=extract_metrics(pages['pages'])
    if len(extracted)!=len(case['evidence']):raise ValueError('证据字段集合变化')
    for raw,fact in zip(extracted,case['evidence']):
        if any(fact.get(k)!=v for k,v in raw.items()):raise ValueError('财务证据不等于原始页内规则结果')

def atomic_latest(path,body):
    path.parent.mkdir(parents=True,exist_ok=True);fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.event-')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as stream:
            json.dump(body,stream,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:Path(temp).unlink(missing_ok=True)

def publish(source_manifest, market_manifest):
    sys.path.insert(0,str(PROJECT/'backend/src'))
    from platform_app.experiments.event_study import analyze
    source_path,market_path=Path(source_manifest).resolve(),Path(market_manifest).resolve()
    if not all(p.is_relative_to(ROOT.resolve()) for p in (source_path,market_path)):raise ValueError('输入清单路径越界')
    source=json.loads(source_path.read_text('utf8'));market=json.loads(market_path.read_text('utf8'))
    artifacts={**source['artifacts'],**market['artifacts'],source_path.relative_to(PROJECT).as_posix():file_sha(source_path),market_path.relative_to(PROJECT).as_posix():file_sha(market_path)}
    verify_artifacts(PROJECT,artifacts)
    validate_derived(source,source_path,market,market_path)
    case=source['case'];catalog=source['catalog'];selected=[e for e in catalog if e['event_id']==case['event_id']]
    if len(selected)!=1 or selected[0]['symbol']!='600519':raise ValueError('固定案例身份不符')
    event=selected[0]
    if event['report_period']!='2024Q1':raise ValueError('本轮案例不是预先固定的茅台2024Q1')
    if event['qualification']!='qualified_date_only' or event['document_type']!='quarterly':raise ValueError('固定案例不是合格季度正文')
    pdf=PROJECT/case['pdf_path']
    if artifacts.get(case['pdf_path'])!=case['pdf_sha256'] or file_sha(pdf)!=case['pdf_sha256']:raise ValueError('案例PDF摘要未绑定')
    review_path=ROOT/'reviews'/(case['pdf_sha256']+'.json');review=json.loads(review_path.read_text('utf8'))
    expected={f['metric']:f['value'] for f in case['evidence']}
    if (review['pdf_sha256']!=case['pdf_sha256'] or review['values']!=expected or review['period']!='2024Q1' or
        review['scope']!='consolidated' or review['unit']!='元' or not set(case['visual_review_pages'])<=set(review['reviewed_pages'])):raise ValueError('视觉核验收据不符')
    artifacts[review_path.relative_to(PROJECT).as_posix()]=file_sha(review_path)
    case={**case,'visual_review':review,'evidence':[{**f,'verification':'rule_extracted_visual_reviewed'} for f in case['evidence']]}
    stock=market['stocks']['600519'];benchmark=market['benchmark']
    if stock['symbol']!='600519':raise ValueError('案例行情标的不符')
    facts=committee_facts(case)
    source_names=['backend/src/platform_app/experiments/event_study.py','apps/committee/src/lib/filings/core.ts']
    source_names += sorted(p.relative_to(PROJECT).as_posix() for p in Path(__file__).parent.glob('*.py'))
    sources={name:file_sha(PROJECT/name) for name in source_names}
    protocol={'schema':'event-study-protocol-v1','catalog_publication_range':['2024-01-01','2025-12-31'],
      'symbols':['600519','600036','600585'],'fixed_case':'600519/2024Q1','estimation_offsets':[-130,-21],
      'event_window_default':[-5,5],'window_preview_each_side':[1,10],
      'selection':'case fixed before returns inspected; historical descriptive teaching, not causal identification',
      'source_manifest_sha256':file_sha(source_path),'market_manifest_sha256':file_sha(market_path),'visual_review_sha256':file_sha(review_path),'sources':sources}
    run_id='event-'+digest(protocol);folder=ROOT/'publications'/run_id
    write_json(folder/'protocol.json',protocol)
    for name,expected in sources.items():
        path=folder/'source-code'/name;path.parent.mkdir(parents=True,exist_ok=True);raw=(PROJECT/name).read_bytes()
        if file_sha(PROJECT/name)!=expected:raise ValueError('编排期间源码变化')
        if path.exists():
            if path.read_bytes()!=raw:raise ValueError('源码快照变化')
        else:
            with path.open('xb') as stream:stream.write(raw)
        artifacts[path.relative_to(PROJECT).as_posix()]=expected
    artifacts[(folder/'protocol.json').relative_to(PROJECT).as_posix()]=file_sha(folder/'protocol.json')
    analysis=analyze(stock,benchmark,event,pre=5,post=5)
    limitations=list(dict.fromkeys(source.get('limitations',[])+market.get('limitations',[])+analysis.get('limitations',[])+[
      '公告来源当前可见版本不证明历史首次公开时刻；日期代理及修订状态须结合目录理解。',
      '本案例预先固定，单事件反应不证明因果，不代表策略收益；调整窗口属于探索。',
      '本轮仅建立规则抽取与原文核验案例，模型抽取尚未运行，未建立独立标注集和准确率。',
      '兼容智投委Fact字段的公开证据导出不会自动导入原账号工作区，私有财报仍走原认证。']))
    archive=PROJECT/'backend/data/event-study'/(run_id+'.json')
    created=datetime.now(timezone.utc).isoformat()
    if archive.exists():created=json.loads(archive.read_text('utf8'))['record']['created_at']
    record={'schema':'event-study-publication-v1','run_id':run_id,'created_at':created,'protocol':protocol,'sources':sources,
      'catalog':catalog,'case':case,'stock':stock,'benchmark':benchmark,'analysis':analysis,'artifacts':artifacts,'limitations':limitations,
      'committee_compatibility':{'schema':'Fact','source_contract':'apps/committee/src/lib/filings/core.ts','facts':facts,'workspace_imported':False,
        'period_mapping':'季度/半年度期间映射至Fact.period期末日期，annualFlow=false；原期间和单位保留于case.evidence，不能当年度流量。'},
      'extraction_evaluation':{'rule':'规则抽取；逐字段核验状态见证据','model':'not_run','gold':'not_established'},
      'catalog_audit':source.get('audit',{})}
    verify_artifacts(PROJECT,artifacts)
    if any(file_sha(PROJECT/name)!=sha for name,sha in sources.items()):raise ValueError('发布前源码变化')
    envelope={'record':record,'sha256':digest(record)};write_json(archive,envelope);atomic_latest(archive.parent/'latest.json',envelope)
    print(json.dumps({'run_id':run_id,'catalog_rows':len(catalog),'case':event['title'],'analysis':analysis['summary'],'sha256':envelope['sha256']},ensure_ascii=False),flush=True)
    return envelope

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sources',type=Path,required=True);p.add_argument('--market',type=Path,required=True);a=p.parse_args();publish(a.sources,a.market)
