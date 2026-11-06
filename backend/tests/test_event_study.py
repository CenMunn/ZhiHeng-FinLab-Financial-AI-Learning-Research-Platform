import copy, math, unittest
from datetime import date,timedelta
from platform_app.experiments.event_study import analyze

def fixture():
    days=[];d=date(2023,1,2)
    while len(days)<220:
        if d.weekday()<5:days.append(str(d))
        d+=timedelta(days=1)
    sp=mp=100.;sb=[];mb=[]
    for i,day in enumerate(days):
        if i:
            x=((i%7)-3)*.001
            mp*=1+x;sp*=1+.0002+1.5*x
        sb.append({'session':day,'close':str(sp)});mb.append({'session':day,'close':str(mp)})
    stock={'symbol':'600519','market':'ashare','bars':sb,'expected_sessions':days,'dividends':[],'splits':[]}
    benchmark={'symbol':'000300','bars':mb,'expected_sessions':days}
    event={'event_id':'example','symbol':'600519','publication_date':days[169],'publication_at':None,'time_precision':'date'}
    return stock,benchmark,event

class EventStudyTests(unittest.TestCase):
 def test_known_ols_and_sum_ar(self):
    s,b,e=fixture();r=analyze(s,b,e)
    self.assertEqual(r['event_session'],s['expected_sessions'][170]);self.assertEqual(r['estimation']['n'],110)
    self.assertAlmostEqual(r['estimation']['alpha'],.0002,places=12);self.assertAlmostEqual(r['estimation']['beta'],1.5,places=12)
    self.assertEqual([x['offset'] for x in r['rows']],list(range(-5,6)))
    self.assertAlmostEqual(r['summary']['car'],0,places=12)
    self.assertAlmostEqual(r['rows'][-1]['cumulative_abnormal_return'],sum(x['abnormal_return'] for x in r['rows']))
 def test_date_only_uses_next_session_even_midnight_metadata(self):
    s,b,e=fixture();e['publication_date']='2023-08-25';e['publication_at']='2023-08-25T00:00:00+08:00'
    r=analyze(s,b,e);self.assertEqual(r['event_session'],'2023-08-28')
 def test_exact_timestamp_before_or_after_open(self):
    s,b,e=fixture();e.update(publication_date='2023-08-25',time_precision='minute',publication_at='2023-08-25T09:00:00+08:00')
    self.assertEqual(analyze(s,b,e)['event_session'],'2023-08-25')
    e['publication_at']='2023-08-25T09:30:00+08:00';self.assertEqual(analyze(s,b,e)['event_session'],'2023-08-28')
 def test_event_and_future_prices_never_change_fit(self):
    s,b,e=fixture();before=analyze(s,b,e)
    for row in s['bars'][165:]:row['close']=str(float(row['close'])*1.1)
    after=analyze(s,b,e);self.assertEqual(before['estimation'],after['estimation'])
    self.assertGreater(after['summary']['car'],.09)
 def test_dividend_total_return_and_window(self):
    s,b,e=fixture();s['dividends']=[{'session':s['expected_sessions'][170],'amount':'2'}]
    r=analyze(s,b,e,pre=1,post=2);row=next(x for x in r['rows'] if x['offset']==0)
    expected=(float(s['bars'][170]['close'])+2)/float(s['bars'][169]['close'])-1
    self.assertAlmostEqual(row['stock_return'],expected)
    self.assertEqual(len(r['rows']),4)
 def test_missing_duplicate_invalid_and_split_refused(self):
    s,b,e=fixture()
    for which,mutate in [('stock',lambda x:x['bars'].pop(60)),('benchmark',lambda x:x['bars'].pop(170)),('stock',lambda x:x['bars'].append(x['bars'][-1])),('stock',lambda x:x['bars'][170].update(close='NaN')),('stock',lambda x:x.update(splits=[{'session':'2023-08-28','ratio':'2'}]))]:
      ss,bb=copy.deepcopy(s),copy.deepcopy(b);mutate(ss if which=='stock' else bb)
      with self.assertRaises(ValueError):analyze(ss,bb,e)
 def test_insufficient_constant_market_and_bad_window_refused(self):
    s,b,e=fixture();e['publication_date']=s['expected_sessions'][80]
    with self.assertRaises(ValueError):analyze(s,b,e)
    s,b,e=fixture()
    for row in b['bars']:row['close']='100'
    with self.assertRaises(ValueError):analyze(s,b,e)
    s,b,e=fixture()
    for pre,post in [(0,5),(11,5),(5,True),(5,11)]:
      with self.assertRaises(ValueError):analyze(s,b,e,pre,post)
 def test_identity_and_naive_timestamp_refused(self):
    s,b,e=fixture();e['symbol']='600036'
    with self.assertRaises(ValueError):analyze(s,b,e)
    e.update(symbol='600519',time_precision='minute',publication_at=e['publication_date']+'T10:00:00')
    with self.assertRaises(ValueError):analyze(s,b,e)
