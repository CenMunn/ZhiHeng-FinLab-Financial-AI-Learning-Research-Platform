"""Post-freeze rolling evaluation and a continuous, costed cash account."""
import argparse,json,sys
from pathlib import Path
from datetime import date
from decimal import Decimal,localcontext
import numpy as np
from research.rolling.common import PROJECT,sources,digest,file_sha,write_json,read_checked,verify_files
from research.market.evaluate import metrics,paired_block_interval
from research.rolling.acquire import MODEL,verify_model_files

sys.path.insert(0,str(PROJECT/'backend/src'))
from platform_app.contracts.public_backtests import PublicDataset
from platform_app.contracts.market_experiments import CostAssumptions
from platform_app.contracts.models import stable_hash
from platform_app.experiments.backtest import default_config,signals,simulate

MAIN=['zero','train_mean','last_return','ridge','lightgbm','dlinear_ensemble','enhanced']
NAMES={'zero':'零收益','train_mean':'训练均值','last_return':'最近已知收益','ridge':'岭回归','lightgbm':'LightGBM','dlinear_ensemble':'DLinear三种子集成',
    'enhanced':'LightGBM＋特征组','chronos':'冻结Chronos＋岭读出','random_encoder':'随机T5编码器＋岭读出',
    'without_momentum':'剔除动量','without_volatility':'剔除波动','without_bar_shape':'剔除K线形态','without_drawdown':'剔除回撤'}


def continuous_policy(dataset,folds,method,multiplier=1,signal_rows=None):
    first=folds[0]['rows'][0]['entry_session'];last=folds[-1]['rows'][-1]['exit_session'];base=default_config(dataset)
    costs=base.costs.model_dump();costs={key:format(Decimal(value)*multiplier,'f') if key!='kind' else value for key,value in costs.items()}
    config=base.model_copy(update={'start':date.fromisoformat(first),'end':date.fromisoformat(last),'window':60,'costs':CostAssumptions.model_validate(costs)})
    with localcontext() as ctx:
        ctx.prec=40
        all_signals=signal_rows or signals(dataset,config);lag=1 if dataset.snapshot.market=='ashare' else 2
        indices=[i for i,d in enumerate(dataset.snapshot.sessions) if first<=str(d)<=last]
        targets={all_signals[i-lag]['session']:{'target':int(method=='buy_hold'),'decision_at':all_signals[i-lag]['decision_at']} for i in indices}
        if method!='buy_hold':
            for fold in folds:
                values=[1]*len(fold['rows']) if method=='quarterly_hold' else fold['predictions'][method]
                if len(values)!=len(fold['rows']):raise ValueError('冻结预测和执行日数量不一致')
                for row,pred in zip(fold['rows'],values):targets[row['signal_session']]={'target':int(pred>0),'decision_at':row['decision_at']}
                end=dataset.snapshot.sessions.index(date.fromisoformat(fold['rows'][-1]['exit_session']));closure=all_signals[end-lag]
                targets[closure['session']]={'target':0,'decision_at':closure['decision_at']}
        else:
            closure=all_signals[indices[-1]-lag];targets[closure['session']]={'target':0,'decision_at':closure['decision_at']}
        result=simulate(dataset,config,all_signals,indices,'forecast',targets=targets)
    return {'config':config.model_dump(mode='json'),'multiplier':multiplier,'boundary':'cash in purged gaps, target exit at each quarter boundary; continuous capital',**result}


def verify_phase(root,name):
    body=json.loads((root/name).read_text('utf8'))
    verify_files(root,body['files'])
    return body


def aggregate(folds,methods):
    y=np.concatenate([f['actual'] for f in folds]);answer={}
    for method in methods:
        p=np.concatenate([f['predictions'][method] for f in folds])
        answer[method]={'name':NAMES.get(method,method),'metrics':metrics(y,p),
            'wins_vs_zero':sum(metrics(f['actual'],f['predictions'][method])['rmse']<metrics(f['actual'],np.zeros(len(f['rows'])))['rmse'] for f in folds),'folds':len(folds)}
    return answer


def score_market(root,market,identity,base_phase,pretrain_phase):
    dataset=PublicDataset.model_validate(json.loads((root/market/'dataset.json').read_text('utf8')))
    if stable_hash(dataset.model_dump(mode='json'))!=identity['datasets'][market]:raise ValueError('公开数据身份错配')
    fold_data=[];artifacts={};fold_reports=[]
    for spec in identity['folds']:
        folder=root/market/spec['fold'];m=json.loads((folder/'preparation.json').read_text('utf8'))
        if m['identity_sha256']!=digest(identity) or m['rolling_sources']!=sources():raise ValueError('滚动准备版本错配')
        labels=read_checked(folder,m,'evaluation_labels.json');base=json.loads((folder/'predictions.json').read_text('utf8'));training=json.loads((folder/'training.json').read_text('utf8'))
        if base['preparation_sha256']!=file_sha(folder/'preparation.json') or base['training_sha256']!=file_sha(folder/'training.json'):raise ValueError('预测/模型指纹错配')
        if labels['rows']!=base['outputs']['evaluation_features']['rows']:raise ValueError('评估标签未与预测对齐')
        for name,sha in training['artifacts'].items():
            if file_sha(folder/name)!=sha:raise ValueError('原模型权重变化')
        diagnostic=json.loads((folder/'diagnostics.json').read_text('utf8'))
        for name,sha in diagnostic['artifacts'].items():
            if file_sha(folder/name)!=sha:raise ValueError('增强/消融模型变化')
        prediction=dict(base['outputs']['evaluation_features']['predictions'])
        prediction.update({name:values['evaluation_features'] for name,values in diagnostic['predictions'].items()})
        if spec['fold'].startswith('2025'):
            pretrained=json.loads((folder/'pretrained-predictions.json').read_text('utf8'))
            if pretrained['preparation_sha256']!=file_sha(folder/'preparation.json') or pretrained['heads_sha256']!=file_sha(folder/'pretrained-heads.json') or pretrained['acquisition_sha256']!=file_sha(MODEL/'acquisition.json'):raise ValueError('预训练读出指纹错配')
            prediction.update({name:values['evaluation_features'] for name,values in pretrained['predictions'].items()})
        fold={'fold':spec['fold'],'rows':labels['rows'],'actual':labels['y'],'predictions':prediction}
        report={'fold':spec['fold'],'bounds':spec,'counts':m['counts'],'purged':m['purged'],'models':{},'diagnostics':{k:diagnostic[k] for k in ('validation_permutation','label_free_drift','group_selection')},
            'training':{'lightgbm_best_iteration':training['models']['lightgbm']['best_iteration'],'dlinear':{key:{k:value[k] for k in ('best_epoch','epochs','updates','device','elapsed_seconds')} for key,value in training['models'].items() if key.startswith('dlinear_')}}}
        for name,values in prediction.items():
            measured=metrics(labels['y'],values);report['models'][name]={'name':NAMES.get(name,name),'metrics':measured}
            if name in MAIN or name in ('chronos','random_encoder'):report['models'][name]['mse_difference_interval']=paired_block_interval(labels['y'],values)
        fold_data.append(fold);fold_reports.append(report)
        # Bind model and preparation files, not just aggregate scores. No pickle.
        names=set(m['files'])|set(training['artifacts'])|set(diagnostic['artifacts'])|{'preparation.json','training.json','predictions.json','diagnostics.json'}
        if spec['fold'].startswith('2025'):names|={'pretrained-heads.json','pretrained-predictions.json'}
        for name in names:artifacts[(folder/name).relative_to(PROJECT).as_posix()]=file_sha(folder/name)
    sessions=[r['signal_session'] for f in fold_data for r in f['rows']]
    if sessions!=sorted(set(sessions)):raise ValueError('滚动评估日期重叠、重复或乱序')
    common=[key for key in fold_data[0]['predictions'] if key not in ('chronos','random_encoder')];overall=aggregate(fold_data,common)
    cohort=[fold for fold in fold_data if fold['fold'].startswith('2025')];cohort_models=aggregate(cohort,[*MAIN,'chronos','random_encoder']);cohort_sensitivity={}
    signal_rows=signals(dataset,default_config(dataset).model_copy(update={'window':60}));policies={};sensitivity={};cohort_policies={}
    for key in [*MAIN,'buy_hold','quarterly_hold']:
        policies[key]=continuous_policy(dataset,fold_data,key,1,signal_rows)
        if key in MAIN:
            sensitivity[key]={str(mult):continuous_policy(dataset,fold_data,key,mult,signal_rows)['metrics'] for mult in (0,1,2)}
    for key in [*MAIN,'chronos','random_encoder','buy_hold','quarterly_hold']:
        cohort_policies[key]=continuous_policy(dataset,cohort,key,1,signal_rows)
        if key not in ('buy_hold','quarterly_hold'):cohort_sensitivity[key]={str(mult):continuous_policy(dataset,cohort,key,mult,signal_rows)['metrics'] for mult in (0,1,2)}
    for file in (root/market/'embeddings').glob('*'):
        if file.is_file():artifacts[file.relative_to(PROJECT).as_posix()]=file_sha(file)
    for name in ('acquisition.json','config.json','generation_config.json','README.md','model.safetensors'):artifacts[(MODEL/name).relative_to(PROJECT).as_posix()]=file_sha(MODEL/name)
    for name in ('identity.json','base-phase.json','pretrained-phase.json'):artifacts[(root/name).relative_to(PROJECT).as_posix()]=file_sha(root/name)
    for name in ('dataset.json','contexts.json'):artifacts[(root/market/name).relative_to(PROJECT).as_posix()]=file_sha(root/market/name)
    run_identity={'market':market,'dataset_sha256':identity['datasets'][market],'protocol_sha256':digest(identity),
        'base_phase_sha256':file_sha(root/'base-phase.json'),'pretrained_phase_sha256':file_sha(root/'pretrained-phase.json')}
    observations=[{'fold':f['fold'],**row,'actual_return':float(f['actual'][i]),'predictions':{k:float(p[i]) for k,p in f['predictions'].items()}} for f in fold_data for i,row in enumerate(f['rows'])]
    return {'schema':'rolling-result-v1','run_id':'rolling-'+digest(run_identity),'identity':run_identity,'created_at':pretrain_phase['finished_at'],'market':market,
        'instrument':dataset.snapshot.instrument,'currency':dataset.snapshot.currency,'dataset_sha256':identity['datasets'][market],'dataset':dataset.model_dump(mode='json'),
        'protocol':identity,'folds':fold_reports,'overall':overall,'policies':policies,'cost_sensitivity':sensitivity,'observations':observations,
        'pretrained':{'cohort':'2025 four quarters only','models':cohort_models,'policies':cohort_policies,'cost_sensitivity':cohort_sensitivity,'acquisition':json.loads((MODEL/'acquisition.json').read_text('utf8')),
            'encoders':{key:json.loads((root/market/'embeddings'/(key+'.json')).read_text('utf8')) for key in ('chronos','random_encoder')}},
        'phase_receipts':{'base':base_phase,'pretrained':pretrain_phase},'artifacts':artifacts,
        'limitations':list(dataset.snapshot.limitations)+[
            '历史滚动验证，2024–2025已被研究过；不是未见盲测。时间折/日收益有关联，折胜率不能当独立试验概率。',
            '每折train扩展，validation为此前一年；标签entry/exit不跨段，统计仅拟合train，验证用于早停/置换，不用评估标签选特征。',
            '增强LightGBM输入为60收益＋8个固定特征；属于输入消融实验，不能把差异单独归因于模型架构。',
            'PSI仅分布诊断，训练分位边界固定；分组块置换会受相关特征影响，不是因果贡献。',
            '总体RMSE由全部逐条误差计算，非各折RMSE平均；区间只在各折内配对重采样，不跨折假装独立。',
            '资金账本连续，季度最后可评分退出日目标现金，标签清除间隙现金，拒单继续保留；另给跨季度持有与同协议季度持有基准。',
            '成本0/1/2倍敏感性复用同一冻结预测，不是重新调阈值；含期末估值及A股税前不可再投应收。',
            'Chronos固定2024-03-27 checkpoint，仅评价2025；具体训练截止及早期金融重叠未知。',
            '预训练与随机T5控制均冻结编码器，同60期输入，257维表示＋训练段alpha10岭读出。不是零样本收益预测或基座微调。',
            '2025预训练比较只用共同四折同一行集合，不能和2024–2025全部样本直接排名；未证明未来收益或跨股票泛化。']}


def score(root):
    root=Path(root).resolve();allowed=(PROJECT/'research/artifacts/rolling').resolve()
    if not root.is_relative_to(allowed):raise ValueError('评分目录越界')
    identity=json.loads((root/'identity.json').read_text('utf8'))
    if identity['sources']!=sources():raise ValueError('滚动源码版本已变化')
    base=verify_phase(root,'base-phase.json');pre=verify_phase(root,'pretrained-phase.json')
    verify_files(MODEL,pre['model_files']);verify_model_files(json.loads((MODEL/'acquisition.json').read_text('utf8')))
    if base['identity_sha256']!=digest(identity) or pre['base_phase_sha256']!=file_sha(root/'base-phase.json') or pre['encoder_acquisition_sha256']!=file_sha(MODEL/'acquisition.json'):raise ValueError('阶段身份错配')
    summaries=[]
    for market in ('ashare','btc'):
        record=score_market(root,market,identity,base,pre);write_json(PROJECT/'backend/data/rolling-runs'/(record['run_id']+'.json'),{'sha256':digest(record),'record':record})
        summary={key:record[key] for key in ('run_id','created_at','market','instrument','identity','overall','folds','cost_sensitivity')}
        summary['pretrained']={key:record['pretrained'][key] for key in ('cohort','models','encoders','acquisition')};summary['policies']={key:value['metrics'] for key,value in record['policies'].items()}
        summary['pretrained_policy_metrics']={key:value['metrics'] for key,value in record['pretrained']['policies'].items()};summaries.append(summary)
        print(json.dumps({'scored':market,'rows':len(record['observations']),'rmse':{k:v['metrics']['rmse'] for k,v in record['overall'].items()}},ensure_ascii=False),flush=True)
    write_json(root/'summary.json',{'runs':summaries})
    write_json(PROJECT/'docs/research'/('2026-10-30-rolling-'+digest(summaries)[:12]+'.json'),{'artifact_root':root.relative_to(PROJECT).as_posix(),'runs':summaries})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();score(args.root)
