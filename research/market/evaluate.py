"""Scoring is deliberately separate from training and label-free prediction."""
import numpy as np


def metrics(y,prediction):
    y=np.asarray(y,dtype=np.float64);p=np.asarray(prediction,dtype=np.float64)
    if y.ndim!=1 or y.shape!=p.shape or not len(y) or not np.isfinite(y).all() or not np.isfinite(p).all():raise ValueError('评分需要对齐、非空、有限的预测和标签')
    error=p-y;mse=float(np.mean(error**2));base=float(np.mean(y**2));nonzero=y!=0
    correlation=float(np.corrcoef(y,p)[0,1]) if len(y)>1 and np.std(y)>1e-15 and np.std(p)>1e-15 else None
    return {'rows':len(y),'mae':float(np.mean(np.abs(error))),'rmse':float(np.sqrt(mse)),'bias':float(np.mean(error)),
        'mse_skill_vs_zero':1-mse/base if base else None,'direction_accuracy':float(np.mean(np.sign(p[nonzero])==np.sign(y[nonzero]))) if nonzero.any() else None,
        'zero_actual_rows':int((~nonzero).sum()),'neutral_prediction_rows':int((p==0).sum()),'temporal_correlation':correlation}


def paired_block_interval(y,prediction,block_length=20,resamples=2000,seed=20261030):
    y=np.asarray(y,dtype=np.float64);p=np.asarray(prediction,dtype=np.float64);metrics(y,p)
    delta=(p-y)**2-y**2;n=len(y);block=min(block_length,n)
    if block<1 or resamples<1:raise ValueError('bootstrap预算必须为正')
    rng=np.random.default_rng(seed);means=[]
    for _ in range(resamples):
        starts=rng.integers(0,n-block+1,size=(n+block-1)//block)
        indices=(starts[:,None]+np.arange(block)).ravel()[:n];means.append(float(np.mean(delta[indices])))
    low,high=np.quantile(means,[.025,.975])
    return {'quantity':'model MSE minus zero-return MSE','estimate':float(np.mean(delta)),'low':float(low),'high':float(high),
        'block_length':block,'resamples':resamples,'seed':seed,'assumption':'moving-block paired bootstrap; exploratory, no iid or causal claim'}
