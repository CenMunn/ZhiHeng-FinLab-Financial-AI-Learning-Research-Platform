import {afterEach,expect,it,vi} from 'vitest';
import {volatilityApi,volatilityPercent,metricNumber,latestVolatilityRuns} from './volatility-api';
afterEach(()=>vi.unstubAllGlobals());
it('distinguishes unknown from zero and shows annualized proxy amplitude',()=>{
  expect(metricNumber(null)).toBe('—');expect(metricNumber(0)).toBe('0.000');
  expect(volatilityPercent(.0001,252)).toBe('15.87%');
});
it('retains a latest version for every market and horizon without dropping old identity',()=>{
  const runs=[{run_id:'new5',market:'ashare',horizon:5},{run_id:'new1',market:'ashare',horizon:1},{run_id:'old5',market:'ashare',horizon:5},{run_id:'btc',market:'btc',horizon:1}];
  expect(latestVolatilityRuns(runs as never).map(r=>r.run_id)).toEqual(['new5','new1','btc']);
});
it('rejects corrupt and unreadable results and does not POST',async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'波动记录校验失败'}),{status:409}));vi.stubGlobal('fetch',fetch);
  await expect(volatilityApi.runs()).rejects.toThrow('波动记录校验失败');
  expect(fetch.mock.calls[0][1]).not.toHaveProperty('method','POST');
});
it('discards late responses and binds detail identity to the selected record',async()=>{
  const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('[]');}));
  await expect(volatilityApi.runs(c.signal)).rejects.toMatchObject({name:'AbortError'});
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({record:{run_id:'wrong'}}))));
  await expect(volatilityApi.reopen('expected')).rejects.toThrow('身份');
});
it('rejects malformed success responses before they reach the result view',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}')));
  await expect(volatilityApi.runs()).rejects.toThrow('目录格式');
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({record:{run_id:'expected'}}))));
  await expect(volatilityApi.reopen('expected')).rejects.toThrow('结果格式');
});
