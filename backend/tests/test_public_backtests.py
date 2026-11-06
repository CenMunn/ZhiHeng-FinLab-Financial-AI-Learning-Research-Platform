from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io, json, unittest, zipfile


class PublicSourceTests(unittest.TestCase):
    def test_dividend_date_uses_exchange_timezone(self):
        from platform_app.adapters.public_market import parse_yahoo_dividends
        stamp=int(datetime(2024,1,1,16,tzinfo=timezone.utc).timestamp())
        body={'chart':{'result':[{'meta':{'symbol':'600519.SS','currency':'CNY','exchangeTimezoneName':'Asia/Shanghai'},
              'events':{'dividends':{'1':{'date':stamp,'amount':1}}}}]}}
        self.assertEqual(parse_yahoo_dividends(json.dumps(body).encode(),(date(2024,1,2),))[0].session,date(2024,1,2))

    def test_tencent_raw_prices_and_volume_units(self):
        from platform_app.adapters.public_market import parse_tencent_chart
        raw=json.dumps({'code':0,'data':{'sh600519':{'day':[['2024-01-02','10.000','10.500','11.000','9.000','123.000']]}}}).encode()
        bars=parse_tencent_chart(raw,(date(2024,1,2),))
        self.assertEqual(bars[0].volume,'12300')
        self.assertEqual(bars[0].close,'10.5')
        with self.assertRaises(ValueError):parse_tencent_chart(raw,(date(2024,1,3),))

    def test_binance_millisecond_and_microsecond_are_same_sessions(self):
        from platform_app.adapters.public_market import parse_binance_zip
        def archive(stamp, end):
            output=io.BytesIO()
            with zipfile.ZipFile(output,'w') as z:z.writestr('data.csv',f'{stamp},10,12,9,11,50,{end},0,1,0,0,0\n')
            return output.getvalue()
        old=parse_binance_zip(archive(1704067200000,1704153599999))
        new=parse_binance_zip(archive(1735689600000000,1735775999999999))
        self.assertEqual(old[0].session,date(2024,1,1))
        self.assertEqual(new[0].session,date(2025,1,1))
        self.assertEqual(new[0].close_at,datetime(2025,1,2,tzinfo=timezone.utc))

    def test_calendar_uses_explicit_holidays_and_preserves_covid_closure(self):
        from platform_app.adapters.public_market import parse_xshg_calendar
        text='precomputed_shanghai_holidays = pd.to_datetime(["2020-01-31", "2020-01-30"])'
        result=parse_xshg_calendar(text,date(2020,1,30),date(2020,2,3))
        self.assertEqual(result,(date(2020,2,3),))
        with self.assertRaises(ValueError):parse_xshg_calendar('import os',date(2020,1,1),date(2020,1,3))

    def test_missing_quote_and_duplicate_and_split_fail_closed(self):
        from platform_app.adapters.public_market import parse_yahoo_chart
        body={'chart':{'error':None,'result':[{'meta':{'symbol':'600519.SS','currency':'CNY','exchangeTimezoneName':'Asia/Shanghai'},'timestamp':[1704159000],
              'indicators':{'quote':[{'open':[10],'high':[11],'low':[9],'close':[10],'volume':[100]}]},'events':{}}]}}
        calendar=(date(2024,1,2),)
        bars,dividends=parse_yahoo_chart(json.dumps(body).encode(),calendar)
        self.assertEqual(bars[0].open,'10');self.assertEqual(dividends,())
        for mutate in [lambda d:d['chart']['result'][0]['timestamp'].append(1704159000),
                       lambda d:d['chart']['result'][0]['indicators']['quote'][0]['close'].__setitem__(0,None),
                       lambda d:d['chart']['result'][0].update(events={'splits':{'1':{'date':1704159000}}})]:
            changed=deepcopy(body);mutate(changed)
            with self.assertRaises(ValueError):parse_yahoo_chart(json.dumps(changed).encode(),calendar)
        with self.assertRaises(ValueError):parse_yahoo_chart(json.dumps(body).encode(),calendar+(date(2024,1,3),))

    def test_wolf_cycle_boundaries_and_two_directions(self):
        from platform_app.experiments.backtest import cycle_position
        self.assertEqual(cycle_position(840000)['index'],'0.5')
        self.assertEqual(cycle_position(918750)['index'],'1')
        self.assertEqual(cycle_position(971250)['index'],'0')
        self.assertEqual(cycle_position(918750)['phase'],'falling')
        self.assertEqual(cycle_position(971250)['phase'],'rising')
        self.assertEqual(cycle_position(855750)['index'],cycle_position(939750)['index'])


def fixture(market='ashare'):
    from platform_app.experiments.samples import sample_snapshots
    from platform_app.contracts.public_backtests import PublicDataset
    body=sample_snapshots()[0 if market=='ashare' else 1].model_dump(mode='json')
    body.update(source_kind='public',calendar_kind='venue',source_uri='https://example.org/fixture',calendar_source='Explicit test sessions')
    body['snapshot_id']='fixture-'+market
    # Stable small prices allow independent cash arithmetic and avoid limit-up artifacts.
    for i,b in enumerate(body['bars']):
        for k in ('open','high','low','close'):b[k]=str(10+i//3)
    blocks=[]
    if market=='btc':
        for b in body['bars']:
            close=datetime.fromisoformat(b['close_at'].replace('Z','+00:00'))
            blocks.append({'session':b['session'],'observed_at':(close-timedelta(hours=1)).isoformat(),
                'block_at':(close-timedelta(hours=2)).isoformat(),'height':840000,'block_hash':'a'*64})
    return PublicDataset.model_validate({'snapshot':body,'receipts':[{'url':'https://example.org/fixture','retrieved_at':'2026-10-30T00:00:00Z','sha256':'b'*64,'file':'raw/test'}],
        'blocks':blocks,'timing_assumption':'fixture','quality':{}})


def configuration(dataset,**changes):
    from platform_app.contracts.public_backtests import BacktestConfig
    base={'start':str(dataset.snapshot.sessions[5]),'end':str(dataset.snapshot.sessions[-1]),'window':3,'initial_cash':'10000',
          'costs':{'commission_bps':'0','minimum_commission':'0','sell_tax_bps':'0','transfer_bps':'0','slippage_bps':'0'}}
    base.update(changes)
    return BacktestConfig.model_validate(base)


class BacktestEngineTests(unittest.TestCase):
    def test_engine_fingerprint_includes_acquisition_code(self):
        from platform_app.experiments.backtest import ENGINE_SOURCES
        self.assertIn('acquisition/fetch_public_market_data.py',ENGINE_SOURCES)

    def test_buy_hold_exact_cash_lot_and_wealth(self):
        from platform_app.experiments.backtest import compare
        data=fixture();result=compare(data,configuration(data));run=result['strategies']['buy_hold']
        self.assertEqual(run['trades'][0]['quantity'],'900') # 10000 / 11, rounded down to 100-share lot
        self.assertEqual(run['curve'][0]['cash'],'100')
        self.assertEqual(run['curve'][-1]['equity'],'12700') # 100 + 900*14
        self.assertEqual(run['metrics']['return'],'0.27')
        self.assertEqual(run['metrics']['max_drawdown'],'0')

    def test_all_trades_follow_signal_and_btc_cannot_fill_at_same_boundary(self):
        from platform_app.experiments.backtest import compare
        for market in ('ashare','btc'):
            data=fixture(market);result=compare(data,configuration(data))
            trade=result['strategies']['trend']['trades'][0]
            self.assertLess(datetime.fromisoformat(trade['decision_at']),datetime.fromisoformat(trade['fill_at']))
            fill=date.fromisoformat(trade['session']);signal=date.fromisoformat(trade['signal_session'])
            self.assertGreaterEqual(data.snapshot.sessions.index(fill)-data.snapshot.sessions.index(signal),2 if market=='btc' else 1)

    def test_future_prices_never_change_past_trades_or_curves(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture('btc');config=configuration(data);a=compare(data,config)
        changed=data.model_dump(mode='json')
        for k in ('open','high','low','close'):changed['snapshot']['bars'][-1][k]='100'
        b=compare(PublicDataset.model_validate(changed),config)
        for key in a['strategies']:
            self.assertEqual(a['strategies'][key]['curve'][:-1],b['strategies'][key]['curve'][:-1])
            self.assertEqual([t for t in a['strategies'][key]['trades'] if t['session']<str(data.snapshot.sessions[-1])],
                             [t for t in b['strategies'][key]['trades'] if t['session']<str(data.snapshot.sessions[-1])])

    def test_future_dividend_never_back_adjusts_earlier_signals(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture();config=configuration(data);a=compare(data,config)
        body=data.model_dump(mode='json');body['dividends']=[{'session':str(data.snapshot.sessions[-1]),'amount':'1'}]
        b=compare(PublicDataset.model_validate(body),config)
        self.assertEqual(a['strategies']['trend']['curve'][:-1],b['strategies']['trend']['curve'][:-1])

    def test_a_share_sell_follows_next_session_and_applies_sell_only_tax(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture();body=data.model_dump(mode='json')
        for b in body['snapshot']['bars'][6:]:
            for key in ('open','high','low','close'):b[key]='10'
        data=PublicDataset.model_validate(body)
        config=configuration(data,costs={'commission_bps':'3','minimum_commission':'5','sell_tax_bps':'5','transfer_bps':'0.1','slippage_bps':'2'})
        run=compare(data,config)['strategies']['trend'];buy,sell=run['trades'][:2]
        self.assertGreater(sell['session'],buy['session']);self.assertEqual(buy['costs']['tax'],'0')
        self.assertEqual(sell['costs']['tax'],'4.5');self.assertEqual(sell['costs']['total'],'11.39')
        self.assertEqual(run['curve'][1]['cash'],'9081.531')

    def test_halted_unknown_prices_stop_without_forward_fill(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture();body=data.model_dump(mode='json')
        body['snapshot']['bars'][7].update(status='halted',open=None,high=None,low=None,close=None,volume='0')
        with self.assertRaisesRegex(ValueError,'未知价格'):compare(PublicDataset.model_validate(body),configuration(data))

    def test_fee_deduction_and_insufficient_cash_are_not_free_fills(self):
        from platform_app.experiments.backtest import compare
        data=fixture();config=configuration(data,costs={'commission_bps':'3','minimum_commission':'5','sell_tax_bps':'5','transfer_bps':'0.1','slippage_bps':'2'})
        run=compare(data,config)['strategies']['buy_hold']
        self.assertEqual(run['trades'][0]['costs']['total'],'7.079')
        self.assertEqual(run['curve'][0]['cash'],'92.921')
        empty=compare(data,configuration(data,initial_cash='100'))['strategies']['buy_hold']
        self.assertEqual(empty['trades'],[]);self.assertTrue(empty['rejections'])

    def test_ex_dividend_entitlement_before_open_is_receivable_not_cash(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture();body=data.model_dump(mode='json');body['dividends']=[{'session':str(data.snapshot.sessions[7]),'amount':'1'}]
        result=compare(PublicDataset.model_validate(body),configuration(data))['strategies']['buy_hold']
        self.assertEqual(result['curve'][2]['dividend_receivable'],'900')
        self.assertEqual(result['curve'][2]['cash'],'100')
        self.assertEqual(result['metrics']['dividend_receivable'],'900')
        # Someone buying on the ex-date must not receive that distribution.
        late=compare(PublicDataset.model_validate(body),configuration(data,start=str(data.snapshot.sessions[7])))['strategies']['buy_hold']
        self.assertEqual(late['metrics']['dividend_receivable'],'0')

    def test_flat_prices_fees_cause_drawdown_and_t1_sell_after_buy(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture();body=data.model_dump(mode='json')
        for b in body['snapshot']['bars']:
            for k in ('open','high','low','close'):b[k]='10'
        config=configuration(data,costs={'commission_bps':'0','minimum_commission':'5','sell_tax_bps':'0','transfer_bps':'0','slippage_bps':'0'})
        run=compare(PublicDataset.model_validate(body),config)['strategies']['buy_hold']
        self.assertEqual(run['metrics']['return'],'-0.0005');self.assertEqual(run['metrics']['max_drawdown'],'0.0005')
        self.assertEqual(run['trades'][0]['quantity'],'900')

    def test_future_block_and_missing_cycle_coverage_rejected(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        from pydantic import ValidationError
        data=fixture('btc');body=data.model_dump(mode='json');body['blocks'][0]['block_at']='2099-01-01T00:00:00Z'
        with self.assertRaises(ValidationError):PublicDataset.model_validate(body)
        body=data.model_dump(mode='json');body['blocks']=[]
        with self.assertRaises(ValueError):compare(PublicDataset.model_validate(body),configuration(data))

    def test_parameters_and_market_invalid_fee_and_short_window_rejected(self):
        from platform_app.experiments.backtest import compare
        data=fixture('btc')
        with self.assertRaises(ValueError):compare(data,configuration(data,start=str(data.snapshot.sessions[0])))
        with self.assertRaises(ValueError):compare(data,configuration(data,costs={'sell_tax_bps':'5'}))

    def test_zero_wealth_preserves_total_loss_and_undefined_later_year(self):
        from platform_app.experiments.backtest import compare
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture('btc');body=data.model_dump(mode='json')
        # 45 days spanning a year: buy 50 units for 50 + 50 fee, then sell 50 for 50 fee.
        first=date(2025,12,1);bars=[];blocks=[]
        for i in range(45):
            day=first+timedelta(days=i);close=datetime.combine(day+timedelta(days=1),datetime.min.time(),timezone.utc)
            bars.append({'session':str(day),'close_at':close.isoformat(),'available_at':(close+timedelta(minutes=1)).isoformat(),
                         'open':'1','high':'1','low':'1','close':'1','volume':'1000'})
            blocks.append({'session':str(day),'observed_at':(close-timedelta(hours=1)).isoformat(),'block_at':(close-timedelta(hours=2)).isoformat(),
                           'height':840000 if i<6 else 918750,'block_hash':'a'*64})
        body['snapshot'].update(sessions=[b['session'] for b in bars],bars=bars,quantity_step='1');body['blocks']=blocks
        data=PublicDataset.model_validate(body)
        config=configuration(data,start=str(first+timedelta(days=5)),end=str(first+timedelta(days=44)),initial_cash='100',
            costs={'commission_bps':'0','minimum_commission':'50','sell_tax_bps':'0','transfer_bps':'0','slippage_bps':'0'})
        run=compare(data,config)['strategies']['halving_cycle']
        self.assertEqual(run['metrics']['return'],'-1');self.assertEqual(run['metrics']['max_drawdown'],'1')
        self.assertEqual(run['annual'][-1]['return'],None)
        self.assertGreater(run['undefined_relative_windows'],0)

    def test_btc_unaffordable_minimum_commission_has_bounded_cost_search(self):
        from unittest.mock import patch
        from platform_app.experiments import backtest
        data=fixture('btc');config=configuration(data,costs={'commission_bps':'0','minimum_commission':'1000000','sell_tax_bps':'0','transfer_bps':'0','slippage_bps':'0'})
        real=backtest.estimate_costs;calls=0
        def bounded(*args):
            nonlocal calls
            calls+=1
            if calls>200:raise AssertionError('费用计算次数超过有界预算')
            return real(*args)
        with patch.object(backtest,'estimate_costs',side_effect=bounded) as observed:
            result=backtest.compare(data,config)
        self.assertLess(observed.call_count,100)
        self.assertTrue(all(not s['trades'] for s in result['strategies'].values()))


if __name__=='__main__':unittest.main()
