"""D26 independent target scoring and deterministic risk-budget accounts."""
import argparse,json,sys
from pathlib import Path
import numpy as np
from research.market.common import PROJECT,digest,file_sha,write_json
from research.volatility.metrics import metrics,paired_comparison
from research.five_asset.score import verify_calibration
from research.risk_budget.shadow import register
sys.path.insert(0,str(PROJECT/'backend/src'))

ENGINE='backend/src/platform_app/experiments/risk_budget.py'
STRATEGIES=('hold_full','fixed_risk','ewma_raw','ewma_calibrated','lightgbm_raw','lightgbm_calibrated','dlinear_raw','dlinear_calibrated')

def score(root):
    from research.risk_budget.common import sources,verify,environment
    from platform_app.adapters.validation_foundation_store import ValidationFoundationStore
    from platform_app.experiments.risk_budget import simulate
    root=Path(root).resolve()
    if not root.is_relative_to((PROJECT/'research/artifacts/risk-budget').resolve()):raise ValueError('评分目录越界')
    protocol=json.loads((root/'protocol.json').read_text('utf8'));frozen=json.loads((root/'frozen.json').read_text('utf8'));inputs=json.loads((root/'inputs.json').read_text('utf8'))
    if protocol['sources']!=sources() or protocol['environment']!=environment() or frozen['protocol_sha256']!=digest(protocol) or frozen['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('风险实验代码/环境/输入身份变化')
    verify(root,inputs['files']);verify(root,frozen['files'])
    source=json.loads((root/'source.json').read_text('utf8'));current=ValidationFoundationStore(PROJECT/'backend/data/validation-foundation',PROJECT).get(protocol['source_report_id'])
    if current['record_sha256']!=protocol['source_report_sha256'] or source['record_sha256']!=current['record_sha256'] or current['artifact_status']!='verified':raise ValueError('资格源已变化或缺失')
    artifacts={root.relative_to(PROJECT).as_posix()+'/'+n:sha for n,sha in frozen['files'].items()};artifacts[root.relative_to(PROJECT).as_posix()+'/frozen.json']=file_sha(root/'frozen.json')
    summaries=[]
    for asset in source['record']['assets']:
        if asset['status']!='qualified':continue
        symbol=asset['symbol'];dataset=json.loads((root/symbol/'dataset.json').read_text('utf8'));annual=252 if asset['market']=='ashare' else 365
        observations=[];folds=[];names={}
        for spec in asset['folds']:
            folder=root/symbol/spec['fold'];done=json.loads((folder/'completed.json').read_text('utf8'))
            if done['inputs_sha256']!=file_sha(root/'inputs.json'):raise ValueError('单元输入摘要变化')
            verify(folder,done['files']);training=json.loads((folder/'training.json').read_text('utf8'));prediction=json.loads((folder/'predictions.json').read_text('utf8'))
            ev=json.loads((folder/'evaluation_features.json').read_text('utf8'));labels=json.loads((folder/'evaluation_labels.json').read_text('utf8'));cal=json.loads((folder/'calibration.json').read_text('utf8'))
            if ev['rows']!=labels['rows'] or prediction['evaluation_labels_read'] is not False:raise ValueError('评估日期/隔离状态错配')
            names={k:v['name'] for k,v in training['models'].items()}
            if set(names)!=set(prediction['models']) or len(labels['y'])!=len(ev['rows']):raise ValueError('预测集合/标签数量错配')
            for key in names:
                verify_calibration(prediction['models'][key],cal['y'])
                if len(prediction['models'][key]['raw'])!=len(ev['rows']):raise ValueError('预测日期数量错配')
            for i,row in enumerate(ev['rows']):
                observations.append({**row,'fold':spec['fold'],'realized_variance':float(labels['y'][i]),'raw':{k:float(prediction['models'][k]['raw'][i]) for k in names},'calibrated':{k:float(prediction['models'][k]['calibrated'][i]) for k in names}})
            folds.append({'fold':spec['fold'],'bounds':training['bounds'],'counts':training['counts'],'training':training,'calibration':{k:{f:prediction['models'][k][f] for f in ('c','raw_c','clipped','calibration_rows')} for k in names}})
        y=np.array([r['realized_variance'] for r in observations]);groups=[r['fold'] for r in observations];base=np.array([r['raw']['ewma'] for r in observations]);models={}
        for key,name in names.items():
            raw=np.array([r['raw'][key] for r in observations]);cal=np.array([r['calibrated'][key] for r in observations])
            models[key]={'name':name,'raw':metrics(y,raw,annual),'calibrated':metrics(y,cal,annual),'raw_vs_ewma':paired_comparison(y,raw,base,groups),'calibrated_vs_ewma':paired_comparison(y,cal,base,groups),'calibrated_vs_raw':paired_comparison(y,cal,raw,groups)}
        scenarios={str(cost):{strategy:simulate(dataset,observations,strategy,'0.10',cost) for strategy in STRATEGIES} for cost in (0,1,2)}
        identity={'protocol_sha256':digest(protocol),'source_report_sha256':source['record_sha256'],'symbol':symbol};run_id='risk-'+digest(identity)
        shadow=register(PROJECT/'research/artifacts/risk-budget/shadow',run_id,digest(protocol));registry=Path(shadow['registry_file']);shadow['registry_file']=registry.relative_to(PROJECT).as_posix()
        record={'schema':'risk-budget-result-v1','run_id':run_id,'identity':identity,'created_at':frozen['created_at'],'symbol':symbol,'name':asset['name'],'market':asset['market'],'annualization':annual,'source_report_id':protocol['source_report_id'],'source_report_sha256':source['record_sha256'],'protocol':protocol,
            'dataset':dataset,'dataset_sha256':digest(dataset),'models':models,'folds':folds,'observations':observations,'scenarios':scenarios,'artifacts':{**artifacts,shadow['registry_file']:shadow['registry_sha256']},'shadow':shadow,
            'limitations':['预测目标已重训为可成交开盘到下一开盘的总收益平方，输入仅成熟open到open历史，不沿用D25收盘模型。','A股延后1交易日开盘、crypto延后2UTC开盘，严格晚于close+1分钟决策；是教学日线成交近似。','费用/步长/10%保守过滤是固定教学假设，不代表真实历史法定规则、竞价流动性或实际券商过滤器。','季度边界及清除间隙尝试现金；被拒绝的交易不假装完成，资金账本连续。','股息计税前不可再投应收；现金无利率、无做空和杠杆，风险不足可能由仓位上限及边界现金造成。','风险统计采用净开盘账户收益；不能把少持仓自然降低波动等同AI优势，应同时看fixed_risk参照。','独立校准只用calibration，早停只用early_stopping；四段和历史已研究背景保持。','5标的相关，不视为独立统计样本；历史收益不代表未来回报，未做多重模型确认检验。','前瞻仅注册/追加校验机制，未连接实时行情或自动推理，当前没有前瞻预测和成绩。']}
        write_json(PROJECT/'backend/data/risk-budget-runs'/(run_id+'.json'),{'record':record,'sha256':digest(record)})
        summary={k:record[k] for k in ('run_id','symbol','name','market','created_at','models')};summary['strategies']={k:v['metrics'] for k,v in scenarios['1'].items()};summary['rows']=len(observations);summaries.append(summary)
        print(json.dumps({'scored':symbol,'rows':len(observations),'risk':{k:v['metrics']['annualized_volatility'] for k,v in scenarios['1'].items()}},ensure_ascii=False),flush=True)
    write_json(PROJECT/'docs/research'/('2026-11-05-risk-budget-'+digest(summaries)[:12]+'.json'),{'artifact_root':root.relative_to(PROJECT).as_posix(),'runs':summaries})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);score(p.parse_args().root)
