from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError
from platform_app.contracts.market_experiments import MarketSnapshot, FoundationConfig, CostAssumptions
from platform_app.experiments.samples import sample_snapshots
from platform_app.experiments.foundation import build_foundation
from platform_app.experiments.data import snapshot_hash
from platform_app.experiments.markets import estimate_costs, valid_buy_quantity, earliest_sell_session


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b=sample_snapshots()
        self.config=FoundationConfig(train_count=8,validation_count=3,window=3,horizon=1,
            as_of=max(bar.available_at for bar in self.a.bars),costs=CostAssumptions())

    def edited(self,snapshot,fn):
        body=snapshot.model_dump(mode='json');fn(body)
        return MarketSnapshot.model_validate(body)

    def test_two_markets_have_stable_content_addressed_snapshots(self):
        self.assertEqual(snapshot_hash(self.a),snapshot_hash(MarketSnapshot.model_validate_json(self.a.model_dump_json())))
        changed=self.edited(self.a,lambda d:d['bars'][0].update(volume='999'))
        self.assertNotEqual(snapshot_hash(self.a),snapshot_hash(changed))
        self.assertEqual(self.a.source_kind,'synthetic');self.assertEqual(self.b.source_kind,'synthetic')
        self.assertTrue(any(day.weekday()==6 for day in self.b.sessions))
        self.assertTrue(all(day.weekday()<5 for day in self.a.sessions))

    def test_engine_manifest_includes_shared_decimal_and_hash_rules(self):
        from platform_app.experiments import foundation
        self.assertIn('contracts/models.py',foundation.ENGINE_SOURCES)

    def test_duplicate_missing_and_unordered_bars_are_rejected(self):
        for mutate in [lambda d:d['bars'].append(d['bars'][0]),lambda d:d['bars'].pop(2),lambda d:d['bars'].reverse()]:
            with self.subTest(mutate=mutate),self.assertRaises(ValidationError):self.edited(self.a,mutate)

    def test_decimal_and_ohlc_and_halt_validation(self):
        for change in [{'close':12.5},{'close':'NaN'},{'low':'999'},{'volume':'-1'},{'status':'halted'}]:
            with self.subTest(change=change),self.assertRaises(ValidationError):
                self.edited(self.a,lambda d:d['bars'][0].update(change))

    def test_timezone_close_time_and_available_time(self):
        for change in [{'close_at':'2026-09-07T15:00:00'},
                       {'available_at':'2026-09-07T00:00:00Z'},
                       {'close_at':'2026-09-07T08:00:00Z'}]:
            with self.subTest(change=change),self.assertRaises(ValidationError):
                self.edited(self.a,lambda d:d['bars'][0].update(change))
        with self.assertRaises(ValidationError):self.edited(self.b,lambda d:d['sessions'].pop(2))
        with self.assertRaises(ValidationError):self.edited(self.a,lambda d:d.update(source_kind='public'))

    def test_features_have_warmup_and_exact_trailing_mean(self):
        run=build_foundation(self.a,self.config)
        self.assertIsNone(run['features'][0]['sma'])
        expected=sum(Decimal(b.close) for b in self.a.bars[:3])/3
        self.assertEqual(Decimal(run['features'][2]['sma']),expected)
        self.assertIsNone(run['features'][2]['volatility'])
        self.assertIsNotNone(run['features'][3]['volatility'])

    def test_future_price_does_not_change_past_features_or_train_scaler(self):
        changed=self.edited(self.a,lambda d:d['bars'][-1].update(open='1000',high='1002',low='999',close='1001'))
        first,second=build_foundation(self.a,self.config),build_foundation(changed,self.config)
        self.assertEqual(first['features'][:-1],second['features'][:-1])
        self.assertEqual(first['scaler'],second['scaler'])
        self.assertNotEqual(first['features'][-1]['return_1d'],second['features'][-1]['return_1d'])

    def test_boundary_labels_are_purged_and_never_part_of_features(self):
        run=build_foundation(self.a,self.config)
        for split in run['splits']:
            labels=run['labels'][split['name']]
            self.assertTrue(all(label['target_session']<=split['end'] for label in labels))
            self.assertEqual(split['purged_count'],1)
        self.assertTrue(all('forward_return' not in row for row in run['features']))
        self.assertEqual(run['scaler']['fit_count'],7)
        self.assertEqual(run['scaler']['fit_end'],str(self.a.sessions[7]))

    def test_late_data_not_used_at_earlier_decisions(self):
        changed=self.edited(self.a,lambda d:d['bars'][1].update(available_at=d['bars'][6]['available_at']))
        run=build_foundation(changed,self.config)
        self.assertIsNone(run['features'][2]['sma'])
        self.assertIsNone(run['features'][2]['return_1d'])
        self.assertIsNotNone(run['features'][6]['sma'])

    def test_halted_unknown_prices_do_not_become_zero_or_carried_forward(self):
        snapshot=self.edited(self.a,lambda d:d['bars'][3].update(status='halted',open=None,high=None,low=None,close=None,volume='0'))
        run=build_foundation(snapshot,self.config)
        self.assertIsNone(run['features'][3]['sma']);self.assertIsNone(run['features'][4]['return_1d'])

    def test_asof_excludes_unavailable_rows_and_requires_nonempty_splits(self):
        config=self.config.model_copy(update={'as_of':self.a.bars[12].available_at})
        run=build_foundation(self.a,config)
        self.assertEqual(run['quality']['eligible_rows'],13)
        self.assertEqual(run['quality']['excluded_as_of'],2)
        with self.assertRaises(ValueError):build_foundation(self.a,self.config.model_copy(update={'train_count':14}))

    def test_cutoff_before_decision_does_not_admit_a_partially_available_bar(self):
        run=build_foundation(self.a,self.config.model_copy(update={'as_of':self.a.bars[12].close_at}))
        self.assertEqual(run['quality']['eligible_rows'],12)

    def test_fees_are_decimal_side_specific_and_zero_notional_is_free(self):
        costs=CostAssumptions(commission_bps='3',minimum_commission='5',sell_tax_bps='5',transfer_bps='0.1',slippage_bps='2')
        buy,sell=estimate_costs('10000','buy',costs),estimate_costs('10000','sell',costs)
        self.assertEqual(Decimal(buy['commission']),Decimal('5'))
        self.assertEqual(Decimal(buy['total']),Decimal('7.1'))
        self.assertEqual(Decimal(sell['total']),Decimal('12.1'))
        self.assertEqual(estimate_costs('0','sell',costs)['total'],'0')
        with self.assertRaises(ValidationError):CostAssumptions(commission_bps=-1)

    def test_market_rules_and_calendar_tplus1_are_distinct(self):
        self.assertFalse(valid_buy_quantity(self.a,'50'));self.assertTrue(valid_buy_quantity(self.a,'100'))
        self.assertTrue(valid_buy_quantity(self.b,'0.002'));self.assertFalse(valid_buy_quantity(self.b,'0.000000001'))
        friday=next(day for day in self.a.sessions[:-1] if day.weekday()==4)
        self.assertEqual(earliest_sell_session(self.a,friday).weekday(),0)
        self.assertIsNone(earliest_sell_session(self.a,self.a.sessions[-1]))
        self.assertEqual(earliest_sell_session(self.b,self.b.sessions[0]),self.b.sessions[0])


if __name__=='__main__':unittest.main()
