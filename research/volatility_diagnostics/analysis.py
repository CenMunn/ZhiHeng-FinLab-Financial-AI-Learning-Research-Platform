"""Descriptive diagnostics; calibration accepts validation observations only."""
import numpy as np
from research.volatility.metrics import PREDICTION_FLOOR,qlike
from research.volatility.data import REGIMES,regime_key

def checked(y,p):
    y=np.asarray(y,dtype=float);p=np.asarray(p,dtype=float)
    if y.ndim!=1 or y.shape!=p.shape or not len(y) or not np.isfinite(y).all() or not np.isfinite(p).all() or (y<0).any() or (p<0).any():raise ValueError('诊断必须使用对齐且非负有限样本')
    return y,np.maximum(p,PREDICTION_FLOOR)

def fit_scale(validation_y,validation_p):
    y,p=checked(validation_y,validation_p);raw=float(np.mean(y/p));c=float(np.clip(raw,.25,4.))
    return {'raw_c':raw,'c':c,'clipped':raw!=c,'validation_rows':len(y)}

def reliability_bins(validation_p,evaluation_p,evaluation_y):
    y,p=checked(evaluation_y,evaluation_p);vp=np.asarray(validation_p,dtype=float)
    if vp.ndim!=1 or not len(vp) or not np.isfinite(vp).all() or (vp<0).any():raise ValueError('非法验证预测分箱输入')
    edges=np.unique(np.quantile(np.maximum(vp,PREDICTION_FLOOR),[.2,.4,.6,.8]));assigned=np.searchsorted(edges,p,side='left');result=[]
    for i in range(len(edges)+1):
        mask=assigned==i;n=int(mask.sum());pred=float(p[mask].mean()) if n else None;actual=float(y[mask].mean()) if n else None
        result.append({'lower':float(edges[i-1]) if i else None,'upper':float(edges[i]) if i<len(edges) else None,'rows':n,'prediction_mean':pred,'realized_mean':actual,'ratio':pred/actual if n and actual>0 else None})
    return result

def failure_windows(rows,model,c,fold):
    result=[]
    for start in range(0,len(rows),20):
        window=rows[start:start+20];y=np.array([r['realized_variance'] for r in window]);p=np.array([r['predictions'][model] for r in window]);base=np.array([r['predictions']['ewma'] for r in window]);cal=np.maximum(p*c,PREDICTION_FLOOR)
        raw=float(qlike(y,p).mean());calibrated=float(qlike(y,cal).mean());ewma=float(qlike(y,base).mean())
        result.append({'fold':fold,'start':window[0]['session'],'end':window[-1]['session'],'rows':len(window),'raw_qlike':raw,'calibrated_qlike':calibrated,'ewma_qlike':ewma,'raw_delta':raw-ewma,'calibrated_delta':calibrated-ewma,'underforecast_count':int((y>4*p).sum()),'max_realized_variance':float(y.max())})
    return result

def coverage_rows(parts,thresholds):
    groups={k:[regime_key(x,thresholds) for x in part['x']] for k,part in parts.items()};answer=[]
    for key,name in REGIMES.items():
        counts={split:groups[split].count(key) for split in parts};last=None;nonoverlap=0
        for row,group in zip(parts['evaluation']['rows'],groups['evaluation']):
            if group==key and (last is None or row['label_start']>last):nonoverlap+=1;last=row['label_end']
        train_share=counts['train']/len(groups['train']);evaluation_share=counts['evaluation']/len(groups['evaluation'])
        answer.append({'regime':key,'name':name,'train_rows':counts['train'],'validation_rows':counts['validation'],'evaluation_rows':counts['evaluation'],'nonoverlap_count':nonoverlap,'missing_to_30':max(0,30-counts['evaluation']),'train_share':train_share,'evaluation_share':evaluation_share,'share_change':evaluation_share-train_share})
    return answer
