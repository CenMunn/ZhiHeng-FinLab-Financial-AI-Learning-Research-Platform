import {afterEach,expect,it,vi} from 'vitest';
import {readValidationFoundation,validationFoundationReport} from './validation-foundation-api';
afterEach(()=>vi.unstubAllGlobals());
it('shows missing publication honestly and only reads',async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response('{}',{status:404}));vi.stubGlobal('fetch',fetch);
 await expect(readValidationFoundation()).rejects.toThrow('尚未发布');
 expect(fetch.mock.calls[0][0]).toBe('/api/v1/validation-foundation/report');expect(fetch.mock.calls[0][1].cache).toBe('no-store');expect(fetch.mock.calls[0][1].method).toBeUndefined();
});
it('rejects an abandoned response and malformed success before rendering',async()=>{
 const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('{}');}));
 await expect(readValidationFoundation(c.signal)).rejects.toMatchObject({name:'AbortError'});
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}')));await expect(readValidationFoundation()).rejects.toThrow('格式');
});
it('preserves server integrity refusal and network recovery messages',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'完整性拒绝'}),{status:409})));await expect(readValidationFoundation()).rejects.toThrow('完整性拒绝');
 vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));await expect(readValidationFoundation()).rejects.toThrow('暂不可用');
});
it('exports complete evidence and an explicit no-results prospective boundary with real newlines',()=>{
 const body={record:{report_id:'fixture',protocol_sha256:'abc',limitations:['fixture only'],assets:[]},record_sha256:'abc',artifact_status:'missing',missing_artifacts:['fixture.json']};
 const text=validationFoundationReport(body as never);expect(text).toContain('\n\n');expect(text).toContain('2026-11-06');expect(text).toContain('无前瞻成绩');expect(text).toContain('fixture.json');expect(text).toContain('"assets": []');
});
