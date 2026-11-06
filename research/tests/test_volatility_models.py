"""D22 regression tests: target units, causality, dependence, and real updates."""
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np


class VolatilityMetricsTests(unittest.TestCase):
    def test_zero_truth_is_retained_and_floor_and_annualization_are_explicit(self):
        from research.volatility.metrics import metrics, qlike
        result = metrics([0., 4.], [0., 1.], 4)
        self.assertEqual(result['rows'], 2)
        self.assertEqual(result['prediction_floor_count'], 1)
        self.assertAlmostEqual(result['qlike'], (math.log(1e-10) + 4) / 2)
        self.assertAlmostEqual(result['variance_rmse'], math.sqrt((1e-20 + 9) / 2))
        self.assertAlmostEqual(result['volatility_rmse_ann'], math.sqrt((4e-10 + 4) / 2))
        self.assertAlmostEqual(result['calibration_ratio'], (1 + 1e-10) / 4)
        self.assertAlmostEqual(qlike([0.], [2.])[0], math.log(2))
        self.assertEqual(metrics([0.], [1e-10], 252)['prediction_floor_count'], 1)

    def test_invalid_observations_are_rejected_without_dropping_rows(self):
        from research.volatility.metrics import metrics
        for y, p in [([-1.], [1.]), ([1.], [float('nan')]), ([1.], [float('inf')]), ([1., 2.], [1.])]:
            with self.assertRaises(ValueError):
                metrics(y, p, 252)

    def test_blocks_stay_inside_quarters_without_compressing_regimes(self):
        from research.volatility.metrics import _block_indices, paired_comparison
        folds = ['Q1'] * 45 + ['Q2'] * 50
        indices = _block_indices(folds, np.random.default_rng(17), 20)
        self.assertEqual(len(indices), 95)
        self.assertTrue(np.all(indices[:45] < 45))
        self.assertTrue(np.all(indices[45:] >= 45))
        for start, end in [(0, 20), (20, 40), (45, 65), (65, 85)]:
            np.testing.assert_array_equal(np.diff(indices[start:end]), np.ones(end-start-1))
        y = np.linspace(.1, 3, 95)
        p = np.linspace(.5, 2., 95)
        mask = np.arange(95) % 3 == 0
        result = paired_comparison(y, p, p, folds, mask)
        self.assertEqual(result['delta_qlike'], 0)
        self.assertEqual(result['ci_low'], 0)
        self.assertEqual(result['ci_high'], 0)
        self.assertEqual(result['repeats'], 2000)
        self.assertEqual(result['block'], 20)
        self.assertEqual(result['rows'], int(mask.sum()))

    def test_regime_bootstrap_draws_full_series_then_filters(self):
        from research.volatility.metrics import paired_comparison
        # Only one selected row per quarter: the paired constant difference must
        # stay exactly log(2)-1/2, despite draws where neither row occurs.
        y = np.ones(100)
        mask = np.zeros(100, dtype=bool)
        mask[[8, 73]] = True
        result = paired_comparison(y, np.full(100, 2.), y, ['Q1']*50+['Q2']*50, mask)
        self.assertAlmostEqual(result['delta_qlike'], math.log(2)-.5)
        self.assertAlmostEqual(result['ci_low'], math.log(2)-.5)
        self.assertGreater(result['empty_resamples'], 0)


class VolatilityModelTests(unittest.TestCase):
    def test_garch_multistep_is_daily_average_and_uses_current_observation(self):
        from research.volatility.models import garch_forecast
        params = {'omega': .1, 'alpha': .2, 'beta': .5, 'initial_variance': 1.}
        history = [0., 2., 3., 999.]
        # At t=1: sigma²[t+1]=.1+.2*4+.5*1=1.4;
        # E sigma²[t+2]=.1+.7*1.4=1.08.
        np.testing.assert_allclose(garch_forecast(history, [1], params, 1), [1.4])
        np.testing.assert_allclose(garch_forecast(history, [1], params, 2), [1.24])
        np.testing.assert_allclose(garch_forecast(history, [1, 2], params, 1), [1.4, 2.6])
        altered = [0., 2., 3., -99999.]
        np.testing.assert_allclose(garch_forecast(history, [1, 2], params, 5), garch_forecast(altered, [1, 2], params, 5))

    def test_garch_fit_is_stationary_and_reports_real_optimizer_status(self):
        from research.volatility.models import fit_garch
        returns = np.random.default_rng(7).normal(0, .02, 400)
        fit = fit_garch(returns)
        self.assertGreater(fit['omega'], 0)
        self.assertGreaterEqual(fit['alpha'], 0)
        self.assertGreaterEqual(fit['beta'], 0)
        self.assertLess(fit['alpha'] + fit['beta'], 1)
        self.assertTrue(fit['converged'])
        self.assertTrue(math.isfinite(fit['objective']))
        self.assertEqual(fit['observations'], 400)

    def test_garch_optimizer_bound_warnings_are_preserved_in_receipt(self):
        import warnings
        from research.volatility.models import fit_garch
        values = np.random.default_rng(203).normal(0, .02, 320)[1:180]
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter('always')
            result = fit_garch(values)
        self.assertIn('optimizer_warnings', result)
        self.assertTrue(any('outside bounds' in text for text in result['optimizer_warnings']))
        self.assertEqual(emitted, [])

    def test_ewma_incorporates_every_known_return_without_future_values(self):
        from research.volatility.models import ewma_forecast
        np.testing.assert_allclose(ewma_forecast([0., 2., 3., 100.], [1, 2], decay=.5), [4., 6.5])

    def test_har_fits_nonnegative_multiscale_variance_without_future_inputs(self):
        from research.volatility.models import har_features, fit_har, predict_har
        x = np.random.default_rng(7).normal(0, .03, (160, 60))
        feature = har_features(x)
        self.assertEqual(feature.shape, (160, 3))
        np.testing.assert_allclose(feature[:, 0], x[:, -1]**2)
        y = .0002 + .2*feature[:, 0] + .3*feature[:, 1] + .1*feature[:, 2]
        fitted = fit_har(x, y)
        self.assertTrue(np.all(np.asarray(fitted['coefficients']) >= 0))
        np.testing.assert_allclose(predict_har(fitted, x), y, atol=1e-10)

    def test_dlinear_positive_head_reconstructs_input_and_updates_parameters(self):
        import torch
        from research.volatility.models import VolatilityDLinear
        torch.manual_seed(17)
        model = VolatilityDLinear(60, 25)
        x = torch.rand(8, 60)
        trend, residual = model.decompose(x)
        torch.testing.assert_close(trend + residual, x)
        before = [p.detach().clone() for p in model.parameters()]
        optimizer = torch.optim.Adam(model.parameters(), lr=.01)
        prediction = model(x)
        self.assertEqual(tuple(prediction.shape), (8,))
        self.assertTrue(bool((prediction > 0).all()))
        loss = (prediction.log() + torch.ones(8) / prediction).mean()
        loss.backward()
        optimizer.step()
        self.assertTrue(any(not torch.equal(a, b) for a, b in zip(before, model.parameters())))

    def test_gamma_booster_and_dlinear_smoke_save_reload_exact_predictions(self):
        from research.volatility.models import fit_lightgbm, fit_dlinear, predict_dlinear, load_lightgbm
        rng = np.random.default_rng(3)
        x = rng.normal(0, .02, (160, 60))
        y = .0001 + x[:, -1]**2
        y[0] = 0.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '中文模型'
            path.mkdir()
            fitted, receipt = fit_lightgbm(x[:120], y[:120], x[120:], y[120:], path/'lightgbm.txt', rounds=8, patience=3)
            self.assertGreater(receipt['best_iteration'], 0)
            self.assertTrue(np.isfinite(fitted.predict(x[120:]**2/receipt['target_scale'])).all())
            loaded = load_lightgbm(path/'lightgbm.txt')
            np.testing.assert_array_equal(fitted.predict(x[120:]**2/receipt['target_scale']), loaded.predict(x[120:]**2/receipt['target_scale']))
            model, info = fit_dlinear(x[:120], y[:120], x[120:], y[120:], path/'dlinear.pt', seed=17, epochs=2, patience=2, device='cpu')
            self.assertGreater(info['optimizer_steps'], 0)
            self.assertTrue(info['parameters_changed'])
            self.assertGreater(info['gradient_max'], 0)
            np.testing.assert_array_equal(predict_dlinear(model, x[120:], info), predict_dlinear(path/'dlinear.pt', x[120:]))

    def test_fit_boundary_rejects_mismatched_windows_and_unpurged_targets(self):
        from research.volatility.models import fit_models
        history = np.random.default_rng(9).normal(0, .01, 300)
        history[0] = 0.
        indices = [np.arange(60, 180), np.arange(185, 225), np.arange(230, 250)]
        features = [np.stack([history[i-59:i+1] for i in part]) for part in indices]
        labels = [np.array([np.mean(history[i+1:i+6]**2) for i in part]) for part in indices[:2]]
        with tempfile.TemporaryDirectory() as directory:
            kwargs = dict(horizon=5, annualization=252, history_returns=history, train_indices=indices[0], val_indices=indices[1], eval_indices=indices[2], folder=directory)
            changed = features[2].copy()
            changed[0, 0] += 1
            with self.assertRaisesRegex(ValueError, 'causal history'):
                fit_models(features[0], labels[0], features[1], labels[1], changed, **kwargs)
            adjacent = np.arange(181, 221)
            kwargs['val_indices'] = adjacent
            with self.assertRaisesRegex(ValueError, 'overlap'):
                fit_models(features[0], labels[0], np.stack([history[i-59:i+1] for i in adjacent]), labels[1], features[2], **kwargs)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
