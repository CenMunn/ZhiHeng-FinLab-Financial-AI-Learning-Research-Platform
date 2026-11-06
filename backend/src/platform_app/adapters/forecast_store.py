"""Read-only offline-model results; missing artifacts do not erase saved history."""
import hashlib,json,re
from pathlib import Path,PurePosixPath
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from platform_app.contracts.forecast_results import ForecastResult


class ForecastStore:
    def __init__(self,folder:Path,project:Path):self.folder=Path(folder);self.project=Path(project)

    def get(self,run_id:str):
        if not re.fullmatch(r'forecast-[a-f0-9]{64}',run_id):raise KeyError(run_id)
        path=self.folder/(run_id+'.json')
        if not path.exists():raise KeyError(run_id)
        try:
            envelope=json.loads(path.read_text('utf8'));record=envelope['record']
            if stable_hash(record)!=envelope['sha256'] or record['run_id']!=run_id:raise ValueError('存储摘要/查询身份错配')
            parsed=ForecastResult.model_validate(record)
            if stable_hash(parsed.dataset.model_dump(mode='json'))!=record['dataset_sha256']:raise ValueError('数据快照错配')
            if record['dataset_id']!=parsed.dataset.snapshot.snapshot_id or record['market']!=parsed.dataset.snapshot.market:raise ValueError('市场身份错配')
            identity={key:record[key] for key in ('dataset_sha256','preparation_sha256','training_sha256','prediction_sha256','labels_sha256')}
            if run_id!='forecast-'+stable_hash(identity):raise ValueError('训练/预测/标签身份错配')
            for name,key in [('preparation.json','preparation_sha256'),('training.json','training_sha256'),('predictions.json','prediction_sha256'),('evaluation_labels.json','labels_sha256')]:
                if record['artifacts'].get(name)!=record[key]:raise ValueError('来源产物指纹错配')
            directory=record['artifact_directory']
            if '\\' in directory or ':' in directory or PurePosixPath(directory).is_absolute() or '..' in PurePosixPath(directory).parts:raise ValueError('非法产物目录')
            root=(self.project/directory).resolve();allowed=(self.project/'research/artifacts/market-forecast').resolve()
            if not root.is_relative_to(allowed):raise ValueError('产物目录越界')
            missing=[]
            for name,sha in record['artifacts'].items():
                if not re.fullmatch(r'[A-Za-z0-9_.-]+',name):raise ValueError('非法产物名称')
                artifact=(root/name).resolve()
                if not artifact.is_relative_to(root):raise ValueError('产物链接越界')
                if not artifact.exists():missing.append(name)
                elif hashlib.sha256(artifact.read_bytes()).hexdigest()!=sha:raise ValueError('模型/预测/标签产物已变化')
            return {'record':record,'record_sha256':envelope['sha256'],'artifact_status':'missing' if missing else 'verified','missing_artifacts':missing}
        except (ValueError,KeyError,TypeError,AttributeError,OSError):
            raise DomainConflict('forecast_corrupt','离线预测实验完整性校验失败，未作为有效结果读取。') from None

    def list(self):
        if not self.folder.exists():return []
        results=[]
        for path in sorted(self.folder.glob('forecast-*.json'),key=lambda p:p.name):
            body=self.get(path.stem);r=body['record']
            results.append({key:r[key] for key in ('run_id','created_at','market','instrument','currency','counts','evaluation','dataset_sha256','prediction_sha256')}|
                {'artifact_status':body['artifact_status'],'models':{key:{'name':model['name'],'evaluation':model['evaluation'],'validation':model['validation']} for key,model in r['models'].items()}})
        return sorted(results,key=lambda r:(r['created_at'],r['run_id']),reverse=True)[:50]
