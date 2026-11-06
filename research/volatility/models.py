"""Frozen D22 volatility estimators. No evaluation-label argument or file reads.

GARCH recursion: https://arch.readthedocs.io/en/latest/univariate/forecasting.html
DLinear structure: https://github.com/cure-lab/LTSF-Linear (positive variance adaptation)
LightGBM gamma: https://lightgbm.readthedocs.io/en/v4.6.0/Parameters.html
"""
import hashlib
import json
import math
import os
import platform
import warnings
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize, nnls
from scipy.signal import lfilter
import torch
from torch import nn
from torch.nn import functional as F

from .metrics import PREDICTION_FLOOR, qlike

SEEDS = (17, 42, 2025)
DLINEAR_EPOCHS = 100
DLINEAR_PATIENCE = 12
LIGHTGBM_ROUNDS = 200
LIGHTGBM_PATIENCE = 20
MODEL_NAMES = {'train_mean': '训练段均方', 'hist20': '最近20期均方', 'ewma': 'EWMA 0.94',
               'garch': 'GARCH(1,1)', 'har': 'HAR式多尺度非负回归',
               'lightgbm': 'LightGBM Gamma', 'dlinear': 'DLinear 三种子均值',
               **{f'dlinear_seed_{s}': f'DLinear 种子{s}' for s in SEEDS}}


def _vector(values, name, nonnegative=False):
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 1 or not len(result) or not np.isfinite(result).all():
        raise ValueError(f'{name} must be a nonempty finite vector')
    if nonnegative and (result < 0).any():
        raise ValueError(f'{name} must be nonnegative')
    return result


def _features(values):
    result = np.asarray(values, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != 60 or not np.isfinite(result).all():
        raise ValueError('features must contain 60 finite known log returns per row')
    return result


def _target_scale(y):
    return max(float(_vector(y, 'training targets', True).mean()), PREDICTION_FLOOR)


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def ewma_forecast(history_returns, indices, decay=.94):
    history = _vector(history_returns, 'history returns')
    indices = np.asarray(indices, dtype=int)
    if not 0 < decay < 1 or (indices < 1).any() or (indices >= len(history)).any():
        raise ValueError('invalid EWMA decay or signal indices')
    states = np.empty(len(history))
    states[0] = 0.
    states[1] = history[1]**2
    for t in range(2, int(indices.max())+1):
        states[t] = decay*states[t-1] + (1-decay)*history[t]**2
    return np.maximum(states[indices], PREDICTION_FLOOR)


def _garch_variances(squared, omega, alpha, beta, initial):
    variances = np.empty(len(squared))
    variances[0] = initial
    if len(squared) > 1:
        variances[1:] = lfilter([1.], [1., -beta], omega+alpha*squared[:-1], zi=[beta*initial])[0]
    return variances


def fit_garch(returns):
    """Normal QMLE on chronological unique train-known returns, scaled for stability."""
    values = _vector(returns, 'GARCH training returns')
    scale = float(np.mean(values**2))
    if len(values) < 30 or scale <= 0:
        raise ValueError('GARCH needs at least 30 returns and positive training variance')
    squared = values**2/scale

    def objective(parameters):
        omega, alpha, beta = parameters
        variances = _garch_variances(squared, omega, alpha, beta, 1.)
        if (variances <= 0).any() or not np.isfinite(variances).all():
            return 1e30
        return float(np.mean(np.log(variances)+squared/variances))

    candidates = []
    optimizer_warnings = []
    for start in ((.05, .05, .90), (.1, .15, .75), (.2, .02, .5)):
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter('always', RuntimeWarning)
            fitted = minimize(objective, start, method='SLSQP', bounds=((1e-8, 10.), (0., .999), (0., .999)),
                              constraints=({'type': 'ineq', 'fun': lambda v: .9999-v[1]-v[2]},),
                              options={'maxiter': 500, 'ftol': 1e-10})
        optimizer_warnings.extend(str(item.message) for item in captured)
        candidates.append(fitted)
    valid = [fit for fit in candidates if fit.success and np.isfinite(fit.fun) and fit.x[1]+fit.x[2] < 1 and fit.x[0] > 0]
    if not valid:
        raise RuntimeError('GARCH optimizer failed: '+ '; '.join(str(fit.message) for fit in candidates))
    best = min(valid, key=lambda fit: fit.fun)
    return dict(omega=float(best.x[0]*scale), alpha=float(best.x[1]), beta=float(best.x[2]),
                initial_variance=scale, converged=True, objective=float(best.fun), observations=len(values),
                iterations=int(best.nit), optimizer='scipy SLSQP', distribution='zero-mean Normal QMLE',
                optimizer_warnings=list(dict.fromkeys(optimizer_warnings)),
                scaled_variance=scale, initialization='train return mean square',
                candidates=[dict(success=bool(v.success), objective=float(v.fun), iterations=int(v.nit), message=str(v.message)) for v in candidates])


def garch_forecast(history_returns, indices, parameters, horizon):
    history = _vector(history_returns, 'history returns')
    indices = np.asarray(indices, dtype=int)
    if horizon < 1 or (indices < 1).any() or (indices >= len(history)).any():
        raise ValueError('invalid horizon or signal indices')
    omega, alpha, beta = (float(parameters[k]) for k in ('omega', 'alpha', 'beta'))
    if omega <= 0 or min(alpha, beta) < 0 or alpha+beta >= 1:
        raise ValueError('GARCH parameters must be positive and stationary')
    current = float(parameters['initial_variance'])
    next_variances = np.empty(len(history))
    for t in range(1, int(indices.max())+1):
        current = omega + alpha*history[t]**2 + beta*current
        next_variances[t] = current
    forecast = next_variances[indices].copy()
    total = forecast.copy()
    for _ in range(1, horizon):
        forecast = omega + (alpha+beta)*forecast
        total += forecast
    return np.maximum(total/horizon, PREDICTION_FLOOR)


def har_features(x):
    squared = _features(x)**2
    return np.column_stack([squared[:, -length:].mean(axis=1) for length in (1, 5, 22)])


def fit_har(x, y):
    scale = _target_scale(y)
    features = har_features(x)/scale
    design = np.column_stack([np.ones(len(features)), features])
    coefficients, residual = nnls(design, np.asarray(y)/scale)
    return dict(coefficients=coefficients.tolist(), scale=scale, residual_norm=float(residual),
                windows=[1, 5, 22], estimator='nonnegative least squares including intercept')


def predict_har(model, x):
    features = har_features(x)/model['scale']
    design = np.column_stack([np.ones(len(features)), features])
    return np.maximum(design@np.asarray(model['coefficients'])*model['scale'], PREDICTION_FLOOR)


def load_lightgbm(path):
    import lightgbm as lgb
    return lgb.Booster(model_str=Path(path).read_text(encoding='utf-8'))


def fit_lightgbm(train_x, train_y, val_x, val_y, path, *, rounds=LIGHTGBM_ROUNDS, patience=LIGHTGBM_PATIENCE):
    import lightgbm as lgb
    scale = _target_scale(train_y)
    train = lgb.Dataset(_features(train_x)**2/scale, label=np.maximum(train_y, PREDICTION_FLOOR)/scale)
    # Gamma training requires positive labels; the custom validation metric still
    # sees the original realized zeros. No evaluation label is supplied.
    validation = lgb.Dataset(_features(val_x)**2/scale, label=np.asarray(val_y)/scale, reference=train)
    params = dict(objective='gamma', metric='None', learning_rate=.03, num_leaves=7,
                  max_depth=3, min_data_in_leaf=30, lambda_l2=1., feature_fraction=1.,
                  bagging_fraction=1., verbosity=-1, num_threads=2, deterministic=True,
                  force_col_wise=True, seed=17)
    logs = {}

    def validation_qlike(predictions, dataset):
        return 'qlike', float(qlike(dataset.get_label()*scale, predictions*scale).mean()), False

    booster = lgb.train(params, train, num_boost_round=rounds, valid_sets=[validation], valid_names=['validation'],
                        feval=validation_qlike, callbacks=[lgb.early_stopping(patience, verbose=False), lgb.record_evaluation(logs)])
    path = Path(path)
    with path.open('x', encoding='utf-8') as stream:
        stream.write(booster.model_to_string(num_iteration=booster.best_iteration))
    info = dict(name=MODEL_NAMES['lightgbm'], best_iteration=int(booster.best_iteration),
                target_scale=scale, parameters=params, maximum_rounds=rounds, patience=patience,
                validation_qlike=logs['validation']['qlike'], label_floor_count=int(np.sum(np.asarray(train_y)<PREDICTION_FLOOR)),
                input_transform='60 squared log returns / training target mean', version=lgb.__version__)
    return booster, info


class VolatilityDLinear(nn.Module):
    """Univariate DLinear trend/residual map with a positive softplus variance head."""
    def __init__(self, length=60, kernel=25):
        super().__init__()
        self.kernel = kernel
        self.trend = nn.Linear(length, 1)
        self.residual = nn.Linear(length, 1)
        # Random small weights keep seed runs distinct; initialize near unit scale.
        nn.init.normal_(self.trend.weight, mean=0., std=.01)
        nn.init.normal_(self.residual.weight, mean=0., std=.01)
        nn.init.constant_(self.trend.bias, math.log(math.expm1(1.)))
        nn.init.zeros_(self.residual.bias)

    def decompose(self, x):
        padded = F.pad(x.unsqueeze(1), ((self.kernel-1)//2, (self.kernel-1)//2), mode='replicate')
        trend = F.avg_pool1d(padded, kernel_size=self.kernel, stride=1).squeeze(1)
        return trend, x-trend

    def forward(self, x):
        trend, residual = self.decompose(x)
        return F.softplus(self.trend(trend)+self.residual(residual)).squeeze(-1)+1e-8


def fit_dlinear(train_x, train_y, val_x, val_y, path, *, seed, epochs=DLINEAR_EPOCHS,
                patience=DLINEAR_PATIENCE, device=None):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(2)
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    scale = _target_scale(train_y)
    model = VolatilityDLinear().to(device)
    before = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    train = torch.tensor(_features(train_x)**2/scale, dtype=torch.float32, device=device)
    targets = torch.tensor(np.asarray(train_y)/scale, dtype=torch.float32, device=device)
    validation = torch.tensor(_features(val_x)**2/scale, dtype=torch.float32, device=device)
    valid_y = torch.tensor(np.asarray(val_y)/scale, dtype=torch.float32, device=device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.001, weight_decay=.001)
    generator = torch.Generator(device='cpu').manual_seed(seed)
    best_score = float('inf')
    best_state = None
    best_epoch = 0
    steps = 0
    gradient_max = 0.
    history = []
    floor = PREDICTION_FLOOR/scale
    for epoch in range(1, epochs+1):
        model.train()
        order = torch.randperm(len(train), generator=generator).to(device)
        losses = []
        for indices in order.split(64):
            optimizer.zero_grad(set_to_none=True)
            prediction = model(train[indices]).clamp_min(floor)
            loss = (prediction.log()+targets[indices]/prediction).mean()
            if not bool(torch.isfinite(loss)):
                raise RuntimeError('nonfinite DLinear training QLIKE')
            loss.backward()
            for parameter in model.parameters():
                if parameter.grad is not None:
                    gradient_max = max(gradient_max, float(parameter.grad.abs().max().item()))
            torch.nn.utils.clip_grad_norm_(model.parameters(), 10., error_if_nonfinite=True)
            optimizer.step()
            steps += 1
            losses.append((float(loss.detach().item()), len(indices)))
        model.eval()
        with torch.no_grad():
            prediction = model(validation).clamp_min(floor)
            score = float((prediction.log()+valid_y/prediction).mean().item())
        if not math.isfinite(score):
            raise RuntimeError('nonfinite DLinear validation QLIKE')
        history.append(dict(epoch=epoch, train_qlike=sum(v*n for v, n in losses)/len(train)+math.log(scale), validation_qlike=score+math.log(scale)))
        if score < best_score-1e-7:
            best_score, best_epoch = score, epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        if epoch-best_epoch >= patience:
            break
    if best_state is None:
        raise RuntimeError('DLinear completed without a finite checkpoint')
    changed = any(not torch.equal(before[k], best_state[k]) for k in before)
    if not changed or gradient_max <= 0:
        raise RuntimeError('DLinear did not make a real parameter update')
    model.load_state_dict(best_state)
    info = dict(name=f'DLinear 种子{seed}', seed=seed, target_scale=scale, device=str(device),
                device_name=torch.cuda.get_device_name(0) if str(device).startswith('cuda') else platform.processor(),
                optimizer_steps=steps, best_epoch=best_epoch, epochs_completed=len(history), maximum_epochs=epochs,
                patience=patience, gradient_max=gradient_max, parameters_changed=changed, parameter_count=sum(p.numel() for p in model.parameters()),
                input_transform='60 squared log returns / training target mean', head='softplus positive daily mean square',
                loss='QLIKE', learning_rate=.001, weight_decay=.001, batch_size=64, kernel=25,
                version=str(torch.__version__), history=history)
    with Path(path).open('xb') as stream:
        torch.save({'state_dict': best_state, 'receipt': info}, stream)
    return model, info


def predict_dlinear(model, x, receipt=None):
    if isinstance(model, (str, Path)):
        checkpoint = torch.load(model, map_location='cpu', weights_only=True)
        model = VolatilityDLinear()
        model.load_state_dict(checkpoint['state_dict'])
        receipt = checkpoint['receipt']
    if receipt is None:
        raise ValueError('DLinear inference requires training scale receipt')
    device = next(model.parameters()).device
    model.eval()
    with torch.no_grad():
        prediction = model(torch.tensor(_features(x)**2/receipt['target_scale'], dtype=torch.float32, device=device)).cpu().numpy().astype(np.float64)
    return np.maximum(prediction*receipt['target_scale'], PREDICTION_FLOOR)


def fit_models(train_x, train_y, val_x, val_y, eval_x, *, horizon, annualization,
               history_returns, train_indices, val_indices, eval_indices, folder):
    """Train, freeze artifacts, then infer. Evaluation labels cannot enter this API."""
    if horizon not in (1, 5) or annualization not in (252, 365):
        raise ValueError('D22 allows horizons 1/5 and annualization 252/365')
    train_x, val_x, eval_x = map(_features, (train_x, val_x, eval_x))
    train_y, val_y = _vector(train_y, 'training targets', True), _vector(val_y, 'validation targets', True)
    history_returns = _vector(history_returns, 'history returns')
    partitions = [(train_x, np.asarray(train_indices, dtype=int)), (val_x, np.asarray(val_indices, dtype=int)), (eval_x, np.asarray(eval_indices, dtype=int))]
    for x, indices in partitions:
        if not len(indices) or len(x) != len(indices) or (np.diff(indices) <= 0).any() or indices.min() < 60 or indices.max() >= len(history_returns):
            raise ValueError('causal indices must be ordered, unique, and match feature rows')
        expected = np.stack([history_returns[i-59:i+1] for i in indices])
        if not np.allclose(x, expected, rtol=1e-10, atol=1e-12):
            raise ValueError('features do not match their causal history windows')
    if len(train_x) != len(train_y) or len(val_x) != len(val_y):
        raise ValueError('labels must match their own training or validation features')
    if partitions[0][1].max()+horizon >= partitions[1][1].min() or partitions[1][1].max()+horizon >= partitions[2][1].min():
        raise ValueError('training/validation label horizons overlap a later partition')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    predictions, models, artifacts = {}, {}, {}

    def save_receipt(key, receipt):
        receipt = {'name': MODEL_NAMES[key], **receipt}
        models[key] = receipt
        _write_json(folder/f'{key}.json', receipt)

    def record_prediction(key, validation, evaluation):
        values = {}
        for split, result in [('validation', validation), ('evaluation', evaluation)]:
            result = np.asarray(result, dtype=float)
            if not np.isfinite(result).all() or (result <= 0).any():
                raise RuntimeError(f'{key} emitted nonpositive or nonfinite predictions')
            values[split] = np.maximum(result, PREDICTION_FLOOR).tolist()
        predictions[key] = values

    mean = float(train_y.mean())
    record_prediction('train_mean', np.full(len(val_x), max(mean, PREDICTION_FLOOR)), np.full(len(eval_x), max(mean, PREDICTION_FLOOR)))
    save_receipt('train_mean', {'mean': mean, 'fit_rows': len(train_y)})
    record_prediction('hist20', np.maximum((val_x[:, -20:]**2).mean(axis=1), PREDICTION_FLOOR), np.maximum((eval_x[:, -20:]**2).mean(axis=1), PREDICTION_FLOOR))
    save_receipt('hist20', {'window': 20, 'learned_parameters': 0})
    record_prediction('ewma', ewma_forecast(history_returns, val_indices), ewma_forecast(history_returns, eval_indices))
    save_receipt('ewma', {'decay': .94, 'initialization': 'first observed return square', 'horizon_forecast': 'constant daily variance', 'learned_parameters': 0})
    last_train = int(partitions[0][1].max())
    garch = fit_garch(history_returns[1:last_train+1])
    record_prediction('garch', garch_forecast(history_returns, val_indices, garch, horizon), garch_forecast(history_returns, eval_indices, garch, horizon))
    save_receipt('garch', {**garch, 'training_return_indices': [1, last_train], 'forecast': 'analytic average of next h daily conditional variances', 'scipy_version': scipy.__version__})
    har = fit_har(train_x, train_y)
    record_prediction('har', predict_har(har, val_x), predict_har(har, eval_x))
    save_receipt('har', har)
    booster, info = fit_lightgbm(train_x, train_y, val_x, val_y, folder/'lightgbm.txt')
    record_prediction('lightgbm', booster.predict(val_x**2/info['target_scale'])*info['target_scale'], booster.predict(eval_x**2/info['target_scale'])*info['target_scale'])
    save_receipt('lightgbm', info)
    for seed in SEEDS:
        model, info = fit_dlinear(train_x, train_y, val_x, val_y, folder/f'dlinear_seed_{seed}.pt', seed=seed)
        key = f'dlinear_seed_{seed}'
        record_prediction(key, predict_dlinear(model, val_x, info), predict_dlinear(model, eval_x, info))
        save_receipt(key, info)
    record_prediction('dlinear', np.mean([predictions[f'dlinear_seed_{s}']['validation'] for s in SEEDS], axis=0), np.mean([predictions[f'dlinear_seed_{s}']['evaluation'] for s in SEEDS], axis=0))
    save_receipt('dlinear', {'seeds': list(SEEDS), 'aggregation': 'arithmetic mean of all three fixed seeds; no evaluation selection'})
    for path in folder.iterdir():
        if path.is_file():
            artifacts[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'predictions': predictions, 'models': models, 'artifacts': artifacts}
