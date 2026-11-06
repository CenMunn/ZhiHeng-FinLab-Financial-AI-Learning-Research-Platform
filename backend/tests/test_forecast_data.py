from copy import deepcopy
from datetime import date
from decimal import Decimal
import unittest
from test_public_backtests import fixture


class ForecastDataTests(unittest.TestCase):
    def test_executable_return_and_market_delay(self):
        from platform_app.experiments.forecast_data import make_samples
        for market,lag in [('ashare',1),('btc',2)]:
            data=fixture(market);rows=make_samples(data,lookback=3)
            row=rows[0];bars=data.snapshot.bars;i=data.snapshot.sessions.index(date.fromisoformat(row['signal_session']))
            self.assertEqual(row['entry_session'],str(bars[i+lag].session))
            self.assertEqual(row['exit_session'],str(bars[i+lag+1].session))
            self.assertEqual(Decimal(row['target']),Decimal(bars[i+lag+1].open)/Decimal(bars[i+lag].open)-1)
            self.assertLess(row['decision_at'],row['entry_at']);self.assertEqual(len(row['x']),3)

    def test_future_prices_and_dividends_never_change_previous_inputs(self):
        from platform_app.experiments.forecast_data import make_samples
        from platform_app.contracts.public_backtests import PublicDataset
        data=fixture();a=make_samples(data,lookback=3);body=data.model_dump(mode='json')
        for key in ('open','high','low','close'):body['snapshot']['bars'][-1][key]='100'
        body['dividends']=[{'session':str(data.snapshot.sessions[-1]),'amount':'1'}]
        b=make_samples(PublicDataset.model_validate(body),lookback=3)
        for left,right in zip(a,b):self.assertEqual(left['x'],right['x'])

    def test_partition_purges_exit_crossing_boundary(self):
        from platform_app.experiments.forecast_data import split_samples
        rows=[{'signal_session':'2021-12-29','entry_session':'2021-12-30','exit_session':'2021-12-31'},
              {'signal_session':'2021-12-30','entry_session':'2021-12-31','exit_session':'2022-01-04'},
              {'signal_session':'2022-01-04','entry_session':'2022-01-05','exit_session':'2022-01-06'}]
        splits,removed=split_samples(rows)
        self.assertEqual(len(splits['train']),1);self.assertEqual(len(splits['validation']),1)
        self.assertEqual(removed['train'],1);self.assertFalse(splits['evaluation'])

    def test_prediction_policy_requires_complete_targets_and_matches_decision_time(self):
        from platform_app.experiments.backtest import signals,simulate
        from test_public_backtests import configuration
        data=fixture('btc');config=configuration(data);rows=signals(data,config);indices=list(range(5,len(data.snapshot.bars)))
        targets={rows[i-2]['session']:{'target':1 if i<len(data.snapshot.bars)-1 else 0,'decision_at':rows[i-2]['decision_at']} for i in indices}
        result=simulate(data,config,rows,indices,'forecast',targets=targets)
        self.assertEqual(result['metrics']['final_quantity'],'0')
        self.assertEqual(len(result['trades']),2)
        targets.pop(rows[4]['session'])
        with self.assertRaises(ValueError):simulate(data,config,rows,indices,'forecast',targets=targets)


if __name__=='__main__':unittest.main()
