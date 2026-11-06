"""D26 open-to-open teaching ledger. Pure stdlib; no fitting or label access.

All balances, quantities, weights and fees use Decimal. Only sample risk
statistics use floats, after the completed net open account returns are known.
"""
from datetime import datetime, time, timedelta, timezone, date
from decimal import Decimal, localcontext, ROUND_DOWN, ROUND_HALF_UP
import math
import statistics

STRATEGIES = ('hold_full', 'fixed_risk', 'ewma_raw', 'ewma_calibrated',
              'lightgbm_raw', 'lightgbm_calibrated', 'dlinear_raw', 'dlinear_calibrated')
ZERO = Decimal(0)
ONE = Decimal(1)
Q8 = Decimal('.00000001')


def _number(value):
    if not value:return '0'
    result = format(value, 'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def _money(value):
    return value.quantize(Q8, rounding=ROUND_HALF_UP)


def _decimal(value):
    try:result = Decimal(str(value))
    except Exception as exc:raise ValueError('Invalid Decimal value') from exc
    if not result.is_finite():raise ValueError('Nonfinite Decimal value')
    return result


def _timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:raise ValueError('Timezone required')
    return result


def _open(session, is_a):
    return datetime.combine(date.fromisoformat(session), time(1,30) if is_a else time(), timezone.utc)


def _costs(notional, side, is_a, multiplier):
    profile = (Decimal('3'), Decimal('5'), Decimal('5'), Decimal('.1')) if is_a else (Decimal('10'), ZERO, ZERO, ZERO)
    commission, minimum, tax, transfer = profile
    raw = dict(commission=max(notional*commission/10000, minimum) if notional else ZERO,
               tax=notional*tax/10000 if side=='sell' else ZERO,
               transfer=notional*transfer/10000, slippage=notional*Decimal('2')/10000)
    fees = {key:_money(value*multiplier) for key,value in raw.items()}
    fees['total'] = sum(fees.values(), ZERO)
    return fees


def _weight(variance, target, annual):
    var = _decimal(variance)
    if var < 0:raise ValueError('Forecast variance must be nonnegative')
    return min(ONE, target/(max(var,Decimal('1e-10'))*annual).sqrt())


def simulate(dataset, observations, strategy, target_volatility='0.10', cost_multiplier=1):
    """Replay one asset, all 2024–25 opens, using only frozen causal forecasts.

    Dividend entitlement is inventory immediately before ex-date open. Receivables
    contribute to equity but never to spendable cash. No day high/low/volume is read.
    The first open has no elapsed return. Any first-open fee enters the first
    full elapsed interval; every subsequent cash/gap/quarter date enters risk.
    """
    with localcontext() as context:
        context.prec = 40
        return _simulate(dataset, observations, strategy, target_volatility, cost_multiplier)


def _simulate(dataset, observations, strategy, target_volatility, cost_multiplier):
    if strategy not in STRATEGIES:raise ValueError('Unknown risk-budget strategy')
    target = _decimal(target_volatility)
    if not Decimal('.05')<=target<=Decimal('.30'):raise ValueError('Target volatility outside 5%–30%')
    if type(cost_multiplier) is not int or cost_multiplier not in (0,1,2):raise ValueError('Cost multiplier must be 0, 1 or 2')
    market = dataset['market']
    if market not in ('ashare','crypto'):raise ValueError('Unsupported market')
    is_a = market=='ashare'; annual = 252 if is_a else 365
    symbol = dataset['symbol']
    if not is_a and symbol not in ('BTCUSDT','ETHUSDT'):raise ValueError('Unknown crypto quantity step')
    step = Decimal('100') if is_a else Decimal('.00001' if symbol=='BTCUSDT' else '.0001')
    initial = Decimal('1000000' if is_a else '100000')
    bars = dataset['bars']; sessions = [b['session'] for b in bars]
    if sessions != sorted(set(sessions)) or not bars:raise ValueError('Bars must be unique and ordered')
    indices = {day:i for i,day in enumerate(sessions)}
    prefix = []; latest = None
    for b in bars:
        available = _timestamp(b['available_at'])
        latest = available if latest is None else max(latest, available)
        prefix.append(latest)
        if _decimal(b['open'])<=0:raise ValueError('Nonpositive execution open')
    dividends = {}
    for event in dataset.get('dividends',[]):
        session = event['session']; amount = _decimal(event['amount'])
        if session in dividends or session not in indices or amount<0:raise ValueError('Invalid dividend map')
        dividends[session] = amount
    entries = {}; signals = set(); fold_last = {}; fixed = {}
    for row in observations:
        signal, entry, exit_day = (row[k] for k in ('signal_session','entry_session','exit_session'))
        if signal not in indices or entry not in indices or exit_day not in indices:raise ValueError('Unknown observation session')
        if entry in entries or signal in signals:raise ValueError('Duplicate observation mapping')
        i,j,k = indices[signal],indices[entry],indices[exit_day]
        decision = _timestamp(row['decision_at']); opened = _open(entry,is_a); exited = _open(exit_day,is_a)
        if j!=i+(1 if is_a else 2) or k!=j+1:raise ValueError('Incorrect executable open interval')
        if not decision<opened<exited or _timestamp(row['entry_at'])!=opened or _timestamp(row['exit_at'])!=exited:
            raise ValueError('Decision must precede actual entry and exit opens')
        if decision!=_timestamp(bars[i]['close_at'])+timedelta(minutes=1) or prefix[i]>decision:
            raise ValueError('Signal input not fully published at decision')
        if not '2024-01-01'<=entry<exit_day<='2025-12-31':raise ValueError('Observation outside evaluation')
        fold=row['fold']; mean=_decimal(row['raw']['train_mean'])
        if fold in fixed and fixed[fold]!=mean:raise ValueError('Train mean changes within fold')
        fixed[fold]=mean; fold_last[fold]=max(exit_day,fold_last.get(fold,exit_day))
        entries[entry]=row; signals.add(signal)
    forced = set(fold_last.values())
    if forced & set(entries):raise ValueError('Fold liquidation conflicts with an entry')
    evaluation = [i for i,s in enumerate(sessions) if '2024-01-01'<=s<='2025-12-31']
    if not evaluation:raise ValueError('No evaluation opens')
    cash=initial; quantity=ZERO; receivable=ZERO; total_cost=ZERO; peak=initial; prior=initial
    curve=[]; trades=[]; rejections=[]; returns=[]; rolling=[]; turnover_amount=ZERO; last_buy=None
    for i in evaluation:
        bar=bars[i]; session=bar['session']; price=_decimal(bar['open'])
        receivable += quantity*dividends.get(session,ZERO)
        equity=cash+quantity*price+receivable
        row=entries.get(session)
        desired=ZERO
        if row and session not in forced:
            if strategy=='hold_full':desired=ONE
            elif strategy=='fixed_risk':desired=_weight(fixed[row['fold']],target,annual)
            else:
                model,kind=strategy.rsplit('_',1)
                desired=_weight(row['raw' if kind=='raw' else 'calibrated'][model],target,annual)
        actual=quantity*price/equity if equity else ZERO
        # The 5 pp band never prevents a mandatory cash liquidation/retry.
        rebalance=(desired==ZERO and quantity>0) or abs(desired-actual)>Decimal('.05')
        wanted=(desired*equity/price/step).to_integral_value(rounding=ROUND_DOWN)*step
        delta=wanted-quantity
        side='buy' if delta>0 else 'sell'
        reason=None
        if rebalance and not delta and desired>actual:
            rejections.append(dict(session=session,side='buy',reason='insufficient_cash_for_step_and_costs',
                                   target_weight=_number(desired),actual_weight=_number(actual)))
        if rebalance and delta:
            if is_a:
                if i==0 or _timestamp(bars[i-1]['available_at'])>=_open(session,is_a):
                    reason='previous_close_not_available'
                else:
                    reference=_decimal(bars[i-1]['close'])-dividends.get(session,ZERO)
                    upper=(reference*Decimal('1.1')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                    lower=(reference*Decimal('.9')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                    if reference<=0 or price>=upper or price<=lower:reason='approximate_limit_open_no_fill'
                if side=='sell' and last_buy==session:reason='t_plus_one'
            qty=abs(delta) if side=='buy' else min(quantity,abs(delta))
            if not reason and side=='buy':
                low=0; high=int(qty/step)
                while low<high:
                    mid=(low+high+1)//2; proposed=_money(Decimal(mid)*step*price)
                    if proposed+_costs(proposed,side,is_a,cost_multiplier)['total']<=cash:low=mid
                    else:high=mid-1
                qty=Decimal(low)*step
                if qty<=0:reason='insufficient_cash_for_step_and_costs'
            if not reason:
                notional=_money(qty*price); fees=_costs(notional,side,is_a,cost_multiplier)
                after=cash-notional-fees['total'] if side=='buy' else cash+notional-fees['total']
                if after<0:reason='cash_insolvent_order'
            if reason:rejections.append(dict(session=session,side=side,reason=reason,target_weight=_number(desired),actual_weight=_number(actual)))
            else:
                cash=after; quantity+=qty if side=='buy' else -qty
                if side=='buy':last_buy=session
                total_cost+=fees['total']; turnover_amount+=notional
                trades.append(dict(session=session,side=side,quantity=_number(qty),price=_number(price),notional=_number(notional),
                    costs={k:_number(v) for k,v in fees.items()},fill_at=_open(session,is_a).isoformat(),
                    signal_session=row['signal_session'] if row else None,decision_at=row['decision_at'] if row else None,
                    decision_kind='published_close_signal' if row else 'precommitted_cash_boundary',fold=row['fold'] if row else None))
        if cash<0 or quantity<0:raise ArithmeticError('Negative cash or quantity')
        equity=cash+quantity*price+receivable
        net=equity/prior-ONE if curve else None
        if net is not None:returns.append(float(net))
        peak=max(peak,equity); drawdown=(peak-equity)/peak
        # Preserve initial-open costs in the first genuine elapsed return.
        if curve:prior=equity
        risk=statistics.stdev(returns[-20:])*math.sqrt(annual) if len(returns)>=20 else None
        if risk is not None:rolling.append(risk)
        curve.append(dict(session=session,open=_number(price),cash=_number(_money(cash)),quantity=_number(quantity),
            dividend_receivable=_number(_money(receivable)),equity=_number(_money(equity)),wealth=_number(equity/initial),
            target_weight=_number(desired),actual_weight=_number(quantity*price/equity if equity else ZERO),
            net_return=_number(net) if net is not None else None,drawdown=_number(drawdown),rolling20_volatility=risk,
            fold=row['fold'] if row else None,signal_session=row['signal_session'] if row else None))
    vol=statistics.stdev(returns)*math.sqrt(annual) if len(returns)>1 else None
    windows=[]
    for i in range(20,len(curve)):
        baseline=initial if i==20 else _decimal(curve[i-20]['equity'])
        windows.append(dict(start=curve[i-20]['session'],end=curve[i]['session'],periods=20,
                            **{'return':_number(_decimal(curve[i]['equity'])/baseline-ONE)}))
    worst=sorted(windows,key=lambda p:_decimal(p['return']))[:3]
    mean_equity=sum((_decimal(p['equity']) for p in curve),ZERO)/len(curve)
    metrics=dict(**{'return':_number(equity/initial-ONE)},max_drawdown=_number(max(_decimal(p['drawdown']) for p in curve)),
        costs=_number(total_cost),turnover=_number(turnover_amount/mean_equity),
        exposure_fraction=_number(Decimal(sum(_decimal(p['quantity'])>0 for p in curve))/len(curve)),
        average_weight=_number(sum((_decimal(p['actual_weight']) for p in curve),ZERO)/len(curve)),
        final_equity=_number(_money(equity)),final_cash=_number(_money(cash)),final_quantity=_number(quantity),
        dividend_receivable=_number(_money(receivable)),annualized_volatility=vol,
        target_error_abs=abs(vol-float(target)) if vol is not None else None,
        rolling20_volatility_rmse=math.sqrt(statistics.mean((r-float(target))**2 for r in rolling)) if rolling else None,
        return_periods=len(returns),trade_count=len(trades),rejection_count=len(rejections),worst20=worst)
    config=dict(strategy=strategy,target_volatility=_number(target),cost_multiplier=cost_multiplier,initial_cash=_number(initial),
        currency='CNY' if is_a else 'USDT',annualization=annual,quantity_step=_number(step),rebalance_band='0.05',
        variance_floor='0.0000000001',cash_interest='0',valuation='open_after_costs_plus_dividend_receivable',
        evaluation_start='2024-01-01',evaluation_end='2025-12-31',return_convention='first_open_baseline_initial_fee_in_first_elapsed_interval',
        fees=dict(commission_bps='3' if is_a else '10',minimum_commission='5' if is_a else '0',
                  sell_tax_bps='5' if is_a else '0',transfer_bps='0.1' if is_a else '0',slippage_bps='2',rounding_places=8))
    return dict(metrics=metrics,curve=curve,trades=trades,rejections=rejections,config=config)
