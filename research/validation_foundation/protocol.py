from datetime import date,datetime,timedelta,timezone

CANDIDATES=[{'symbol':s,'name':n,'market':m,'role':r} for s,n,m,r in [
    ('600519','贵州茅台','ashare','消费/原锚'),('600036','招商银行','ashare','银行迁移'),('600900','长江电力','ashare','公用事业迁移'),('600585','海螺水泥','ashare','周期迁移'),('600276','恒瑞医药','ashare','医药迁移'),('BTCUSDT','Bitcoin/USDT','crypto','原锚'),('ETHUSDT','Ether/USDT','crypto','币种迁移')]]

def shift(day,months):
    total=day.year*12+day.month-1+months;return date(total//12,total%12+1,1)

def folds():
    result=[]
    for year in (2024,2025):
        for quarter,month in enumerate((1,4,7,10),1):
            start=date(year,month,1);early=shift(start,-12);cal=shift(start,-6)
            result.append({'fold':f'{year}Q{quarter}','bounds':{'train':['2018-01-01',str(early-timedelta(days=1))],
                'early_stopping':[str(early),str(cal-timedelta(days=1))],'calibration':[str(cal),str(start-timedelta(days=1))],
                'evaluation':[str(start),str(shift(start,3)-timedelta(days=1))]}})
    return result

PROTOCOL={'schema':'independent-validation-protocol-v1','candidates':CANDIDATES,'period':['2018-01-01','2025-12-31'],'folds':folds(),'horizons':[1,5],'lookback':60,
    'selection':'predeclared curated current-survivor educational cohort; not historical population or unbiased universe; no performance-based substitution',
    'target':'future h mean squared dividend-adjusted log daily close returns; raw prices; unsupported split/bonus events reject',
    'roles':{'train':'fit weights/scalers only','early_stopping':'select stopping only','calibration':'fit positive scale only, never early stopping','evaluation':'separate labels; score only after predictions frozen'},
    'prospective_signal_start':'2026-11-06','prospective_status':'pending future observations; no forward results; no automatic collection or trading',
    'available_at':'historical reconstruction with close+1minute assumption, not point-in-time vintage',
    'model_stage':'preparation only; no trained or evaluated models in this report'}

def partition(rows,bounds):
    parts={k:[] for k in bounds};purged={k:0 for k in bounds}
    for row in rows:
        for key,(start,end) in bounds.items():
            if start<=row['signal_session']<=end:
                cutoff=datetime.combine(date.fromisoformat(end)+timedelta(days=1),datetime.min.time(),timezone.utc)+timedelta(minutes=1)
                if start<=row['label_start']<=row['label_end']<=end and datetime.fromisoformat(row['label_available_at'])<=cutoff:parts[key].append(row)
                else:purged[key]+=1
                break
    return parts,purged

if __name__=='__main__':
    import json
    from research.market.common import PROJECT,write_json,digest
    target=PROJECT/'research/artifacts/validation-foundation/protocol-freeze-20261105.json'
    if target.exists():
        existing=json.loads(target.read_text('utf8'))
        if existing['protocol_sha256']!=digest(PROTOCOL) or existing['protocol']!=PROTOCOL:raise ValueError('已有冻结协议不同，拒绝改写')
    else:write_json(target,{'protocol':PROTOCOL,'protocol_sha256':digest(PROTOCOL),'frozen_at':datetime.now(timezone.utc).isoformat(),'scope':'frozen before qualification/performance inspection; candidate text predeclared in plan'})
    print(target)
