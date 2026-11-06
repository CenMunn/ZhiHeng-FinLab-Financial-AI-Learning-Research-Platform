import numpy as np
import torch
from torch import nn
from torch.nn import functional as F


def save_lightgbm(model,path):
    from pathlib import Path
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():raise ValueError('拒绝覆盖已有LightGBM模型')
    # C++ fopen on Windows does not reliably accept a UTF-8 Chinese pathname.
    with path.open('x',encoding='utf8') as stream:stream.write(model.model_to_string())


def load_lightgbm(path):
    from pathlib import Path
    import lightgbm as lgb
    return lgb.Booster(model_str=Path(path).read_text('utf8'))


def fit_scaler(x,y):
    x=np.asarray(x,dtype=np.float64);y=np.asarray(y,dtype=np.float64)
    if not np.isfinite(x).all() or not np.isfinite(y).all():raise ValueError('训练值必须有限')
    return {'x_mean':float(x.mean()),'x_std':float(x.std()) or 1.,'y_mean':float(y.mean()),'y_std':float(y.std()) or 1.,'fit_rows':len(y)}


def standardize(x,scaler):return (np.asarray(x,dtype=np.float64)-scaler['x_mean'])/scaler['x_std']


def ridge_fit(x,y,alpha=10):
    x=np.asarray(x,dtype=np.float64);a=np.c_[np.ones(len(x)),x];penalty=np.eye(a.shape[1])*alpha;penalty[0,0]=0
    weight=np.linalg.solve(a.T@a+penalty,a.T@y) if alpha else np.linalg.lstsq(a,y,rcond=None)[0]
    return {'weight':weight.tolist(),'alpha':alpha}


def ridge_predict(model,x):return np.c_[np.ones(len(x)),x]@np.asarray(model['weight'])


class DLinear(nn.Module):
    """DLinear decomposition/linear heads, adapted to executable return targets.

    Official reference: cure-lab/LTSF-Linear at 0c113668a3b88c4c4ee586b8c5ec3e539c4de5a6.
    Centered smoothing uses ONLY the already-observed input window, not future bars.
    """
    def __init__(self,lookback=60,kernel=25):
        super().__init__()
        if kernel<1 or kernel%2!=1:raise ValueError('分解核须为正奇数')
        self.kernel=kernel;self.trend=nn.Linear(lookback,1);self.residual=nn.Linear(lookback,1)

    def decompose(self,x):
        trend=F.avg_pool1d(F.pad(x.unsqueeze(1),(self.kernel//2,self.kernel//2),mode='replicate'),self.kernel,stride=1).squeeze(1)
        return trend,x-trend

    def forward(self,x):
        trend,residual=self.decompose(x)
        return (self.trend(trend)+self.residual(residual)).squeeze(-1)
