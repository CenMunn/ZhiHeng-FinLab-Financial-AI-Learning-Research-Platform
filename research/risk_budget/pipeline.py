"""D26 immutable reconstruction, independent fitting/calibration and pre-score freeze."""
import argparse
import json
import shutil
import traceback
from datetime import datetime,timezone
from pathlib import Path
from .common import CONFIG,FOLDS,SYMBOLS,SOURCE_REPORT_ID,PROJECT,digest,file_sha,write_json,read,verify,sources,environment,archive_sources
from .data import make_rows,partition

ROLES=('train','early_stopping','calibration','evaluation_features','evaluation_labels')

def now():return datetime.now(timezone.utc).isoformat()

def load_role(folder,role):
    if role not in ROLES[:-1]:raise ValueError('Training may not load evaluation labels')
    return read(Path(folder)/(role+'.json'))

def calibration_features(folder):
    text=(Path(folder)/'calibration.json').read_text(encoding='utf8')
    decoder=json.JSONDecoder();position=text.index('{')+1;result={}
    for expected in ('rows','x','y'):
        while text[position].isspace() or text[position]==',':position+=1
        key,position=decoder.raw_decode(text,position)
        if key!=expected:raise ValueError('Noncanonical calibration keys')
        if key=='y':return result
        while text[position].isspace() or text[position]==':':position+=1
        result[key],position=decoder.raw_decode(text,position)
    raise ValueError('Missing calibration features')

def prepare(*,attempt='initial',output=None):
    import sys
    sys.path.insert(0,str(PROJECT/'backend/src'))
    from platform_app.adapters.validation_foundation_store import ValidationFoundationStore
    source=ValidationFoundationStore(PROJECT/'backend/data/validation-foundation',PROJECT).get(SOURCE_REPORT_ID)
    if source['artifact_status']!='verified' or len(source['record']['artifacts'])!=876:raise ValueError('D24 fixed 876-file source must verify')
    source={'record':source['record'],'record_sha256':source['record_sha256']}
    identity=dict(config=CONFIG,sources=sources(),environment=environment(),source_report_id=SOURCE_REPORT_ID,
                  source_report_sha256=source['record_sha256'],attempt=attempt)
    root=Path(output) if output else PROJECT/'research/artifacts/risk-budget'/digest(identity)
    if not root.resolve().is_relative_to((PROJECT/'research/artifacts/risk-budget').resolve()):raise ValueError('Output outside D26 artifact root')
    if (root/'protocol.json').exists():
        protocol=read(root/'protocol.json')
        if {k:protocol[k] for k in identity}!=identity:raise ValueError('Changed identity; use new --attempt')
        verify(root,read(root/'inputs.json')['files']);return root
    root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):raise ValueError('Partial attempt preserved; use new --attempt')
    write_json(root/'protocol.json',{**identity,'created_at':now()});write_json(root/'source.json',source)
    inputs={n:file_sha(root/n) for n in ('protocol.json','source.json')};inputs.update(archive_sources(root,identity['sources']))
    mapping=source['record']['artifacts']
    for symbol in SYMBOLS:
        asset=next(a for a in source['record']['assets'] if a['symbol']==symbol)
        if asset['status']!='qualified':raise ValueError('Unqualified asset')
        original=next(n for n in mapping if n.endswith('/datasets/'+symbol+'.json'))
        if file_sha(PROJECT/original)!=mapping[original]:raise ValueError('D24 dataset changed')
        target=root/symbol/'dataset.json';target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(PROJECT/original,target)
        if file_sha(target)!=mapping[original]:raise ValueError('Dataset snapshot copy mismatch')
        dataset=read(target);rows,history=make_rows(dataset)
        write_json(root/symbol/'history.json',history)
        for fold in asset['folds']:
            folder=root/symbol/fold['fold'];parts,purged=partition(rows,fold['bounds'])
            counts={k:len(v) for k,v in parts.items()}
            if min(counts.values())<20:raise ValueError('Insufficient D26 role rows')
            for role,items in parts.items():
                payload={'rows':[{k:v for k,v in r.items() if k not in ('x','target')} for r in items], 'x':[r['x'] for r in items]}
                if role=='evaluation':
                    write_json(folder/'evaluation_labels.json',{'rows':payload['rows'],'y':[r['target'] for r in items]});name='evaluation_features'
                else:payload['y']=[r['target'] for r in items];name=role
                write_json(folder/(name+'.json'),payload)
            write_json(folder/'preparation.json',dict(bounds=fold['bounds'],counts=counts,purged=purged,lead=2 if dataset['market']=='ashare' else 3))
    inputs.update({p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*.json')})
    write_json(root/'inputs.json',{'files':inputs});print('PREPARED '+str(root),flush=True);return root

def run_unit(root,symbol,fold):
    from .train import fit_models,calibrate
    folder=root/symbol/fold;input_sha=file_sha(root/'inputs.json')
    if (folder/'completed.json').exists():
        completed=read(folder/'completed.json')
        if completed['inputs_sha256']!=input_sha:raise ValueError('Completed input mismatch')
        verify(folder,completed['files']);return
    if any((folder/n).exists() for n in ('models','failed.json','training.json','predictions.json')):raise ValueError('Incomplete unit retained; use explicit new --attempt')
    train=load_role(folder,'train');early=load_role(folder,'early_stopping');cal=calibration_features(folder);evaluation=load_role(folder,'evaluation_features')
    history=read(root/symbol/'history.json');indices=[[r['history_index'] for r in p['rows']] for p in (train,early,cal,evaluation)]
    preparation=read(folder/'preparation.json')
    fit=fit_models(train,early,cal,evaluation,history_returns=history,indices=indices,lead=preparation['lead'],folder=folder/'models')
    y=load_role(folder,'calibration')['y']
    predictions={k:calibrate(p['calibration_raw'],y,p['raw']) for k,p in fit['predictions'].items()}
    write_json(folder/'predictions.json',dict(models=predictions,calibration_labels_read=True,evaluation_labels_read=False))
    write_json(folder/'training.json',dict(models=fit['models'],artifacts={'models/'+k:v for k,v in fit['artifacts'].items()},
               bounds=preparation['bounds'],counts=preparation['counts'],purged=preparation['purged'],source_inputs_sha256=input_sha,evaluation_labels_read=False))
    verify(root,read(root/'inputs.json')['files'])
    files={p.relative_to(folder).as_posix():file_sha(p) for p in folder.rglob('*') if p.is_file()}
    write_json(folder/'completed.json',dict(inputs_sha256=input_sha,files=files));print(f'COMPLETED {symbol} {fold} '+now(),flush=True)

def run(root,*,symbols=None):
    protocol=read(root/'protocol.json')
    if protocol['sources']!=sources() or protocol['environment']!=environment():raise ValueError('Frozen source/environment changed')
    inputs=read(root/'inputs.json');verify(root,inputs['files'])
    if (root/'frozen.json').exists():
        frozen=read(root/'frozen.json')
        if frozen['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('Frozen input identity changed')
        verify(root,frozen['files']);return
    for symbol in symbols or SYMBOLS:
        if symbol not in SYMBOLS:raise ValueError('Unknown symbol')
        for fold in FOLDS:
            try:run_unit(root,symbol,fold)
            except Exception:
                write_json(root/symbol/fold/'failed.json',dict(created_at=now(),error=traceback.format_exc()));raise
    if symbols is not None:return
    if protocol['sources']!=sources():raise ValueError('Source changed during training; refusing freeze')
    verify(root,inputs['files'])
    for symbol in SYMBOLS:
        for fold in FOLDS:
            completed=read(root/symbol/fold/'completed.json')
            if completed['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('Unit inputs changed')
            verify(root/symbol/fold,completed['files'])
    files={p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file()}
    write_json(root/'frozen.json',dict(created_at=now(),protocol_sha256=digest(protocol),inputs_sha256=file_sha(root/'inputs.json'),files=files));print('FROZEN '+str(root),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='initial');parser.add_argument('--output',type=Path)
    parser.add_argument('--root',type=Path);parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--symbols',nargs='+');args=parser.parse_args()
    root=args.root or prepare(attempt=args.attempt,output=args.output)
    if not args.prepare_only:run(root,symbols=args.symbols)

if __name__=='__main__':main()
