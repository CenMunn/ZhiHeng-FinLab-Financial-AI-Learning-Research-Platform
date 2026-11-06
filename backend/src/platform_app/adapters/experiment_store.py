from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import json
import sqlite3
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.market_experiments import MarketSnapshot,FoundationConfig
from platform_app.contracts.models import stable_hash
from platform_app.experiments.data import snapshot_hash

class ExperimentStore:
    """An independent local research store, not an account or M1 scenario database."""
    def __init__(self,path:Path):self.path=Path(path)

    def _decode(self,payload:str,digest:str,expected_run_id:str)->dict:
        try:
            record=json.loads(payload)
            if stable_hash(record)!=digest or record['run_id']!=expected_run_id:raise ValueError('checksum or lookup identity')
            snapshot=MarketSnapshot.model_validate(record['snapshot'])
            result=record['result'];config=FoundationConfig.model_validate(result['config'])
            identity={'engine_version':result['engine_version'],'engine_sha256':result['engine_sha256'],'snapshot_sha256':snapshot_hash(snapshot),'config':config.model_dump(mode='json')}
            if 'engine_runtime' in result:identity['engine_runtime']=result['engine_runtime']
            expected=stable_hash(identity)
            if result['snapshot_sha256']!=snapshot_hash(snapshot) or result['input_hash']!=expected or record['run_id']!='foundation-'+expected:raise ValueError('identity')
            return record
        except (ValueError,KeyError,TypeError,AttributeError):
            raise DomainConflict('experiment_corrupt','实验记录完整性校验失败，未作为有效实验读取。') from None

    def save(self,snapshot:dict,result:dict)->tuple[dict,bool]:
        record={'run_id':'foundation-'+result['input_hash'],'created_at':datetime.now(timezone.utc).isoformat(),'snapshot':snapshot,'result':result}
        digest=stable_hash(record);payload=json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False)
        self._decode(payload,digest,record['run_id'])
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS experiment_runs (run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL)')
            cursor=db.execute('INSERT OR IGNORE INTO experiment_runs VALUES (?,?,?,?)',(record['run_id'],record['created_at'],payload,digest))
            replayed=cursor.rowcount==0
            row=db.execute('SELECT payload,digest FROM experiment_runs WHERE run_id=?',(record['run_id'],)).fetchone()
            stored=self._decode(*row,record['run_id'])
        return stored,replayed

    def get(self,run_id:str)->dict:
        if not self.path.exists():raise KeyError(run_id)
        with closing(sqlite3.connect(self.path)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_runs'").fetchone():raise KeyError(run_id)
            row=db.execute('SELECT payload,digest FROM experiment_runs WHERE run_id=?',(run_id,)).fetchone()
        if row is None:raise KeyError(run_id)
        return self._decode(*row,run_id)

    def list(self)->list[dict]:
        if not self.path.exists():return []
        with closing(sqlite3.connect(self.path)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='experiment_runs'").fetchone():return []
            rows=db.execute('SELECT run_id,payload,digest FROM experiment_runs ORDER BY created_at DESC,run_id LIMIT 50').fetchall()
        records=[self._decode(payload,digest,run_id) for run_id,payload,digest in rows]
        return [{'run_id':r['run_id'],'created_at':r['created_at'],'snapshot_id':r['result']['snapshot_id'],'market':r['result']['market'],
                 'input_hash':r['result']['input_hash'],'window':r['result']['config']['window'],'source_kind':r['result']['source_kind']} for r in records]
