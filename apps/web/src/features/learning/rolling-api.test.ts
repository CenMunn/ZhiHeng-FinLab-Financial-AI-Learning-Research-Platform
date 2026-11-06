import {afterEach,expect,it,vi} from 'vitest';
import {rollingApi,diagnosticNumber} from './rolling-api';
afterEach(()=>vi.unstubAllGlobals());
it('keeps unknown diagnostic values distinct from measured zero',()=>{
  expect(diagnosticNumber(null)).toBe('—');expect(diagnosticNumber(0)).toBe('0.000');
});
it('does not accept a corrupt rolling record as a successful run',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'滚动校验失败'}),{status:409})));
  await expect(rollingApi.runs()).rejects.toThrow('滚动校验失败');
});
it('discards a response after its request context is aborted',async()=>{
  const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('[]');}));
  await expect(rollingApi.runs(c.signal)).rejects.toMatchObject({name:'AbortError'});
});
