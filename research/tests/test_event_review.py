"""Independent synthetic source-binding regressions; no private/user records."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from research.market.common import file_sha
from research.event_study.sources import normalize,link_versions,extract_metrics
from research.event_study.pipeline import validate_derived

class EventDerivedReviewTests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.project=Path(self.tmp.name)
    root=self.project/'research/artifacts/event-study';self.src=root/'source-fixture';self.mkt=root/'market-fixture'
    self.src.mkdir(parents=True);(self.mkt/'datasets').mkdir(parents=True);(self.src/'case').mkdir()
    self.source_path=self.src/'catalog.json';self.market_path=self.mkt/'manifest.json'
    def write(path,body):path.write_text(json.dumps(body,ensure_ascii=False),encoding='utf8');return path.relative_to(self.project).as_posix()
    catalog=[];audit=[];source_artifacts={}
    for symbol in ('600519','600036','600585'):
      raw={'SECURITY_CODE':symbol,'SSEDATE':'2024-04-27','TITLE':symbol+'2024年第一季度报告','URL':'/disclosure/listedinfo/announcement/c/new/2024-04-27/'+symbol+'.pdf','BULLETIN_HEADING':'定期报告','BULLETIN_TYPE':'季度报告'}
      path=self.src/(symbol+'.json');name=write(path,{'result':[raw],'pageHelp':{'pageNo':1,'pageSize':100,'pageCount':1,'total':1}});sha=file_sha(path)
      event=normalize(raw,symbol);event.update(catalog_source=name,catalog_source_sha256=sha);catalog.append(event)
      audit.append({'symbol':symbol,'sources':[{'file':name,'sha256':sha}],'all_announcement_count':1,'received_count':1,'pages':1,'complete_pagination':True})
      source_artifacts[name]=sha
    link_versions(catalog);catalog.sort(key=lambda e:(e['symbol'],e['publication_date'],e['title']))
    text='单位：元 币种：人民币 营业收入100.00归属于上市公司股东的净利润50.00经营活动产生的现金流量净额20.00'
    pdf=self.src/'case/report.pdf';pdf.write_bytes(b'%PDF-synthetic-evidence');pdfsha=file_sha(pdf);pdfname=pdf.relative_to(self.project).as_posix();source_artifacts[pdfname]=pdfsha
    pagepath=self.src/'case/pages.json';pagename=write(pagepath,{'pages':[text],'extractor':'fixture','pdf_sha256':pdfsha});source_artifacts[pagename]=file_sha(pagepath)
    self.source={'catalog':catalog,'audit':audit,'case':{'event_id':next(e['event_id'] for e in catalog if e['symbol']=='600519'),'pdf_path':pdfname,'pdf_sha256':pdfsha,'page_count':1,'evidence':extract_metrics([text])},'artifacts':source_artifacts}
    stocks={};market_artifacts={}
    for symbol in ('600519','600036','600585'):
      data={'symbol':symbol,'bars':[{'session':'2024-01-02','close':'100'}]};stocks[symbol]=data
      path=self.mkt/'datasets'/(symbol+'.json');name=write(path,data);market_artifacts[name]=file_sha(path)
    benchmark={'symbol':'000300','bars':[{'session':'2024-01-02','close':'100'}]};path=self.mkt/'datasets/000300.json';name=write(path,benchmark);market_artifacts[name]=file_sha(path)
    self.market={'stocks':stocks,'benchmark':benchmark,'artifacts':market_artifacts}
    write(self.source_path,self.source);write(self.market_path,self.market)
    self.patch=patch('research.event_study.pipeline.PROJECT',self.project);self.patch.start();self.addCleanup(self.patch.stop)
 def check(self,source=None,market=None):
    return validate_derived(source or self.source,self.source_path,market or self.market,self.market_path)
 def test_embedded_market_values_must_equal_pinned_dataset(self):
    self.check();changed=copy.deepcopy(self.market);changed['benchmark']['bars'][0]['close']='999'
    with self.assertRaises(ValueError):self.check(market=changed)
 def test_catalog_date_and_fact_value_cannot_diverge_from_raw(self):
    self.check();changed=copy.deepcopy(self.source);changed['catalog'][0]['publication_date']='2024-04-28'
    with self.assertRaises(ValueError):self.check(source=changed)
    changed=copy.deepcopy(self.source);changed['case']['evidence'][0]['value']='999.00'
    with self.assertRaises(ValueError):self.check(source=changed)
