"""D26 causal open-to-open log total returns and executable single-day targets."""
import math
from datetime import date,datetime,time,timedelta,timezone


def open_at(bar,market):
    day=date.fromisoformat(bar['session'])
    return datetime.combine(day,time(1,30) if market=='ashare' else time(),timezone.utc)


def make_rows(dataset):
    bars=dataset['bars'];market=dataset['market']
    if market not in ('ashare','crypto'):raise ValueError('Unknown market')
    dividends={d['session']:float(d['amount']) for d in dataset.get('dividends',[])}
    history=[0.]+[math.log((float(bars[j]['open'])+dividends.get(bars[j]['session'],0.))/float(bars[j-1]['open'])) for j in range(1,len(bars))]
    if not all(math.isfinite(v) for v in history):raise ValueError('Nonfinite history')
    prefix=[];latest=datetime.fromisoformat(bars[0]['available_at'])
    for bar in bars:
        available=datetime.fromisoformat(bar['available_at'])
        if available.tzinfo is None:raise ValueError('Naive availability')
        latest=max(latest,available);prefix.append(latest)
    lead=2 if market=='ashare' else 3;rows=[]
    for i in range(60,len(bars)-lead):
        decision=datetime.fromisoformat(bars[i]['close_at'])+timedelta(minutes=1)
        if prefix[i]>decision:continue
        entry,exit=bars[i+lead-1],bars[i+lead]
        entry_at,exit_at=open_at(entry,market),open_at(exit,market)
        if not decision<entry_at<exit_at:raise ValueError('Nonexecutable interval')
        rows.append(dict(signal_session=bars[i]['session'],decision_at=decision.isoformat(),
                         entry_session=entry['session'],entry_at=entry_at.isoformat(),
                         exit_session=exit['session'],exit_at=exit_at.isoformat(),
                         label_available_at=prefix[i+lead].isoformat(),feature_available_at=prefix[i].isoformat(),
                         history_index=i,lead=lead,holding_intervals=1,
                         x=history[i-59:i+1],target=history[i+lead]**2))
    return rows,history


def partition(rows,bounds):
    parts={k:[] for k in bounds};purged={k:0 for k in bounds}
    for row in rows:
        for role,(start,end) in bounds.items():
            if start<=row['signal_session']<=end:
                cutoff=datetime.combine(date.fromisoformat(end)+timedelta(days=1),time(),timezone.utc)+timedelta(minutes=1)
                if (start<=row['entry_session']<row['exit_session']<=end
                    and datetime.fromisoformat(row['label_available_at'])<=cutoff):parts[role].append(row)
                else:purged[role]+=1
                break
    return parts,purged
