"""Separate, post-prediction scoring process. Publishes a read-only local bundle."""
import argparse
from datetime import datetime,timezone,date
from decimal import Decimal,localcontext
import json
from pathlib import Path
import sys
import numpy as np
from research.market.common import PROJECT,code_manifest,digest,file_sha,read_checked,write_json
from research.market.evaluate import metrics,paired_block_interval

sys.path.insert(0,str(PROJECT/'backend/src'))
from platform_app.contracts.public_backtests import PublicDataset
from platform_app.contracts.models import stable_hash
from platform_app.experiments.backtest import default_config,signals,simulate

MAIN_METHODS=['zero','train_mean','last_return','ridge','lightgbm','dlinear_ensemble']
NAMES={'zero':'零收益基线','train_mean':'训练均值','last_return':'上一期收益','ridge':'岭回归','lightgbm':'LightGBM','dlinear_ensemble':'DLinear 三种子集成',
       'dlinear_42':'DLinear 种子42','dlinear_43':'DLinear 种子43','dlinear_44':'DLinear 种子44','buy_hold':'同区间买入持有'}


def policy(dataset,rows,prediction,lookback):
    cfg=default_config(dataset).model_copy(update={'start':date.fromisoformat(rows[0]['entry_session']),
        'end':date.fromisoformat(rows[-1]['exit_session']),'window':lookback})
    targets={row['signal_session']:{'target':int(value>0),'decision_at':row['decision_at']} for row,value in zip(rows,prediction)}
    all_signals=signals(dataset,cfg);snapshot=dataset.snapshot
    indices=[i for i,d in enumerate(snapshot.sessions) if cfg.start<=d<=cfg.end]
    lag=1 if snapshot.market=='ashare' else 2;closure=all_signals[indices[-1]-lag]
    targets[closure['session']]={'target':0,'decision_at':closure['decision_at']}
    with localcontext() as ctx:
        ctx.prec=40;result=simulate(dataset,cfg,all_signals,indices,'forecast',targets=targets)
    return {'config':cfg.model_dump(mode='json'),'closure':'预先固定在最后可评分退出日开盘目标清仓；非期末收盘市值比较',**result}


def score_market(root):
    m=json.loads((root/'preparation.json').read_text('utf8'))
    if m['code_sources']!=code_manifest():raise ValueError('代码已变化，不能把旧训练归到新方法')
    training=json.loads((root/'training.json').read_text('utf8'));predictions=json.loads((root/'predictions.json').read_text('utf8'))
    if training['preparation_sha256']!=file_sha(root/'preparation.json') or predictions['preparation_sha256']!=training['preparation_sha256'] or predictions['training_sha256']!=file_sha(root/'training.json'):
        raise ValueError('预测与训练/准备版本不一致')
    for name,sha in training['artifacts'].items():
        if file_sha(root/name)!=sha:raise ValueError('模型产物已变化')
    dataset=PublicDataset.model_validate(read_checked(root,m,'dataset.json'))
    if stable_hash(dataset.model_dump(mode='json'))!=m['dataset_sha256']:raise ValueError('原行情快照身份变化')
    val=read_checked(root,m,'validation.json');labels=read_checked(root,m,'evaluation_labels.json')
    evaluation=predictions['outputs']['evaluation_features'];validation=predictions['outputs']['validation']
    if evaluation['rows']!=labels['rows'] or validation['rows']!=val['rows']:raise ValueError('标签与预测日期/执行时点不一致')
    y=np.array(labels['y']);models={};rows=labels['rows'];cfg=m['config']
    for name,pred in evaluation['predictions'].items():
        p=np.asarray(pred);model={'name':NAMES[name],'evaluation':metrics(y,p),'validation':metrics(val['y'],validation['predictions'][name]),
            'mse_difference_interval':paired_block_interval(y,p,**cfg['bootstrap']),'annual':[]}
        for year in ('2024','2025'):
            mask=np.array([row['signal_session'].startswith(year) for row in rows]);model['annual'].append({'year':year,**metrics(y[mask],p[mask])})
        if name in MAIN_METHODS:model['policy']=policy(dataset,rows,p,cfg['lookback'])
        models[name]=model
    benchmark=policy(dataset,rows,np.ones(len(rows)),cfg['lookback'])
    artifacts={name:file_sha(root/name) for name in ['preparation.json','training.json','predictions.json','evaluation_labels.json',*training['artifacts']]}
    identity=json.loads((root.parent/'identity.json').read_text('utf8'))
    identity_sha=digest(identity)
    if identity_sha!=m['identity_sha256']:raise ValueError('运行身份改变')
    result={'schema':'market-forecast-result-v1','market':m['market'],'dataset_id':m['dataset_id'],'instrument':dataset.snapshot.instrument,
        'currency':dataset.snapshot.currency,'dataset_sha256':m['dataset_sha256'],'config':cfg,'counts':m['counts'],'purged':m['purged'],
        'scaler':training['scaler'],'training':training,'models':models,'benchmark':benchmark,
        'evaluation':{'first_signal':rows[0]['signal_session'],'last_signal':rows[-1]['signal_session'],'rows':len(rows),
            'first_entry':rows[0]['entry_session'],'last_exit':rows[-1]['exit_session']},
        'observations':[{'signal_session':row['signal_session'],'decision_at':row['decision_at'],'entry_session':row['entry_session'],'exit_session':row['exit_session'],
            'actual_return':float(actual),'predictions':{key:float(value[i]) for key,value in evaluation['predictions'].items()}} for i,(row,actual) in enumerate(zip(rows,y))],
        'environment':identity['environment'],'code_sources':m['code_sources'],'artifacts':artifacts,'artifact_directory':root.relative_to(PROJECT).as_posix(),
        'dataset':dataset.model_dump(mode='json'),'prediction_sha256':file_sha(root/'predictions.json'),'preparation_sha256':file_sha(root/'preparation.json'),
        'training_sha256':file_sha(root/'training.json'),'labels_sha256':file_sha(root/'evaluation_labels.json'),
        'limitations':list(dataset.snapshot.limitations)+[
            '预测目标为下一可执行open到下一open的税前总收益，非明天收盘价；预测评分不含交易成本，仓位账户单独扣费用。',
            '同一60期已知日收益输入；X全局均值/std、y均值/std仅拟合训练矩阵；树与神经模型只用验证损失早停。',
            '2024–2025价格此前已用于规则回放，本次为冻结协议下历史评估，不是未见过的盲测。样本重叠且存在时间依赖。',
            'DLinear为原结构的收益任务适配、122参数线性分解模型；三种子均值集成不挑最好种子，也不构成三个独立市场样本。',
            '方向命中只评价实际非零日；预测恰为0表示中性，不当作涨跌命中。时序Pearson不是横截面IC，常量相关为未知。',
            '20期移动块bootstrap区间为探索性MSE差估计，不能等同收益显著性、因果效果或多次比较校正。',
            '仓位阈值固定0；同区间买入持有与预测策略在最后可评分退出日开盘尝试清仓，实际拒单继续留痕；不能直接与上一轮不同起止日期/尾仓的规则收益排名。',
            '仅一步收益预测；波动预测、walk-forward再训练、多标的、预训练模型仍未开展。']}
    result['run_id']='forecast-'+digest({'dataset_sha256':m['dataset_sha256'],'preparation_sha256':result['preparation_sha256'],
        'training_sha256':result['training_sha256'],'prediction_sha256':result['prediction_sha256'],'labels_sha256':result['labels_sha256']})
    result['created_at']=training['finished_at']
    return result


def score_publish(root):
    root=Path(root).resolve()
    if not root.is_relative_to((PROJECT/'research/artifacts/market-forecast').resolve()):raise ValueError('评分目录必须位于本项目隔离产物目录')
    published=[];folder=PROJECT/'backend/data/forecast-runs'
    for market in ('ashare','btc'):
        result=score_market(root/market);envelope={'sha256':digest(result),'record':result}
        write_json(folder/(result['run_id']+'.json'),envelope)
        summary={key:result[key] for key in ('run_id','created_at','market','instrument','dataset_sha256','counts','purged','evaluation','environment','prediction_sha256','preparation_sha256','training_sha256')}
        summary['models']={name:{'evaluation':value['evaluation'],'validation':value['validation'],'mse_difference_interval':value['mse_difference_interval'],
            'policy_metrics':value.get('policy',{}).get('metrics')} for name,value in result['models'].items()}
        published.append(summary);print(json.dumps({'market':market,'published':result['run_id'],'metrics':{k:v['evaluation']['rmse'] for k,v in result['models'].items()}},ensure_ascii=False),flush=True)
    write_json(root/'summary.json',{'runs':published})
    report=PROJECT/'docs/research'/('2026-10-30-market-forecast-'+digest(published)[:12]+'.json')
    write_json(report,{'schema':'market-forecast-receipt-v1','artifact_root':root.relative_to(PROJECT).as_posix(),'runs':published})
    return published


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();score_publish(args.root)
