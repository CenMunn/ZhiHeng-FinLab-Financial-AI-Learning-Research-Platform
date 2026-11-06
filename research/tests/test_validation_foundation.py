import unittest
import tempfile,json
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from research.validation_foundation.protocol import folds,partition
from research.validation_foundation.qualify import inspect_dataset,samples

def dataset():
    bars=[]
    for i in range(200):
        d=date(2023,9,1)+timedelta(days=i);close=datetime.combine(d+timedelta(days=1),datetime.min.time(),timezone.utc)
        bars.append(dict(session=str(d),open='100',high='102',low='99',close='101',volume='10',close_at=close.isoformat(),available_at=(close+timedelta(minutes=1)).isoformat()))
    return dict(market='crypto',bars=bars,expected_sessions=[b['session'] for b in bars],dividends=[],splits=[])

class ValidationTests(unittest.TestCase):
    def test_sources_required_and_manifest_snapshot_immutable(self):
        from research.validation_foundation.prepare import verify_receipts,snapshot_acquisition
        with self.assertRaises(ValueError):verify_receipts({'receipts':[]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'latest.json';source.write_text('{"assets":[]}')
            snapshot_acquisition(source,root/'run');source.write_text('{"assets":[1]}')
            self.assertEqual(json.loads((root/'run/acquisition.json').read_text()),{'assets':[]})

    def test_preflight_rejects_short_partitions_before_writing(self):
        from research.validation_foundation.prepare import preflight
        with self.assertRaisesRegex(ValueError,'不足20'):preflight(dataset())

    def test_four_segments_and_purged_labels(self):
        f=folds()[0];self.assertEqual(f['bounds']['early_stopping'],['2023-01-01','2023-06-30']);self.assertEqual(f['bounds']['calibration'],['2023-07-01','2023-12-31'])
        rows=samples(dataset(),5);parts,purged=partition(rows,f['bounds'])
        self.assertEqual(purged['calibration'],5)
        self.assertTrue(all(r['label_end']<=f['bounds']['calibration'][1] for r in parts['calibration']))
        self.assertTrue(all(r['signal_session']>'2023-12-31' for r in parts['evaluation']))

    def test_quality_missing_duplicate_ohlc_splits(self):
        d=dataset();self.assertEqual(inspect_dataset(d)['issues'],[])
        d['bars'].pop(10);self.assertTrue(inspect_dataset(d)['issues'])
        d=dataset();d['bars'][0]['high']='1';self.assertTrue(inspect_dataset(d)['issues'])
        d=dataset();d['splits']=[{'session':d['bars'][2]['session'],'ratio':'2'}];self.assertTrue(any('拆股' in e for e in inspect_dataset(d)['issues']))

    def test_prefix_availability_future_edit_and_known_dividends(self):
        d=dataset();r=samples(d,1);known=r[0]['x'];d['bars'][70]['close']='100'
        self.assertEqual(samples(d,1)[0]['x'],known)
        d['bars'][0]['available_at']='2030-01-01T00:00:00+00:00';self.assertEqual(samples(d,1),[])

    def test_label_maturity_purged(self):
        rows=[{'signal_session':'2023-12-20','label_start':'2023-12-21','label_end':'2023-12-25','label_available_at':'2024-01-10T00:00:00+00:00'}]
        parts,purged=partition(rows,folds()[0]['bounds']);self.assertFalse(parts['calibration']);self.assertEqual(purged['calibration'],1)
