import copy,json,tempfile,unittest
from pathlib import Path
from research.event_study.market import parse_index,validate_index,verify_artifacts

def payload(rows):return json.dumps({'code':0,'data':{'sh000300':{'day':rows}}}).encode()

class EventMarketTests(unittest.TestCase):
 def test_raw_index_and_exact_calendar(self):
    rows=parse_index(payload([['2024-01-02','100','102','103','99','1000'],['2024-01-03','102','101','104','100','2000']]),2024)
    self.assertEqual(rows[0]['close'],'102');validate_index(rows,['2024-01-02','2024-01-03'])
    with self.assertRaises(ValueError):validate_index(rows,['2024-01-02','2024-01-03','2024-01-04'])
 def test_duplicates_wrong_year_nonfinite_and_adjusted_series_refused(self):
    row=['2024-01-02','100','102','103','99','1000']
    for rows in [[row,row],[['2023-01-02']+row[1:]],[row[:2]+['NaN']+row[3:]]]:
      with self.assertRaises(ValueError):parse_index(payload(rows),2024)
    with self.assertRaises(ValueError):parse_index(json.dumps({'code':0,'data':{'sh000300':{'qfqday':[row]}}}).encode(),2024)
 def test_artifact_tamper_and_escape_refused(self):
    import hashlib
    with tempfile.TemporaryDirectory() as t:
      root=Path(t);p=root/'data.json';p.write_text('a');files={'data.json':hashlib.sha256(b'a').hexdigest()};verify_artifacts(root,files)
      p.write_text('b')
      with self.assertRaises(ValueError):verify_artifacts(root,files)
      with self.assertRaises(ValueError):verify_artifacts(root,{'../escape':files['data.json']})
