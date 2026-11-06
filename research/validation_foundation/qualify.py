"""Historical research qualification, never a declaration of PIT completeness."""
from datetime import datetime,timedelta,date,time,timezone
import numpy as np

def inspect_dataset(data):
    bars=data['bars'];expected=data['expected_sessions'];days=[b['session'] for b in bars];issues=[]
    if not bars or not expected:issues.append('空行情或空日历')
    missing=sorted(set(expected)-set(days));extra=sorted(set(days)-set(expected))
    if days!=sorted(set(days)):issues.append('重复或乱序行情')
    if expected!=sorted(set(expected)):issues.append('期望日历重复或乱序')
    if missing or extra:issues.append(f'日历不一致：缺{len(missing)}、多{len(extra)}；不前填停牌或未知行情')
    if data.get('splits'):issues.append('发现拆股/送转事件，当前收益处理不支持，拒绝进入模型准备')
    for bar in bars:
        try:
            o,h,l,c,v=[float(bar[k]) for k in ('open','high','low','close','volume')]
            if not np.isfinite([o,h,l,c,v]).all() or min(o,h,l,c)<=0 or v<0 or not l<=min(o,c)<=max(o,c)<=h:raise ValueError()
            close=datetime.fromisoformat(bar['close_at']);available=datetime.fromisoformat(bar['available_at'])
            if close.tzinfo is None or available.tzinfo is None or available<close:raise ValueError()
            day=date.fromisoformat(bar['session']);expected_close=datetime.combine(day,time(7),timezone.utc) if data['market']=='ashare' else datetime.combine(day+timedelta(days=1),time(),timezone.utc)
            if close!=expected_close:raise ValueError()
        except (ValueError,TypeError,KeyError):issues.append('存在未知/非法OHLC、成交量或时间');break
    event_days=[d['session'] for d in data.get('dividends',[])]
    if data['market']=='crypto':
        if event_days:issues.append('现货币对不应有股息')
        if any(date.fromisoformat(b)-date.fromisoformat(a)!=timedelta(days=1) for a,b in zip(expected,expected[1:])):issues.append('币对期望日历不连续')
    if len(event_days)!=len(set(event_days)) or not set(event_days)<=set(expected):issues.append('分红重复或不属于日历')
    if any(not np.isfinite(float(d['amount'])) or float(d['amount'])<=0 for d in data.get('dividends',[])):issues.append('分红金额非法')
    return {'issues':issues,'coverage':{'expected':len(expected),'missing':len(missing),'extra':len(extra)},'events':{'dividends':len(event_days),'splits':len(data.get('splits',[]))}}

def samples(data,horizon):
    if isinstance(horizon,bool) or horizon not in (1,5):raise ValueError('期限仅1/5')
    bars=data['bars'];div={d['session']:float(d['amount']) for d in data.get('dividends',[])}
    history=[0.]+[float(np.log((float(bars[i]['close'])+div.get(bars[i]['session'],0))/float(bars[i-1]['close']))) for i in range(1,len(bars))]
    availability=[];latest=datetime.fromisoformat(bars[0]['available_at'])
    for b in bars:latest=max(latest,datetime.fromisoformat(b['available_at']));availability.append(latest)
    rows=[]
    for i in range(60,len(bars)-horizon):
        decision=datetime.fromisoformat(bars[i]['close_at'])+timedelta(minutes=1)
        if availability[i]>decision:continue
        future=bars[i+1:i+horizon+1]
        if datetime.fromisoformat(future[0]['close_at'])<=decision:raise ValueError('标签窗口并非未来')
        rows.append({'signal_session':bars[i]['session'],'label_start':future[0]['session'],'label_end':future[-1]['session'],
            'label_available_at':max(datetime.fromisoformat(b['available_at']) for b in future).isoformat(),
            'decision_at':decision.isoformat(),'x':history[i-59:i+1],'target':float(np.mean(np.square(history[i+1:i+horizon+1])))})
    return rows
