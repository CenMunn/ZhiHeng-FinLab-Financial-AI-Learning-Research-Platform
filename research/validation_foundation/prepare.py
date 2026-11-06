import json,sys,re
from datetime import datetime,timezone
from pathlib import Path
from research.market.common import PROJECT,digest,file_sha,write_json
from research.validation_foundation.protocol import PROTOCOL,CANDIDATES,partition
from research.validation_foundation.qualify import inspect_dataset,samples

DATA=PROJECT/'research/artifacts/validation-data/v1'

def verify_receipts(data):
    if not data.get('receipts'):raise ValueError('缺少数据来源凭据')
    for r in data['receipts']:
        legacy=r.get('url') in ('legacy-public-market:ashare-600519-2018-2025','legacy-public-market:btc-btcusdt-2018-2025')
        if (not r.get('url','').startswith('https://') and not legacy) or not re.fullmatch('[a-f0-9]{64}',r.get('sha256','')) or datetime.fromisoformat(r['retrieved_at']).tzinfo is None:raise ValueError('来源凭据字段不完整')
        target=(DATA/r['file']).resolve()
        if not target.is_relative_to(DATA.resolve()) or not target.is_file() or file_sha(target)!=r['sha256']:raise ValueError('数据来源文件缺失/变化/越界')
        if r.get('publisher_checksum') and r['publisher_checksum']!=r['sha256']:raise ValueError('发布者CHECKSUM不一致')
        if legacy:
            source=json.loads(target.read_text('utf8'));proof=r.get('provenance',{})
            if proof.get('source_file_sha256')!=r['sha256'] or proof.get('source_dataset_sha256')!=digest(source['dataset']) or source['sha256']!=proof['source_dataset_sha256'] or not proof.get('legacy_receipts') or proof['legacy_receipts']!=source['dataset']['receipts']:raise ValueError('既有快照缺少可验证的原始来源链')

def snapshot_acquisition(source,root):
    write_json(root/'acquisition.json',json.loads(source.read_text('utf8')))

def preflight(data):
    rows={h:samples(data,h) for h in (1,5)};prepared=[]
    for f in PROTOCOL['folds']:
        for h in (1,5):
            parts,purged=partition(rows[h],f['bounds']);counts={k:len(v) for k,v in parts.items()}
            if min(counts.values())<20:raise ValueError('四段中存在不足20条样本的分区')
            prepared.append((f,h,parts,purged,counts))
    return prepared

def main():
    # Fixed protocol is recorded before acquisition inspection or sample selection.
    sources={p.relative_to(PROJECT).as_posix():file_sha(p) for p in (PROJECT/'research/validation_foundation').glob('*.py')}
    freeze=PROJECT/'research/artifacts/validation-foundation/protocol-freeze-20261105.json'
    frozen=json.loads(freeze.read_text('utf8'))
    if frozen['protocol_sha256']!=digest(PROTOCOL) or frozen['protocol']!=PROTOCOL:raise ValueError('协议已改变，必须显式建立新冻结版本，不能沿用本轮资格报告')
    acquisition=json.loads((DATA/'acquisition.json').read_text('utf8'))
    identity={'protocol_sha256':digest(PROTOCOL),'sources':sources,'acquisition_sha256':file_sha(DATA/'acquisition.json')};root=PROJECT/'research/artifacts/validation-foundation'/digest(identity)
    meta=root/'protocol.json'
    if meta.exists():created=json.loads(meta.read_text('utf8'))['frozen_at']
    else:created=datetime.now(timezone.utc).isoformat();write_json(meta,{'frozen_at':created,'identity':identity,'protocol':PROTOCOL})
    snapshot_acquisition(DATA/'acquisition.json',root)
    entries={a['symbol']:a for a in acquisition['assets']};assets=[]
    for candidate in CANDIDATES:
        a={**candidate,'status':'rejected','rows':0,'issues':[],'warnings':[],'coverage':{'expected':0,'missing':0,'extra':0},'events':{'dividends':0,'splits':0},'folds':[],'source_receipts':[]}
        entry=entries.get(a['symbol'])
        if not entry or entry['status']!='acquired':a['issues']=[entry.get('error','未取得数据') if entry else '候选未采集'];assets.append(a);continue
        try:
            path=(DATA/entry['dataset_file']).resolve()
            if not path.is_relative_to(DATA.resolve()):raise ValueError('数据路径越界')
            if file_sha(path)!=entry['dataset_sha256']:raise ValueError('采集登记的数据摘要变化')
            data=json.loads(path.read_text('utf8'));verify_receipts(data)
            if (data['symbol'],data['market'])!=(a['symbol'],a['market']):raise ValueError('标的身份错配')
            check=inspect_dataset(data);a.update(check);a['rows']=len(data['bars']);a['source_receipts']=data['receipts'];a['warnings']=data.get('warnings',[])
            if not a['issues']:
                prepared=preflight(data);a['status']='qualified'
                for f in PROTOCOL['folds']:
                    fold={**f,'horizons':[]}
                    for h in (1,5):
                        _,_,parts,purged,counts=next(p for p in prepared if p[0]['fold']==f['fold'] and p[1]==h);folder=root/a['symbol']/f['fold']/f'h{h}'
                        for key,items in parts.items():
                            features={'rows':[{k:v for k,v in r.items() if k not in ('x','target')} for r in items],'x':[r['x'] for r in items]}
                            if key=='evaluation':write_json(folder/'evaluation_labels.json',{'rows':features['rows'],'y':[r['target'] for r in items]});name='evaluation_features'
                            else:features['y']=[r['target'] for r in items];name=key
                            write_json(folder/(name+'.json'),features)
                        fold['horizons'].append({'horizon':h,'counts':counts,'purged':purged})
                    a['folds'].append(fold)
        except (ValueError,KeyError,TypeError,OSError) as exc:a['status']='rejected';a['issues'].append(str(exc));a['folds']=[]
        assets.append(a);print(json.dumps({'symbol':a['symbol'],'status':a['status'],'rows':a['rows'],'issues':a['issues']},ensure_ascii=False),flush=True)
    # Current mutable acquisition pointer never belongs to a historical report.
    for entry in entries.values():
        if entry['status']=='acquired':
            path=(DATA/entry['dataset_file']).resolve()
            if not path.is_relative_to(DATA.resolve()) or file_sha(path)!=entry['dataset_sha256']:raise ValueError('资格准备过程中输入数据变化')
            verify_receipts(json.loads(path.read_text('utf8')))
    qualified={a['symbol'] for a in assets if a['status']=='qualified'}
    artifacts={p.relative_to(PROJECT).as_posix():file_sha(p) for p in root.rglob('*') if p.is_file() and (len(p.relative_to(root).parts)==1 or p.relative_to(root).parts[0] in qualified)}
    artifacts.update({p.relative_to(PROJECT).as_posix():file_sha(p) for p in DATA.rglob('*') if p.is_file() and p!=DATA/'acquisition.json'})
    artifacts[freeze.relative_to(PROJECT).as_posix()]=file_sha(freeze)
    record={'schema':'validation-foundation-v1','created_at':created,'protocol':PROTOCOL,'protocol_sha256':digest(PROTOCOL),'assets':assets,'artifacts':artifacts,
        'limitations':['本轮是数据资格与四段准备，不包含模型训练/校准成绩或交易回放。','人工挑选当前存续标的，有选择与幸存偏差，不能代表历史市场。','公开重建日线、事件与close+1分钟是假设，不是历史PIT发布/接收日志。','原始公开数据仅本地使用，公开可访问不等于可任意再分发。','未支持的停牌缺日/拆股送转拒绝；拒绝标的不按成绩替换。','2024–2025已用于研究，不是未知盲测；2026-11-06起的前瞻观测尚未积累，无前瞻成绩。','多个标的受到共同市场冲击，不等同新增独立统计样本。']}
    record['report_id']='validation-'+digest({k:record[k] for k in ('protocol_sha256','assets','artifacts')})
    envelope={'record':record,'sha256':digest(record)}
    # Publish immutable per-report and atomic latest, retaining previous preparation reports.
    out=PROJECT/'backend/data/validation-foundation';write_json(out/'versions'/(record['report_id']+'.json'),envelope)
    tmp=out/(record['report_id']+'.tmp');write_json(tmp,envelope);tmp.replace(out/'latest.json')
    write_json(PROJECT/'docs/research'/('2026-11-05-validation-'+record['report_id'][-12:]+'.json'),{'report_id':record['report_id'],'protocol_sha256':record['protocol_sha256'],'assets':assets,'created_at':created,'artifact_root':root.relative_to(PROJECT).as_posix()})
    print(record['report_id'])

if __name__=='__main__':main()
