import tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone
from research.risk_budget.shadow import register,append_prediction
from research.market.common import digest

class ShadowTests(unittest.TestCase):
    def test_pending_registration_no_fabricated_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);meta=register(p,'risk-'+'a'*64,'b'*64)
            self.assertEqual(meta['records'],0);self.assertEqual(meta['status'],'pending')
            self.assertEqual(len(list(p.rglob('prediction-*.json'))),0)

    def test_late_old_or_changed_prediction_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);run='risk-'+'a'*64;register(p,run,'b'*64)
            inputs={'available_at':'2026-11-06T07:01:00+00:00','feature_asof':'2026-11-06','x':[.01]*60}
            record={'source_run_id':run,'model_key':'ewma','mode':'calibrated','signal_session':'2026-11-06','decision_at':'2026-11-06T07:01:00+00:00','entry_at':'2026-11-09T01:30:00+00:00','variance':.0001,'target_weight':'0.5','input_sha256':digest(inputs),'model_sha256':'c'*64}
            now=datetime(2026,11,6,8,tzinfo=timezone.utc)
            append_prediction(p,record,inputs,{'c'*64},_now=now)
            self.assertEqual(len(list(p.rglob('prediction-*.json'))),1)
            with self.assertRaises(ValueError):append_prediction(p,{**record,'variance':.1},inputs,{'c'*64},_now=now)
            with self.assertRaises(ValueError):append_prediction(p,record,inputs,{'c'*64},_now=datetime(2026,11,10,tzinfo=timezone.utc))
            with self.assertRaises(ValueError):append_prediction(p,{**record,'signal_session':'2025-12-31'},inputs,{'c'*64},_now=now)
