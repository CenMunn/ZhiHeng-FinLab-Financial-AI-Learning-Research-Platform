"""Daily close-return second moment proxy, independent of trade-return D20/D21."""
from datetime import date,datetime,timedelta,timezone
import numpy as np

REGIMES={f'{v}_{t}':f'{vn}波动 · {tn}' for v,vn in [('low','低'),('mid','中'),('high','高')] for t,tn in [('up','过去60期上涨/持平'),('down','过去60期下跌')]}


def make_rows(dataset,horizon):
    if isinstance(horizon,bool) or horizon not in (1,5):raise ValueError('只登记1/5期日均方目标')
    bars=dataset.snapshot.bars;div={d.session:float(d.amount) for d in dataset.dividends}
    if any(b.close is None or not np.isfinite(float(b.close)) or float(b.close)<=0 for b in bars):raise ValueError('未知/非法价格不能填充为波动样本')
    history=[0.]+[float(np.log((float(bars[i].close)+div.get(bars[i].session,0))/float(bars[i-1].close))) for i in range(1,len(bars))]
    rows=[];prefix_available=[];latest=bars[0].available_at
    for bar in bars:
        latest=max(latest,bar.available_at);prefix_available.append(latest)
    for i in range(60,len(bars)-horizon):
        decision=bars[i].close_at+timedelta(minutes=1)
        if prefix_available[i]>decision:continue
        future=bars[i+1:i+horizon+1]
        if future[0].close_at<=decision:raise ValueError('未来收益窗口须晚于决策')
        rows.append({'signal_session':str(bars[i].session),'decision_at':decision.isoformat(),'label_start':str(future[0].session),
            'label_end':str(future[-1].session),'label_available_at':max(b.available_at for b in future).isoformat(),
            'history_index':i,'x':history[i-59:i+1],'target':float(np.mean(np.square(history[i+1:i+horizon+1])))})
    return rows,history


def partition(rows,spec):
    result={k:[] for k in ('train','validation','evaluation')};purged={k:0 for k in result}
    for row in rows:
        for key in result:
            start,end=spec[key]
            if start<=row['signal_session']<=end:
                cutoff=datetime.combine(date.fromisoformat(end)+timedelta(days=1),datetime.min.time(),timezone.utc)+timedelta(minutes=1)
                if start<=row['label_start']<=row['label_end']<=end and datetime.fromisoformat(row['label_available_at'])<=cutoff:result[key].append(row)
                else:purged[key]+=1
                break
    return result,purged


def regime_thresholds(train_x):
    values=np.asarray(train_x,dtype=float)
    if values.ndim!=2 or values.shape[1]!=60 or not np.isfinite(values).all():raise ValueError('非法训练市况输入')
    return np.quantile(np.mean(values[:,-20:]**2,axis=1),[1/3,2/3]).tolist()


def regime_key(x,thresholds):
    x=np.asarray(x,dtype=float);rv=float(np.mean(x[-20:]**2))
    state='low' if rv<=thresholds[0] else 'mid' if rv<=thresholds[1] else 'high'
    return state+('_up' if float(x.sum())>=0 else '_down')
