"""Causal forecasting rows. No numpy, model framework or fitted statistics here."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext


def make_samples(dataset,lookback=60):
    if isinstance(lookback,bool) or not isinstance(lookback,int) or not 2<=lookback<=120:raise ValueError('lookback须为2–120的整数')
    from platform_app.experiments.backtest import open_at
    bars=dataset.snapshot.bars;lag=1 if dataset.snapshot.market=='ashare' else 2
    dividends={d.session:Decimal(d.amount) for d in dataset.dividends};returns=[None];rows=[]
    with localcontext() as ctx:
        ctx.prec=28
        for i in range(1,len(bars)):
            if bars[i].close is None or bars[i-1].close is None:raise ValueError('不能前填未知行情来构造训练样本')
            returns.append((Decimal(bars[i].close)+dividends.get(bars[i].session,Decimal(0)))/Decimal(bars[i-1].close)-1)
        for i in range(lookback,len(bars)-lag-1):
            entry=i+lag;exit=entry+1;decision=bars[i].close_at+timedelta(minutes=1)
            if any(b.available_at>decision for b in bars[i-lookback:i+1]):continue
            entered=open_at(dataset.snapshot,bars[entry].session);exited=open_at(dataset.snapshot,bars[exit].session)
            if not decision<entered<exited:raise ValueError('预测决策必须早于可交易开盘')
            target=(Decimal(bars[exit].open)+dividends.get(bars[exit].session,Decimal(0)))/Decimal(bars[entry].open)-1
            rows.append({'signal_session':str(bars[i].session),'decision_at':decision.isoformat(),
                'entry_session':str(bars[entry].session),'entry_at':entered.isoformat(),'exit_session':str(bars[exit].session),'exit_at':exited.isoformat(),
                'label_available_at':bars[exit].available_at.isoformat(),'x':[str(v) for v in returns[i-lookback+1:i+1]],'target':str(target)})
    return rows


def split_samples(rows):
    bounds={'train':('2018-01-01','2021-12-31'),'validation':('2022-01-01','2023-12-31'),'evaluation':('2024-01-01','2025-12-31')}
    splits={key:[] for key in bounds};purged={key:0 for key in bounds}
    for row in rows:
        for key,(start,end) in bounds.items():
            if start<=row['signal_session']<=end:
                cutoff=datetime(int(end[:4])+1,1,1,0,1,tzinfo=timezone.utc)
                mature='label_available_at' not in row or datetime.fromisoformat(row['label_available_at'])<=cutoff
                if not start<=row['entry_session']<=row['exit_session']<=end or not mature:purged[key]+=1
                else:splits[key].append(row)
                break
    return splits,purged
