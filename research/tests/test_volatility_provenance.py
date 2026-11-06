import json,tempfile,unittest
from pathlib import Path
from research.volatility.common import file_sha,write_json
from research.volatility.provenance import seal_inputs,check_inputs,seal_fold,check_fold,reject_partial

class ProvenanceTests(unittest.TestCase):
    def test_input_and_predictions_cannot_be_reblessed_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'a/h1/Q';folder.mkdir(parents=True)
            write_json(root/'protocol.json',{'x':1});write_json(folder/'preparation.json',{'x':1})
            write_json(root/'a/dataset.json',{'x':1});write_json(root/'a/h1/history.json',[1])
            seal_inputs(root);check_inputs(root)
            write_json(folder/'predictions.json',{'p':[1]});write_json(folder/'training.json',{'models':{},'artifacts':{},'preparation_sha256':file_sha(folder/'preparation.json')})
            seal_fold(root,folder);check_fold(root,folder)
            (folder/'predictions.json').write_text('{}')
            with self.assertRaises(ValueError):check_fold(root,folder)
            (root/'a/h1/history.json').write_text('[2]')
            with self.assertRaises(ValueError):check_inputs(root)

    def test_incomplete_fold_rejected_and_input_manifest_immutable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write_json(root/'protocol.json',{'x':1});seal_inputs(root)
            with self.assertRaises(ValueError):check_fold(root,root/'missing')
            (root/'protocol.json').write_text('{}')
            with self.assertRaises(ValueError):seal_inputs(root)

    def test_partial_fold_requires_new_attempt_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);reject_partial(folder)
            write_json(folder/'models/train_mean.json',{'mean':1})
            with self.assertRaisesRegex(ValueError,'--attempt'):reject_partial(folder)
            self.assertEqual(json.loads((folder/'models/train_mean.json').read_text()),{'mean':1})
