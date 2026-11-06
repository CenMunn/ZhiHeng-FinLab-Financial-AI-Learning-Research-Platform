import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from platform_app.adapters.forward_store import ForwardStore
from platform_app.api.forward import forward_router
from platform_app.contracts.errors import DomainConflict
from platform_app.contracts.models import stable_hash


class ForwardStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'backend/data/forward-market'
        self.folder.mkdir(parents=True)
        self.source = self.root / 'research/artifacts/forward-market/source.json'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('{}', encoding='utf8')
        self.record = {'schema': 'forward-market-status-v1', 'updated_at': '2026-11-06T01:00:00+00:00',
                       'status': 'waiting', 'items': [{'symbol':'BTCUSDT','name':'BTC','market':'crypto',
                       'state':'waiting_signal','reason':'等待首个合格收盘','latest_session':'2026-11-04',
                       'source_retrieved_at':'2026-11-06T00:00:00+00:00','forecast_count':0,'scored_count':0,'predictions':[]}],
                       'limitations':['无前向成绩'], 'artifacts':{self.source.relative_to(self.root).as_posix(): hashlib.sha256(self.source.read_bytes()).hexdigest()}}
        self.store = ForwardStore(self.folder, self.root)

    def save(self):
        (self.folder/'status.json').write_text(json.dumps({'record':self.record,'sha256':stable_hash(self.record)}), encoding='utf8')

    def test_empty_is_not_a_zero_score(self):
        result=self.store.get()
        self.assertEqual(result['artifact_status'],'empty')
        self.assertIsNone(result['record'])

    def test_readonly_verified_and_missing(self):
        self.save(); before=(self.folder/'status.json').read_bytes()
        self.assertEqual(self.store.get()['artifact_status'],'verified')
        self.assertEqual((self.folder/'status.json').read_bytes(),before)
        self.source.unlink()
        self.assertEqual(self.store.get()['artifact_status'],'missing')

    def test_corruption_refused_on_next_request(self):
        self.save(); self.store.get(); self.source.write_text('changed')
        with self.assertRaises(DomainConflict):self.store.get()

    def test_identity_and_path_traversal_refused(self):
        self.save(); body=json.loads((self.folder/'status.json').read_text()); body['record']['status']='active'
        (self.folder/'status.json').write_text(json.dumps(body))
        with self.assertRaises(DomainConflict):self.store.get()
        self.record['artifacts']={'research/artifacts/forward-market/../../secret':'a'*64};self.save()
        with self.assertRaises(DomainConflict):self.store.get()

    def test_count_and_naive_timestamp_refused(self):
        self.record['items'][0]['forecast_count']=1;self.save()
        with self.assertRaises(DomainConflict):self.store.get()
        self.record['items'][0]['forecast_count']=0;self.record['updated_at']='2026-11-06T01:00:00';self.save()
        with self.assertRaises(DomainConflict):self.store.get()

    def test_future_execution_and_scoring_order(self):
        p={'forecast_id':'forecast-1','signal_session':'2026-11-06','created_at':'2026-11-07T00:01:00+00:00',
           'decision_at':'2026-11-07T00:01:00+00:00','entry_at':'2026-11-08T00:00:00+00:00','exit_at':'2026-11-09T00:00:00+00:00',
           'predictions':{'ewma':{'raw':0.01,'calibrated':0.02}},'outcome':None}
        i=self.record['items'][0];i.update(predictions=[p],forecast_count=1,state='waiting_outcome');self.save()
        self.assertEqual(self.store.get()['artifact_status'],'verified')
        p['created_at']=p['entry_at'];self.save()
        with self.assertRaises(DomainConflict):self.store.get()
        p['created_at']=p['decision_at'];p['outcome']={'realized_variance':0.01,'log_return':0.1,'scored_at':p['entry_at'],'errors':{'ewma':{'raw_qlike':1.0,'calibrated_qlike':2.0}}};i['scored_count']=1;self.save()
        with self.assertRaises(DomainConflict):self.store.get()

    def test_get_route_no_store_no_write(self):
        self.save();app=FastAPI();app.include_router(forward_router(self.store))
        client=TestClient(app);result=client.get('/api/v1/forward-market/status')
        self.assertEqual(result.status_code,200);self.assertEqual(result.headers['cache-control'],'no-store')
        self.assertEqual(client.post('/api/v1/forward-market/status').status_code,405)

