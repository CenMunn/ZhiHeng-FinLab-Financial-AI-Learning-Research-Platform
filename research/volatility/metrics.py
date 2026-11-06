"""D22 daily mean-square losses and quarter-stratified paired block intervals."""
from functools import lru_cache
import math

import numpy as np

PREDICTION_FLOOR = 1e-10
BOOTSTRAP_BLOCK = 20
BOOTSTRAP_REPEATS = 2000
BOOTSTRAP_SEED = 20261104


def _observations(y, p):
    truth = np.asarray(y, dtype=np.float64)
    prediction = np.asarray(p, dtype=np.float64)
    if truth.ndim != 1 or prediction.shape != truth.shape:
        raise ValueError('truth and predictions must be equally sized one-dimensional arrays')
    if not np.isfinite(truth).all() or not np.isfinite(prediction).all() or (truth < 0).any():
        raise ValueError('observations must be finite and realized variance nonnegative')
    return truth, np.maximum(prediction, PREDICTION_FLOOR)


def qlike(y, p):
    """Common-constant QLIKE, retaining zero realized variance observations."""
    truth, prediction = _observations(y, p)
    return np.log(prediction) + truth / prediction


def metrics(y, p, annualization):
    truth, prediction = _observations(y, p)
    if not math.isfinite(float(annualization)) or annualization <= 0:
        raise ValueError('annualization must be positive')
    rows = len(truth)
    result = dict(rows=rows, qlike=None, variance_rmse=None, variance_mae=None,
                  volatility_rmse_ann=None, calibration_ratio=None,
                  prediction_floor_count=int(np.sum(np.asarray(p) <= PREDICTION_FLOOR)))
    if not rows:
        return result
    difference = prediction - truth
    result.update(qlike=float(np.mean(np.log(prediction) + truth/prediction)),
                  variance_rmse=float(np.sqrt(np.mean(difference**2))),
                  variance_mae=float(np.mean(np.abs(difference))),
                  volatility_rmse_ann=float(np.sqrt(np.mean((np.sqrt(prediction*annualization)-np.sqrt(truth*annualization))**2))),
                  calibration_ratio=float(prediction.mean()/truth.mean()) if truth.mean() > 0 else None)
    return result


def _quarter_groups(folds):
    groups = []
    seen = set()
    for i, fold in enumerate(folds):
        if i == 0 or fold != folds[i-1]:
            if fold in seen:
                raise ValueError('each quarter must occupy one contiguous chronological segment')
            seen.add(fold)
            groups.append([i, i+1])
        else:
            groups[-1][1] = i+1
    return groups


def _block_indices(folds, rng, block=BOOTSTRAP_BLOCK):
    """Noncircular moving blocks; each original quarter keeps its row count."""
    sampled = []
    for start, end in _quarter_groups(folds):
        size = end-start
        length = min(block, size)
        starts = rng.integers(0, size-length+1, size=math.ceil(size/length))
        sampled.append((start + starts[:, None] + np.arange(length)).reshape(-1)[:size])
    return np.concatenate(sampled) if sampled else np.empty(0, dtype=int)


@lru_cache(maxsize=8)
def _bootstrap_indices(folds):
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    # Cache the same fixed draws across models, so comparisons remain paired.
    return np.asarray([_block_indices(folds, rng) for _ in range(BOOTSTRAP_REPEATS)], dtype=np.int32)


def paired_comparison(y, p, base, folds, mask=None):
    truth, prediction = _observations(y, p)
    _, baseline = _observations(y, base)
    if len(folds) != len(truth):
        raise ValueError('one quarter is required per observation')
    selected = np.ones(len(truth), dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if selected.shape != truth.shape:
        raise ValueError('regime mask must align with complete chronological observations')
    result = dict(delta_qlike=None, ci_low=None, ci_high=None, block=BOOTSTRAP_BLOCK,
                  repeats=BOOTSTRAP_REPEATS, rows=int(selected.sum()), empty_resamples=0,
                  seed=BOOTSTRAP_SEED, method='quarter-stratified moving blocks, then regime filter')
    if not selected.any():
        return result
    delta = np.log(prediction/baseline) + truth/prediction-truth/baseline
    result['delta_qlike'] = float(delta[selected].mean())
    indices = _bootstrap_indices(tuple(folds))
    resampled_mask = selected[indices]
    counts = resampled_mask.sum(axis=1)
    valid = counts > 0
    result['empty_resamples'] = int((~valid).sum())
    samples = (delta[indices]*resampled_mask).sum(axis=1)[valid]/counts[valid]
    if len(samples):
        result['ci_low'], result['ci_high'] = map(float, np.quantile(samples, [.025, .975]))
    return result
