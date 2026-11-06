"""One bounded, idempotent collection/prediction/settlement cycle; no training."""
import argparse,json,os,tempfile
from pathlib import Path
from research.market.common import PROJECT,digest,file_sha
from research.forward_market.journal import register,read_verified,record_prediction,settle,utcnow

ROOT=PROJECT/'research/artifacts/forward-market'
STATUS=PROJECT/'backend/data/forward-market/status.json'
SYMBOLS={'600519':'贵州茅台','600036':'招商银行','600585':'海螺水泥','BTCUSDT':'Bitcoin / USDT','ETHUSDT':'Ether / USDT'}
LIMITATIONS=['模型固定为D26最新时间折2025Q4，未重训，存在模型陈旧和分布变化风险。',
 '预测时间取实际接收及写入时间；历史行情修订不可改写已经登记的预测。',
 '仅验证单持有区间的收益平方预测，不是成交模拟或投资收益；样本少时不能判断模型有效。',
 'A股仅在已验证的年度交易日历内安排；分红事件来自公开提供者，完整性有局限。',
 '到期需等退出日完整日线收到后评分，因此不会在退出开盘立即显示成绩。']

def verify_snapshot(snapshot, root=ROOT):
    root=Path(root).resolve();path=Path(snapshot['snapshot_path']).resolve()
    if not path.is_relative_to(root):raise ValueError('快照路径越界')
    body={k:v for k,v in snapshot.items() if k not in ('snapshot_sha256','snapshot_path')}
    if digest(body)!=snapshot['snapshot_sha256'] or json.loads(path.read_text('utf8'))!=snapshot:raise ValueError('行情快照已变化')
    for evidence in snapshot['source_evidence']:
        if evidence.get('status')=='failed':continue
        raw=Path(evidence['file']).resolve()
        if not raw.is_relative_to(root) or file_sha(raw)!=evidence['sha256']:raise ValueError('原始行情来源已变化')

def publish(path, record):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps({'record':record,'sha256':digest(record)},ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)
    fd,tmp=tempfile.mkstemp(prefix='.status-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:Path(tmp).unlink(missing_ok=True)

def run_once():
    from research.forward_market.data import acquire
    from research.forward_market.inference import load_bundle,build_history,predict
    ROOT.mkdir(parents=True,exist_ok=True);lock=ROOT/'.cycle.lock'
    try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise RuntimeError('前向采集正在运行或遗留锁待检查，拒绝并发启动') from None
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    try:
        items=[];artifacts={};source_hashes={p.relative_to(PROJECT).as_posix():file_sha(p) for p in Path(__file__).parent.glob('*.py')}
        for symbol,name in SYMBOLS.items():
            item={'symbol':symbol,'name':name,'market':'crypto' if symbol.endswith('USDT') else 'ashare','state':'blocked',
                  'reason':'等待数据检查','latest_session':None,'source_retrieved_at':None,'forecast_count':0,'scored_count':0,'predictions':[]}
            snapshot=None
            try:
                bundle=load_bundle(symbol);artifacts.update(bundle['artifacts'])
                protocol=register(ROOT,{**bundle,'runtime_sources':source_hashes})
                snapshot=acquire(symbol,ROOT/'snapshots')
                verify_snapshot(snapshot)
                item['source_retrieved_at']=snapshot['retrieved_at']
                if snapshot['bars']:item['latest_session']=snapshot['bars'][-1]['session']
                if snapshot['status']!='ready':raise ValueError('；'.join(snapshot.get('reasons',[]) or ['公开行情资格未满足']))
                # Reconstruct full history even before launch, so ingestion is actually checked.
                history=build_history(bundle,snapshot,item['latest_session'])
                if item['latest_session']<'2026-11-06':
                    item.update(state='waiting_signal',reason='等待2026-11-06或之后的完整日线；不会补记起点之前的预测。')
                else:
                    folder=ROOT/protocol['protocol_id']
                    known=[read_verified(p) for p in folder.glob('prediction-*.json')]
                    if any(r['signal_session']==item['latest_session'] for r in known):
                        item.update(state='waiting_outcome',reason='本期预测已封存，等待持有区间结束及完整日线。')
                    else:
                        values=predict(bundle,history)
                        prediction={k:{m:values[m][k] for m in ('raw','calibrated')} for k in values['raw']}
                        if any(file_sha(PROJECT/name)!=sha for name,sha in source_hashes.items()):raise ValueError('运行期间前向源码变化，请用新版本重新运行')
                        verify_snapshot(snapshot)
                        record_prediction(ROOT,protocol,snapshot,prediction)
                        item.update(state='waiting_outcome',reason='冻结模型预测已记录，等待持有区间结束及完整日线。')
            except Exception as error:
                item.update(state='blocked',reason=str(error)[:500])
            # Include all immutable protocol versions; an upgrade never hides an older forecast.
            for folder in sorted(ROOT.glob('forward-*')):
                protocol=read_verified(folder/'protocol.json')
                if protocol['identity']['bundle']['symbol']!=symbol:continue
                artifacts.update(protocol['identity']['bundle'].get('artifacts',{}))
                for path in sorted(folder.glob('prediction-*.json')):
                    forecast=read_verified(path);outcome=None
                    outcome_path=folder/('outcome-'+forecast['forecast_id'][11:]+'.json')
                    if outcome_path.exists():
                        outcome=read_verified(outcome_path)
                        if outcome['forecast_sha256']!=digest(forecast):raise ValueError('既有结果与原预测不符')
                    elif snapshot and snapshot['status']=='ready':
                        try:
                            verify_snapshot(snapshot)
                            outcome=settle(ROOT,forecast,snapshot)
                        except Exception as error:item.update(state='blocked',reason='到期核验失败：'+str(error)[:400])
                    shown={k:forecast[k] for k in ('forecast_id','signal_session','created_at','decision_at','entry_at','exit_at','predictions')}
                    shown['outcome']={k:outcome[k] for k in ('realized_variance','log_return','scored_at','errors')} if outcome else None
                    item['predictions'].append(shown)
            item['predictions'].sort(key=lambda r:(r['signal_session'],r['created_at']))
            item['forecast_count']=len(item['predictions']);item['scored_count']=sum(r['outcome'] is not None for r in item['predictions'])
            if item['forecast_count'] and item['scored_count']==item['forecast_count'] and item['state']!='blocked':
                item.update(state='scored',reason='已登记预测全部到期核验；等待下一期完整日线。')
            items.append(item);print(json.dumps({k:item[k] for k in ('symbol','state','reason','latest_session','forecast_count','scored_count')},ensure_ascii=False),flush=True)
        for path in ROOT.rglob('snapshot.json'):verify_snapshot(json.loads(path.read_text('utf8')))
        for path in ROOT.rglob('*'):
            if path.is_file() and not path.name.startswith('.'):
                artifacts[path.relative_to(PROJECT).as_posix()]=file_sha(path)
        state='blocked' if all(i['state']=='blocked' for i in items) else 'active' if any(i['forecast_count'] for i in items) else 'waiting'
        record={'schema':'forward-market-status-v1','updated_at':utcnow().isoformat(),'status':state,'items':items,'limitations':LIMITATIONS,'artifacts':artifacts}
        publish(STATUS,record);return record
    finally:lock.unlink(missing_ok=True)

if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    run_once()
