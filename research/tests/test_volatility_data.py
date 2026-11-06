import copy
import unittest
from datetime import date,timedelta,datetime,timezone
from types import SimpleNamespace as NS
import numpy as np
from research.volatility.data import make_rows,partition,regime_thresholds,regime_key


def fixture():
    bars=[]
    for i in range(150):
        day=date(2023,11,1)+timedelta(days=i)
        close_at=datetime.combine(day,datetime.min.time(),timezone.utc)+timedelta(hours=23,minutes=59)
        bars.append(NS(session=day,close=str(100*np.exp(i*.01)),close_at=close_at,available_at=close_at+timedelta(minutes=1)))
    return NS(snapshot=NS(bars=bars),dividends=[])


class VolatilityDataTests(unittest.TestCase):
    def test_future_edits_cannot_change_known_features_or_state(self):
        d=fixture();rows,history=make_rows(d,5);changed=copy.deepcopy(d)
        changed.snapshot.bars[80].close='900'
        again,_=make_rows(changed,5)
        self.assertEqual(rows[10]['x'],again[10]['x'])
        self.assertAlmostEqual(rows[10]['target'],.0001,places=13)
        self.assertEqual(len(rows[0]['x']),60)
        self.assertEqual(rows[0]['label_end'],str(d.snapshot.bars[65].session))
        self.assertEqual(rows[0]['label_available_at'],d.snapshot.bars[65].available_at.isoformat())
        self.assertAlmostEqual(history[1],.01,places=13)

    def test_purge_targets_crossing_partition_or_late_availability(self):
        rows,_=make_rows(fixture(),5)
        spec={'train':['2023-11-01','2024-01-15'],'validation':['2024-01-16','2024-02-15'],'evaluation':['2024-02-16','2024-03-28']}
        parts,purged=partition(rows,spec)
        self.assertEqual(purged['train'],5)
        for key,items in parts.items():
            self.assertTrue(all(r['label_end']<=spec[key][1] for r in items))
        late=copy.deepcopy(rows);late[0]['label_available_at']='2025-01-01T00:00:00+00:00'
        p2,_=partition(late,spec);self.assertEqual(len(p2['train']),len(parts['train'])-1)

    def test_regimes_train_only_and_ties_deterministic(self):
        x=np.array([[.01]*60,[.02]*60,[.03]*60]);thresholds=regime_thresholds(x)
        self.assertEqual(regime_key(x[0],thresholds),'low_up')
        self.assertEqual(regime_key(-x[2],thresholds),'high_down')
        self.assertEqual(regime_thresholds(np.zeros((3,60))),[0.,0.])
        self.assertEqual(regime_key(np.zeros(60),[0.,0.]),'low_up')

    def test_late_input_and_dividend_adjustment(self):
        d=fixture();d.dividends=[NS(session=d.snapshot.bars[61].session,amount='1')]
        rows,history=make_rows(d,1)
        self.assertGreater(rows[0]['target'],.0001)
        d.snapshot.bars[60].available_at=d.snapshot.bars[70].available_at
        rows,_=make_rows(d,1)
        self.assertTrue(all(r['history_index']!=60 for r in rows))

    def test_invalid_horizon_and_missing_prices(self):
        with self.assertRaises(ValueError):make_rows(fixture(),2)
        d=fixture();d.snapshot.bars[30].close=None
        with self.assertRaises(ValueError):make_rows(d,1)

    def test_recursive_models_require_all_prefix_data_available(self):
        d=fixture();d.snapshot.bars[1].available_at=d.snapshot.bars[-1].available_at+timedelta(days=1)
        rows,_=make_rows(d,1)
        self.assertEqual(rows,[])

