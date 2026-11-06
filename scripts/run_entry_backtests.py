"""Run and save both frozen default comparisons through the actual local API."""
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8010/api/v1/backtests'


def call(path,body=None):
    request=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=90) as response:return response.status,json.load(response)


if __name__=='__main__':
    _,catalog=call('/datasets')
    if len(catalog['datasets'])!=2 or catalog['unavailable']:raise RuntimeError('两市场快照必须同时就绪')
    receipts=[]
    for dataset in catalog['datasets']:
        body={'dataset_id':dataset['dataset_id'],'expected_dataset_sha256':dataset['dataset_sha256'],'config':dataset['default_config']}
        status,record=call('/compare',body);replay,again=call('/compare',body)
        assert replay==200 and record==again
        r=record['result']
        summary={key:r[key] for key in ('dataset_id','dataset_sha256','engine_sha256','engine_sources','engine_runtime','input_sha256','config','evaluation','quality','rules','limitations')}
        summary.update(run_id=record['run_id'],created_at=record['created_at'],api_status=status,replay_status=replay,
            receipt_count=len(record['dataset']['receipts']),strategies={k:{'metrics':s['metrics'],'annual':s['annual'],
                'worst_relative_window':s['worst_relative_window'],'first_trade':s['trades'][:1],'last_trade':s['trades'][-1:]} for k,s in r['strategies'].items()})
        receipts.append(summary)
        print(json.dumps({'market':r['market'],'run_id':record['run_id'],'metrics':{k:v['metrics'] for k,v in r['strategies'].items()}},ensure_ascii=False))
    target=ROOT/'docs/research/2026-10-30-entry-backtest-results.json'
    target.write_text(json.dumps({'schema':'entry-backtest-receipt-v1','results':receipts},ensure_ascii=False,indent=2),encoding='utf8')
