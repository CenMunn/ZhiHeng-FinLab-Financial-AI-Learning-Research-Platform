import hashlib
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
CONFIG=PROJECT/'research/configs/market-forecast-v1.json'


def file_sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(body):return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def write_json(path,body):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(body,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
    if path.exists():
        if path.read_text('utf8')!=text:raise ValueError('拒绝覆盖已有产物：'+str(path))
        return
    with path.open('x',encoding='utf8') as f:f.write(text)


def read_checked(root,manifest,name):
    path=Path(root)/name
    if name not in manifest['files'] or file_sha(path)!=manifest['files'][name]:raise ValueError('产物校验失败：'+name)
    return json.loads(path.read_text('utf8'))


def load_split(root,manifest,split):
    # Training and inference share this loader; held-out answers are not a valid key.
    if split not in ('train','validation','evaluation_features'):raise ValueError('此入口不允许读取评估标签')
    return read_checked(root,manifest,split+'.json')


def code_manifest():
    files=[p.relative_to(PROJECT).as_posix() for p in (PROJECT/'research/market').glob('*.py')]
    files+=['backend/src/platform_app/experiments/forecast_data.py','backend/src/platform_app/experiments/backtest.py',
            'backend/src/platform_app/experiments/markets.py','backend/src/platform_app/adapters/public_market.py',
            'backend/src/platform_app/contracts/models.py','backend/src/platform_app/contracts/market_experiments.py',
            'backend/src/platform_app/contracts/public_backtests.py']
    return {name:file_sha(PROJECT/name) for name in sorted(files)}
