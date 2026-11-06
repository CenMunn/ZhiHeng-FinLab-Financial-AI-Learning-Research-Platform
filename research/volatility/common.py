import sys
from importlib.metadata import version
from research.market.common import PROJECT,digest,file_sha,write_json,read_checked
sys.path.insert(0,str(PROJECT/'backend/src'))

def sources():
    names=[p.relative_to(PROJECT).as_posix() for p in (PROJECT/'research/volatility').glob('*.py')]
    names+=['research/market/common.py','research/rolling/data.py','backend/src/platform_app/adapters/public_market.py','backend/src/platform_app/contracts/public_backtests.py','backend/src/platform_app/contracts/market_experiments.py','backend/src/platform_app/contracts/models.py']
    return {n:file_sha(PROJECT/n) for n in sorted(names)}

def environment():return {n:version(n) for n in ('numpy','scipy','torch','lightgbm','pydantic')}

def verify(root,files):
    root=root.resolve()
    for n,sha in files.items():
        p=(root/n).resolve()
        if not p.is_relative_to(root) or not p.is_file() or file_sha(p)!=sha:raise ValueError('冻结文件变化/缺失/越界：'+n)
