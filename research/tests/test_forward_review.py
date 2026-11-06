"""Independent D27 journal checks using deterministic teaching fixtures only."""
import tempfile
import unittest
from pathlib import Path
from research.tests.test_forward_journal import fixture, stamp
from research.forward_market.journal import KEYS, register, record_prediction


class ForwardReviewTests(unittest.TestCase):
    def run_invalid(self, mutate):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            bundle={'symbol':'BTCUSDT','market':'crypto','calibration':{k:2. for k in KEYS}}
            protocol=register(root,bundle,_now=stamp('2026-11-06T01:00:00+00:00'))
            snapshot,predictions=fixture()
            mutate(predictions)
            with self.assertRaises(ValueError):
                record_prediction(root,protocol,snapshot,predictions,_now=stamp('2026-11-07T00:03:00+00:00'))
            self.assertEqual(list(root.rglob('prediction-*.json')),[])

    def test_calibrated_prediction_must_use_frozen_coefficient(self):
        self.run_invalid(lambda p:p['ewma'].update(calibrated=.003))

    def test_dlinear_mean_must_keep_all_three_fixed_seeds(self):
        # Internally consistent calibration is not enough if the ensemble was cherry-picked.
        self.run_invalid(lambda p:p['dlinear'].update(raw=.002,calibrated=.004))


if __name__=='__main__':unittest.main()
