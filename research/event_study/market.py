"""D28 fixed D24 stock/calendar snapshots and bounded CSI300 raw price acquisition."""
import argparse,json,hashlib,shutil
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path,PurePosixPath
from urllib.request import Request,urlopen
from urllib.parse import urlparse
from research.market.common import PROJECT,digest,file_sha,write_json

SOURCE_ID='validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c'
SYMBOLS=('600519','600036','600585')
YEARS=(2023,2024,2025)

def verify_artifacts(root,files):
    root=Path(root).resolve()
    for name,sha in files.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:raise ValueError('Unsafe artifact path')
        p=(root/name).resolve()
        if not p.is_relative_to(root) or not p.is_file() or file_sha(p)!=sha:raise ValueError('Missing/changed artifact: '+name)

def parse_index(raw,year):
    body=json.loads(raw)
    if body.get('code')!=0:raise ValueError('Index provider error')
    series=body['data']['sh000300']
    if 'day' not in series:raise ValueError('Raw index day series missing')
    result=[]
    for row in series['day']:
        session=date.fromisoformat(row[0])
        if session.year!=year or len(row)<6:raise ValueError('Unexpected index year/shape')
        try:values=[Decimal(str(x)) for x in row[1:6]]
        except InvalidOperation:raise ValueError('Invalid index number') from None
        op,cl,hi,lo,vol=values
        if not all(x.is_finite() for x in values) or min(op,cl,hi,lo)<=0 or vol<0 or not lo<=min(op,cl)<=max(op,cl)<=hi:raise ValueError('Invalid index OHLCV')
        result.append(dict(session=str(session),open=str(op),close=str(cl),high=str(hi),low=str(lo),volume=str(vol)))
    days=[r['session'] for r in result]
    if not days or days!=sorted(set(days)):raise ValueError('Index dates missing/duplicate/unordered')
    return result

def validate_index(rows,calendar):
    if [r['session'] for r in rows]!=calendar:raise ValueError('Index does not cover exact frozen trading calendar')

def acquire(*,attempt='initial'):
    source_path=PROJECT/'backend/data/validation-foundation/versions'/(SOURCE_ID+'.json')
    source=json.loads(source_path.read_text('utf8'));report=source['record']
    if digest(report)!=source['sha256'] or report['report_id']!=SOURCE_ID or report['protocol_sha256']!=digest(report['protocol']):raise ValueError('D24 source changed')
    if SOURCE_ID!='validation-'+digest({k:report[k] for k in ('protocol_sha256','assets','artifacts')}):raise ValueError('D24 source identity mismatch')
    verify_artifacts(PROJECT,report['artifacts'])
    identity={'source_report_id':SOURCE_ID,'source_report_sha256':source['sha256'],'symbols':list(SYMBOLS),'benchmark':'000300','years':list(YEARS),'attempt':attempt,'normalizer_sha256':file_sha(Path(__file__))}
    root=PROJECT/'research/artifacts/event-study'/('market-'+digest(identity));manifest_path=root/'manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text('utf8'))
        if manifest['identity']!=identity:raise ValueError('Market identity changed')
        verify_artifacts(PROJECT,manifest['artifacts'])
        return {**manifest,'manifest_path':str(manifest_path),'artifacts':{**manifest['artifacts'],manifest_path.relative_to(PROJECT).as_posix():file_sha(manifest_path)}}
    root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):raise ValueError('Partial market acquisition retained; use new --attempt')
    try:
        # Original source manifest and receipt bytes remain attributable to their fixed D24 hash.
        copied={};stocks={};calendar=None
        def copy_source(original,target_name):
            p=PROJECT/original;sha=report['artifacts'][original]
            if file_sha(p)!=sha:raise ValueError('Source changed during copy')
            target=root/target_name;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if file_sha(target)!=sha:raise ValueError('Copied source differs')
            else:shutil.copyfile(p,target)
            if file_sha(target)!=sha:raise ValueError('Source copy failed')
            copied[target.relative_to(PROJECT).as_posix()]={'original_path':original,'sha256':sha}
            return target
        write_json(root/'d24-source.json',source)
        for symbol in SYMBOLS:
            asset=next(a for a in report['assets'] if a['symbol']==symbol)
            if asset['status']!='qualified':raise ValueError('Unqualified D24 stock')
            original='research/artifacts/validation-data/v1/datasets/'+symbol+'.json'
            path=copy_source(original,'datasets/'+symbol+'.json');dataset=json.loads(path.read_text('utf8'))
            stocks[symbol]=dataset
            sessions=dataset['expected_sessions']
            if calendar is not None and sessions!=calendar:raise ValueError('Frozen stock calendars differ')
            calendar=sessions
            for receipt in asset['source_receipts']:
                original='research/artifacts/validation-data/v1/'+receipt['file']
                copy_source(original,'d24/'+receipt['file'])
                receipt_original=original+'.receipt.json'
                if receipt_original in report['artifacts']:copy_source(receipt_original,'d24/'+receipt['file']+'.receipt.json')
        rows=[];receipts=[]
        for year in YEARS:
            url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000300,day,{year}-01-01,{year}-12-31,640,'
            request=Request(url,headers={'User-Agent':'FinancialLearningLab/0.1 (historical event-study research)'})
            with urlopen(request,timeout=20) as response:
                if urlparse(response.url).scheme!='https' or urlparse(response.url).netloc!='web.ifzq.gtimg.cn':raise ValueError('Unexpected index redirect')
                raw=response.read(4_000_001)
                if len(raw)>4_000_000:raise ValueError('Index response exceeds4MB')
            path=root/'raw'/f'tencent-000300-{year}.json';path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(raw)
            receipt={'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'sha256':file_sha(path),'file':path.relative_to(PROJECT).as_posix(),'bytes':len(raw)}
            write_json(path.with_suffix('.receipt.json'),receipt);receipts.append(receipt);rows+=parse_index(raw,year)
        calendar=[d for d in calendar if '2023-01-01'<=d<='2025-12-31'];validate_index(rows,calendar)
        benchmark={'symbol':'000300','name':'沪深300价格指数','market':'ashare-index','bars':rows,'expected_sessions':calendar,'dividends':[],
                   'return_basis':'price index close-to-close; excludes reinvested cash dividends','receipts':receipts}
        write_json(root/'datasets/000300.json',benchmark)
        artifacts={p.relative_to(PROJECT).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file()}
        manifest={'schema':'event-market-input-v1','identity':identity,'created_at':datetime.now(timezone.utc).isoformat(),'stocks':stocks,'benchmark':benchmark,
                  'source_copies':copied,'artifacts':artifacts,'limitations':['股票与日历来自固定D24历史重建，不是历史逐时PIT数据。','沪深300为价格指数；股票收益含税前现金分红，两者不是完全相同的总收益口径。','市场模型仅用于单事件描述，不模拟交易、费用或显著性。']}
        write_json(manifest_path,manifest)
        return {**manifest,'manifest_path':str(manifest_path),'artifacts':{**artifacts,manifest_path.relative_to(PROJECT).as_posix():file_sha(manifest_path)}}
    except Exception as error:
        write_json(root/'failed.json',{'created_at':datetime.now(timezone.utc).isoformat(),'error':str(error),'identity':identity});raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--attempt',default='initial');args=parser.parse_args()
    value=acquire(attempt=args.attempt)
    print(json.dumps({'manifest_path':value['manifest_path'],'benchmark_rows':len(value['benchmark']['bars']),'stocks':list(value['stocks']),'artifacts':len(value['artifacts'])},ensure_ascii=False))
