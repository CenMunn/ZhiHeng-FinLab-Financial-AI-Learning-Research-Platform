"""Quarterly expanding-window experiments, then feature diagnosis and encoders."""
import argparse,json,subprocess,sys,time
from datetime import datetime,timezone,date
from pathlib import Path
import numpy as np
import lightgbm as lgb
from research.rolling.common import PROJECT,sources,environment,digest,file_sha,write_json,load_split,verify_files
from research.rolling.data import fold_specs,partition,engineered,FEATURES,GROUPS
from research.rolling.diagnostics import psi,block_permute
from research.rolling.acquire import acquire,MODEL
from research.market.common import code_manifest
from research.market.models import standardize,save_lightgbm
from research.market.runner import smoke,train,predict

sys.path.insert(0,str(PROJECT/'backend/src'))
from platform_app.adapters.public_market import IDS,load_dataset
from platform_app.experiments.forecast_data import make_samples
from platform_app.contracts.models import stable_hash


def now():return datetime.now(timezone.utc).isoformat()


def prepare():
    base=json.loads((PROJECT/'research/configs/market-forecast-v1.json').read_text('utf8'));acquisition=acquire()
    datasets=[load_dataset(PROJECT/'backend/data/public-market',key) for key in IDS]
    identity={'schema':'rolling-protocol-v1','base_config':base,'folds':fold_specs(),'groups':GROUPS,'features':FEATURES,'sources':sources(),'environment':environment(),
        'datasets':{d.snapshot.market:stable_hash(d.model_dump(mode='json')) for d in datasets},'encoder_acquisition_sha256':file_sha(MODEL/'acquisition.json'),
        'permutation':{'block':20,'repeats':5,'seed':42},'encoder_cohort':'2025 only','readout_alpha':10,'random_encoder_seed':42,
        'cost_multipliers':[0,1,2],'quarter_boundary':'target cash at last eligible exit; cash in purged gaps; continuous capital'}
    root=PROJECT/'research/artifacts/rolling'/('v1-'+digest(identity)[:24]);write_json(root/'identity.json',identity)
    for data in datasets:
        market=data.snapshot.market;rows=make_samples(data,base['lookback']);extras={row['signal_session']:engineered(data.snapshot.bars,data.dividends,data.snapshot.sessions.index(date.fromisoformat(row['signal_session']))) for row in rows}
        write_json(root/market/'dataset.json',data.model_dump(mode='json'))
        write_json(root/market/'contexts.json',{'sessions':[r['signal_session'] for r in rows],'x':[[float(v) for v in r['x']] for r in rows]})
        for spec in identity['folds']:
            folder=root/market/spec['fold'];splits,purged=partition(rows,spec);files={}
            if any(len(splits[key])<20 for key in splits):raise ValueError('滚动区间样本不足')
            for key,items in splits.items():
                features={'rows':[{k:v for k,v in r.items() if k not in ('x','target')} for r in items],'x':[[float(v) for v in r['x']] for r in items]}
                if key=='evaluation':
                    name='evaluation_features.json';write_json(folder/name,features);files[name]=file_sha(folder/name)
                    name='evaluation_labels.json';write_json(folder/name,{'rows':features['rows'],'y':[float(r['target']) for r in items]});files[name]=file_sha(folder/name)
                else:
                    features['y']=[float(r['target']) for r in items];name=key+'.json';write_json(folder/name,features);files[name]=file_sha(folder/name)
                name=key+'-extras.json';write_json(folder/name,{'features':FEATURES,'rows':features['rows'],'x':[extras[r['signal_session']] for r in items]});files[name]=file_sha(folder/name)
            manifest={'schema':'rolling-preparation-v1','market':market,'fold':spec['fold'],'bounds':spec,'config':base,'code_sources':code_manifest(),'rolling_sources':identity['sources'],
                'files':files,'purged':purged,'counts':{key:len(items) for key,items in splits.items()},'dataset_sha256':identity['datasets'][market],'identity_sha256':digest(identity)}
            write_json(folder/'preparation.json',manifest)
        print(json.dumps({'market':market,'folds':8,'root':str(root)},ensure_ascii=False),flush=True)
    return root


def checked(root):
    identity=json.loads((root/'identity.json').read_text('utf8'))
    if identity['sources']!=sources():raise ValueError('滚动代码已改变，需准备新身份，不覆盖旧结果')
    if identity['environment']!=environment():raise ValueError('运行环境版本改变，不能归入旧身份')
    return identity


def augmentation(folder):
    marker=folder/'diagnostics.json'
    if marker.exists():return json.loads(marker.read_text('utf8'))
    m=json.loads((folder/'preparation.json').read_text('utf8'));receipt=json.loads((folder/'training.json').read_text('utf8'));scaler=receipt['scaler']
    raw={key:load_split(folder,m,key) for key in ('train','validation','evaluation_features')};extras={}
    for key in raw:
        phase='evaluation' if key=='evaluation_features' else key
        extra=json.loads((folder/(phase+'-extras.json')).read_text('utf8'))
        if file_sha(folder/(phase+'-extras.json'))!=m['files'][phase+'-extras.json'] or extra['rows']!=raw[key]['rows']:raise ValueError('增强特征未与日期对齐')
        extras[key]=np.asarray(extra['x'])
    mean=extras['train'].mean(axis=0);std=extras['train'].std(axis=0);std[std<1e-12]=1
    matrix={key:np.c_[standardize(data['x'],scaler),(extras[key]-mean)/std] for key,data in raw.items()}
    y=(np.asarray(raw['train']['y'])-scaler['y_mean'])/scaler['y_std'];vy=(np.asarray(raw['validation']['y'])-scaler['y_mean'])/scaler['y_std']
    predictions={};models={};artifacts={};full=None
    for variant in ['enhanced',*['without_'+g for g in GROUPS]]:
        removed=[] if variant=='enhanced' else [60+i for i in GROUPS[variant.removeprefix('without_')]]
        columns=[i for i in range(68) if i not in removed];cfg=dict(m['config']['lightgbm']);rounds=cfg.pop('num_boost_round');wait=cfg.pop('early_stopping_rounds')
        booster=lgb.train(cfg,lgb.Dataset(matrix['train'][:,columns],label=y),num_boost_round=rounds,
            valid_sets=[lgb.Dataset(matrix['validation'][:,columns],label=vy)],callbacks=[lgb.early_stopping(wait,verbose=False)])
        name=variant+'.txt';save_lightgbm(booster,folder/name);artifacts[name]=file_sha(folder/name)
        predictions[variant]={key:(booster.predict(matrix[key][:,columns],num_threads=2)*scaler['y_std']+scaler['y_mean']).tolist() for key in ('validation','evaluation_features')}
        models[variant]={'best_iteration':booster.best_iteration,'columns':columns}
        if variant=='enhanced':full=booster
    baseline=np.asarray(predictions['enhanced']['validation']);actual=np.asarray(raw['validation']['y']);base_mse=float(np.mean((baseline-actual)**2));importance={}
    for group,columns in {'lag_returns':list(range(60)),**{key:[60+i for i in cols] for key,cols in GROUPS.items()}}.items():
        values=[]
        for repeat in range(5):
            permuted=block_permute(matrix['validation'],columns,42+repeat,20);p=full.predict(permuted,num_threads=2)*scaler['y_std']+scaler['y_mean']
            values.append(float(np.mean((p-actual)**2))-base_mse)
        importance[group]={'validation_delta_mse_mean':float(np.mean(values)),'repeat_std':float(np.std(values,ddof=1)),'repeats':5,'block':20}
    drift={name:{key:psi(extras['train'][:,i],extras[key][:,i]) for key in ('validation','evaluation_features')} for i,name in enumerate(FEATURES)}
    body={'schema':'feature-diagnostics-v1','preparation_sha256':file_sha(folder/'preparation.json'),'training_sha256':file_sha(folder/'training.json'),
        'predictions':predictions,'models':models,'artifacts':artifacts,'validation_permutation':importance,'label_free_drift':drift,
        'extra_scaler':{'mean':mean.tolist(),'std':std.tolist()},'group_selection':'all predefined groups reported; no evaluation-label feature selection'}
    write_json(marker,body);return body


def base_phase(root):
    identity=checked(root)
    if (root/'base-phase.json').exists():verify_files(root,json.loads((root/'base-phase.json').read_text('utf8'))['files']);return
    started=now();files={}
    for market in ('ashare','btc'):
        for spec in identity['folds']:
            folder=root/market/spec['fold']
            if not (folder/'smoke.json').exists():smoke(folder)
            train(folder);predict(folder);augmentation(folder)
            m=json.loads((folder/'preparation.json').read_text('utf8'));t=json.loads((folder/'training.json').read_text('utf8'));d=json.loads((folder/'diagnostics.json').read_text('utf8'))
            for name in set(m['files'])|set(t['artifacts'])|set(d['artifacts'])|{'preparation.json','training.json','predictions.json','diagnostics.json'}:files[(folder/name).relative_to(root).as_posix()]=file_sha(folder/name)
            print(json.dumps({'base_complete':market,'fold':spec['fold']},ensure_ascii=False),flush=True)
        for name in ('contexts.json','dataset.json'):files[f'{market}/{name}']=file_sha(root/market/name)
    write_json(root/'base-phase.json',{'started_at':started,'finished_at':now(),'identity_sha256':digest(identity),'files':files,'stage':'rolling baselines and feature diagnostics before pretrained readout'})


def pretrained_phase(root):
    from research.rolling.pretrained import cache,readout
    identity=checked(root)
    if not (root/'base-phase.json').exists():raise ValueError('须先完成全部滚动验证和特征诊断')
    verify_files(root,json.loads((root/'base-phase.json').read_text('utf8'))['files'])
    if (root/'pretrained-phase.json').exists():verify_files(root,json.loads((root/'pretrained-phase.json').read_text('utf8'))['files']);return
    started=now();files={}
    for market in ('ashare','btc'):
        context=json.loads((root/market/'contexts.json').read_text('utf8'));position={day:i for i,day in enumerate(context['sessions'])}
        features=cache(root/market/'embeddings',context['x'])
        for name in ('chronos.npz','chronos.json','random_encoder.npz','random_encoder.json','random-encoder.safetensors'):
            file=root/market/'embeddings'/name;files[file.relative_to(root).as_posix()]=file_sha(file)
        for spec in identity['folds']:
            if not spec['fold'].startswith('2025'):continue
            folder=root/market/spec['fold'];m=json.loads((folder/'preparation.json').read_text('utf8'))
            train_data=load_split(folder,m,'train');evaluation=load_split(folder,m,'evaluation_features');validation=load_split(folder,m,'validation')
            result={};heads={}
            for kind,embedding in features.items():
                tx=embedding[[position[r['signal_session']] for r in train_data['rows']]]
                result[kind]={};heads[kind]=None
                for key,data in [('validation',validation),('evaluation_features',evaluation)]:
                    px=embedding[[position[r['signal_session']] for r in data['rows']]];p,head=readout(tx,train_data['y'],px,10)
                    result[kind][key]=p.tolist();heads[kind]=head
            write_json(folder/'pretrained-heads.json',heads)
            write_json(folder/'pretrained-predictions.json',{'preparation_sha256':file_sha(folder/'preparation.json'),'heads_sha256':file_sha(folder/'pretrained-heads.json'),
                'acquisition_sha256':file_sha(MODEL/'acquisition.json'),'predictions':result,'evaluation_labels_read':False,'base_parameters_frozen':True})
            for name in ('pretrained-heads.json','pretrained-predictions.json'):files[(folder/name).relative_to(root).as_posix()]=file_sha(folder/name)
            print(json.dumps({'pretrained_complete':market,'fold':spec['fold']},ensure_ascii=False),flush=True)
    model_files={name:file_sha(MODEL/name) for name in ('README.md','config.json','generation_config.json','model.safetensors','acquisition.json')}
    write_json(root/'pretrained-phase.json',{'started_at':started,'finished_at':now(),'base_phase_sha256':file_sha(root/'base-phase.json'),'encoder_acquisition_sha256':file_sha(MODEL/'acquisition.json'),'model_files':model_files,'files':files})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','base','pretrained','score','all']);parser.add_argument('--root',type=Path);args=parser.parse_args()
    root=args.root.resolve() if args.root else prepare()
    if not root.is_relative_to((PROJECT/'research/artifacts/rolling').resolve()):raise ValueError('非法滚动产物目录')
    try:
        if args.stage in ('base','all'):base_phase(root)
        if args.stage in ('pretrained','all'):pretrained_phase(root)
        if args.stage in ('score','all'):subprocess.run([sys.executable,'-X','utf8','-m','research.rolling.score','--root',str(root)],cwd=PROJECT,check=True)
    except Exception as exc:
        write_json(root/('failure-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json'),{'recorded_at':now(),'stage':args.stage,'error':type(exc).__name__,'message':str(exc)});raise
    print(json.dumps({'stage':args.stage,'root':str(root)},ensure_ascii=False))


if __name__=='__main__':main()
