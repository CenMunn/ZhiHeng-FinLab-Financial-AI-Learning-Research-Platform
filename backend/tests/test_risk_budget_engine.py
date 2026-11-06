"""Hand-calculated isolated D26 ledger tests; no archived evaluation data."""
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import unittest

from platform_app.experiments.risk_budget import simulate


def fixture(prices, market='crypto', dividends=None):
    start = datetime(2023, 12, 28, tzinfo=timezone.utc)
    bars = []
    for i, price in enumerate(prices):
        day = start + timedelta(days=i)
        close = day.replace(hour=7) if market == 'ashare' else day + timedelta(days=1)
        bars.append(dict(session=day.date().isoformat(), open=str(price), close=str(price),
                         high='999999', low='0.01', volume='0', close_at=close.isoformat(),
                         available_at=(close+timedelta(minutes=1)).isoformat()))
    return dict(symbol='600519' if market == 'ashare' else 'BTCUSDT', market=market,
                bars=bars, dividends=dividends or [])


def observation(data, entry, variance='0.0001', fold='2024Q1'):
    bars = data['bars']; lag = 1 if data['market'] == 'ashare' else 2
    def opened(i):
        return bars[i]['session']+('T01:30:00+00:00' if data['market']=='ashare' else 'T00:00:00+00:00')
    return dict(signal_session=bars[entry-lag]['session'],
                decision_at=bars[entry-lag]['available_at'], entry_session=bars[entry]['session'],
                exit_session=bars[entry+1]['session'], entry_at=opened(entry), exit_at=opened(entry+1),
                fold=fold, raw={k:variance for k in ('train_mean','ewma','lightgbm','dlinear')},
                calibrated={k:variance for k in ('ewma','lightgbm','dlinear')})


class RiskBudgetEngineTests(unittest.TestCase):
    def test_constant_full_cash_boundaries_and_all_dates(self):
        data=fixture([100]*10); obs=[observation(data,i) for i in (4,5,6)]
        run=simulate(data,obs,'hold_full',cost_multiplier=0)
        self.assertEqual(run['metrics']['return'],'0')
        self.assertEqual(run['metrics']['annualized_volatility'],0)
        self.assertEqual([p['session'] for p in run['curve']],[b['session'] for b in data['bars'][4:]])
        self.assertEqual([t['side'] for t in run['trades']],['buy','sell'])
        self.assertEqual(run['curve'][-1]['quantity'],'0')

    def test_jump_open_return_and_sample_volatility(self):
        data=fixture([100]*5+[110]*5); obs=[observation(data,i) for i in (4,5,6)]
        run=simulate(data,obs,'hold_full',cost_multiplier=0)
        self.assertEqual(run['metrics']['return'],'0.1')
        self.assertEqual(run['curve'][1]['net_return'],'0.1')
        self.assertAlmostEqual(run['metrics']['annualized_volatility'], (0.01/5*365)**.5)

    def test_dividends_entitlement_before_entry_exit_and_not_spendable(self):
        data=fixture([100]*10,'ashare',[
            dict(session='2024-01-01',amount='2'),dict(session='2024-01-04',amount='3')])
        run=simulate(data,[observation(data,i) for i in (4,5,6)],'hold_full',cost_multiplier=0)
        self.assertEqual(run['curve'][0]['dividend_receivable'],'0')
        self.assertEqual(run['curve'][3]['dividend_receivable'],'30000')
        self.assertEqual(run['metrics']['final_cash'],'1000000')
        self.assertEqual(run['metrics']['return'],'0.03')

    def test_fees_lots_and_cash_solvency(self):
        data=fixture([100]*10,'ashare')
        run=simulate(data,[observation(data,4)],'hold_full')
        buy,sell=run['trades']
        self.assertEqual(buy['quantity'],'9900')
        self.assertEqual(buy['costs']['commission'],'297')
        self.assertEqual(buy['costs']['transfer'],'9.9')
        self.assertEqual(buy['costs']['slippage'],'198')
        self.assertEqual(sell['costs']['tax'],'495')
        self.assertTrue(all(D(p['cash'])>=0 for p in run['curve']))

    def test_limit_rejection_retries_and_keeps_actual_position(self):
        data=fixture([100]*5+[90,89,89,89,89],'ashare')
        run=simulate(data,[observation(data,4)],'hold_full',cost_multiplier=0)
        self.assertEqual(run['rejections'][0]['reason'],'approximate_limit_open_no_fill')
        self.assertEqual(run['curve'][1]['quantity'],'10000')
        self.assertEqual(run['curve'][2]['quantity'],'0')

    def test_no_lookahead_intraday_or_labels(self):
        data=fixture([100]*10); obs=[observation(data,i) for i in (4,5,6)]
        first=simulate(data,obs,'ewma_raw')
        altered=copy.deepcopy(data)
        for bar in altered['bars']:bar.update(high='NaN',low='NaN',volume='NaN',close='987654321')
        for row in obs:row.update(realized_variance='999999',y='-999')
        second=simulate(altered,obs,'ewma_raw')
        self.assertEqual(first,second)

    def test_fixed_train_mean_and_band(self):
        data=fixture([100]*10); obs=[observation(data,i,'0.0001') for i in (4,5,6)]
        obs[1]['raw']['ewma']='0.000101'
        run=simulate(data,obs,'ewma_raw',cost_multiplier=0)
        self.assertEqual(len(run['trades']),2)
        self.assertAlmostEqual(float(run['curve'][0]['target_weight']),.1/(.0001*365)**.5)
        self.assertEqual(simulate(data,obs,'fixed_risk',cost_multiplier=0)['curve'][0]['target_weight'],run['curve'][0]['target_weight'])

    def test_reject_duplicate_mapping_and_late_source(self):
        data=fixture([100]*10); row=observation(data,4)
        with self.assertRaises(ValueError):simulate(data,[row,row],'hold_full')
        data['bars'][0]['available_at']='2025-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):simulate(data,[row],'hold_full')

    def test_crypto_steps_and_config_validation(self):
        data=fixture([123]*10); data['symbol']='ETHUSDT'
        run=simulate(data,[observation(data,4)],'hold_full')
        self.assertEqual(D(run['trades'][0]['quantity'])%D('.0001'),0)
        for target in ('0','0.31','NaN'):
            with self.assertRaises(ValueError):simulate(data,[],'hold_full',target_volatility=target)
        with self.assertRaises(ValueError):simulate(data,[],'unknown')

    def test_sub_lot_target_is_an_explicit_rejection(self):
        data=fixture([20000]*10,'ashare')
        run=simulate(data,[observation(data,4)],'hold_full')
        self.assertEqual(run['trades'],[])
        self.assertEqual(run['rejections'][0]['reason'],'insufficient_cash_for_step_and_costs')

    def test_twenty_elapsed_returns_and_first_fee_are_not_padded(self):
        data=fixture([100]*30)
        rows=[observation(data,i) for i in range(4,27)]
        run=simulate(data,rows,'hold_full')
        curve=run['curve']
        self.assertIsNone(curve[0]['net_return'])
        self.assertEqual(run['metrics']['return_periods'],len(curve)-1)
        self.assertLess(D(curve[1]['net_return']),0)
        self.assertIsNone(curve[19]['rolling20_volatility'])
        self.assertIsNotNone(curve[20]['rolling20_volatility'])
        self.assertEqual(run['metrics']['worst20'][0]['periods'],20)

    def test_t_plus_one_same_session_exit_is_invalid(self):
        data=fixture([100]*10,'ashare'); row=observation(data,4)
        row['exit_session']=row['entry_session']; row['exit_at']=row['entry_at']
        with self.assertRaises(ValueError):simulate(data,[row],'hold_full')

    def test_calibrated_strategy_consumes_only_selected_forecast(self):
        data=fixture([100]*10); row=observation(data,4)
        row['calibrated']['ewma']='0.01'
        raw=simulate(data,[row],'ewma_raw',cost_multiplier=0)
        cal=simulate(data,[row],'ewma_calibrated',cost_multiplier=0)
        self.assertGreater(D(raw['curve'][0]['quantity']),D(cal['curve'][0]['quantity']))

    def test_minimum_commission_on_small_ex_dividend_exit(self):
        data=fixture([100]*5+[1]*5,'ashare',[dict(session='2024-01-02',amount='99')])
        run=simulate(data,[observation(data,4)],'hold_full')
        self.assertEqual(run['trades'][1]['quantity'],'9900')
        self.assertEqual(run['trades'][1]['costs']['commission'],'5')


if __name__=='__main__':unittest.main()
