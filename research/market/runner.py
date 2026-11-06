"""Offline stages; prediction stage never loads evaluation_labels.json."""
import os
os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG',':4096:8')
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import random
import sys
import time
import numpy as np
import torch
import lightgbm as lgb
from safetensors.torch import save_file,load_file
from research.market.common import PROJECT,code_manifest,digest,file_sha,write_json,load_split,read_checked
from research.market.models import DLinear,fit_scaler,standardize,ridge_fit,ridge_predict,save_lightgbm,load_lightgbm

sys.path.insert(0,str(PROJECT/'backend/src'))


def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False


def manifest(root):
    body=json.loads((root/'preparation.json').read_text('utf8'))
    if body['code_sources']!=code_manifest():raise ValueError('准备后代码已变化，请生成新版本而不是覆盖实验')
    return body


def arrays(data,scaler):
    return torch.tensor(standardize(data['x'],scaler),dtype=torch.float32,device='cuda'),torch.tensor((np.asarray(data['y'])-scaler['y_mean'])/scaler['y_std'],dtype=torch.float32,device='cuda')


def smoke(root):
    m=manifest(root);train=load_split(root,m,'train');scaler=fit_scaler(train['x'],train['y'])
    if not torch.cuda.is_available():raise RuntimeError('配置要求NVIDIA CUDA；本次不伪造GPU验证或静默改CPU')
    seed_all(42);model=DLinear(m['config']['lookback'],m['config']['dlinear']['kernel_size']).cuda()
    x,y=arrays(train,scaler);x=x[:32];y=y[:32]
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001)
    before=[p.detach().clone() for p in model.parameters()];loss=(model(x)-y).square().mean();loss.backward()
    norm=float(torch.nn.utils.clip_grad_norm_(model.parameters(),1.));optimizer.step();after=float((model(x)-y).square().mean().detach())
    delta=sum(float((p.detach()-old).abs().sum()) for p,old in zip(model.parameters(),before))
    if not np.isfinite([float(loss.detach()),after,norm,delta]).all() or norm<=0 or delta<=0:raise ValueError('前后向/参数更新验证失败')
    receipt={'device':torch.cuda.get_device_name(0),'dtype':'float32','rows':len(x),'parameters':sum(p.numel() for p in model.parameters()),
        'loss_before':float(loss.detach()),'loss_after':after,'gradient_norm':norm,'parameter_delta_l1':delta,'cuda':torch.version.cuda,'torch':torch.__version__}
    write_json(root/'smoke.json',receipt);print(json.dumps({'market':m['market'],'smoke':receipt},ensure_ascii=False),flush=True)
    del model,x,y;torch.cuda.empty_cache()
    return receipt


def train(root):
    m=manifest(root);training=root/'training.json'
    if training.exists():
        old=json.loads(training.read_text('utf8'))
        if old['preparation_sha256']!=file_sha(root/'preparation.json'):raise ValueError('训练准备指纹变化')
        for name,sha in old['artifacts'].items():
            if file_sha(root/name)!=sha:raise ValueError('既有模型产物校验失败')
        return old
    train=load_split(root,m,'train');val=load_split(root,m,'validation');cfg=m['config'];scaler=fit_scaler(train['x'],train['y'])
    write_json(root/'scaler.json',scaler);artifacts={};models={};start=time.perf_counter()
    x=standardize(train['x'],scaler);vx=standardize(val['x'],scaler)
    y=(np.asarray(train['y'])-scaler['y_mean'])/scaler['y_std'];vy=(np.asarray(val['y'])-scaler['y_mean'])/scaler['y_std']
    baseline={'train_mean':scaler['y_mean'],'ridge':ridge_fit(x,y,cfg['ridge_alpha'])}
    write_json(root/'baselines.json',baseline);artifacts['baselines.json']=file_sha(root/'baselines.json')
    models['baselines']={'elapsed_seconds':time.perf_counter()-start,'fitted_rows':len(y),'methods':['zero','train_mean','last_return','ridge']}
    lcfg=dict(cfg['lightgbm']);rounds=lcfg.pop('num_boost_round');patience=lcfg.pop('early_stopping_rounds');history={};start=time.perf_counter()
    booster=lgb.train(lcfg,lgb.Dataset(x,label=y),num_boost_round=rounds,valid_sets=[lgb.Dataset(vx,label=vy)],valid_names=['validation'],
        callbacks=[lgb.early_stopping(patience,verbose=False),lgb.record_evaluation(history)])
    if (root/'lightgbm.txt').exists():raise ValueError('拒绝覆盖已有LightGBM模型')
    save_lightgbm(booster,root/'lightgbm.txt');artifacts['lightgbm.txt']=file_sha(root/'lightgbm.txt')
    models['lightgbm']={'best_iteration':booster.best_iteration,'elapsed_seconds':time.perf_counter()-start,'validation_l2_history':history['validation']['l2'],
        'importance_gain':booster.feature_importance(importance_type='gain').tolist(),'device':'CPU','threads':2}
    if not (root/'smoke.json').exists():raise ValueError('先完成GPU小批前后向验证')
    for seed in cfg['dlinear']['seeds']:
        seed_all(seed);dcfg=cfg['dlinear'];model=DLinear(cfg['lookback'],dcfg['kernel_size']).cuda()
        tx,ty=arrays(train,scaler);tvx,tvy=arrays(val,scaler);optimizer=torch.optim.AdamW(model.parameters(),lr=dcfg['learning_rate'],weight_decay=dcfg['weight_decay'])
        best=float('inf');best_state=None;best_epoch=0;wait=0;logs=[];updates=0;start=time.perf_counter()
        for epoch in range(1,dcfg['epochs']+1):
            model.train();order=torch.randperm(len(tx),device='cuda');loss_sum=0.
            for offset in range(0,len(tx),dcfg['batch_size']):
                batch=order[offset:offset+dcfg['batch_size']];optimizer.zero_grad(set_to_none=True)
                loss=(model(tx[batch])-ty[batch]).square().mean()
                if not torch.isfinite(loss):raise ValueError('DLinear训练损失非有限')
                loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),dcfg['gradient_clip']);optimizer.step();updates+=1
                loss_sum+=float(loss.detach())*len(batch)
            model.eval()
            with torch.no_grad():validation=float((model(tvx)-tvy).square().mean())
            if not np.isfinite(validation):raise ValueError('验证损失非有限')
            logs.append({'epoch':epoch,'train_mse_standardized':loss_sum/len(tx),'validation_mse_standardized':validation})
            if validation<best:
                best=validation;best_epoch=epoch;wait=0;best_state={k:v.detach().cpu().clone().contiguous() for k,v in model.state_dict().items()}
            else:wait+=1
            if wait>=dcfg['patience']:break
        torch.cuda.synchronize();name=f'dlinear-{seed}.safetensors'
        if (root/name).exists():raise ValueError('拒绝覆盖已有DLinear权重')
        save_file(best_state,str(root/name));artifacts[name]=file_sha(root/name)
        models[f'dlinear_{seed}']={'seed':seed,'best_epoch':best_epoch,'epochs':epoch,'updates':updates,'history':logs,
            'best_validation_mse_standardized':best,'elapsed_seconds':time.perf_counter()-start,'device':torch.cuda.get_device_name(0),'dtype':'float32',
            'parameter_count':sum(p.numel() for p in model.parameters())}
        print(json.dumps({'market':m['market'],'model':f'dlinear_{seed}','best_epoch':best_epoch,'epochs':epoch,'updates':updates},ensure_ascii=False),flush=True)
        del model,tx,ty,tvx,tvy,optimizer;torch.cuda.empty_cache()
    for name in ('scaler.json','smoke.json'):artifacts[name]=file_sha(root/name)
    receipt={'schema':'market-training-v1','preparation_sha256':file_sha(root/'preparation.json'),'scaler':scaler,'models':models,'artifacts':artifacts,
        'training_inputs':{name:m['files'][name] for name in ('train.json','validation.json')},'evaluation_labels_read':False,
        'finished_at':datetime.now(timezone.utc).isoformat()}
    write_json(training,receipt);return receipt


def predict(root):
    m=manifest(root);receipt=train_receipt(root);scaler=receipt['scaler'];cfg=m['config'];baseline=json.loads((root/'baselines.json').read_text('utf8'))
    booster=load_lightgbm(root/'lightgbm.txt');outputs={}
    for split in ('validation','evaluation_features'):
        data=load_split(root,m,split);x=standardize(data['x'],scaler);n=len(x)
        predictions={'zero':np.zeros(n),'train_mean':np.full(n,baseline['train_mean']),'last_return':np.asarray(data['x'])[:,-1],
            'ridge':ridge_predict(baseline['ridge'],x)*scaler['y_std']+scaler['y_mean'],
            'lightgbm':booster.predict(x,num_threads=2)*scaler['y_std']+scaler['y_mean']}
        for seed in cfg['dlinear']['seeds']:
            model=DLinear(cfg['lookback'],cfg['dlinear']['kernel_size']);model.load_state_dict(load_file(str(root/f'dlinear-{seed}.safetensors')));model.eval()
            with torch.no_grad():p=model(torch.tensor(x,dtype=torch.float32)).numpy().astype(np.float64)*scaler['y_std']+scaler['y_mean']
            predictions[f'dlinear_{seed}']=p
        predictions['dlinear_ensemble']=np.mean([predictions[f'dlinear_{seed}'] for seed in cfg['dlinear']['seeds']],axis=0)
        if any(not np.isfinite(p).all() for p in predictions.values()):raise ValueError('预测包含非有限值')
        outputs[split]={'rows':data['rows'],'predictions':{key:p.tolist() for key,p in predictions.items()}}
    body={'schema':'market-predictions-v1','preparation_sha256':file_sha(root/'preparation.json'),'training_sha256':file_sha(root/'training.json'),
          'feature_files':{name:m['files'][name] for name in ('validation.json','evaluation_features.json')},'evaluation_labels_read':False,'outputs':outputs}
    write_json(root/'predictions.json',body);print(json.dumps({'market':m['market'],'predictions_frozen_sha256':file_sha(root/'predictions.json')},ensure_ascii=False),flush=True)
    return body


def train_receipt(root):
    m=manifest(root);receipt=json.loads((root/'training.json').read_text('utf8'))
    if receipt['preparation_sha256']!=file_sha(root/'preparation.json'):raise ValueError('准备版本已变化')
    for name,sha in receipt['artifacts'].items():
        if file_sha(root/name)!=sha:raise ValueError('模型/缩放产物哈希变化：'+name)
    return receipt


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','smoke','train','predict','score','all']);parser.add_argument('--root',type=Path)
    args=parser.parse_args()
    from research.market.prepare import prepare
    root=args.root or prepare()
    for market in ('ashare','btc'):
        target=root/market
        try:
            if args.stage in ('smoke','all') and not (target/'smoke.json').exists():smoke(target)
            if args.stage in ('train','all'):train(target)
            if args.stage in ('predict','all'):predict(target)
        except Exception as exc:
            write_json(target/('failure-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.json'),
                {'stage':args.stage,'recorded_at':datetime.now(timezone.utc).isoformat(),'error_type':type(exc).__name__,'message':str(exc)})
            raise
    if args.stage in ('score','all'):
        import subprocess
        subprocess.run([sys.executable,'-X','utf8','-m','research.market.publish','--root',str(root)],cwd=PROJECT,check=True)
    print(json.dumps({'stage':args.stage,'root':str(root)},ensure_ascii=False))


if __name__=='__main__':main()
