import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fastapi.testclient import TestClient
from platform_app.api.app import create_app
from platform_app.adapters.scenario_store import ScenarioStore
from platform_app.adapters.experiment_store import ExperimentStore
from platform_app.adapters.backtest_store import BacktestStore
from platform_app.evidence.service import CaseService
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash
from test_public_backtests import fixture


class VolatilityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'backend/data/volatility-runs'
        self.folder.mkdir(parents=True)
        self.file = self.root / 'research/artifacts/volatility/job/model.json'
        self.file.parent.mkdir(parents=True)
        self.file.write_bytes(b'weights')
        dataset = fixture().model_dump(mode='json')
        protocol = {'fixture': True}
        identity = {'market': 'ashare', 'horizon': '1', 'dataset_sha256': stable_hash(dataset), 'protocol_sha256': stable_hash(protocol)}
        metric = dict(rows=1, qlike=-8.0, variance_rmse=0.0, variance_mae=0.0,
                      volatility_rmse_ann=0.0, calibration_ratio=1.0, prediction_floor_count=0)
        comparison = dict(delta_qlike=0.0, ci_low=0.0, ci_high=0.0, block=20, repeats=2000)
        model = dict(name='EWMA', metrics=metric, comparison=comparison)
        folds, observations = [], []
        for year in (2024, 2025):
            for quarter in (1, 2, 3, 4):
                fold = f'{year}Q{quarter}'
                session = f'{year}-{(quarter-1)*3+1:02d}-02'
                folds.append(dict(fold=fold, bounds={}, counts={'evaluation': 1}, purged={}, regime_thresholds={}, models={'ewma': deepcopy(model)}, training={}))
                observations.append(dict(session=session, label_end=session[:-2]+'03', fold=fold, regime='low_up', realized_variance=.001, predictions={'ewma': .001}))
        overall = deepcopy(model)
        overall['metrics']['rows'] = 8
        overall.update(wins_vs_ewma=0, folds=8)
        regime = deepcopy(model)
        regime['metrics']['rows'] = 8
        self.record = dict(schema='volatility-result-v1', run_id='volatility-'+stable_hash(identity), identity=identity,
            created_at='2026-11-04T00:00:00Z', market='ashare', instrument=dataset['snapshot']['instrument'], currency='CNY', horizon=1, annualization=252,
            dataset_sha256=stable_hash(dataset), dataset=dataset, protocol=protocol, folds=folds, overall={'ewma': overall},
            regimes={'low_up': dict(name='低波动 · 上涨', rows=8, sufficient=False, models={'ewma': regime})},
            observations=observations, phase_receipts={}, limitations=['测试夹具，不是训练成果'],
            artifacts={self.file.relative_to(self.root).as_posix(): hashlib.sha256(b'weights').hexdigest()})
        self.path = self.folder / (self.record['run_id']+'.json')
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.path.write_text(json.dumps({'record': self.record, 'sha256': stable_hash(self.record)}), encoding='utf8')

    def store(self):
        from platform_app.adapters.volatility_store import VolatilityStore
        return VolatilityStore(self.folder, self.root)

    def test_readonly_api_and_negative_qlike(self):
        client = TestClient(create_app(cases=CaseService(()), store=ScenarioStore(self.root/'scenarios.sqlite3'),
            experiment_store=ExperimentStore(self.root/'experiments.sqlite3'),
            backtest_store=BacktestStore(self.root/'experiments.sqlite3'), volatility_store=self.store()))
        rows = client.get('/api/v1/volatility/runs')
        self.assertEqual(rows.status_code, 200)
        self.assertEqual(rows.headers['cache-control'], 'no-store')
        self.assertEqual(rows.json()[0]['horizon'], 1)
        result = client.get('/api/v1/volatility/runs/'+self.record['run_id'])
        self.assertEqual(result.json()['record']['overall']['ewma']['metrics']['qlike'], -8)
        self.assertEqual(result.json()['artifact_status'], 'verified')
        self.assertEqual(client.post('/api/v1/volatility/runs').status_code, 405)
        self.assertEqual(client.post('/api/v1/volatility/train').status_code, 404)

    def test_missing_artifacts_preserve_snapshot_without_replacement(self):
        self.file.unlink()
        body = self.store().get(self.record['run_id'])
        self.assertEqual(body['artifact_status'], 'missing')
        self.assertEqual(body['missing_artifacts'], list(self.record['artifacts']))
        self.assertEqual(body['record_sha256'], stable_hash(self.record))

    def test_changed_artifact_rejected(self):
        self.file.write_bytes(b'changed')
        with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])

    def test_lookup_and_record_digest_bound(self):
        self.path.write_text(json.dumps({'record': self.record, 'sha256': 'a'*64}), encoding='utf8')
        with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])
        with self.assertRaises(KeyError): self.store().get('../private')

    def test_other_experiments_and_traversal_paths_rejected(self):
        for name in ('../private', 'research/artifacts/rolling/weights', 'research/artifacts/volatility/../private', 'C:/private', 'research\\artifacts\\volatility\\x'):
            with self.subTest(name=name):
                self.record['artifacts'] = {name: 'a'*64}; self.save()
                with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])

    def test_identity_and_dataset_mismatch_rejected_even_with_new_record_digest(self):
        original = deepcopy(self.record)
        for mutate in (lambda r: r.update(horizon=5), lambda r: r.update(annualization=365),
                       lambda r: r.update(instrument='other'), lambda r: r['identity'].update(protocol_sha256='a'*64)):
            self.record = deepcopy(original); mutate(self.record); self.save()
            with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])

    def test_invalid_metrics_rows_and_model_keys_rejected(self):
        original = deepcopy(self.record)
        mutations = [lambda r: r['overall']['ewma']['metrics'].update(variance_rmse=-1),
            lambda r: r['overall']['ewma']['metrics'].update(rows=99),
            lambda r: r['overall']['ewma']['metrics'].update(prediction_floor_count=99),
            lambda r: r['overall']['ewma']['comparison'].update(ci_low=2, ci_high=1),
            lambda r: r['observations'][0]['predictions'].update(unknown=.001),
            lambda r: r['observations'][0]['predictions'].update(ewma=0),
            lambda r: r['regimes']['low_up'].update(sufficient=True),
            lambda r: r['folds'][0]['models']['ewma']['metrics'].update(rows=2),
            lambda r: r['observations'][1].update(session=r['observations'][0]['session'])]
        for i, mutate in enumerate(mutations):
            with self.subTest(case=i):
                self.record = deepcopy(original); mutate(self.record); self.save()
                with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])

    def test_nonfinite_metric_is_rejected(self):
        self.record['overall']['ewma']['metrics']['qlike'] = float('nan')
        self.path.write_text(json.dumps({'record': self.record, 'sha256': 'a'*64}), encoding='utf8')
        with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])

    def test_empty_regime_preserves_null_metrics_and_comparison(self):
        self.record['regimes']['high_down'] = dict(name='高波动 · 下跌', rows=0, sufficient=False,
            models={'ewma': dict(name='EWMA', metrics=None, comparison=None)})
        self.save()
        actual = self.store().get(self.record['run_id'])['record']['regimes']['high_down']
        self.assertIsNone(actual['models']['ewma']['metrics'])
        self.record['regimes']['low_up']['models']['ewma']['metrics'] = None
        self.save()
        with self.assertRaises(DomainConflict): self.store().get(self.record['run_id'])

    def test_empty_catalog_is_read_only(self):
        from platform_app.adapters.volatility_store import VolatilityStore
        missing = self.root/'absent'
        self.assertEqual(VolatilityStore(missing, self.root).list(), [])
        self.assertFalse(missing.exists())


if __name__ == '__main__': unittest.main()
