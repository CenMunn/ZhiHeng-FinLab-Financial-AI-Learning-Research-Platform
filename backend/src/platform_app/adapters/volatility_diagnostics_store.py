"""Read-only D23 publication adapter; no research runtime imports."""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path, PurePosixPath
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from platform_app.contracts.volatility_results import VolatilityMetrics, VolatilityComparison


def require(condition):
    if not condition:
        raise ValueError('诊断结果不一致')


def count(value):
    require(type(value) is int and value >= 0)
    return value


def finite_tree(value):
    if isinstance(value, float): require(math.isfinite(value))
    elif isinstance(value, dict):
        for child in value.values(): finite_tree(child)
    elif isinstance(value, list):
        for child in value: finite_tree(child)


def validate(record, parent):
    finite_tree(record)
    require(record['schema'] == 'volatility-diagnostics-v1')
    require((record['source_run_id'], record['source_record_sha256'], record['market'], record['horizon']) ==
            (parent['record']['run_id'], parent['record_sha256'], parent['record']['market'], parent['record']['horizon']))
    require(datetime.fromisoformat(record['created_at']).tzinfo is not None)
    identity = dict(source_record_sha256=record['source_record_sha256'], protocol_sha256=stable_hash(record['protocol']), sources=record['sources'])
    require(record['diagnostic_id'] == 'vdiag-'+stable_hash(identity))
    require(isinstance(record['limitations'], list) and bool(record['limitations']) and all(isinstance(s,str) for s in record['limitations']))
    source = parent['record']; folds = [f['fold'] for f in source['folds']]
    require(set(record['models']) == set(source['overall']))
    for key, model in record['models'].items():
        require(model['name'] == source['overall'][key]['name'])
        for metrics in (model['raw'], model['calibrated']):
            require(VolatilityMetrics.model_validate(metrics).rows == len(source['observations']))
        require(model['raw'] == source['overall'][key]['metrics'])
        VolatilityComparison.model_validate({k:model['comparison'][k] for k in ('delta_qlike','ci_low','ci_high','block','repeats')})
        require([f['fold'] for f in model['folds']] == folds)
        for fold, original in zip(model['folds'], source['folds']):
            n = original['counts']['evaluation']
            require(type(fold['clipped']) is bool and fold['raw_c'] >= 0 and fold['c'] == min(4,max(.25,fold['raw_c'])) and fold['clipped'] == (fold['raw_c'] != fold['c']))
            require(count(fold['validation_rows']) == original['counts'].get('validation', fold['validation_rows']))
            for m in ('raw','calibrated'): require(VolatilityMetrics.model_validate(fold[m]).rows == n)
            require(bool(fold['bins']) and sum(count(b['rows']) for b in fold['bins']) == n)
            edges = [b['upper'] for b in fold['bins'][:-1]]
            require(fold['bins'][0]['lower'] is None and fold['bins'][-1]['upper'] is None and edges == sorted(set(edges)))
            for i,b in enumerate(fold['bins']):
                if i: require(b['lower'] == edges[i-1])
                if not b['rows']: require(all(b[k] is None for k in ('prediction_mean','realized_mean','ratio')))
                else:
                    require(b['prediction_mean'] >= 0 and b['realized_mean'] >= 0)
                    require(b['ratio'] is None if b['realized_mean'] == 0 else b['ratio'] >= 0)
        expected = []
        for fold in folds:
            rows = [o for o in source['observations'] if o['fold'] == fold]
            expected.extend((fold,rows[i]['session'],rows[min(i+19,len(rows)-1)]['session'],len(rows[i:i+20])) for i in range(0,len(rows),20))
        require([(w['fold'],w['start'],w['end'],count(w['rows'])) for w in model['windows']] == expected)
        for w in model['windows']:
            require(count(w['underforecast_count']) <= w['rows'] and w['max_realized_variance'] >= 0)
            for field in ('raw_qlike','calibrated_qlike','ewma_qlike','raw_delta','calibrated_delta'): require(type(w[field]) in (int,float))
        require(model['worst_windows'] == sorted(model['windows'],key=lambda w:w['raw_delta'],reverse=True)[:3])
    require([f['fold'] for f in record['coverage_folds']] == folds)
    def coverage(groups, n):
        require(len(groups) == 6 and len({g['regime'] for g in groups}) == 6)
        require(sum(count(g['evaluation_rows']) for g in groups) == n)
        for g in groups:
            count(g['train_rows']); count(g['validation_rows'])
            require(count(g['nonoverlap_count']) <= g['evaluation_rows'])
            require(g['missing_to_30'] == max(0,30-g['evaluation_rows']))
            require(0 <= g['train_share'] <= 1 and 0 <= g['evaluation_share'] <= 1)
            require(abs(g['share_change']-(g['evaluation_share']-g['train_share'])) < 1e-10)
    coverage(record['coverage'],len(source['observations']))
    for f, original in zip(record['coverage_folds'],source['folds']): coverage(f['regimes'],original['counts']['evaluation'])


class VolatilityDiagnosticsStore:
    def __init__(self, folder, project, source_store):
        self.folder, self.project, self.source_store = Path(folder), Path(project), source_store

    def get(self, run_id):
        if not re.fullmatch(r'volatility-[a-f0-9]{64}',run_id): raise KeyError(run_id)
        path = self.folder/(run_id+'.json')
        if not path.exists(): raise KeyError(run_id)
        parent = self.source_store.get(run_id)
        try:
            require(path.resolve().is_relative_to(self.folder.resolve()))
            body = json.loads(path.read_text('utf8')); record = body['record']
            require(stable_hash(record) == body['sha256'])
            validate(record,parent)
            missing = list(parent['missing_artifacts'])
            allowed = (self.project/'research/artifacts/volatility-diagnostics').resolve()
            require(bool(record['sources']) and bool(record['artifacts']))
            for group in ('sources','artifacts'):
                for name,sha in record[group].items():
                    relative = PurePosixPath(name)
                    require('\\' not in name and ':' not in name and not relative.is_absolute() and '..' not in relative.parts and re.fullmatch('[a-f0-9]{64}',sha))
                    artifact = (self.project/name).resolve()
                    permitted = allowed if group == 'artifacts' else (self.project/'research').resolve()
                    require(artifact.is_relative_to(permitted) and artifact != permitted)
                    if group == 'sources': require(relative.suffix == '.py' and (name.startswith('research/volatility_diagnostics/') or name in ('research/volatility/metrics.py','research/volatility/data.py')))
                    if not artifact.exists(): missing.append(name)
                    else:
                        require(artifact.is_file())
                        with artifact.open('rb') as stream: require(hashlib.file_digest(stream,'sha256').hexdigest() == sha)
            return dict(record=record,record_sha256=body['sha256'],artifact_status='missing' if missing else 'verified',missing_artifacts=sorted(set(missing)))
        except (ValueError,KeyError,TypeError,AttributeError,OSError,OverflowError):
            raise DomainConflict('volatility_diagnostics_corrupt','波动诊断完整性校验失败，未作为有效结果读取。') from None
