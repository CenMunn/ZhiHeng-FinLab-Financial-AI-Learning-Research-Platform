import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from research.volatility.common import PROJECT,digest,file_sha,write_json,read_checked,sources,environment,verify
from research.volatility.data import make_rows,partition,regime_thresholds
from research.rolling.data import fold_specs
from platform_app.adapters.public_market import IDS,load_dataset
from platform_app.contracts.models import stable_hash
from research.volatility.provenance import seal_inputs,check_inputs,seal_fold,check_fold,reject_partial

def prepare(attempt='default'):
    datasets=[load_dataset(PROJECT/'backend/data/public-market',key) for key in IDS]
    protocol={'schema':'volatility-protocol-v2','attempt':attempt,'sources':sources(),'environment':environment(),'folds':fold_specs(),
        'datasets':{d.snapshot.market:stable_hash(d.model_dump(mode='json')) for d in datasets},'horizons':[1,5],
        'target':'mean of next h squared dividend-adjusted log close returns; zero-mean second-moment proxy',
        'models':'train mean,hist20,EWMA .94,zero-mean GARCH11 Normal QMLE,NNLS HAR-style1/5/22,LightGBM gamma200/patience20,DLinear softplus100/patience12 seeds17/42/2025',
        'regime':'train terciles of trailing20 mean square x sign trailing60 summed log return; ties low and flat up',
        'score':'log(pred)+truth/pred; predictionfloor1e-10; 252/365 annualization; no division by horizon',
        'interval':'quarter-stratified20row movingblock2000repeats then regime filter; exploratory pointwise intervals'}
    root=PROJECT/'research/artifacts/volatility'/('v1-'+digest(protocol)[:24]);write_json(root/'protocol.json',protocol)
    for data in datasets:
        market=data.snapshot.market;write_json(root/market/'dataset.json',data.model_dump(mode='json'))
        for h in (1,5):
            rows,history=make_rows(data,h);write_json(root/market/f'h{h}'/'history.json',history)
            for spec in protocol['folds']:
                folder=root/market/f'h{h}'/spec['fold'];parts,purged=partition(rows,spec);files={}
                if min(map(len,parts.values()))<20:raise ValueError('季度样本不足')
                thresholds=regime_thresholds([r['x'] for r in parts['train']])
                for key,items in parts.items():
                    values={'rows':[{k:v for k,v in r.items() if k not in ('x','target')} for r in items],'x':[r['x'] for r in items]}
                    if key=='evaluation':
                        name='evaluation_labels.json';write_json(folder/name,{'rows':values['rows'],'y':[r['target'] for r in items]});files[name]=file_sha(folder/name)
                        name='evaluation_features.json'
                    else:values['y']=[r['target'] for r in items];name=key+'.json'
                    write_json(folder/name,values);files[name]=file_sha(folder/name)
                write_json(folder/'preparation.json',{'files':files,'counts':{k:len(v) for k,v in parts.items()},'purged':purged,'bounds':spec,'regime_thresholds':{'low':thresholds[0],'high':thresholds[1]},'protocol_sha256':digest(protocol)})
    seal_inputs(root)
    return root

def train(root):
    from research.volatility.models import fit_models
    protocol=json.loads((root/'protocol.json').read_text('utf8'))
    if protocol['sources']!=sources() or protocol['environment']!=environment():raise ValueError('代码/环境已变化，不能写入旧身份')
    check_inputs(root)
    if (root/'frozen.json').exists():verify(root,json.loads((root/'frozen.json').read_text('utf8'))['files']);return
    for market in ('ashare','btc'):
        for h in (1,5):
            history=json.loads((root/market/f'h{h}'/'history.json').read_text('utf8'))
            for spec in protocol['folds']:
                folder=root/market/f'h{h}'/spec['fold']
                if (folder/'completed.json').exists():
                    check_fold(root,folder);continue
                reject_partial(folder)
                m=json.loads((folder/'preparation.json').read_text('utf8'))
                tr,va,ev=[read_checked(folder,m,key+'.json') for key in ('train','validation','evaluation_features')]
                result=fit_models(tr['x'],tr['y'],va['x'],va['y'],ev['x'],horizon=h,annualization=252 if market=='ashare' else 365,
                    history_returns=history,train_indices=[r['history_index'] for r in tr['rows']],val_indices=[r['history_index'] for r in va['rows']],eval_indices=[r['history_index'] for r in ev['rows']],folder=folder/'models')
                write_json(folder/'predictions.json',result['predictions'])
                write_json(folder/'training.json',{'models':result['models'],'artifacts':{'models/'+n:s for n,s in result['artifacts'].items()},'preparation_sha256':file_sha(folder/'preparation.json'),'evaluation_labels_read':False})
                seal_fold(root,folder)
                print(json.dumps({'trained':market,'horizon':h,'fold':spec['fold']},ensure_ascii=False),flush=True)
    check_inputs(root)
    for market in ('ashare','btc'):
        for h in (1,5):
            for spec in protocol['folds']:check_fold(root,root/market/f'h{h}'/spec['fold'])
    files={p.relative_to(root).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file()}
    write_json(root/'frozen.json',{'created_at':datetime.now(timezone.utc).isoformat(),'files':files,'protocol_sha256':digest(protocol),'evaluation_labels_read_for_fitting':False})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','train','score','all']);p.add_argument('--root',type=Path);p.add_argument('--attempt',default='default');a=p.parse_args();root=a.root.resolve() if a.root else prepare(a.attempt)
    if not root.is_relative_to((PROJECT/'research/artifacts/volatility').resolve()):raise ValueError('目录越界')
    print('ROOT '+str(root),flush=True)
    if a.stage in ('all','train'):train(root)
    if a.stage in ('all','score'):subprocess.run([sys.executable,'-X','utf8','-m','research.volatility.score','--root',str(root)],cwd=PROJECT,check=True)
