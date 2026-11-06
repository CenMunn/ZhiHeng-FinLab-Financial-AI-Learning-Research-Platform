import hashlib,json,re
from pathlib import Path,PurePosixPath
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from platform_app.contracts.rolling_results import RollingResult


class RollingStore:
    """Only reads published experiment snapshots; never imports a training runtime."""
    def __init__(self,folder,project):self.folder=Path(folder);self.project=Path(project)

    def get(self,run_id):
        if not re.fullmatch(r'rolling-[a-f0-9]{64}',run_id):raise KeyError(run_id)
        path=self.folder/(run_id+'.json')
        if not path.exists():raise KeyError(run_id)
        try:
            body=json.loads(path.read_text('utf8'));r=body['record']
            if stable_hash(r)!=body['sha256'] or r['run_id']!=run_id:raise ValueError('查询身份/存储摘要变化')
            parsed=RollingResult.model_validate(r)
            if stable_hash(parsed.dataset.model_dump(mode='json'))!=r['dataset_sha256'] or r['market']!=parsed.dataset.snapshot.market:raise ValueError('公开行情身份错配')
            if r['identity']['market']!=r['market'] or r['identity']['dataset_sha256']!=r['dataset_sha256'] or r['identity']['protocol_sha256']!=stable_hash(r['protocol']):raise ValueError('协议身份错配')
            if run_id!='rolling-'+stable_hash(r['identity']):raise ValueError('滚动运行身份错配')
            allowed=[(self.project/'research/artifacts'/name).resolve() for name in ('rolling','rolling-model')];missing=[]
            for name,sha in r['artifacts'].items():
                if '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:raise ValueError('产物路径越界')
                artifact=(self.project/name).resolve()
                if not any(artifact.is_relative_to(root) for root in allowed):raise ValueError('产物不属于滚动实验')
                if not artifact.exists():missing.append(name)
                elif hashlib.sha256(artifact.read_bytes()).hexdigest()!=sha:raise ValueError('模型/输入/预测产物变化')
            return {'record':r,'record_sha256':body['sha256'],'artifact_status':'missing' if missing else 'verified','missing_artifacts':missing}
        except (ValueError,KeyError,TypeError,AttributeError,OSError):
            raise DomainConflict('rolling_corrupt','滚动实验完整性校验失败，未作为有效结果读取。') from None

    def list(self):
        if not self.folder.exists():return []
        result=[]
        for file in self.folder.glob('rolling-*.json'):
            body=self.get(file.stem);r=body['record']
            result.append({key:r[key] for key in ('run_id','created_at','market','instrument','currency','dataset_sha256')}|
                {'artifact_status':body['artifact_status'],'rows':len(r['observations']),'folds':len(r['folds'])})
        return sorted(result,key=lambda r:(r['created_at'],r['run_id']),reverse=True)[:50]
