import json,tempfile,unittest
from pathlib import Path
from research.market.common import digest,file_sha
from research.forward_market.pipeline import verify_snapshot

class SnapshotEvidenceTests(unittest.TestCase):
 def test_reception_receipt_cannot_reregister_changed_raw_bytes(self):
    with tempfile.TemporaryDirectory() as t:
      root=Path(t);raw=root/'raw.json';raw.write_text('original')
      snapshot={'retrieved_at':'2026-11-06T00:00:00+00:00','source_evidence':[{'file':str(raw),'sha256':file_sha(raw)}]}
      snapshot['snapshot_sha256']=digest(snapshot);snapshot['snapshot_path']=str(root/'snapshot.json')
      Path(snapshot['snapshot_path']).write_text(json.dumps(snapshot))
      verify_snapshot(snapshot,root)
      raw.write_text('changed')
      with self.assertRaises(ValueError):verify_snapshot(snapshot,root)
 def test_snapshot_path_escape_and_payload_change_rejected(self):
    with tempfile.TemporaryDirectory() as t:
      root=Path(t);snapshot={'source_evidence':[]};snapshot['snapshot_sha256']=digest(snapshot);snapshot['snapshot_path']=str(root/'snapshot.json')
      Path(snapshot['snapshot_path']).write_text(json.dumps(snapshot))
      with self.assertRaises(ValueError):verify_snapshot(snapshot,root/'nested')
      snapshot['source_evidence']=[{'status':'failed'}]
      with self.assertRaises(ValueError):verify_snapshot(snapshot,root)
