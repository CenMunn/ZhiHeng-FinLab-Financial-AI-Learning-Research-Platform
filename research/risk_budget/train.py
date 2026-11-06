"""D26 executable-interval fitting accepts train/early labels only; calibration is a subsequent operation."""
from pathlib import Path
import numpy as np
from research.market.common import file_sha, write_json
from research.volatility import models as old

MODEL_NAMES={k:old.MODEL_NAMES[k] for k in ('train_mean','ewma','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear')}

def validate_features(x, indices, history):
    x=old._features(x); indices=np.asarray(indices, dtype=int);history=np.asarray(history)
    if len(x)!=len(indices) or not len(indices) or indices.min()<60 or indices.max()>=len(history) or (np.diff(indices)<=0).any():
        raise ValueError('Causal signal indices invalid')
    if not np.allclose(x,np.stack([history[i-59:i+1] for i in indices]),rtol=1e-10,atol=1e-12):
        raise ValueError('Features mismatch causal history')

def calibrate(calibration_raw, calibration_y, evaluation_raw):
    p=old._vector(calibration_raw,'calibration predictions',True)
    y=old._vector(calibration_y,'independent calibration labels',True)
    e=old._vector(evaluation_raw,'evaluation predictions',True)
    if (p<=0).any() or (e<=0).any():raise ValueError('Predictions must be strictly positive')
    if len(y)!=len(p):raise ValueError('Calibration lengths mismatch')
    raw_c=float(np.mean(y/np.maximum(p,old.PREDICTION_FLOOR)));c=float(np.clip(raw_c,.25,4.))
    return dict(raw=e.tolist(),calibration_raw=p.tolist(),calibrated=np.maximum(e*c,old.PREDICTION_FLOOR).tolist(),c=c,raw_c=raw_c,
                clipped=c!=raw_c,calibration_rows=len(y))

def fit_models(train, early, calibration_features, evaluation_features, *, history_returns, indices, lead, folder):
    """No calibration or evaluation target argument; complete fitting before inference."""
    if lead not in (2,3):raise ValueError('D26 lead must be 2/3; holding interval is always one day')
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    parts=[train,early,calibration_features,evaluation_features]
    if 'y' in calibration_features or 'y' in evaluation_features:raise ValueError('Inference features must exclude labels')
    xs=[old._features(p['x']) for p in parts]
    for x,i in zip(xs,indices):validate_features(x,i,history_returns)
    for left,right in zip(indices,indices[1:]):
        if max(left)+lead>=min(right):raise ValueError('Label horizons overlap next role')
    tx,vx,cx,ex=xs;ty=old._vector(train['y'],'train targets',True);vy=old._vector(early['y'],'early targets',True)
    if len(ty)!=len(tx) or len(vy)!=len(vx):raise ValueError('Own role labels mismatch')
    receipts={}; predictors={}
    def save(key,receipt):
        receipts[key]={'name':MODEL_NAMES[key], 'fit_rows':len(ty), 'early_stopping_rows':len(vy),
                       'calibration_labels_used_for_fit':False,'evaluation_labels_used':False,**receipt}
        write_json(folder/(key+'.json'),receipts[key])
    mean=max(float(ty.mean()),old.PREDICTION_FLOOR)
    predictors['train_mean']=lambda x,i:np.full(len(x),mean)
    save('train_mean',dict(mean=mean))
    predictors['ewma']=lambda x,i:old.ewma_forecast(history_returns,i)
    save('ewma',dict(decay=.94,learned_parameters=0,initialization='first matured open total return square',forecast='constant conditional future one-day variance at any lead',lead=lead,holding_intervals=1))
    booster,info=old.fit_lightgbm(tx,ty,vx,vy,folder/'lightgbm.txt',rounds=200,patience=20)
    predictors['lightgbm']=lambda x,i:booster.predict(x**2/info['target_scale'])*info['target_scale']
    save('lightgbm',info)
    for seed in old.SEEDS:
        key=f'dlinear_seed_{seed}';path=folder/(key+'.pt')
        model,receipt=old.fit_dlinear(tx,ty,vx,vy,path,seed=seed,epochs=30,patience=6,device='cuda')
        live=old.predict_dlinear(model,vx,receipt);reloaded=old.predict_dlinear(path,vx)
        if not np.allclose(live,reloaded,rtol=1e-5,atol=1e-10):raise RuntimeError('Checkpoint reload prediction mismatch')
        receipt={**receipt,'checkpoint_reload_verified':True,'reload_max_abs_error':float(np.max(np.abs(live-reloaded)))}
        predictors[key]=lambda x,i,m=model,r=receipt:old.predict_dlinear(m,x,r)
        save(key,receipt)
    predictions={}
    for key,predict in predictors.items():
        c=np.asarray(predict(cx,indices[2]),dtype=float);e=np.asarray(predict(ex,indices[3]),dtype=float)
        if not np.isfinite(c).all() or not np.isfinite(e).all() or (c<=0).any() or (e<=0).any():raise RuntimeError('Invalid predictions '+key)
        predictions[key]={'calibration_raw':np.maximum(c,old.PREDICTION_FLOOR).tolist(),'raw':np.maximum(e,old.PREDICTION_FLOOR).tolist()}
    predictions['dlinear']={part:np.mean([predictions[f'dlinear_seed_{s}'][part] for s in old.SEEDS],axis=0).tolist() for part in ('calibration_raw','raw')}
    save('dlinear',dict(seeds=list(old.SEEDS),aggregation='arithmetic mean of all fixed seeds'))
    return dict(models=receipts,predictions=predictions,artifacts={p.name:file_sha(p) for p in folder.iterdir() if p.is_file()})
