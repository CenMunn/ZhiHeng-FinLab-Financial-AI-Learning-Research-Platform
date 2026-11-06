import json
from pathlib import Path
import tempfile
import unittest
import numpy as np


class MarketForecastTests(unittest.TestCase):
    def test_standalone_scoring_normalizes_documented_relative_artifact_root(self):
        from unittest.mock import patch
        from research.market.publish import score_publish
        with patch('research.market.publish.score_market',side_effect=RuntimeError('stop before scoring')) as score:
            with self.assertRaisesRegex(RuntimeError,'stop before scoring'):score_publish(Path('research/artifacts/market-forecast/fixture'))
            self.assertTrue(score.call_args.args[0].is_absolute())

    def test_lightgbm_round_trip_supports_chinese_workspace_path(self):
        import lightgbm as lgb
        from research.market.models import save_lightgbm,load_lightgbm
        x=np.arange(80,dtype=float).reshape(40,2);y=x[:,0]*.1
        model=lgb.train({'objective':'regression','num_threads':1,'verbosity':-1,'min_data_in_leaf':2},lgb.Dataset(x,label=y),num_boost_round=2)
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'中文目录'/'模型.txt';save_lightgbm(model,target)
            np.testing.assert_allclose(model.predict(x),load_lightgbm(target).predict(x))
            with self.assertRaises(ValueError):save_lightgbm(model,target)

    def test_scaler_fit_does_not_consume_validation_and_ridge_recovers_linear_signal(self):
        from research.market.models import fit_scaler,standardize,ridge_fit,ridge_predict
        x=np.array([[0.,1.],[1.,2.],[2.,3.],[3.,4.]])
        y=x[:,0]*2+1
        scaler=fit_scaler(x,y)
        self.assertAlmostEqual(scaler['x_mean'],2.)
        self.assertEqual(scaler,fit_scaler(x.copy(),y.copy()))
        fit=ridge_fit(x,y,alpha=0)
        np.testing.assert_allclose(ridge_predict(fit,x),y,atol=1e-8)
        self.assertTrue(np.isfinite(standardize(np.ones((3,2)),fit_scaler(np.ones((3,2)),np.ones(3)))).all())

    def test_dlinear_decomposition_reconstructs_input_and_real_gradient_updates(self):
        import torch
        from research.market.models import DLinear
        torch.manual_seed(42);model=DLinear(60,25)
        x=torch.randn(8,60);target=torch.randn(8);trend,residual=model.decompose(x)
        torch.testing.assert_close(trend+residual,x)
        self.assertEqual(tuple(model(x).shape),(8,))
        before={k:v.detach().clone() for k,v in model.state_dict().items()}
        optimizer=torch.optim.AdamW(model.parameters(),lr=.001)
        loss=(model(x)-target).square().mean();loss.backward();optimizer.step()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in model.parameters()))
        self.assertTrue(any(not torch.equal(v,before[k]) for k,v in model.state_dict().items()))

    def test_errors_zero_baseline_direction_and_constant_correlation(self):
        from research.market.evaluate import metrics,paired_block_interval
        y=np.array([-.01,.02,0.]);zero=np.zeros(3);perfect=y.copy()
        m=metrics(y,perfect);self.assertEqual(m['rmse'],0);self.assertEqual(m['direction_accuracy'],1)
        z=metrics(y,zero);self.assertEqual(z['mse_skill_vs_zero'],0);self.assertEqual(z['direction_accuracy'],0)
        self.assertIsNone(z['temporal_correlation'])
        ci=paired_block_interval(y,perfect,block_length=2,resamples=100,seed=42)
        self.assertLess(ci['high'],0)
        with self.assertRaises(ValueError):metrics(y,np.array([0.,float('nan'),0.]))

    def test_training_loader_cannot_open_evaluation_labels(self):
        from research.market.common import load_split,write_json,file_sha
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write_json(root/'train.json',{'x':[[1,2]],'y':[3]})
            manifest={'files':{'train.json':file_sha(root/'train.json')}}
            self.assertEqual(load_split(root,manifest,'train')['y'],[3])
            with self.assertRaises(ValueError):load_split(root,manifest,'evaluation_labels')
            (root/'train.json').write_text('changed')
            with self.assertRaises(ValueError):load_split(root,manifest,'train')


if __name__=='__main__':unittest.main()
