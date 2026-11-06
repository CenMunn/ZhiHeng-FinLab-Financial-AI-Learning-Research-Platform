"""D28 descriptive market-model event study; no execution or investment advice."""
import math
from datetime import date,datetime,time,timezone,timedelta
from decimal import Decimal,InvalidOperation

ESTIMATION_START=-130
ESTIMATION_END=-21
CHINA=timezone(timedelta(hours=8))

def _number(value,positive=False):
    if isinstance(value,bool):raise ValueError('Boolean financial value')
    try:value=Decimal(str(value))
    except InvalidOperation:raise ValueError('Invalid financial value') from None
    if not value.is_finite() or (positive and value<=0):raise ValueError('Nonfinite or nonpositive financial value')
    return value

def _sessions(dataset):
    days=dataset['expected_sessions']
    if not days or days!=sorted(set(days)):raise ValueError('Calendar must be nonempty, ordered and unique')
    for day in days:date.fromisoformat(day)
    return days

def _bars(dataset):
    rows=dataset['bars'];keys=[r['session'] for r in rows]
    if keys!=sorted(set(keys)):raise ValueError('Bars must be ordered and unique')
    result={r['session']:_number(r['close'],True) for r in rows}
    if not set(result)<=set(_sessions(dataset)):raise ValueError('Bar is outside documented calendar')
    if dataset.get('splits'):raise ValueError('Unsupported split/bonus history')
    return result

def map_event(calendar,event):
    published=date.fromisoformat(event['publication_date']);precision=event['time_precision']
    if precision=='date':
        eligible=[day for day in calendar if day>str(published)]
        rule='仅有公布日期：保守映射至该日期之后首个交易日；不是精确公告时刻。'
    elif precision in ('minute','second'):
        value=event.get('publication_at')
        if not value:raise ValueError('Missing precise publication time')
        stamp=datetime.fromisoformat(value)
        if stamp.tzinfo is None or stamp.astimezone(CHINA).date()!=published:raise ValueError('Publication timestamp/date inconsistent')
        eligible=[day for day in calendar if datetime.combine(date.fromisoformat(day),time(9,30),CHINA)>stamp]
        rule='有时区的公布时刻：映射至严格晚于该时刻的首个交易日开盘。'
    else:raise ValueError('Unknown publication precision')
    if not eligible:raise ValueError('No subsequent session in verified calendar')
    return eligible[0],rule

def analyze(stock,benchmark,event,pre=5,post=5):
    """OLS uses exactly110 calendar returns at[-130,-21]; window changes never refit."""
    if type(pre) is not int or type(post) is not int or not 1<=pre<=10 or not 1<=post<=10:raise ValueError('Event window must be integers1..10')
    if stock.get('market')!='ashare' or stock['symbol']!=event['symbol']:raise ValueError('Event/stock identity mismatch')
    calendar=_sessions(stock);prices=_bars(stock);market_prices=_bars(benchmark)
    event_session,rule=map_event(calendar,event);index=calendar.index(event_session)
    if index+ESTIMATION_START<1 or index+post>=len(calendar):raise ValueError('Insufficient estimation/event calendar')
    dividends={}
    for item in stock.get('dividends',[]):
        day=item['session'];value=_number(item['amount'])
        if day in dividends or day not in calendar or value<0:raise ValueError('Invalid or duplicate dividend')
        dividends[day]=value
    # No pairwise deletion: a missing scheduled bar must not shorten/redefine the experiment.
    needed=calendar[index+ESTIMATION_START-1:index+post+1]
    if any(day not in prices or day not in market_prices for day in needed):raise ValueError('Missing stock/benchmark session in fixed study range')
    expected_benchmark=_sessions(benchmark)
    if any(day not in expected_benchmark for day in needed):raise ValueError('Benchmark calendar mismatch')
    returns={}
    for i in range(index+ESTIMATION_START,index+post+1):
        day,previous=calendar[i],calendar[i-1]
        stock_return=float((prices[day]+dividends.get(day,Decimal(0)))/prices[previous]-1)
        benchmark_return=float(market_prices[day]/market_prices[previous]-1)
        if not math.isfinite(stock_return) or not math.isfinite(benchmark_return):raise ValueError('Nonfinite return')
        returns[i]=(stock_return,benchmark_return)
    estimation_indices=list(range(index+ESTIMATION_START,index+ESTIMATION_END+1))
    if len(estimation_indices)!=110 or estimation_indices[-1]>=index-pre:raise ValueError('Estimation/event overlap')
    ys=[returns[i][0] for i in estimation_indices];xs=[returns[i][1] for i in estimation_indices];n=len(xs)
    mx=math.fsum(xs)/n;my=math.fsum(ys)/n
    sxx=math.fsum((x-mx)**2 for x in xs)
    if sxx<=1e-20:raise ValueError('Benchmark variance too small for market model')
    beta=math.fsum((x-mx)*(y-my) for x,y in zip(xs,ys))/sxx;alpha=my-beta*mx
    sse=math.fsum((y-alpha-beta*x)**2 for x,y in zip(xs,ys));sst=math.fsum((y-my)**2 for y in ys)
    sigma=math.sqrt(sse/(n-2));r_squared=1-sse/sst if sst>1e-20 else None
    if not all(math.isfinite(v) for v in (alpha,beta,sigma)):raise ValueError('Nonfinite market-model estimate')
    rows=[];residuals=[]
    for offset in range(-pre,post+1):
        i=index+offset;y,x=returns[i];normal=alpha+beta*x;ar=y-normal;residuals.append(ar)
        rows.append(dict(session=calendar[i],offset=offset,stock_return=y,benchmark_return=x,expected_return=normal,
                         abnormal_return=ar,cumulative_abnormal_return=math.fsum(residuals)))
    return dict(event_id=event['event_id'],symbol=stock['symbol'],benchmark_symbol=benchmark['symbol'],event_session=event_session,
                mapping={k:event.get(k) for k in ('publication_date','publication_at','time_precision')}|{'rule':rule},
                config=dict(pre=pre,post=post,estimation_start_offset=ESTIMATION_START,estimation_end_offset=ESTIMATION_END),
                estimation=dict(start=calendar[estimation_indices[0]],end=calendar[estimation_indices[-1]],n=n,
                                alpha=alpha,beta=beta,r_squared=r_squared,residual_sigma=sigma),
                rows=rows,summary=dict(car=rows[-1]['cumulative_abnormal_return'],event_ar=next(r['abnormal_return'] for r in rows if r['offset']==0)),
                limitations=['单事件历史描述，不证明公告造成股价变化；同期信息、市场冲击和信息提前反映都可能影响结果。',
                             '股票使用含税前现金分红的收盘简单总收益；沪深300为价格指数，不含再投资分红，两者口径已明确但不同。',
                             '日期精度不足时保守映射到下一交易日，可能错过实际公告日部分反应；收盘收益并非可成交策略收益。',
                             '调整观察窗口属于探索性敏感性分析，不按结果选择最佳窗口或宣称显著性。',
                             '估计区间固定110个交易日[-130,-21]，模型假设关系稳定；无单事件显著性或因果检验。'])
