"""D25 immutable source snapshot, bounded training and pre-score freeze."""
import argparse
import json
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .common import CONFIG, FOLDS, SYMBOLS, SOURCE_REPORT_ID, PROJECT, digest, file_sha, write_json, read, verify, sources, environment, archive_sources
from .train import fit_models, calibrate

ROLES=('train','early_stopping','calibration','evaluation_features','evaluation_labels')

def now():return datetime.now(timezone.utc).isoformat()

def load_role(folder, role):
    if role not in ROLES[:-1]:raise ValueError('Training may not load evaluation labels')
    return read(Path(folder)/(role+'.json'))

def calibration_features(folder):
    # D24 canonical JSON has sorted keys rows,x,y. Decode only the first two
    # values: label bytes may be hashed/copied, but their values are not parsed.
    text=(Path(folder)/'calibration.json').read_text(encoding='utf8')
    decoder=json.JSONDecoder();position=text.index('{')+1;result={}
    for expected in ('rows','x','y'):
        while text[position].isspace() or text[position]==',':position+=1
        key,position=decoder.raw_decode(text,position)
        if key!=expected:raise ValueError('Noncanonical D24 calibration keys')
        if key=='y':return result
        while text[position].isspace() or text[position]==':':position+=1
        result[key],position=decoder.raw_decode(text,position)
    raise ValueError('Missing calibration features')

def prepare(*, attempt='initial', output=None):
    sys.path.insert(0,str(PROJECT/'backend/src'))
    from platform_app.adapters.validation_foundation_store import ValidationFoundationStore
    source=ValidationFoundationStore(PROJECT/'backend/data/validation-foundation',PROJECT).get(SOURCE_REPORT_ID)
    if source['artifact_status']!='verified' or len(source['record']['artifacts'])!=876:
        raise ValueError('D24 fixed 876-file source must verify before training')
    source={'record':source['record'],'record_sha256':source['record_sha256']}
    identity=dict(config=CONFIG,sources=sources(),environment=environment(),source_report_id=SOURCE_REPORT_ID,
                  source_report_sha256=source['record_sha256'],attempt=attempt)
    root=Path(output) if output else PROJECT/'research/artifacts/five-asset'/digest(identity)
    if not root.resolve().is_relative_to((PROJECT/'research/artifacts/five-asset').resolve()):raise ValueError('Output must stay in D25 artifact root')
    if (root/'protocol.json').exists():
        protocol=read(root/'protocol.json')
        if {k:protocol[k] for k in identity}!=identity:raise ValueError('Changed identity; use explicit new --attempt')
        verify(root,read(root/'inputs.json')['files'])
        return root
    root.mkdir(parents=True,exist_ok=True)
    if any(root.iterdir()):raise ValueError('Partial attempt preserved; choose new --attempt')
    write_json(root/'protocol.json',{**identity,'created_at':now()})
    write_json(root/'source.json',source)
    mapping=source['record']['artifacts'];inputs={name:file_sha(root/name) for name in ('protocol.json','source.json')}
    inputs.update(archive_sources(root,identity['sources']))
    def copy(original,target):
        if file_sha(PROJECT/original)!=mapping[original]:raise ValueError('D24 source changed')
        target=root/target;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PROJECT/original,target)
        if file_sha(target)!=mapping[original]:raise ValueError('Snapshot copy mismatch')
        inputs[target.relative_to(root).as_posix()]=file_sha(target)
    for symbol in SYMBOLS:
        asset=next(a for a in source['record']['assets'] if a['symbol']==symbol)
        if asset['status']!='qualified':raise ValueError('Unqualified asset')
        dataset=next(n for n in mapping if n.endswith('/datasets/'+symbol+'.json'))
        copy(dataset,symbol+'/dataset.json')
        for fold in FOLDS:
            for horizon in (1,5):
                for role in ROLES:
                    suffix=f'/{symbol}/{fold}/h{horizon}/{role}.json'
                    original=next(n for n in mapping if n.endswith(suffix))
                    copy(original,suffix[1:])
    write_json(root/'inputs.json',{'files':inputs})
    print('PREPARED '+str(root),flush=True)
    return root

def history_and_indices(dataset, parts):
    bars=dataset['bars'];div={d['session']:float(d['amount']) for d in dataset.get('dividends',[])}
    history=np.asarray([0.]+[float(np.log((float(bars[i]['close'])+div.get(bars[i]['session'],0))/float(bars[i-1]['close']))) for i in range(1,len(bars))])
    sessions={b['session']:i for i,b in enumerate(bars)}
    return history,[[sessions[r['signal_session']] for r in part['rows']] for part in parts]

def run_unit(root,symbol,fold,horizon):
    folder=root/symbol/fold/f'h{horizon}';input_sha=file_sha(root/'inputs.json')
    if (folder/'completed.json').exists():
        completed=read(folder/'completed.json')
        if completed['inputs_sha256']!=input_sha:raise ValueError('Completed input mismatch')
        verify(folder,completed['files']);return
    if (folder/'models').exists() or (folder/'failed.json').exists():raise ValueError('Incomplete unit retained; use explicit new --attempt')
    dataset=read(root/symbol/'dataset.json')
    train=load_role(folder,'train');early=load_role(folder,'early_stopping')
    # Read calibration x/metadata without exposing its targets to fitting.
    cal_features=calibration_features(folder)
    evaluation=load_role(folder,'evaluation_features')
    history,indices=history_and_indices(dataset,[train,early,cal_features,evaluation])
    fit=fit_models(train,early,cal_features,evaluation,history_returns=history,indices=indices,horizon=horizon,folder=folder/'models')
    # All model selection has finished before calibration labels are consumed.
    calibration_y=load_role(folder,'calibration')['y']
    predictions={key:calibrate(p['calibration_raw'],calibration_y,p['raw']) for key,p in fit['predictions'].items()}
    write_json(folder/'predictions.json',dict(models=predictions,calibration_labels_read=True,evaluation_labels_read=False))
    source=read(root/'source.json')['record'];asset=next(a for a in source['assets'] if a['symbol']==symbol)
    bound=next(f for f in asset['folds'] if f['fold']==fold)
    counts=next(h['counts'] for h in bound['horizons'] if h['horizon']==horizon)
    write_json(folder/'training.json',dict(models=fit['models'],artifacts={'models/'+k:v for k,v in fit['artifacts'].items()},
               bounds=bound['bounds'],counts=counts,source_inputs_sha256=input_sha))
    files={p.relative_to(folder).as_posix():file_sha(p) for p in folder.rglob('*') if p.is_file()}
    write_json(folder/'completed.json',dict(inputs_sha256=input_sha,files=files))
    print(f'COMPLETED {symbol} {fold} h{horizon} '+now(),flush=True)

def run(root):
    protocol=read(root/'protocol.json')
    if protocol['sources']!=sources() or protocol['environment']!=environment():raise ValueError('Frozen source/environment changed')
    inputs=read(root/'inputs.json');verify(root,inputs['files'])
    if (root/'frozen.json').exists():
        frozen=read(root/'frozen.json');verify(root,frozen['files']);return
    for symbol in SYMBOLS:
        for fold in FOLDS:
            for horizon in (1,5):
                try:run_unit(root,symbol,fold,horizon)
                except Exception:
                    failure=root/symbol/fold/f'h{horizon}'/'failed.json'
                    write_json(failure,dict(created_at=now(),error=traceback.format_exc()))
                    raise
    if protocol['sources']!=sources():raise ValueError('Source changed during training; refusing freeze')
    verify(root,inputs['files'])
    files={p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file()}
    write_json(root/'frozen.json',dict(created_at=now(),protocol_sha256=digest(protocol),inputs_sha256=file_sha(root/'inputs.json'),files=files))
    print('FROZEN '+str(root),flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--attempt',default='initial');parser.add_argument('--output',type=Path)
    parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    root=prepare(attempt=args.attempt,output=args.output)
    if not args.prepare_only:run(root)

if __name__=='__main__':main()
