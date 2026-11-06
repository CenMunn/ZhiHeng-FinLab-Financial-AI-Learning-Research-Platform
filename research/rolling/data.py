from datetime import date,datetime,timedelta,timezone
import numpy as np

FEATURES=['mean5','mean20','std5','std20','range','intraday','gap','drawdown60']
GROUPS={'momentum':[0,1],'volatility':[2,3],'bar_shape':[4,5,6],'drawdown':[7]}


def fold_specs():
    folds=[]
    for year in (2024,2025):
        for quarter,month in enumerate((1,4,7,10),1):
            start=date(year,month,1);end=(date(year+1,1,1) if month==10 else date(year,month+3,1))-timedelta(days=1)
            val=date(year-1,month,1)
            folds.append({'fold':f'{year}Q{quarter}','train':['2018-01-01',str(val-timedelta(days=1))],
                'validation':[str(val),str(start-timedelta(days=1))],'evaluation':[str(start),str(end)]})
    return folds


def partition(rows,spec):
    result={key:[] for key in ('train','validation','evaluation')};purged={key:0 for key in result}
    for row in rows:
        for key in result:
            start,end=spec[key]
            if start<=row['signal_session']<=end:
                cutoff=datetime.combine(date.fromisoformat(end)+timedelta(days=1),datetime.min.time(),timezone.utc)+timedelta(minutes=1)
                if start<=row['entry_session']<=row['exit_session']<=end and datetime.fromisoformat(row['label_available_at'])<=cutoff:result[key].append(row)
                else:purged[key]+=1
                break
    return result,purged


def engineered(bars,dividends,index,lookback=60):
    if index<lookback:raise ValueError('特征预热不足')
    div={d.session:float(d.amount) for d in dividends};bar=bars[index]
    r=np.array([(float(bars[j].close)+div.get(bars[j].session,0))/float(bars[j-1].close)-1 for j in range(index-lookback+1,index+1)])
    path=np.r_[1.,np.cumprod(1+r)]
    answer=[r[-5:].mean(),r[-20:].mean(),r[-5:].std(ddof=1),r[-20:].std(ddof=1),
        (float(bar.high)-float(bar.low))/float(bar.close),float(bar.close)/float(bar.open)-1,
        (float(bar.open)+div.get(bar.session,0))/float(bars[index-1].close)-1,path[-1]/path.max()-1]
    if not np.isfinite(answer).all():raise ValueError('诊断特征包含未知或非有限值')
    return [float(v) for v in answer]
