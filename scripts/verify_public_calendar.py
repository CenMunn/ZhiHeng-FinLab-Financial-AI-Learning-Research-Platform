"""Cross-check fixed XSHG against manually encoded SSE announcements, not prices."""
from datetime import date,timedelta
import json
from pathlib import Path
from fetch_public_market_data import fetch,ROOT,parse_xshg_calendar,CALENDAR

# Intervals transcribed before comparison from the linked SSE holiday notices.
RANGES={
 2024:[('01-01','01-01'),('02-09','02-17'),('04-04','04-06'),('05-01','05-05'),('06-10','06-10'),('09-15','09-17'),('10-01','10-07')],
 2025:[('01-01','01-01'),('01-28','02-04'),('04-04','04-06'),('05-01','05-05'),('05-31','06-02'),('10-01','10-08')],
}
URLS={2024:'https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20231226_5733941.shtml',
      2025:'https://www.sse.com.cn/disclosure/dealinstruc/closed/c/c_20241223_10767110.shtml'}

if __name__=='__main__':
    raw,source=fetch(CALENDAR,'xshg-4.11.2.py');results=[]
    for year,ranges in RANGES.items():
        html,receipt=fetch(URLS[year],f'sse-calendar-{year}.html')
        if f'{year}年休市安排' not in html.decode('utf8'):raise ValueError('官方公告标题不匹配')
        holidays=set()
        for first,last in ranges:
            first=date.fromisoformat(f'{year}-{first}');last=date.fromisoformat(f'{year}-{last}')
            holidays.update(first+timedelta(days=i) for i in range((last-first).days+1))
        start=date(year,1,1);end=date(year,12,31)
        official=tuple(start+timedelta(days=i) for i in range((end-start).days+1) if (start+timedelta(days=i)).weekday()<5 and start+timedelta(days=i) not in holidays)
        actual=parse_xshg_calendar(raw.decode(),start,end)
        if actual!=official:raise ValueError('社区日历与官方公告编码不一致')
        results.append({'year':year,'sessions':len(actual),'match':True,'method':'公告范围人工编码，程序比较全年每一日；不是从行情推导','receipt':receipt.model_dump(mode='json')})
    url='https://www.sse.com.cn/disclosure/announcement/general/c/c_20200127_4991582.shtml'
    html,receipt=fetch(url,'sse-covid-extension-2020.html')
    if '2月3日' not in html.decode('utf8'):raise ValueError('延长休市公告内容不匹配')
    days=parse_xshg_calendar(raw.decode(),date(2020,1,31),date(2020,2,3))
    assert days==(date(2020,2,3),)
    results.append({'year':2020,'scope':'只核对1月31日至2月3日延长休市段','match':True,'receipt':receipt.model_dump(mode='json')})
    target=Path(__file__).resolve().parents[1]/'docs/research/2026-10-30-calendar-audit.json'
    target.write_text(json.dumps({'calendar_sha256':source.sha256,'checks':results},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'checks':[{k:v for k,v in r.items() if k!='receipt'} for r in results]},ensure_ascii=False))
