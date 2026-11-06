import importlib.util
from research.experiments.ranking import COMMIT
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


class CheckpointTests(unittest.TestCase):
    def fixture(self,root):
        from research.training import run_ranking as runner
        prep=root/'prepared'; (prep/'inference').mkdir(parents=True); (prep/'labels').mkdir()
        (prep/'inference/train.jsonl').write_text('train-input-fixture')
        (prep/'labels/train.jsonl').write_text('train-label-fixture')
        manifest={'schema_version':'m2-preparation-v1','commit':COMMIT,
            'serialization':'finqa-header-aware-v1','test_content_accessed':False,'gold_added_to_inference_candidates':False,
            'outputs_sha256':{name:runner.file_sha(prep/name) for name in ['inference/train.jsonl','labels/train.jsonl']}}
        (prep/'manifest.json').write_text(json.dumps(manifest))
        base=root/'base'; base.mkdir(); (base/'acquisition.json').write_text('fixed-model-fixture')
        checkpoint=root/'checkpoint'; checkpoint.mkdir(); (checkpoint/'model.safetensors').write_bytes(b'fixture')
        (checkpoint/'config.json').write_text('{"hidden_act":"gelu"}')
        config={'preparation':str(prep),'model':str(base),'max_length':256}
        identity={'preparation_manifest_sha256':runner.file_sha(prep/'manifest.json'),
            'train_input_sha256':runner.file_sha(prep/'inference/train.jsonl'),'train_labels_sha256':runner.file_sha(prep/'labels/train.jsonl'),
            'base_model_acquisition_sha256':runner.file_sha(base/'acquisition.json')}
        receipt={'config':config,'checkpoint_sha256':runner.file_sha(checkpoint/'model.safetensors'),
            'training_identity':identity,'checkpoint_files_sha256':{name:runner.file_sha(checkpoint/name) for name in ('config.json','model.safetensors')}}
        (root/'receipt.json').write_text(json.dumps(receipt))
        return runner,config,checkpoint,prep

    def test_prediction_rejects_checkpoint_or_config_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            runner,config,checkpoint,_=self.fixture(Path(directory))
            weights=checkpoint/'model.safetensors'
            self.assertTrue(runner.verify_checkpoint(config,checkpoint))
            weights.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'checkpoint'): runner.verify_checkpoint(config,checkpoint)
            weights.write_bytes(b'fixture')
            with self.assertRaisesRegex(ValueError,'config'): runner.verify_checkpoint({**config,'max_length':128},checkpoint)

    def test_valid_new_preparation_cannot_relabel_an_old_training_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            runner,config,checkpoint,prep=self.fixture(Path(directory))
            self.assertTrue(runner.verify_checkpoint(config,checkpoint))
            (prep/'labels/train.jsonl').write_text('new-valid-label-version')
            manifest=json.loads((prep/'manifest.json').read_text())
            manifest['outputs_sha256']['labels/train.jsonl']=runner.file_sha(prep/'labels/train.jsonl')
            (prep/'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,'provenance'): runner.verify_checkpoint(config,checkpoint)

    def test_model_config_tampering_is_rejected_even_with_identical_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            runner,config,checkpoint,_=self.fixture(Path(directory))
            self.assertTrue(runner.verify_checkpoint(config,checkpoint))
            (checkpoint/'config.json').write_text('{"hidden_act":"relu"}')
            with self.assertRaisesRegex(ValueError,'checkpoint'): runner.verify_checkpoint(config,checkpoint)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Independent training environment required')
class NeuralLossTests(unittest.TestCase):
    def test_bce_and_partial_accumulation_match_single_effective_batch_gradient(self):
        import torch
        from research.training.run_ranking import logits_loss
        torch.manual_seed(42)
        model=torch.nn.Linear(2,1)
        adapter=lambda **batch:SimpleNamespace(logits=model(batch['x']))
        x=torch.tensor([[1.,2.],[-1.,3.],[2.,-2.]])
        y=torch.tensor([1.,0.,1.])
        expected=torch.nn.functional.binary_cross_entropy_with_logits(model(x).reshape(-1),y)
        expected.backward(); full=model.weight.grad.detach().clone(); model.zero_grad()
        observed=0.
        for start in (0,2):
            loss=logits_loss(torch,adapter,{'x':x[start:start+2]},y[start:start+2])/3
            loss.backward(); observed+=loss.item()
        self.assertAlmostEqual(observed,expected.item(),places=6)
        torch.testing.assert_close(model.weight.grad,full)
        self.assertTrue(torch.isfinite(full).all())

    def test_extreme_logits_produce_finite_bce_and_nonzero_backward(self):
        import torch
        from research.training.run_ranking import logits_loss
        logits=torch.tensor([-100.,100.],requires_grad=True)
        loss=logits_loss(torch,lambda **_:SimpleNamespace(logits=logits),{},torch.tensor([1.,0.]))
        loss.backward()
        self.assertTrue(torch.isfinite(loss)); self.assertTrue(torch.isfinite(logits.grad).all())
        self.assertGreater(logits.grad.abs().sum().item(),0)


if __name__=='__main__': unittest.main()
