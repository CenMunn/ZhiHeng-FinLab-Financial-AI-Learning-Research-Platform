"""One frozen LightGBM run. Test data cannot select parameters or model rounds."""
import sys,json,hashlib,time,platform,math,shutil
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'.local/forecast-python'))
import numpy as np
import pandas as pd
import lightgbm as lgb
OUT=ROOT.parent/'复赛深化/forecast-experiment-2026-10-03';PUBLIC=ROOT/'public/forecast'
read=lambda p:json.loads(p.read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
config=read(OUT/'config.json');lock=read(OUT/'LOCK.json')
for f in lock['files']:assert sha(OUT/f['path'])==f['sha256'],f['path']
recover='--recover-export' in sys.argv
existing=(OUT/'model-v1.json').read_bytes() if (OUT/'model-v1.json').exists() else None
assert existing is None or (recover and not (OUT/'SUMMARY.json').exists()),'Preserve prior test results; new runs require a new version'
if recover:
 assert existing is not None,'Recovery requires the already exported original model'
 dump(OUT/'export-recovery.json',dict(reason='Native save_model cannot write Chinese path; use Python UTF-8 I/O',originalModelSha256=hashlib.sha256(existing).hexdigest(),parametersChanged=False,testBasedSelection=False))
# User order: finish the fair-source execution before training a new model.
run=Path((ROOT.parent/'复赛深化/evaluation/review-v4/run-directory.txt').read_text(encoding='utf8').strip())
assert read(run/'EXECUTION.json')['completedLogicalOutputs']==128,'Finish source comparison first'
started=time.perf_counter();names=config['features'];validStart=config['splits']['validStart'];testStart=config['splits']['testStart']
def features(bars,at):
 close=np.array([x['close'] for x in bars],dtype=float);vol=np.array([x['volume'] for x in bars],dtype=float);b=bars[at]
 def rs(n):return close[at-n+1:at+1]/close[at-n:at]-1
 values=[*[b['close']/close[at-n]-1 for n in [1,5,10,20]],*[b['close']/np.mean(close[at-n+1:at+1]) for n in [5,10,20]],
  np.std(rs(5)),np.std(rs(20)),b['close']/b['open']-1,(b['high']-b['low'])/b['close'],b['open']/close[at-1]-1,
  b['volume']/np.mean(vol[at-4:at+1]),b['volume']/np.mean(vol[at-19:at+1])]
 assert len(values)==len(names) and np.isfinite(values).all()
 return list(map(float,values))
samples=[];snapshots=[];purged=[]
manifest=read(OUT/'data-manifest.json')
for src in manifest:
 bars=read(OUT/'data'/f"{src['code']}-bars.json")
 assert sha(OUT/'data'/f"{src['code']}-bars.json")==src['barsSha256']
 for at in range(config['lookbackBars'],len(bars)-1):
  date=bars[at]['date'];labelDate=bars[at+1]['date']
  if date<validStart:segment='train' if labelDate<validStart else None
  elif date<testStart:segment='valid' if labelDate<testStart else None
  else:segment='test'
  if segment is None:purged.append(dict(code=src['code'],date=date,labelDate=labelDate));continue
  samples.append(dict(code=src['code'],date=date,labelDate=labelDate,segment=segment,features=features(bars,at),label=bars[at+1]['close']/bars[at]['close']-1))
 snapshots.append(dict(code=src['code'],name=src['name'],inputDate=bars[-1]['date'],close=bars[-1]['close'],features=features(bars,len(bars)-1)))
train=[s for s in samples if s['segment']=='train'];valid=[s for s in samples if s['segment']=='valid'];test=[s for s in samples if s['segment']=='test']
assert max(s['labelDate'] for s in train)<min(s['date'] for s in valid)
assert max(s['labelDate'] for s in valid)<min(s['date'] for s in test)
assert all(len(x)>100 for x in [train,valid,test])
xs=lambda rows:np.array([s['features'] for s in rows]);ys=lambda rows:np.array([s['label'] for s in rows])
fitStart=time.perf_counter();model=lgb.train(config['lightgbm'],lgb.Dataset(xs(train),label=ys(train),feature_name=names),num_boost_round=config['numBoostRound'])
fitSeconds=time.perf_counter()-fitStart
inferStart=time.perf_counter();pv=model.predict(xs(valid));pt=model.predict(xs(test));inferSeconds=time.perf_counter()-inferStart
radius=float(np.quantile(np.abs(pv-ys(valid)),.90))
def metrics(actual,predicted):
 predicted=np.asarray(predicted);actual=np.asarray(actual);nonzero=np.abs(predicted)>1e-12
 return dict(samples=len(actual),maePercentagePoints=float(np.mean(np.abs(actual-predicted))*100),
  rmsePercentagePoints=float(np.sqrt(np.mean((actual-predicted)**2))*100),meanBiasPercentagePoints=float(np.mean(predicted-actual)*100),
  directionAccuracy=float(np.mean(np.sign(predicted[nonzero])==np.sign(actual[nonzero]))) if nonzero.any() else None,
  directionalForecastCoverage=float(np.mean(nonzero)),definition='方向仅评价非零预测，零变动基线不伪报方向准确率')
comparisons={key:metrics(ys(test),pred) for key,pred in [('lightgbm',pt),('zero_change',np.zeros(len(test))),('one_day_momentum',xs(test)[:,0])]}
testRows=[]
for row,pred in zip(test,pt):testRows.append({**row,'prediction':float(pred),'zeroPrediction':0,'momentumPrediction':row['features'][0],
 'absoluteError':float(abs(row['label']-pred)),'withinValidationErrorBand':bool(abs(row['label']-pred)<=radius)})
df=pd.DataFrame([dict(date=r['date'],code=r['code'],prediction=r['prediction'],label=r['label']) for r in testRows]);ics=[]
for date,g in df.groupby('date'):
 if len(g)>=4 and g['prediction'].nunique()>1 and g['label'].nunique()>1:ics.append(float(g['prediction'].rank().corr(g['label'].rank())))
perStock={src['code']:{key:metrics([r['label'] for r in testRows if r['code']==src['code']],
 [r['prediction'] if key=='lightgbm' else r['momentumPrediction'] if key=='one_day_momentum' else 0 for r in testRows if r['code']==src['code']])
 for key in comparisons} for src in manifest}
ps=model.predict(np.array([s['features'] for s in snapshots]))
for row,pred in zip(snapshots,ps):row.update(prediction=float(pred),predictedChangePct=float(pred*100),predictedClose=float(row['close']*(1+pred)),
 predictionPeriod='下一实际交易日，未提供交易日历日期',errorBandPct=[float((pred-radius)*100),float((pred+radius)*100)])
modelBytes=(json.dumps(model.dump_model(),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf8')
if recover:
 assert json.loads(modelBytes)==json.loads(existing),'Recovered model differs; preserve original and stop'
 # Original Path.write_text used Windows CRLF; preserve its exact archived bytes.
else:(OUT/'model-v1.json').write_bytes(modelBytes)
(OUT/'model-v1.txt').write_text(model.model_to_string(),encoding='utf8')
dump(OUT/'test-predictions.json',testRows)
dump(OUT/'inference-parity-fixture.json',[dict(code=s['code'],date=s['date'],features=s['features'],expected=float(pred)) for s,pred in zip(test,pt)])
dump(OUT/'feature-parity-fixture.json',[dict(code=src['code'],bars=read(OUT/'data'/f"{src['code']}-bars.json"),lastFeatures=next(s['features'] for s in snapshots if s['code']==src['code'])) for src in manifest])
summary=dict(version='lightgbm-stock-v1',trainedAt=datetime.now(timezone.utc).isoformat(),upstream=read(OUT/'upstream/source.json'),target=config['target'],
 featureNames=names,numBoostRound=config['numBoostRound'],parameters=config['lightgbm'],dataManifest=manifest,
 segments={name:dict(samples=len(rows),firstFeatureDate=min(r['date'] for r in rows),lastFeatureDate=max(r['date'] for r in rows),lastLabelDate=max(r['labelDate'] for r in rows)) for name,rows in [('train',train),('valid',valid),('test',test)]},
 purgedBoundaryRows=purged,comparisons=comparisons,perStock=perStock,rankIC=dict(mean=float(np.mean(ics)) if ics else None,days=len(ics),stocksPerDay=6),
 errorBand=dict(calibration='验证段绝对残差90%分位，非未来保证区间',radiusFraction=radius,testCoverage=float(np.mean(np.abs(pt-ys(test))<=radius))),
 snapshots=snapshots,benchmarkConclusion='本次测试模型MAE低于两个预设基线，单次目的样本不证明稳定优势' if comparisons['lightgbm']['maePercentagePoints']<min(comparisons[k]['maePercentagePoints'] for k in ['zero_change','one_day_momentum']) else '本次测试未同时优于两个预设基线，保留负结果，不宣称已提高投资效果',
 costs=dict(trainingSeconds=fitSeconds,testAndValidationInferenceSeconds=inferSeconds,totalSeconds=time.perf_counter()-started,modelJsonBytes=(OUT/'model-v1.json').stat().st_size,
  paidModelAPIRequests=0,paidAPICost=0,computeCost='本机CPU，电费/硬件成本未计量；不是总运行成本为零'),
 environment=dict(python=sys.version,lightgbm=lgb.__version__,numpy=np.__version__,pandas=pd.__version__,platform=platform.platform(),processor=platform.processor()),
 limitations=config['limitations'],sourceLockSha256=sha(OUT/'LOCK.json'),trainingScriptSha256=sha(Path(__file__)),modelSha256=sha(OUT/'model-v1.json'),
 selfDeveloped='数据冻结、14个OHLCV特征、时间切分/标签隔离、基线评测、Node树推理与页面',externalComponents='官方LightGBM 4.6.0算法/训练库；腾讯日线接口；参考Qlib监督预测工作流，未集成完整Qlib或Alpha158')
dump(OUT/'SUMMARY.json',summary)
PUBLIC.mkdir(exist_ok=True)
for name,dest in [('model-v1.json','model-v1.json'),('SUMMARY.json','summary.json')]:shutil.copy2(OUT/name,PUBLIC/dest)
for src in manifest:shutil.copy2(OUT/'data'/f"{src['code']}-bars.json",PUBLIC/f"{src['code']}-bars.json")
shutil.copy2(OUT/'upstream/LightGBM-LICENSE.txt',PUBLIC/'LightGBM-LICENSE.txt')
print(json.dumps(dict(comparisons=comparisons,trainSamples=len(train),validSamples=len(valid),testSamples=len(test),trainingSeconds=fitSeconds,conclusion=summary['benchmarkConclusion']),ensure_ascii=False))
