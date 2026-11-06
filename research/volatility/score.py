import argparse,json
from pathlib import Path
import numpy as np
from research.volatility.common import PROJECT,digest,file_sha,write_json,read_checked,sources,verify
from research.volatility.data import REGIMES,regime_key
from research.volatility.metrics import metrics,paired_comparison
from platform_app.contracts.volatility_results import VolatilityResult
from research.volatility.provenance import check_inputs,check_fold

def comparison(y,p,b,folds,mask=None):
    raw=paired_comparison(y,p,b,folds,mask)
    return {k:raw[k] for k in ('delta_qlike','ci_low','ci_high','block','repeats')}

def score(root):
    root=root.resolve()
    if not root.is_relative_to((PROJECT/'research/artifacts/volatility').resolve()):raise ValueError('评分目录越界')
    protocol=json.loads((root/'protocol.json').read_text('utf8'));frozen=json.loads((root/'frozen.json').read_text('utf8'))
    if protocol['sources']!=sources() or digest(protocol)!=frozen['protocol_sha256']:raise ValueError('代码/协议身份变化')
    verify(root,frozen['files']);summaries=[]
    check_inputs(root)
    for market in ('ashare','btc'):
        for h in (1,5):
            for spec in protocol['folds']:check_fold(root,root/market/f'h{h}'/spec['fold'])
    artifacts={root.relative_to(PROJECT).as_posix()+'/'+n:sha for n,sha in frozen['files'].items()}
    artifacts[root.relative_to(PROJECT).as_posix()+'/frozen.json']=file_sha(root/'frozen.json')
    for market in ('ashare','btc'):
        dataset=json.loads((root/market/'dataset.json').read_text('utf8'))
        for h in (1,5):
            annual=252 if market=='ashare' else 365;observations=[];foldresults=[];names={}
            for spec in protocol['folds']:
                folder=root/market/f'h{h}'/spec['fold'];m=json.loads((folder/'preparation.json').read_text('utf8'))
                ev=read_checked(folder,m,'evaluation_features.json');labels=read_checked(folder,m,'evaluation_labels.json')
                if ev['rows']!=labels['rows']:raise ValueError('标签日期错配')
                training=json.loads((folder/'training.json').read_text('utf8'));pred=json.loads((folder/'predictions.json').read_text('utf8'))
                if training['preparation_sha256']!=file_sha(folder/'preparation.json'):raise ValueError('训练输入变化')
                names={k:v['name'] for k,v in training['models'].items()};y=np.asarray(labels['y']);base=np.asarray(pred['ewma']['evaluation']);groups=[spec['fold']]*len(y);fm={}
                for k in names:
                    p=np.asarray(pred[k]['evaluation']);fm[k]={'name':names[k],'metrics':metrics(y,p,annual),'comparison':comparison(y,p,base,groups)}
                for i,row in enumerate(ev['rows']):
                    observations.append({'session':row['signal_session'],'label_end':row['label_end'],'fold':spec['fold'],'regime':regime_key(ev['x'][i],list(m['regime_thresholds'][k] for k in ('low','high'))),'realized_variance':float(y[i]),'predictions':{k:float(pred[k]['evaluation'][i]) for k in names}})
                foldresults.append({'fold':spec['fold'],'bounds':spec,'counts':m['counts'],'purged':m['purged'],'regime_thresholds':m['regime_thresholds'],'models':fm,'training':training})
            y=np.array([r['realized_variance'] for r in observations]);folds=[r['fold'] for r in observations];pred={k:np.array([r['predictions'][k] for r in observations]) for k in names};base=pred['ewma'];overall={};regimes={}
            for k in names:
                overall[k]={'name':names[k],'metrics':metrics(y,pred[k],annual),'comparison':comparison(y,pred[k],base,folds),'folds':8,'wins_vs_ewma':sum(f['models'][k]['comparison']['delta_qlike']<0 for f in foldresults)}
            for key,name in REGIMES.items():
                mask=np.array([r['regime']==key for r in observations]);n=int(mask.sum())
                regimes[key]={'name':name,'rows':n,'sufficient':n>=30,'models':{k:{'name':names[k],'metrics':metrics(y[mask],pred[k][mask],annual) if n else None,'comparison':comparison(y,pred[k],base,folds,mask) if n else None} for k in names}}
            identity={'market':market,'horizon':str(h),'dataset_sha256':protocol['datasets'][market],'protocol_sha256':digest(protocol)}
            record={'schema':'volatility-result-v1','run_id':'volatility-'+digest(identity),'identity':identity,'created_at':frozen['created_at'],'market':market,'instrument':dataset['snapshot']['instrument'],'currency':'CNY' if market=='ashare' else 'USDT','horizon':h,'annualization':annual,'dataset_sha256':identity['dataset_sha256'],'dataset':dataset,'protocol':protocol,'folds':foldresults,'overall':overall,'regimes':regimes,'observations':observations,'artifacts':artifacts,'phase_receipts':{'frozen_sha256':file_sha(root/'frozen.json'),'evaluation_labels_read_for_fitting':False},
                'limitations':['日线收益平方仅为零均值下条件二阶矩的噪声代理，不是高频实现方差。','2024–2025已被研究，属于历史重建而非未知盲测；单股/单币不能代表全市场。','5期目标为日均方，窗口重叠；区间按季度内20行块配对抽样，市况随后筛选。','市况以当时已知20期波动及60期趋势定义，阈值仅train；不足30条保留但不下稳定结论。','QLIKE可负，越低越好；区间为探索性逐比较95%区间，未做多重检验或MCS确认。','波动不表示涨跌方向，未由此进行实盘交易或收益承诺。','GARCH是自实现受约束正态QMLE；HAR为收益平方代理的多尺度非负回归，并非原版高频HAR-RV。']}
            VolatilityResult.model_validate(record)
            write_json(PROJECT/'backend/data/volatility-runs'/(record['run_id']+'.json'),{'record':record,'sha256':digest(record)})
            summary={k:record[k] for k in ('run_id','market','horizon','created_at','overall','regimes')};summary['rows']=len(observations);summaries.append(summary)
            print(json.dumps({'scored':market,'horizon':h,'rows':len(y),'qlike':{k:v['metrics']['qlike'] for k,v in overall.items()}},ensure_ascii=False),flush=True)
    write_json(root/'summary.json',{'runs':summaries})
    write_json(PROJECT/'docs/research'/('2026-11-04-volatility-'+digest(summaries)[:12]+'.json'),{'artifact_root':root.relative_to(PROJECT).as_posix(),'runs':summaries})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);score(p.parse_args().root)
