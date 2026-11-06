"""Freeze real daily-price snapshots and parameters before training/test results."""
import json,urllib.request,hashlib,platform,shutil
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT.parent/'复赛深化/forecast-experiment-2026-10-03'
OUT.mkdir(exist_ok=True);(OUT/'data').mkdir(exist_ok=True);(OUT/'upstream').mkdir(exist_ok=True)
assert not (OUT/'LOCK.json').exists(),'Never replace a trained/tested experiment'
stocks=[('600519','贵州茅台','sh'),('000858','五粮液','sz'),('000333','美的集团','sz'),('600036','招商银行','sh'),('601318','中国平安','sh'),('000001','平安银行','sz')]
sha=lambda b:hashlib.sha256(b).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
manifest=[]
for code,name,prefix in stocks:
 url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,1200,qfq'
 raw=urllib.request.urlopen(url,timeout=30).read();j=json.loads(raw);assert j['code']==0
 data=j['data'][prefix+code];assert 'qfqday' in data,'Require explicitly forward-adjusted source'
 rows=data['qfqday'];assert len(rows)>=400
 bars=[]
 for r in rows:
  bars.append(dict(date=r[0],open=float(r[1]),close=float(r[2]),high=float(r[3]),low=float(r[4]),volume=float(r[5])))
 assert len(set(b['date'] for b in bars))==len(bars) and all(bars[i]['date']<bars[i+1]['date'] for i in range(len(bars)-1))
 assert all(b['close']>0 and b['open']>0 and b['low']>0 and b['high']>=max(b['close'],b['open'],b['low']) and b['low']<=min(b['close'],b['open']) and b['volume']>=0 for b in bars)
 (OUT/'data'/f'{code}-raw.json').write_bytes(raw);dump(OUT/'data'/f'{code}-bars.json',bars)
 manifest.append(dict(code=code,name=name,url=url,fetchedAt=datetime.now(timezone.utc).isoformat(),rawSha256=sha(raw),
  barsSha256=sha((OUT/'data'/f'{code}-bars.json').read_bytes()),rows=len(bars),firstDate=bars[0]['date'],lastDate=bars[-1]['date'],adjustment='provider qfq snapshot, not historic point-in-time factors'))
dates=sorted(set.intersection(*[set(b['date'] for b in json.loads((OUT/'data'/f'{code}-bars.json').read_text(encoding='utf8'))) for code,_,_ in stocks]))
eligible=dates[30:-1];cut1=int(len(eligible)*.6);cut2=int(len(eligible)*.8)
config=dict(version='forecast-v1',frozenAt=datetime.now(timezone.utc).isoformat(),symbols=[c for c,_,_ in stocks],
 target='下一交易日前复权收盘价变化率 close[t+1]/close[t]-1；非可交易收益率',horizonBars=1,
 lookbackBars=30,seed=20261003,features=['return1','return5','return10','return20','closeMa5','closeMa10','closeMa20','volatility5','volatility20','intraday','range','openGap','volumeRatio5','volumeRatio20'],
 splits=dict(validStart=eligible[cut1],testStart=eligible[cut2],lastLabelDate=dates[-1],rule='train labelDate < validStart, valid labelDate < testStart; chronological common boundaries, no random split'),
 lightgbm=dict(objective='regression',metric='l2',learning_rate=.03,num_leaves=7,max_depth=3,min_data_in_leaf=60,num_threads=2,seed=20261003,deterministic=True,force_col_wise=True,verbosity=-1),
 numBoostRound=60,selection='单一预设参数，不做调参或测试段选择；验证段只校准残差范围',baselines=['zero_change','one_day_momentum'],
 limitations=['6只预先固定存续股票、约640日目的样本，存在存续选择，不能代表全市场',
 '历史前复权为本次获取快照，非逐日可得复权因子/历史版本；即使标签隔离也不能声称完全解决经济时点前视偏差',
 '不做可交易策略回测，不计交易成本、不输出Sharpe或仓位','数据接口授权与再分发条款未充分核实；仅本地研究展示，不能声称开放数据许可',
 '测试只一次，模型无优于基线保证；误差带来自验证残差，不是未来保证区间'])
dump(OUT/'data-manifest.json',manifest);dump(OUT/'config.json',config)
licenseUrl='https://raw.githubusercontent.com/lightgbm-org/LightGBM/v4.6.0/LICENSE'
(OUT/'upstream/LightGBM-LICENSE.txt').write_bytes(urllib.request.urlopen(licenseUrl,timeout=30).read())
dump(OUT/'upstream/source.json',dict(repository='https://github.com/lightgbm-org/LightGBM',version='4.6.0',license='MIT',licenseUrl=licenseUrl,
 referenceStockWorkflow='https://github.com/microsoft/qlib/tree/main/examples/benchmarks/LightGBM',
 boundary='实际集成官方LightGBM训练算法；自研14项OHLCV特征、切分评测和Node推理，不是完整Qlib/Alpha158或预训练股票模型'))
files=[dict(path=str(p.relative_to(OUT)).replace('\\','/'),sha256=sha(p.read_bytes())) for p in OUT.rglob('*') if p.is_file()]
dump(OUT/'LOCK.json',dict(version='forecast-data-params-lock',at=datetime.now(timezone.utc).isoformat(),modelTrained=False,testResultsSeen=False,files=files))
print(json.dumps(dict(directory=str(OUT),stocks=len(stocks),commonDates=len(dates),validStart=config['splits']['validStart'],testStart=config['splits']['testStart'],trained=False)))
