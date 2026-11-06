import {afterEach,expect,it,vi} from 'vitest';
import {backtestApi,percent,decimalDisplay} from './backtest-api';
afterEach(()=>vi.unstubAllGlobals());
it('distinguishes undefined returns and turnover from zero',()=>{
  expect(percent(null)).toBe('—');expect(percent('0')).toBe('0.00%');
  expect(decimalDisplay(null)).toBe('—');expect(decimalDisplay('0')).toBe('0.00');
});
it('preserves a service validation error instead of returning a fake result',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'缺少区块观察'}),{status:422})));
  await expect(backtestApi.runs()).rejects.toThrow('缺少区块观察');
});
it('rejects a late response when its context was aborted',async()=>{
  const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('[]');}));
  await expect(backtestApi.runs(c.signal)).rejects.toMatchObject({name:'AbortError'});
});
it('explains an unreadable proxy response and encodes a history id',async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response('<html>offline</html>',{status:502}));vi.stubGlobal('fetch',fetch);
  await expect(backtestApi.reopen('x/y')).rejects.toThrow('响应无法读取');
  expect(fetch.mock.calls[0][0]).toBe('/api/v1/backtests/runs/x%2Fy');
});
