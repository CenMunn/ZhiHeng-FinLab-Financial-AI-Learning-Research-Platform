import tempfile
import unittest
from pathlib import Path
import numpy as np


class FiveAssetTrainingTests(unittest.TestCase):
    def test_calibration_uses_independent_labels_and_clips(self):
        from research.five_asset.train import calibrate
        result = calibrate([1., 2.], [10., 20.], [3., 4.])
        self.assertEqual(result['raw_c'], 10.)
        self.assertEqual(result['c'], 4.)
        self.assertEqual(result['calibrated'], [12., 16.])
        self.assertEqual(result['calibration_raw'], [1., 2.])
        with self.assertRaises(ValueError):
            calibrate([1.], [-1.], [2.])
        self.assertEqual(calibrate([1.],[0.],[1e-10])['calibrated'],[1e-10])

    def test_features_must_match_causal_history(self):
        from research.five_asset.train import validate_features
        history = np.arange(100, dtype=float)/1000
        x = np.stack([history[1:61], history[2:62]])
        validate_features(x, [60, 61], history)
        with self.assertRaises(ValueError):
            validate_features(x, [61, 62], history)

    def test_manifest_rejects_tampering_and_escape(self):
        from research.five_asset.common import verify
        from research.market.common import file_sha
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); p=root/'x.json';p.write_text('{}')
            manifest={'x.json':file_sha(p)}
            verify(root, manifest)
            p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):verify(root, manifest)
            with self.assertRaises(ValueError):verify(root, {'../x': '0'*64})

    def test_loader_refuses_evaluation_labels(self):
        from research.five_asset.pipeline import load_role
        with self.assertRaises(ValueError):load_role(Path('.'), 'evaluation_labels')

    def test_calibration_features_do_not_parse_label_value(self):
        from research.five_asset.pipeline import calibration_features
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/'calibration.json'
            p.write_text('{"rows": [], "x": [], "y": UNPARSEABLE_LABELS}',encoding='utf8')
            self.assertEqual(calibration_features(Path(temporary)),{'rows':[],'x':[]})

    def test_completed_unit_requires_input_file_sha_and_checks_every_artifact(self):
        from research.five_asset.pipeline import run_unit
        from research.market.common import write_json,file_sha
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);write_json(root/'inputs.json',{'files':{}})
            folder=root/'BTCUSDT'/'2024Q1'/'h1';write_json(folder/'receipt.json',{'updates':1})
            write_json(folder/'completed.json',{'inputs_sha256':file_sha(root/'inputs.json'),'files':{'receipt.json':file_sha(folder/'receipt.json')}})
            run_unit(root,'BTCUSDT','2024Q1',1)
            (folder/'receipt.json').write_text('{}')
            with self.assertRaises(ValueError):run_unit(root,'BTCUSDT','2024Q1',1)

    def test_source_archive_retains_exact_bytes_and_rejects_changed_source(self):
        from research.five_asset.common import archive_sources
        from research.market.common import PROJECT,file_sha
        source='research/five_asset/train.py'
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            manifest=archive_sources(root,{source:file_sha(PROJECT/source)})
            self.assertEqual((root/'source-code'/source).read_bytes(),(PROJECT/source).read_bytes())
            self.assertEqual(manifest['source-code/'+source],file_sha(PROJECT/source))
            with self.assertRaises(ValueError):archive_sources(root,{source:'0'*64})

if __name__=='__main__':unittest.main()
