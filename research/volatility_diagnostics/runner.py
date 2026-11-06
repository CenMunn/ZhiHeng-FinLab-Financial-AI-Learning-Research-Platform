"""Read verified D22 results; publish separately identified descriptive diagnoses."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from research.market.common import PROJECT,digest,file_sha,write_json
sys.path.insert(0,str(PROJECT/'backend/src'))
from platform_app.adapters.volatility_store import VolatilityStore
from research.volatility.metrics import metrics,paired_comparison
from research.volatility_diagnostics.analysis import fit_scale,reliability_bins,failure_windows,coverage_rows
from research.volatility_diagnostics.publish import publish

PROTOCOL={'schema':'volatility-diagnostic-protocol-v1','scale':'per-fold validation mean(y/max(p,1e-10)), clipped [.25,4]; no evaluation fit','bins':'per-fold validation prediction quintiles; unique edges; (lower, upper] intervals; -infinity/+infinity outer bounds; retain empty bins','windows':'20 evaluation rows, nonoverlapping, quarter-local, retain short tail; worst3 descriptive raw QLIKE minus same-window raw EWMA','coverage':'original train-tercile regimes; label-nonoverlap count quarter-local within regime; minimum30 descriptive only','inference':'quarter-stratified20row2000paired draws calibrated minus raw; exploratory; validation reused by model early stopping'}

def sources():
    files=list((PROJECT/'research/volatility_diagnostics').glob('*.py'))+[PROJECT/'research/volatility/metrics.py',PROJECT/'research/volatility/data.py']
    return {p.relative_to(PROJECT).as_posix():file_sha(p) for p in sorted(files)}

def diagnose(body):
    r=body['record'];source_files=r['artifacts'];models={};coverage_folds=[]
    def read(suffix):
        matches=[n for n in source_files if n.endswith(suffix)]
        if len(matches)!=1:raise ValueError('来源文件身份不唯一：'+suffix)
        n=matches[0]
        if file_sha(PROJECT/n)!=source_files[n]:raise ValueError('来源文件变化')
        return json.loads((PROJECT/n).read_text('utf8'))
    for fold in r['folds']:
        suffix=f"/{r['market']}/h{r['horizon']}/{fold['fold']}/"
        parts={k:read(suffix+name+'.json') for k,name in [('train','train'),('validation','validation'),('evaluation','evaluation_features')]}
        predictions=read(suffix+'predictions.json');thresholds=[fold['regime_thresholds'][k] for k in ('low','high')]
        coverage_folds.append({'fold':fold['fold'],'regimes':coverage_rows(parts,thresholds)})
        observations=[o for o in r['observations'] if o['fold']==fold['fold']];vy=parts['validation']['y'];y=[o['realized_variance'] for o in observations]
        if [x['signal_session'] for x in parts['evaluation']['rows']]!=[o['session'] for o in observations]:raise ValueError('评估来源日期错配')
        for key,original in r['overall'].items():
            vp=predictions[key]['validation'];scale=fit_scale(vy,vp);p=np.array([o['predictions'][key] for o in observations]);cal=np.maximum(p*scale['c'],1e-10)
            if predictions[key]['evaluation']!=p.tolist():raise ValueError('发布预测与冻结预测错配')
            model=models.setdefault(key,{'name':original['name'],'folds':[],'windows':[],'calibrated_predictions':[]})
            model['folds'].append({'fold':fold['fold'],**scale,'raw':metrics(y,p,r['annualization']),'calibrated':metrics(y,cal,r['annualization']),'bins':reliability_bins(vp,p,y)})
            model['windows']+=failure_windows(observations,key,scale['c'],fold['fold']);model['calibrated_predictions']+=cal.tolist()
    y=[o['realized_variance'] for o in r['observations']];folds=[o['fold'] for o in r['observations']]
    for key,m in models.items():
        cal=m.pop('calibrated_predictions');p=[o['predictions'][key] for o in r['observations']]
        m.update(raw=metrics(y,p,r['annualization']),calibrated=metrics(y,cal,r['annualization']),comparison=paired_comparison(y,cal,p,folds),worst_windows=sorted(m['windows'],key=lambda w:w['raw_delta'],reverse=True)[:3])
    coverage=[]
    for i in range(6):
        entries=[f['regimes'][i] for f in coverage_folds];e=entries[0];sums={k:sum(v[k] for v in entries) for k in ('train_rows','validation_rows','evaluation_rows','nonoverlap_count')}
        # Expanding training membership repeats across folds; shares are fold-membership weighted, not unique dates.
        train_total=sum(sum(v['train_rows'] for v in f['regimes']) for f in coverage_folds);n=len(r['observations'])
        ts=sums['train_rows']/train_total;es=sums['evaluation_rows']/n
        coverage.append({'regime':e['regime'],'name':e['name'],**sums,'missing_to_30':max(0,30-sums['evaluation_rows']),'train_share':ts,'evaluation_share':es,'share_change':es-ts})
    return models,coverage,coverage_folds

def main():
    store=VolatilityStore(PROJECT/'backend/data/volatility-runs',PROJECT);receipts=[]
    for summary in store.list():
        body=store.get(summary['run_id'])
        if body['artifact_status']!='verified':raise ValueError('来源产物缺失，不能发布新诊断')
        identity={'source_record_sha256':body['record_sha256'],'protocol_sha256':digest(PROTOCOL),'sources':sources()};did='vdiag-'+digest(identity)
        root=PROJECT/'research/artifacts/volatility-diagnostics'/did;meta=root/'identity.json'
        if meta.exists():created=json.loads(meta.read_text('utf8'))['created_at']
        else:created=datetime.now(timezone.utc).isoformat();write_json(meta,{'identity':identity,'created_at':created})
        write_json(root/'source.json',body);models,coverage,coverage_folds=diagnose(body);r=body['record']
        record={'schema':'volatility-diagnostics-v1','diagnostic_id':did,'source_run_id':r['run_id'],'source_record_sha256':body['record_sha256'],'created_at':created,'market':r['market'],'horizon':r['horizon'],'protocol':PROTOCOL,'sources':sources(),'artifacts':{p.relative_to(PROJECT).as_posix():file_sha(p) for p in (meta,root/'source.json')},'models':models,'coverage':coverage,'coverage_folds':coverage_folds,
            'limitations':['校准验证段也参与原模型早停，不是独立校准集；评估行情已研究过。','分箱只由原始验证预测定义，展示原始预测均值与实际均方；不是概率可靠度。','失败窗口是事后描述，不是可事前识别的风险状态；不跨季度，保留短尾。','标签不重叠窗口数不等于统计独立样本，30条仅展示门槛，不代表统计功效充分。','训练/验证样本在扩展折间重复，总体计数为折成员次数，份额按成员数加权；不能当独立新样本。','覆盖仅限现有单股/单币，尚未获取更多标的/时期；不以合成数据填缺口。','仅进行验证段比例适配和历史诊断，未重新训练模型或启动风险预算交易。']}
        # Detect any concurrent changes to original frozen artifacts before publication.
        current=store.get(r['run_id'])
        if current['record_sha256']!=body['record_sha256'] or current['artifact_status']!='verified':raise ValueError('来源记录或产物中途变化')
        publish(PROJECT/'backend/data/volatility-diagnostics',record)
        receipts.append({'source_run_id':r['run_id'],'diagnostic_id':did,'market':r['market'],'horizon':r['horizon'],'record_sha256':digest(record),'coverage':coverage,'models':{k:{n:v[n] for n in ('name','raw','calibrated','comparison','worst_windows')} for k,v in models.items()}})
        print(json.dumps({'market':r['market'],'horizon':r['horizon'],'id':did},ensure_ascii=False),flush=True)
    write_json(PROJECT/'docs/research'/('2026-11-05-diagnostics-'+digest(receipts)[:12]+'.json'),{'runs':receipts})

if __name__=='__main__':main()

