"""Append-only prospective evidence. Labels are appended only after maturity."""
import json, math, os, tempfile
from datetime import datetime, timedelta, timezone, time, date
from pathlib import Path
from research.market.common import digest, file_sha

START = '2026-11-06'
KEYS = {'train_mean','ewma','lightgbm','dlinear_seed_17','dlinear_seed_42','dlinear_seed_2025','dlinear'}

def utcnow(): return datetime.now(timezone.utc)

def timestamp(value):
    result=datetime.fromisoformat(value)
    if result.tzinfo is None: raise ValueError('时间必须包含时区')
    return result

def immutable(path, record):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    envelope={'record':record,'sha256':digest(record)}
    raw=json.dumps(envelope,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False).encode('utf8')
    if path.exists():
        if read_verified(path)!=record: raise ValueError('拒绝改写不可变记录')
        return
    fd,tmp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        try:os.link(tmp,path)
        except FileExistsError:
            if read_verified(path)!=record:raise ValueError('并发写入冲突')
    finally:Path(tmp).unlink(missing_ok=True)

def read_verified(path):
    body=json.loads(Path(path).read_text('utf8'))
    if digest(body['record'])!=body['sha256']:raise ValueError('记录摘要变化')
    return body['record']

def register(root, bundle, *, _now=None):
    identity={'schema':'forward-protocol-v1','start':START,'bundle':bundle,
              'target':'single executable open-to-open log total return squared',
              'target_volatility':'0.10','source_timing':'actual reception before actual decision',
              'label_maturity':'exit full daily bar received; no early-open scoring'}
    protocol_id='forward-'+digest(identity);path=Path(root)/protocol_id/'protocol.json'
    if path.exists():
        record=read_verified(path)
        if record['identity']!=identity:raise ValueError('协议身份不符')
        return record
    record={'protocol_id':protocol_id,'identity':identity,'registered_at':(_now or utcnow()).isoformat()}
    immutable(path,record);return record

def interval(snapshot, signal):
    days=sorted(set(snapshot['calendar']));market=snapshot['market']
    if market not in ('ashare','crypto') or signal not in days:raise ValueError('未取得可靠交易日历')
    index=days.index(signal);lead=1 if market=='ashare' else 2
    if index+lead+1>=len(days):raise ValueError('未来入场/退出日历不足')
    sessions=days[index+lead:index+lead+2];hour=time(1,30) if market=='ashare' else time()
    return [datetime.combine(date.fromisoformat(s),hour,timezone.utc).isoformat() for s in sessions]

def record_prediction(root, protocol, snapshot, predictions, *, _now=None):
    now=_now or utcnow();bundle=protocol['identity']['bundle'];symbol=bundle['symbol']
    if snapshot['symbol']!=symbol or snapshot['market']!=bundle['market'] or snapshot['status']!='ready':raise ValueError('新行情不合格或标的不符')
    bars=snapshot['bars'];signal=bars[-1]['session']
    if signal<START:raise ValueError('等待起点之后的成熟信号')
    forecast_id='prediction-'+digest({'protocol_id':protocol['protocol_id'],'symbol':symbol,'signal_session':signal})
    path=Path(root)/protocol['protocol_id']/(forecast_id+'.json')
    if path.exists():return read_verified(path)
    received=timestamp(snapshot['retrieved_at']);available=max(timestamp(b['available_at']) for b in bars)
    mature=timestamp(bars[-1]['close_at'])+timedelta(minutes=1)
    entry,exit=interval(snapshot,signal)
    if not timestamp(protocol['registered_at'])<=now or not max(received,available,mature)<=now<timestamp(entry):raise ValueError('输入未成熟或已错过入场，拒绝补记')
    if now-mature>timedelta(days=4):raise ValueError('行情过期')
    if set(predictions)!=KEYS:raise ValueError('预测模型集合变化')
    for values in predictions.values():
        if set(values)!={'raw','calibrated'} or any(not math.isfinite(v) or v<=0 for v in values.values()):raise ValueError('预测非法')
    coefficients=bundle.get('calibration',{})
    if set(coefficients)!=KEYS:raise ValueError('缺少冻结校准系数')
    for key,values in predictions.items():
        expected=max(values['raw']*coefficients[key],1e-10)
        if not math.isclose(values['calibrated'],expected,rel_tol=1e-12,abs_tol=1e-15):raise ValueError('预测校准与冻结系数不符')
    mean=sum(predictions[f'dlinear_seed_{s}']['raw'] for s in (17,42,2025))/3
    if not math.isclose(predictions['dlinear']['raw'],mean,rel_tol=1e-12,abs_tol=1e-15):raise ValueError('DLinear三种子平均不符')
    record={'forecast_id':forecast_id,'protocol_id':protocol['protocol_id'],'symbol':symbol,'market':snapshot['market'],
            'signal_session':signal,'created_at':now.isoformat(),'decision_at':now.isoformat(),'nominal_decision_at':mature.isoformat(),
            'entry_at':entry,'exit_at':exit,'predictions':predictions,'input_sha256':digest(snapshot),'snapshot':snapshot}
    # Check again immediately before writing; an inference completing at entry cannot backdate itself.
    if _now is None and utcnow()>=timestamp(entry):raise ValueError('写入时已错过入场')
    immutable(path,record);return record

def settle(root, forecast, snapshot, *, _now=None):
    now=_now or utcnow();path=Path(root)/forecast['protocol_id']/('outcome-'+forecast['forecast_id'][11:]+'.json')
    original=read_verified(Path(root)/forecast['protocol_id']/(forecast['forecast_id']+'.json'))
    if original!=forecast:raise ValueError('预测记录变化')
    if path.exists():
        out=read_verified(path)
        if out['forecast_sha256']!=digest(forecast):raise ValueError('评分绑定不符')
        return out
    if snapshot['symbol']!=forecast['symbol'] or snapshot['market']!=forecast['market'] or snapshot['status']!='ready':raise ValueError('评分来源不符或不合格')
    if timestamp(snapshot['retrieved_at'])>now:raise ValueError('未来接收时间')
    entry=timestamp(forecast['entry_at']);exit=timestamp(forecast['exit_at'])
    if now<=exit:return None
    bars={b['session']:b for b in snapshot['bars']}
    if len(bars)!=len(snapshot['bars']):raise ValueError('重复行情')
    a,b=bars.get(entry.date().isoformat()),bars.get(exit.date().isoformat())
    if a is None or b is None:return None
    if max(timestamp(b['available_at']),timestamp(b['close_at'])+timedelta(minutes=1))>now:return None
    dividend=sum(float(d['amount']) for d in snapshot['dividends'] if d['session']==b['session'])
    log_return=math.log((float(b['open'])+dividend)/float(a['open']));y=log_return**2
    errors={key:{mode+'_qlike':math.log(max(p,1e-10))+y/max(p,1e-10) for mode,p in values.items()} for key,values in forecast['predictions'].items()}
    result={'forecast_id':forecast['forecast_id'],'forecast_sha256':digest(forecast),'scored_at':now.isoformat(),
            'realized_variance':y,'log_return':log_return,'errors':errors,'snapshot':snapshot,'input_sha256':digest(snapshot)}
    immutable(path,result);return result
