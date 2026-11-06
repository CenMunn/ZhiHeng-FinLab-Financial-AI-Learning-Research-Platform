"""Causal daily cash-spot comparison engine. No training or brokerage execution."""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, localcontext, ROUND_DOWN, ROUND_HALF_UP
import hashlib
from pathlib import Path
import platform
import pydantic
from platform_app.contracts.models import stable_hash
from platform_app.contracts.public_backtests import PublicDataset, BacktestConfig
from platform_app.experiments.markets import estimate_costs, number

UTC=timezone.utc
ROOT=Path(__file__).resolve().parents[1]
ENGINE_SOURCES={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
    'experiments/backtest.py','experiments/markets.py','contracts/models.py','contracts/market_experiments.py',
    'contracts/public_backtests.py','adapters/public_market.py')}
# Source-checkout runs also identify the offline acquisition entry point. A wheel
# without repository scripts can still read historical records and run the engine.
ACQUISITION=ROOT.parents[2]/'scripts/fetch_public_market_data.py'
if ACQUISITION.is_file():ENGINE_SOURCES['acquisition/fetch_public_market_data.py']=hashlib.sha256(ACQUISITION.read_bytes()).hexdigest()
ENGINE_SHA256=stable_hash(ENGINE_SOURCES)
RUNTIME={'python':platform.python_version(),'pydantic':pydantic.__version__,'decimal':__import__('decimal').__libmpdec_version__}


def amount(value):return number(value.quantize(Decimal('.00000001'),rounding=ROUND_HALF_UP))


def default_config(dataset:PublicDataset)->BacktestConfig:
    btc=dataset.snapshot.market=='btc'
    return BacktestConfig(initial_cash='10000' if btc else '1000000',costs={
        'commission_bps':'10' if btc else '3','minimum_commission':'0' if btc else '5',
        'sell_tax_bps':'0' if btc else '5','transfer_bps':'0' if btc else '0.1','slippage_bps':'2'})


def fingerprint(dataset,config):
    return stable_hash({'dataset_sha256':stable_hash(dataset.model_dump(mode='json')),'config':config.model_dump(mode='json'),
                        'engine_sha256':ENGINE_SHA256,'runtime':RUNTIME})


def open_at(snapshot,day):
    return datetime.combine(day,time(1,30) if snapshot.market=='ashare' else time(),UTC)


def signals(dataset,config):
    bars=dataset.snapshot.bars;divs={d.session:Decimal(d.amount) for d in dataset.dividends};adjusted=[];rows=[]
    blocks={b.session:b for b in dataset.blocks}
    for i,bar in enumerate(bars):
        if bar.close is None:raise ValueError('首版回测拒绝未知价格/停牌行，不猜测成交或估值')
        close=Decimal(bar.close)
        adjusted.append(close if not i else adjusted[-1]*(close+divs.get(bar.session,Decimal(0)))/Decimal(bars[i-1].close))
        decision=bar.close_at+timedelta(minutes=1)
        known=all(b.available_at<=decision for b in bars[:i+1])
        sma=sum(adjusted[i-config.window+1:i+1])/config.window if i+1>=config.window and known else None
        point=blocks.get(bar.session)
        cycle=cycle_position(point.height) if point and point.observed_at+timedelta(minutes=1)<=decision else None
        rows.append({'session':str(bar.session),'decision_at':decision.isoformat(),'signal_close':number(adjusted[-1]),
                     'sma':number(sma) if sma is not None else None,'trend':int(adjusted[-1]>sma) if sma is not None else None,'cycle':cycle})
    return rows


def simulate(dataset,config,all_signals,indices,strategy,*,targets=None):
    snapshot=dataset.snapshot;bars=snapshot.bars;is_a=snapshot.market=='ashare'
    cash=Decimal(config.initial_cash);initial=cash;quantity=Decimal(0);receivable=Decimal(0);cost_sum=Decimal(0)
    step=Decimal('100') if is_a else Decimal(snapshot.quantity_step)
    dividends={d.session:Decimal(d.amount) for d in dataset.dividends}
    curve=[];trades=[];rejections=[];last_buy=None
    for i in indices:
        bar=bars[i];opened=open_at(snapshot,bar.session);price=Decimal(bar.open)
        # Entitlement belongs to inventory held before the ex-date open.
        receivable+=quantity*dividends.get(bar.session,Decimal(0))
        j=i-1 if is_a else i-2
        signal=all_signals[j]
        if datetime.fromisoformat(signal['decision_at'])>=opened:raise ValueError('信号尚未可用，禁止同一边界成交')
        if strategy=='forecast':
            point=(targets or {}).get(signal['session'])
            if not point or point.get('decision_at')!=signal['decision_at'] or type(point.get('target')) is not int or point['target'] not in (0,1):
                raise ValueError('缺少或错配的已冻结预测仓位/决策时间')
            target=point['target']
        elif strategy=='buy_hold':target=1
        elif strategy=='trend':
            if signal['trend'] is None:raise ValueError('缺少已发布历史预热数据，不能启动趋势回测')
            target=signal['trend']
        else:
            if signal['cycle'] is None:raise ValueError('缺少相应日期的真实区块观察，不能估算或填充周期')
            target=int(signal['cycle']['phase']=='rising')
        side='buy' if target and quantity==0 else 'sell' if not target and quantity>0 else None
        reason=None
        if side:
            if Decimal(bar.volume)<=0:reason='zero_volume'
            if is_a:
                reference=Decimal(bars[i-1].close)-dividends.get(bar.session,Decimal(0))
                upper=(reference*Decimal('1.1')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                lower=(reference*Decimal('.9')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                if price>=upper or price<=lower:reason='approximate_limit_open_no_fill'
                if side=='sell' and last_buy==bar.session:reason='t_plus_one'
            if not reason:
                if side=='buy':
                    # Rounded costs are monotone in notional. Binary search integer steps,
                    # rather than decrementing millions of BTC quantity ticks.
                    low=0;high=int((cash/price/step).to_integral_value(rounding=ROUND_DOWN)) if cash>Decimal(config.costs.minimum_commission) else 0
                    while low<high:
                        middle=(low+high+1)//2
                        candidate=Decimal(amount(Decimal(middle)*step*price))
                        proposed=estimate_costs(number(candidate),'buy',config.costs)
                        if candidate+Decimal(proposed['total'])<=cash:low=middle
                        else:high=middle-1
                    qty=Decimal(low)*step
                    if qty>0:
                        notional=Decimal(amount(qty*price));costs=estimate_costs(number(notional),'buy',config.costs)
                        if notional<=0:qty=Decimal(0)
                    if qty<=0:reason='insufficient_cash_for_step_and_costs'
                else:
                    qty=quantity;notional=Decimal(amount(qty*price));costs=estimate_costs(number(notional),'sell',config.costs)
                    if notional<Decimal(costs['total']):reason='proceeds_less_than_costs'
            if reason:rejections.append({'session':str(bar.session),'side':side,'reason':reason})
            else:
                fee=Decimal(costs['total']);cost_sum+=fee
                if side=='buy':cash-=notional+fee;quantity+=qty;last_buy=bar.session
                else:cash+=notional-fee;quantity-=qty
                trades.append({'session':str(bar.session),'signal_session':None if strategy=='buy_hold' else signal['session'],
                    'decision_at':(open_at(snapshot,snapshot.sessions[indices[0]])-timedelta(days=1)).isoformat() if strategy=='buy_hold' else signal['decision_at'],
                    'decision_kind':'precommitted_buy_hold' if strategy=='buy_hold' else 'published_close_signal',
                    'fill_at':opened.isoformat(),'side':side,'quantity':number(qty),'price':bar.open,'notional':number(notional),'costs':costs})
        equity=cash+quantity*Decimal(bar.close)+receivable
        if cash<0 or quantity<0:raise ArithmeticError('现金/持仓账本出现负值')
        curve.append({'session':str(bar.session),'cash':amount(cash),'quantity':number(quantity),'close':bar.close,
            'dividend_receivable':amount(receivable),'equity':amount(equity),'wealth':number(equity/initial),
            'signal_session':signal['session'],'target':target,'signal_close':signal['signal_close'],'sma':signal['sma'],'cycle':signal['cycle']})
    final=Decimal(curve[-1]['equity']);peak=initial;mdd=Decimal(0);annual=[];prior=initial;current_year=None;year_start=initial
    for point in curve:
        value=Decimal(point['equity']);peak=max(peak,value);dd=(peak-value)/peak;mdd=max(mdd,dd);point['drawdown']=number(dd)
        year=point['session'][:4]
        if current_year!=year:
            if current_year is not None:annual.append({'year':current_year,'return':number(prior/year_start-1) if year_start else None})
            current_year=year;year_start=prior
        prior=value
    annual.append({'year':current_year,'return':number(prior/year_start-1) if year_start else None})
    days=(bars[indices[-1]].session-bars[indices[0]].session).days+1
    annualized=number((final/initial)**(Decimal('365.25')/days)-1) if days>=30 else None
    average_equity=sum(Decimal(p['equity']) for p in curve)/len(curve)
    turnover=sum(Decimal(t['notional']) for t in trades)/average_equity if average_equity else None
    return {'metrics':{'return':number(final/initial-1),'annualized_return':annualized,'max_drawdown':number(mdd),
            'turnover':number(turnover) if turnover is not None else None,'costs':amount(cost_sum),'trade_count':len(trades),'rejection_count':len(rejections),
            'exposure_fraction':number(Decimal(sum(Decimal(p['quantity'])>0 for p in curve))/len(curve)),
            'final_equity':amount(final),'final_cash':amount(cash),'final_quantity':number(quantity),'dividend_receivable':amount(receivable)},
            'annual':annual,'curve':curve,'trades':trades,'rejections':rejections}


def compare(dataset:PublicDataset,config:BacktestConfig)->dict:
    with localcontext() as context:
        context.prec=40
        snapshot=dataset.snapshot
        if snapshot.market=='btc' and (Decimal(config.costs.sell_tax_bps) or Decimal(config.costs.transfer_bps)):raise ValueError('BTC现货对照不接受A股卖出税/过户费')
        if config.start<snapshot.sessions[0] or config.end>snapshot.sessions[-1]:raise ValueError('评估区间超出登记快照')
        indices=[i for i,day in enumerate(snapshot.sessions) if config.start<=day<=config.end]
        if len(indices)<2 or indices[0]<config.window+2:raise ValueError('至少两个评估日，且须保留均线窗口与成交延迟的预热数据')
        rows=signals(dataset,config)
        strategies={name:simulate(dataset,config,rows,indices,name) for name in (('buy_hold','trend') if snapshot.market=='ashare' else ('buy_hold','trend','halving_cycle'))}
        base=strategies['buy_hold']
        for key,run in strategies.items():
            run['metrics']['excess_return']=number(Decimal(run['metrics']['return'])-Decimal(base['metrics']['return']))
            windows=[];undefined=0;n=min(20,len(run['curve'])-1)
            for i in range(n,len(run['curve'])):
                start_equity=Decimal(run['curve'][i-n]['equity']);base_equity=Decimal(base['curve'][i-n]['equity'])
                if not start_equity or not base_equity:
                    undefined+=1;continue
                strategy_return=Decimal(run['curve'][i]['equity'])/start_equity-1
                base_return=Decimal(base['curve'][i]['equity'])/base_equity-1
                windows.append({'start':run['curve'][i-n]['session'],'end':run['curve'][i]['session'],'sessions':n,
                    'strategy_return':number(strategy_return),'benchmark_return':number(base_return),'excess_return':number(strategy_return-base_return)})
            run['worst_relative_window']=min(windows,key=lambda p:Decimal(p['excess_return'])) if windows else None
            run['undefined_relative_windows']=undefined
        return {'schema_version':'backtest-result-v1','input_sha256':fingerprint(dataset,config),'dataset_sha256':stable_hash(dataset.model_dump(mode='json')),
            'dataset_id':snapshot.snapshot_id,'market':snapshot.market,'instrument':snapshot.instrument,'currency':snapshot.currency,
            'engine_sha256':ENGINE_SHA256,'engine_sources':ENGINE_SOURCES,'engine_runtime':RUNTIME,'config':config.model_dump(mode='json'),
            'evaluation':{'start':str(snapshot.sessions[indices[0]]),'end':str(snapshot.sessions[indices[-1]]),'rows':len(indices),
                'protocol':'历史教学评估；默认2018–2021预留训练、2022–2023预留验证、2024–2025评估；本轮未拟合或优化模型，非盲测。'},
            'strategies':strategies,'quality':dataset.quality,
            'rules':['收盘后1分钟形成决策；只在严格晚于决策的日线开盘尝试成交。A股下一交易日，BTC延后一根完整日线。',
                '趋势：已发生分红的向前累计信号指数高于包含当日的尾随均线则持仓，否则现金；不读取未来事件。',
                '周期：((height % 210000)+78750)%210000 <157500持仓；只检验假设，不拟合价格顶部。',
                '分红计应收不再投资，未扣个人分红税；期末不强制平仓，收益含市值和未实现盈亏。',
                '滑点作为独立现金成本；换手=双边成交金额之和/日收盘平均权益，不除以二；回撤包含初始现金基准和费用。',
                '费用为整个区间固定的教学假设，不冒充实际历史法定税率；日线开盘成交是近似模拟，不保证可实现。'],
            'limitations':list(snapshot.limitations)+['这里只比较显式规则，没有新模型训练；单股票与单个BTC交易所的结果不能外推其他标的或未来。']}


def cycle_position(height:int)->dict:
    if isinstance(height,bool) or not isinstance(height,int) or height<0:raise ValueError('区块高度必须是非负整数')
    p=(height%210000+78750)%210000
    rising=p<157500
    index=Decimal(p)/157500 if rising else 1-Decimal(p-157500)/52500
    return {'height':height,'index':format(index.normalize(),'f'),'phase':'rising' if rising else 'falling'}
