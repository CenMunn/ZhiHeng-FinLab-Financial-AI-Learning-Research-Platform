"""Inference-only D27 adapter for the latest chronological, frozen D26 fold.

No fitting module is imported. All seven outputs retain the original scales,
calibration coefficients and EWMA initialization. Historical replay is only a
verification facility; the caller owns the live decision-time admission gate.
"""
import hashlib
import io
import json
import math
from datetime import datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT/'research/artifacts/risk-budget/6280750f22c41b4f7100f4d9ec7f439da022a6aa92917e6d1fb5b8a1aad62cf7'
FROZEN_SHA = '5f1b7eea708c65a6b4489bc1d4bbf3d01764b5d21eb8409d56c72765c4ec4e0b'
SYMBOLS = ('600519','600036','600585','BTCUSDT','ETHUSDT')
FOLD = '2025Q4'
KEYS = ('train_mean','ewma','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear')
FLOOR = 1e-10
LOADED_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _read(path, expected=None):
    data=Path(path).read_bytes()
    if expected is not None and hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError('Frozen artifact changed: '+str(path))
    return json.loads(data)


def _path(root,name):
    relative=PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
        raise ValueError('Unsafe frozen artifact path')
    p=(root/name).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('Escaped frozen root')
    return p


def _verify_files(root,files):
    for name,expected in files.items():
        path=_path(root,name)
        with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=expected:raise ValueError('Frozen artifact changed: '+name)


def load_bundle(symbol):
    """Verify the complete fixed archive, then return a JSON-serializable manifest."""
    if symbol not in SYMBOLS:raise ValueError('Unsupported forward symbol')
    frozen=_read(ROOT/'frozen.json',FROZEN_SHA)
    _verify_files(ROOT,frozen['files'])
    protocol=_read(ROOT/'protocol.json')
    if _digest(protocol)!=frozen['protocol_sha256']:raise ValueError('Frozen protocol mismatch')
    source=_read(ROOT/'source.json')
    if _digest(source['record'])!=source['record_sha256'] or source['record_sha256']!=protocol['source_report_sha256']:
        raise ValueError('Frozen qualification source mismatch')
    _verify_files(PROJECT,source['record']['artifacts'])
    # Verify archived source bytes; inference never imports their fitting code.
    for name,sha in protocol['sources'].items():
        if hashlib.sha256(_path(ROOT,'source-code/'+name).read_bytes()).hexdigest()!=sha:
            raise ValueError('Archived numerical source changed')
    identity=dict(protocol_sha256=_digest(protocol),source_report_sha256=source['record_sha256'],symbol=symbol)
    run_id='risk-'+_digest(identity)
    publication=_read(PROJECT/'backend/data/risk-budget-runs'/(run_id+'.json'))
    record=publication['record']
    if _digest(record)!=publication['sha256'] or record['identity']!=identity or record['run_id']!=run_id:
        raise ValueError('Frozen publication mismatch')
    if max(f['fold'] for f in record['folds'])!=FOLD:raise ValueError('Chronological fold selection mismatch')
    unit=f'{symbol}/{FOLD}/'
    training=_read(ROOT/unit/'training.json')
    predictions=_read(ROOT/unit/'predictions.json')
    if set(predictions['models'])!=set(KEYS):raise ValueError('Frozen model set mismatch')
    model_files={name:sha for name,sha in frozen['files'].items() if name.startswith(unit+'models/')}
    required=[f'{unit}models/{key}.pt' for key in KEYS if key.startswith('dlinear_seed_')]+[unit+'models/lightgbm.txt']
    if not all(name in model_files for name in required):raise ValueError('Missing model checkpoint')
    selection=[unit+'training.json',unit+'predictions.json',symbol+'/history.json',symbol+'/dataset.json','protocol.json','source.json']
    bundle=dict(schema='forward-frozen-bundle-v1',root=str(ROOT),symbol=symbol,market=record['market'],fold=FOLD,
                source_run_id=run_id,source_record_sha256=publication['sha256'],protocol_sha256=_digest(protocol),
                parent_frozen_sha256=FROZEN_SHA,model_files=model_files,
                context_files={n:frozen['files'][n] for n in selection},
                calibration={k:float(predictions['models'][k]['c']) for k in KEYS},
                receipts=training['models'],bounds=training['bounds'],inference_sha256=LOADED_SHA,
                source_frozen_at=frozen['created_at'],last_frozen_session=record['dataset']['bars'][-1]['session'],
                selection_rule='latest chronological fold 2025Q4; no performance selection; no refitting',
                limitations=['Model fit stops at the frozen 2025Q4 training bounds; parameters may be stale.',
                             'All fixed seeds and calibration coefficients retained; no online retraining.'])
    bundle['artifacts']={ROOT.relative_to(PROJECT).as_posix()+'/'+name:sha
                         for name,sha in {**bundle['context_files'],**model_files,'frozen.json':FROZEN_SHA}.items()}
    bundle['bundle_sha256']=_digest(bundle)
    verify_bundle(bundle)
    return bundle


def verify_bundle(bundle):
    body={k:v for k,v in bundle.items() if k!='bundle_sha256'}
    if _digest(body)!=bundle.get('bundle_sha256'):raise ValueError('Frozen bundle metadata changed')
    if (bundle.get('schema')!='forward-frozen-bundle-v1' or bundle.get('root')!=str(ROOT)
        or bundle.get('symbol') not in SYMBOLS or bundle.get('fold')!=FOLD
        or bundle.get('parent_frozen_sha256')!=FROZEN_SHA
        or bundle.get('inference_sha256')!=LOADED_SHA
        or hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=LOADED_SHA):
        raise ValueError('Frozen bundle context changed; reload with a new version')
    frozen=_read(ROOT/'frozen.json',FROZEN_SHA)
    unit_name=f"{bundle['symbol']}/{FOLD}/"
    model_files={name:sha for name,sha in frozen['files'].items() if name.startswith(unit_name+'models/')}
    context_names=[unit_name+'training.json',unit_name+'predictions.json',bundle['symbol']+'/history.json',
                   bundle['symbol']+'/dataset.json','protocol.json','source.json']
    context_files={name:frozen['files'][name] for name in context_names}
    artifacts={ROOT.relative_to(PROJECT).as_posix()+'/'+name:sha
               for name,sha in {**context_files,**model_files,'frozen.json':FROZEN_SHA}.items()}
    if (bundle['model_files']!=model_files or bundle['context_files']!=context_files or bundle['artifacts']!=artifacts):
        raise ValueError('Incomplete or changed frozen bundle manifest')
    files={**bundle['context_files'],**bundle['model_files']}
    if any(frozen['files'].get(name)!=sha for name,sha in files.items()):raise ValueError('Unpinned bundle files')
    _verify_files(ROOT,files)
    unit=ROOT/bundle['symbol']/FOLD
    receipts=_read(unit/'training.json')['models']
    c={k:float(v['c']) for k,v in _read(unit/'predictions.json')['models'].items()}
    if receipts!=bundle['receipts'] or c!=bundle['calibration']:raise ValueError('Frozen bundle scale/calibration changed')
    return bundle


def predict(bundle,history_returns):
    """Forecast from full original-prefix history through the admitted signal only."""
    import numpy as np
    import torch
    import torch.nn.functional as F
    import lightgbm as lgb
    verify_bundle(bundle)
    h=np.asarray(history_returns,dtype=np.float64)
    if h.ndim!=1 or len(h)<61 or not np.isfinite(h).all() or h[0]!=0:
        raise ValueError('Inference requires full finite history, including original zero anchor')
    original=np.asarray(_read(ROOT/bundle['symbol']/'history.json'),dtype=np.float64)
    n=min(len(h),len(original))
    if not np.allclose(h[:n],original[:n],rtol=0,atol=1e-12):
        raise ValueError('Original history prefix changed or EWMA initialization reset')
    x=h[-60:][None,:]
    receipts=bundle['receipts'];unit=ROOT/bundle['symbol']/FOLD/'models'
    raw={'train_mean':max(float(receipts['train_mean']['mean']),FLOOR)}
    state=h[1]**2
    for value in h[2:]:state=.94*state+.06*value*value
    raw['ewma']=max(float(state),FLOOR)
    scale=receipts['lightgbm']['target_scale']
    model_name=f"{bundle['symbol']}/{FOLD}/models/lightgbm.txt"
    model_data=(ROOT/model_name).read_bytes()
    if hashlib.sha256(model_data).hexdigest()!=bundle['model_files'][model_name]:raise ValueError('Model changed during inference')
    # D26 wrote text via Windows newline translation; tree offsets describe LF.
    # Match Path.read_text universal-newline behavior after hashing exact bytes.
    model=lgb.Booster(model_str=model_data.decode('utf8').replace('\r\n','\n').replace('\r','\n'))
    raw['lightgbm']=max(float(model.predict(x**2/scale,num_threads=2)[0]*scale),FLOOR)
    # Direct tensor forward matches D26 exactly and creates no optimizer/train loop.
    torch.set_num_threads(2)
    for key in KEYS:
        if not key.startswith('dlinear_seed_'):continue
        name=f"{bundle['symbol']}/{FOLD}/models/{key}.pt"
        data=(ROOT/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=bundle['model_files'][name]:raise ValueError('Model changed during inference')
        checkpoint=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True)
        receipt=checkpoint['receipt'];scale=receipt['target_scale'];kernel=receipt['kernel']
        weights=checkpoint['state_dict']
        with torch.inference_mode():
            z=torch.tensor(x**2/scale,dtype=torch.float32)
            trend=F.avg_pool1d(F.pad(z.unsqueeze(1),((kernel-1)//2,(kernel-1)//2),mode='replicate'),kernel_size=kernel,stride=1).squeeze(1)
            value=F.softplus(F.linear(trend,weights['trend.weight'],weights['trend.bias'])+
                             F.linear(z-trend,weights['residual.weight'],weights['residual.bias'])).squeeze(-1)+1e-8
            raw[key]=max(float(value[0].item())*scale,FLOOR)
    raw['dlinear']=float(np.mean([raw[f'dlinear_seed_{seed}'] for seed in (17,42,2025)]))
    if any(not math.isfinite(v) or v<=0 for v in raw.values()):raise ValueError('Invalid frozen model output')
    return {'raw':raw,'calibrated':{k:max(v*bundle['calibration'][k],FLOOR) for k,v in raw.items()}}


def _merge_history(dataset,history,snapshot,signal_session):
    if (snapshot.get('status')!='ready' or snapshot['symbol']!=dataset['symbol'] or snapshot['market']!=dataset['market']):
        raise ValueError('Unqualified or mismatched live snapshot')
    arrival=datetime.fromisoformat(snapshot['retrieved_at'])
    if arrival.tzinfo is None:raise ValueError('Snapshot arrival needs timezone')
    old={b['session']:b for b in dataset['bars']};tail=dataset['bars'][-1]['session']
    if len(old)!=len(history) or signal_session<=tail:raise ValueError('Signal does not extend frozen history')
    allbars=snapshot['bars'];bars={b['session']:b for b in allbars}
    if len(bars)!=len(allbars) or list(bars)!=sorted(bars) or signal_session not in bars or tail not in bars:
        raise ValueError('Missing, duplicated or unordered live sessions/anchor')
    def dividends(rows):
        result={}
        for item in rows:
            day=item['session'];value=Decimal(str(item['amount']))
            if day in result or not value.is_finite() or value<0:raise ValueError('Invalid dividend record')
            result[day]=value
        return result
    od=dividends(dataset.get('dividends',[]));nd=dividends(snapshot.get('dividends',[]))
    for day,bar in bars.items():
        if day>signal_session:continue
        value=Decimal(str(bar['open']))
        available=datetime.fromisoformat(bar['available_at'])
        if not value.is_finite() or value<=0 or available.tzinfo is None or available>arrival:
            raise ValueError('Invalid open or future input availability')
        if day in old and (value!=Decimal(str(old[day]['open'])) or nd.get(day,Decimal(0))!=od.get(day,Decimal(0))):
            raise ValueError('Frozen/live overlap revised; preserve both and investigate')
    if any(tail<s['session']<=signal_session for s in snapshot.get('splits',[])):
        raise ValueError('Unsupported split in live history')
    calendar=snapshot['calendar']
    if len(set(calendar))!=len(calendar) or calendar!=sorted(calendar):raise ValueError('Invalid live calendar')
    expected=[d for d in calendar if tail<d<=signal_session]
    actual=[d for d in bars if tail<d<=signal_session]
    if not expected or expected!=actual or expected[-1]!=signal_session:
        raise ValueError('Missing or extra sessions in live history')
    result=list(history);previous=float(old[tail]['open'])
    for day in expected:
        current=float(bars[day]['open']);result.append(math.log((current+float(nd.get(day,0)))/previous));previous=current
    return result


def build_history(bundle,snapshot,signal_session):
    verify_bundle(bundle)
    dataset=_read(ROOT/bundle['symbol']/'dataset.json')
    history=_read(ROOT/bundle['symbol']/'history.json')
    return _merge_history(dataset,history,snapshot,signal_session)
