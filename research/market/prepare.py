import json
import sys
import platform
from importlib.metadata import version
from pathlib import Path
from research.market.common import PROJECT,CONFIG,code_manifest,digest,file_sha,write_json

sys.path.insert(0,str(PROJECT/'backend/src'))
from platform_app.adapters.public_market import IDS,load_dataset
from platform_app.contracts.models import stable_hash
from platform_app.experiments.forecast_data import make_samples,split_samples


def prepare():
    config=json.loads(CONFIG.read_text('utf8'));code=code_manifest()
    datasets=[load_dataset(PROJECT/'backend/data/public-market',key) for key in IDS]
    hashes={d.snapshot.snapshot_id:stable_hash(d.model_dump(mode='json')) for d in datasets}
    identity={'config':config,'code':code,'datasets':hashes,'environment':{'python':platform.python_version(),
        **{name:version(name) for name in ('numpy','torch','lightgbm','scipy','pydantic','safetensors')}}}
    root=PROJECT/'research/artifacts/market-forecast'/('v1-'+digest(identity)[:24]);root.mkdir(parents=True,exist_ok=True)
    write_json(root/'identity.json',identity)
    for dataset in datasets:
        market=dataset.snapshot.market;target=root/market;rows=make_samples(dataset,config['lookback']);splits,purged=split_samples(rows);files={}
        if any(len(splits[k])<30 for k in splits):raise ValueError('时间区间样本不足，不填充演示成绩')
        for split,items in splits.items():
            features={'rows':[{k:v for k,v in item.items() if k not in ('x','target')} for item in items],
                      'x':[[float(v) for v in item['x']] for item in items]}
            if split=='evaluation':
                name='evaluation_features.json';write_json(target/name,features);files[name]=file_sha(target/name)
                name='evaluation_labels.json';write_json(target/name,{'rows':features['rows'],'y':[float(item['target']) for item in items]});files[name]=file_sha(target/name)
            else:
                features['y']=[float(item['target']) for item in items];name=split+'.json';write_json(target/name,features);files[name]=file_sha(target/name)
        name='dataset.json';write_json(target/name,dataset.model_dump(mode='json'));files[name]=file_sha(target/name)
        manifest={'schema':'market-preparation-v1','identity_sha256':digest(identity),'dataset_sha256':hashes[dataset.snapshot.snapshot_id],
            'dataset_id':dataset.snapshot.snapshot_id,'market':market,'config':config,'code_sources':code,'files':files,'purged':purged,
            'counts':{key:len(items) for key,items in splits.items()},'train_first_signal':splits['train'][0]['signal_session'],
            'train_last_signal':splits['train'][-1]['signal_session'],'evaluation_first_signal':splits['evaluation'][0]['signal_session'],
            'evaluation_last_signal':splits['evaluation'][-1]['signal_session'],'evaluation_labels_excluded_from_training':True}
        write_json(target/'preparation.json',manifest)
        print(json.dumps({'market':market,'counts':manifest['counts'],'purged':purged,'path':str(target)},ensure_ascii=False),flush=True)
    return root


if __name__=='__main__':print(prepare())
