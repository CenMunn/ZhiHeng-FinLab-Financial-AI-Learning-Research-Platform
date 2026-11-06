import {afterEach,expect,it,vi} from 'vitest';
import {readDiagnostics,diagnosticReport} from './diagnostic-api';
const source={record:{run_id:'volatility-selected',market:'ashare',horizon:1,overall:{ewma:{}},folds:[{}]},record_sha256:'parent-sha'} as never;
afterEach(()=>vi.unstubAllGlobals());
it('uses read-only GET and binds diagnostics to the parent SHA, market and horizon',async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({record:{source_run_id:'volatility-selected',source_record_sha256:'wrong',market:'ashare',horizon:1}})));vi.stubGlobal('fetch',fetch);
 await expect(readDiagnostics(source)).rejects.toThrow('版本不符');expect(fetch.mock.calls[0][0]).toContain('runs/volatility-selected/diagnostics');expect(fetch.mock.calls[0][1]).not.toHaveProperty('method','POST');
});
it('explains missing diagnostics and preserves backend integrity errors',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:404})));await expect(readDiagnostics(source)).rejects.toThrow('尚无此版本');
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'完整性失败'}),{status:409})));await expect(readDiagnostics(source)).rejects.toThrow('完整性失败');
});
it('discards aborted late responses',async()=>{const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('{}');}));await expect(readDiagnostics(source,c.signal)).rejects.toMatchObject({name:'AbortError'});});
it('rejects malformed successful data before rendering',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({record:{source_run_id:'volatility-selected',source_record_sha256:'parent-sha',market:'ashare',horizon:1}}))));await expect(readDiagnostics(source)).rejects.toThrow('格式不完整');});
it('exports source identities, every model and complete evidence with limitations',()=>{
 const body={record:{market:'ashare',horizon:5,source_run_id:'original-id',source_record_sha256:'original-sha',models:{a:{name:'all-seed-model',raw:{qlike:2},calibrated:{qlike:3},comparison:{delta_qlike:1},windows:[{start:'window-date'}]}},limitations:['not independent calibration']},record_sha256:'diagnostic-sha',artifact_status:'missing',missing_artifacts:['missing-file']} as never;
 const text=diagnosticReport(body);for(const value of ['original-id','original-sha','all-seed-model','window-date','not independent calibration','missing-file','diagnostic-sha'])expect(text).toContain(value);
});
