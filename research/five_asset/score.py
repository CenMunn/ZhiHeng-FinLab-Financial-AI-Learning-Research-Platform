"""D25 isolated final scoring. Only this process loads evaluation labels."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from research.market.common import PROJECT,digest,file_sha,write_json
from research.volatility.metrics import metrics,paired_comparison,PREDICTION_FLOOR
from research.volatility.data import regime_thresholds,regime_key,REGIMES
sys.path.insert(0,str(PROJECT/'backend/src'))

def verify_calibration(prediction,calibration_y):
    y=np.asarray(calibration_y,dtype=float);p=np.asarray(prediction['calibration_raw'],dtype=float)
    if y.ndim!=1 or len(y)==0 or y.shape!=p.shape or not np.isfinite(y).all() or not np.isfinite(p).all() or (y<0).any() or (p<=0).any():raise ValueError('校准段预测/标签错配')
    raw_c=float(np.mean(y/np.maximum(p,PREDICTION_FLOOR)));c=float(np.clip(raw_c,.25,4.))
    if prediction['raw_c']!=raw_c or prediction['c']!=c or prediction['clipped']!=(raw_c!=c) or prediction['calibration_rows']!=len(y):raise ValueError('校准系数未绑定独立校准段')
    raw=np.asarray(prediction['raw'],dtype=float);cal=np.asarray(prediction['calibrated'],dtype=float)
    if raw.shape!=cal.shape or not np.isfinite(raw).all() or not np.isfinite(cal).all() or (raw<PREDICTION_FLOOR).any() or not np.allclose(cal,np.maximum(raw*c,PREDICTION_FLOOR),rtol=1e-12,atol=0):raise ValueError('校准评估预测不一致')

def summarize(rows,names,annualization,full_rows=None,mask=None):
    full_rows=rows if full_rows is None else full_rows
    y=np.array([r['realized_variance'] for r in full_rows]);folds=[r['fold'] for r in full_rows]
    selected=np.ones(len(full_rows),dtype=bool) if mask is None else np.asarray(mask,dtype=bool)
    base=np.array([r['raw']['ewma'] for r in full_rows]);result={}
    for k,name in names.items():
        raw=np.array([r['raw'][k] for r in full_rows]);cal=np.array([r['calibrated'][k] for r in full_rows])
        result[k]={'name':name,'raw':metrics(y[selected],raw[selected],annualization) if selected.any() else None,'calibrated':metrics(y[selected],cal[selected],annualization) if selected.any() else None,
            'raw_vs_ewma':paired_comparison(y,raw,base,folds,selected) if selected.any() else None,
            'calibrated_vs_ewma':paired_comparison(y,cal,base,folds,selected) if selected.any() else None,
            'calibrated_vs_raw':paired_comparison(y,cal,raw,folds,selected) if selected.any() else None}
    return result

def score(root):
    from research.five_asset.common import sources,verify,environment
    from platform_app.adapters.validation_foundation_store import ValidationFoundationStore
    root=Path(root).resolve();allowed=(PROJECT/'research/artifacts/five-asset').resolve()
    if not root.is_relative_to(allowed):raise ValueError('评分目录越界')
    protocol=json.loads((root/'protocol.json').read_text('utf8'));frozen=json.loads((root/'frozen.json').read_text('utf8'))
    if protocol['sources']!=sources() or protocol['environment']!=environment() or frozen['protocol_sha256']!=digest(protocol) or frozen['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('代码/环境/协议/冻结输入版本变化')
    verify(root,frozen['files']);inputs=json.loads((root/'inputs.json').read_text('utf8'));verify(root,inputs['files'])
    source=json.loads((root/'source.json').read_text('utf8'))
    current=ValidationFoundationStore(PROJECT/'backend/data/validation-foundation',PROJECT).get(protocol['source_report_id'])
    if source['record_sha256']!=protocol['source_report_sha256'] or current['record_sha256']!=source['record_sha256'] or current['artifact_status']!='verified':raise ValueError('原资格报告身份/产物变化')
    assets=[a for a in source['record']['assets'] if a['status']=='qualified'];summaries=[]
    artifacts={root.relative_to(PROJECT).as_posix()+'/'+n:sha for n,sha in frozen['files'].items()}
    artifacts[root.relative_to(PROJECT).as_posix()+'/frozen.json']=file_sha(root/'frozen.json')
    for asset in assets:
        symbol=asset['symbol'];annual=252 if asset['market']=='ashare' else 365
        for horizon in (1,5):
            observations=[];folds=[];names={}
            for spec in asset['folds']:
                folder=root/symbol/spec['fold']/f'h{horizon}'
                completed=json.loads((folder/'completed.json').read_text('utf8'))
                if completed['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('折输入冻结版本变化')
                verify(folder,completed['files'])
                training=json.loads((folder/'training.json').read_text('utf8'));prediction=json.loads((folder/'predictions.json').read_text('utf8'))
                ev=json.loads((folder/'evaluation_features.json').read_text('utf8'));labels=json.loads((folder/'evaluation_labels.json').read_text('utf8'));cal=json.loads((folder/'calibration.json').read_text('utf8'));train=json.loads((folder/'train.json').read_text('utf8'))
                if ev['rows']!=labels['rows'] or len(labels['y'])!=len(ev['rows']) or prediction['evaluation_labels_read'] is not False:raise ValueError('评估日期或标签读取状态错配')
                thresholds=regime_thresholds(train['x']);names={k:v['name'] for k,v in training['models'].items()}
                if set(names)!=set(prediction['models']) or 'ewma' not in names:raise ValueError('模型集合错配')
                for key in names:
                    values=prediction['models'][key];verify_calibration(values,cal['y'])
                    if len(values['raw'])!=len(ev['rows']):raise ValueError('冻结预测行数错配')
                unit=[]
                for i,row in enumerate(ev['rows']):
                    unit.append({'session':row['signal_session'],'label_end':row['label_end'],'fold':spec['fold'],'regime':regime_key(ev['x'][i],thresholds),'realized_variance':float(labels['y'][i]),
                        'raw':{k:float(prediction['models'][k]['raw'][i]) for k in names},'calibrated':{k:float(prediction['models'][k]['calibrated'][i]) for k in names}})
                fm=summarize(unit,names,annual)
                for key in fm:
                    fm[key].update({k:prediction['models'][key][k] for k in ('c','raw_c','clipped','calibration_rows')})
                observations+=unit
                counts=next(h['counts'] for h in spec['horizons'] if h['horizon']==horizon)
                folds.append({'fold':spec['fold'],'bounds':spec['bounds'],'counts':counts,'models':fm,'training':training})
            overall=summarize(observations,names,annual)
            for key in names:
                overall[key].update(folds=8,wins_raw=sum(f['models'][key]['raw_vs_ewma']['delta_qlike']<0 for f in folds),wins_calibrated=sum(f['models'][key]['calibrated_vs_ewma']['delta_qlike']<0 for f in folds))
            regimes={}
            for key,name in REGIMES.items():
                mask=np.array([r['regime']==key for r in observations]);n=int(mask.sum());regimes[key]={'name':name,'rows':n,'sufficient':n>=30,'models':summarize([],names,annual,observations,mask)}
            identity={'protocol_sha256':digest(protocol),'source_report_sha256':source['record_sha256'],'symbol':symbol,'horizon':str(horizon)}
            record={'schema':'five-asset-result-v1','run_id':'five-'+digest(identity),'identity':identity,'created_at':frozen['created_at'],'symbol':symbol,'name':asset['name'],'market':asset['market'],'horizon':horizon,'annualization':annual,
                'source_report_id':protocol['source_report_id'],'source_report_sha256':source['record_sha256'],'protocol':protocol,'overall':overall,'folds':folds,'regimes':regimes,'observations':observations,'artifacts':artifacts,
                'limitations':['逐标的重训的有限预算对照，不是模型零样本跨标的迁移或充分调参。','神经最多30epoch/patience6，固定三种子全部保留；早停仅early_stopping，比例仅calibration。','预测为未来1/5市场日收益平方日均代理，不是高频实现方差或涨跌方向。','2024–2025历史已研究，非未知盲测；2026-11-06前瞻仍待真实观测，无前瞻成绩。','单标的/期限内配对20行块区间为探索性，系数固定，未包含校准重估不确定性或多模型检验校正。','5期标签重叠；跨标的相关，不拼成独立样本宣称显著泛化。','原价/公司事件与close+1分钟假设为公开历史重建，不能证明PIT和事件完整性。','原始EWMA为共同基准，所有模型校准前后均报告；不足30条市况保留提示。','未进行仓位回放、风险预算、交易或收益承诺。']}
            out=PROJECT/'backend/data/five-asset-runs'/(record['run_id']+'.json');write_json(out,{'record':record,'sha256':digest(record)})
            summaries.append({k:record[k] for k in ('run_id','symbol','name','market','horizon','created_at','overall')})
            print(json.dumps({'scored':symbol,'horizon':horizon,'rows':len(observations),'qlike':{k:{'raw':v['raw']['qlike'],'calibrated':v['calibrated']['qlike']} for k,v in overall.items()}},ensure_ascii=False),flush=True)
    write_json(PROJECT/'docs/research'/('2026-11-05-five-asset-'+digest(summaries)[:12]+'.json'),{'artifact_root':root.relative_to(PROJECT).as_posix(),'runs':summaries})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);score(p.parse_args().root)
