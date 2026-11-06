from datetime import date,datetime,time,timedelta
from decimal import Decimal
from functools import lru_cache
from platform_app.contracts.market_experiments import MarketSnapshot,MarketBar,FoundationConfig,CostAssumptions,UTC,SHANGHAI

@lru_cache(maxsize=1)
def sample_snapshots()->tuple[MarketSnapshot,...]:
    snapshots=[]
    for market in ('ashare','btc'):
        sessions=tuple(date(2026,9,7)+timedelta(days=i) for i in range(21)
                       if market=='btc' or (date(2026,9,7)+timedelta(days=i)).weekday()<5)
        bars=[]
        for index,session in enumerate(sessions):
            base=Decimal('20') if market=='ashare' else Decimal('60000')
            step=Decimal('0.1') if market=='ashare' else Decimal('200')
            close=base+step*Decimal(index+(0,2,-1,3,-2)[index%5])
            opening=close-step;closing=datetime.combine(session,time(15),SHANGHAI) if market=='ashare' else datetime.combine(session+timedelta(days=1),time(),UTC)
            bars.append(MarketBar(session=session,close_at=closing,available_at=closing+timedelta(minutes=1),open=str(opening),high=str(close+step*2),low=str(opening-step),close=str(close),volume=str(100000+index*1000)))
        snapshots.append(MarketSnapshot(snapshot_id=f'{market}-synthetic-v1',market=market,instrument='SYNTH.A' if market=='ashare' else 'BTCUSDT',venue='synthetic-mainboard' if market=='ashare' else 'synthetic-spot',currency='CNY' if market=='ashare' else 'USDT',source_kind='synthetic',source_uri='builtin://deterministic-market-samples/v1',source_license='Project-authored synthetic fixture; no market-data claim',calendar_kind='synthetic',calendar_source='builtin://synthetic-session-fixture/v1',sessions=sessions,bars=tuple(bars),quantity_step='1' if market=='ashare' else '0.000001',limitations=('确定性合成行情和日历，不是真实历史数据或官方日历。','未复权价格，不处理分红/拆股；不能直接用作真实收益回测。','BTC数量步长仅为教学配置。' if market=='btc' else '仅演示普通主板规则子集，不含科创板/风险警示/上市初期。')))
    return tuple(snapshots)

def default_config(snapshot:MarketSnapshot)->FoundationConfig:
    return FoundationConfig(train_count=8 if snapshot.market=='ashare' else 12,validation_count=3 if snapshot.market=='ashare' else 4,as_of=max(b.available_at for b in snapshot.bars),costs=CostAssumptions() if snapshot.market=='ashare' else CostAssumptions(commission_bps='10',minimum_commission='0',sell_tax_bps='0',transfer_bps='0',slippage_bps='3'))
