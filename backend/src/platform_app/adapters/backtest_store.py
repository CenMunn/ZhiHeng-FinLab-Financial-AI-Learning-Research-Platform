from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from platform_app.contracts.public_backtests import PublicDataset, BacktestConfig


class BacktestStore:
    """Independent table in the laboratory DB; self-contained historical snapshots."""
    def __init__(self,path:Path):self.path=Path(path)

    def _decode(self,payload,digest,expected_id):
        try:
            record=json.loads(payload)
            if record['run_id']!=expected_id or stable_hash(record)!=digest:raise ValueError('record checksum/key')
            dataset=PublicDataset.model_validate(record['dataset']);result=record['result']
            config=BacktestConfig.model_validate(result['config']);data_hash=stable_hash(dataset.model_dump(mode='json'))
            fingerprint=stable_hash({'dataset_sha256':data_hash,'config':config.model_dump(mode='json'),
                'engine_sha256':result['engine_sha256'],'runtime':result['engine_runtime']})
            if stable_hash(result['engine_sources'])!=result['engine_sha256']:raise ValueError('engine manifest')
            if result['dataset_sha256']!=data_hash or result['input_sha256']!=fingerprint or record['run_id']!='backtest-'+fingerprint:raise ValueError('fingerprint')
            if result['dataset_id']!=dataset.snapshot.snapshot_id or result['market']!=dataset.snapshot.market:raise ValueError('snapshot identity')
            return record
        except (ValueError,KeyError,TypeError,AttributeError):
            raise DomainConflict('backtest_corrupt','回测记录完整性校验失败，未作为有效结果读取。') from None

    def save(self,dataset:dict,result:dict):
        record={'run_id':'backtest-'+result['input_sha256'],'created_at':datetime.now(timezone.utc).isoformat(),'dataset':dataset,'result':result}
        digest=stable_hash(record);payload=json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False)
        self._decode(payload,digest,record['run_id']);self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS public_backtest_runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)')
            cursor=db.execute('INSERT OR IGNORE INTO public_backtest_runs VALUES (?,?,?,?)',(record['run_id'],record['created_at'],payload,digest))
            replayed=cursor.rowcount==0
            row=db.execute('SELECT payload,digest FROM public_backtest_runs WHERE run_id=?',(record['run_id'],)).fetchone()
            return self._decode(*row,record['run_id']),replayed

    def _rows(self,run_id=None):
        if not self.path.exists():return []
        with closing(sqlite3.connect(self.path)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='public_backtest_runs'").fetchone():return []
            if run_id is not None:return db.execute('SELECT run_id,payload,digest FROM public_backtest_runs WHERE run_id=?',(run_id,)).fetchall()
            return db.execute('SELECT run_id,payload,digest FROM public_backtest_runs ORDER BY created_at DESC,run_id LIMIT 50').fetchall()

    def get(self,run_id):
        rows=self._rows(run_id)
        if not rows:raise KeyError(run_id)
        key,payload,digest=rows[0];return self._decode(payload,digest,key)

    def list(self):
        records=[self._decode(payload,digest,key) for key,payload,digest in self._rows()]
        return [{'run_id':r['run_id'],'created_at':r['created_at'],'dataset_id':r['result']['dataset_id'],'market':r['result']['market'],
                 'window':r['result']['config']['window'],'start':r['result']['config']['start'],'end':r['result']['config']['end'],
                 'engine_sha256':r['result']['engine_sha256']} for r in records]
