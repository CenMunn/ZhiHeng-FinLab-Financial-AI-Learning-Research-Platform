import {afterEach,expect,it,vi} from 'vitest';
import {forecastApi,errorBps} from './forecast-api';
afterEach(()=>vi.unstubAllGlobals());
it('shows error in basis points and preserves undefined values',()=>{
  expect(errorBps(.017)).toBe('170.00 bp');expect(errorBps(null)).toBe('—');
});
it('never treats corrupt experiments as valid results',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'离线结果校验失败'}),{status:409})));
  await expect(forecastApi.runs()).rejects.toThrow('离线结果校验失败');
});
it('rejects late responses after a market context abort',async()=>{
  const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('[]');}));
  await expect(forecastApi.runs(c.signal)).rejects.toMatchObject({name:'AbortError'});
});
