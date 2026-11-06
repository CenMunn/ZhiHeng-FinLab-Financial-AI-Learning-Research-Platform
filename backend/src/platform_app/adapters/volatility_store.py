import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from platform_app.contracts.volatility_results import VolatilityResult


class VolatilityStore:
    """Read-only published snapshots, bound to their original volatility artifacts."""
    def __init__(self, folder, project):
        self.folder = Path(folder)
        self.project = Path(project)

    def get(self, run_id):
        if not re.fullmatch(r'volatility-[a-f0-9]{64}', run_id):
            raise KeyError(run_id)
        path = self.folder/(run_id+'.json')
        if not path.exists():
            raise KeyError(run_id)
        try:
            if not path.resolve().is_relative_to(self.folder.resolve()):
                raise ValueError('记录路径越界')
            body = json.loads(path.read_text('utf8'))
            record = body['record']
            if stable_hash(record) != body['sha256'] or record['run_id'] != run_id:
                raise ValueError('查询身份或记录摘要变化')
            parsed = VolatilityResult.model_validate(record)
            snapshot = parsed.dataset.snapshot
            if stable_hash(parsed.dataset.model_dump(mode='json')) != parsed.dataset_sha256:
                raise ValueError('行情快照摘要变化')
            if (parsed.market, parsed.instrument, parsed.currency) != (snapshot.market, snapshot.instrument, snapshot.currency):
                raise ValueError('市场或标的身份错配')
            identity = parsed.identity
            if (identity['market'], identity['horizon'], identity['dataset_sha256'], identity['protocol_sha256']) != (
                    parsed.market, str(parsed.horizon), parsed.dataset_sha256, stable_hash(parsed.protocol)):
                raise ValueError('协议身份错配')
            if run_id != 'volatility-'+stable_hash(identity):
                raise ValueError('运行身份错配')
            allowed = (self.project/'research/artifacts/volatility').resolve()
            missing = []
            for name, sha in parsed.artifacts.items():
                relative = PurePosixPath(name)
                if '\\' in name or ':' in name or relative.is_absolute() or '..' in relative.parts:
                    raise ValueError('产物路径越界')
                artifact = (self.project/name).resolve()
                if not artifact.is_relative_to(allowed) or artifact == allowed:
                    raise ValueError('产物不属于波动实验')
                if not artifact.exists():
                    missing.append(name)
                else:
                    if not artifact.is_file():
                        raise ValueError('产物不是文件')
                    with artifact.open('rb') as stream:
                        if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                            raise ValueError('原始模型或预测产物变化')
            return dict(record=record, record_sha256=body['sha256'],
                        artifact_status='missing' if missing else 'verified', missing_artifacts=missing)
        except (ValueError, KeyError, TypeError, AttributeError, OSError):
            raise DomainConflict('volatility_corrupt', '波动实验完整性校验失败，未作为有效结果读取。') from None

    def list(self):
        if not self.folder.exists():
            return []
        result = []
        for file in self.folder.glob('volatility-*.json'):
            body = self.get(file.stem)
            record = body['record']
            result.append({key: record[key] for key in ('run_id', 'created_at', 'market', 'instrument', 'horizon')} |
                          dict(rows=len(record['observations']), artifact_status=body['artifact_status']))
        return sorted(result, key=lambda record: (record['created_at'], record['run_id']), reverse=True)
