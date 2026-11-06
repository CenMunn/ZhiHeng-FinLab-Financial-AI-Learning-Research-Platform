"""D25 immutable protocol, source identity and bounded artifact verification."""
import importlib.metadata
import json
import platform
import shutil
from pathlib import Path, PurePosixPath
from research.market.common import PROJECT, digest, file_sha, write_json

SOURCE_REPORT_ID = 'validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c'
SYMBOLS = ('600519', '600036', '600585', 'BTCUSDT', 'ETHUSDT')
FOLDS = tuple(f'{year}Q{quarter}' for year in (2024, 2025) for quarter in (1, 2, 3, 4))
CONFIG = dict(schema='five-asset-protocol-v1', symbols=list(SYMBOLS), folds=list(FOLDS), horizons=[1,5],
              seeds=[17,42,2025], lookback=60, ewma_decay=.94, lightgbm_rounds=200, lightgbm_patience=20,
              dlinear_epochs=30, dlinear_patience=6, batch_size=64, learning_rate=.001, weight_decay=.001,
              calibration=dict(method='mean(y/max(p,1e-10))', clip=[.25,4.]),
              roles=dict(train='fit weights/scalers', early_stopping='stopping only; six months',
                         calibration='scale only after selected checkpoint; six months', evaluation='features only until separate scorer'),
              bootstrap=dict(block_rows=20, replicates=2000, within_quarter=True), prospective_start='2026-11-06',
              prospective_status='pending', scope='finite model comparison; retrained per asset; historical nonblind research')

def sources():
    names = ['research/market/common.py', 'research/volatility/models.py', 'research/volatility/metrics.py',
             'research/volatility/data.py']
    names += [p.relative_to(PROJECT).as_posix() for p in (PROJECT/'research/five_asset').glob('*.py')]
    return {name:file_sha(PROJECT/name) for name in sorted(names)}

def environment():
    return {'python':platform.python_version(), 'platform':platform.platform(),
            'packages':{name:importlib.metadata.version(name) for name in ('numpy','scipy','torch','lightgbm')}}

def verify(root, files):
    root=Path(root).resolve()
    for name, sha in files.items():
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe artifact path: '+name)
        path=(root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or file_sha(path)!=sha:
            raise ValueError('Missing or changed artifact: '+name)

def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))

def archive_sources(root, files):
    verify(PROJECT,files);result={}
    for name,sha in files.items():
        target=Path(root)/'source-code'/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if file_sha(target)!=sha:raise ValueError('Source archive changed')
        else:shutil.copyfile(PROJECT/name,target)
        if file_sha(target)!=sha:raise ValueError('Source archive copy mismatch')
        result['source-code/'+name]=sha
    return result
