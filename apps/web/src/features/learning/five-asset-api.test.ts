import {afterEach,expect,it,vi} from 'vitest';
import {fiveAssetApi,fiveAssetReport} from './five-asset-api';
afterEach(()=>vi.unstubAllGlobals());
it('keeps read-only errors and discards delayed responses',async()=>{
 const fetch=vi.fn().mockResolvedValue(new Response(JSON.stringify({message:'来源校验失败'}),{status:409}));vi.stubGlobal('fetch',fetch);
 await expect(fiveAssetApi.runs()).rejects.toThrow('来源校验失败');expect(fetch.mock.calls[0][1]).not.toHaveProperty('method','POST');
 const c=new AbortController();vi.stubGlobal('fetch',vi.fn(async()=>{c.abort();return new Response('[]');}));await expect(fiveAssetApi.runs(c.signal)).rejects.toMatchObject({name:'AbortError'});
});
it('binds full symbol/horizon/version context and rejects malformed catalogs',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}')));await expect(fiveAssetApi.runs()).rejects.toThrow('目录');
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({record:{run_id:'expected',symbol:'ETHUSDT',horizon:5}}))));await expect(fiveAssetApi.reopen('expected','600519',1)).rejects.toThrow('身份');
});
it('exports complete evidence and truthful retraining boundary',()=>{
 const body={record:{symbol:'600519',name:'fixture',horizon:1,run_id:'five-test',overall:{},limitations:['有限预算'],folds:[],regimes:{},protocol:{budget:30}},record_sha256:'sha',artifact_status:'missing',missing_artifacts:['model']};
 const text=fiveAssetReport(body as never);expect(text).toContain('逐标的重训');expect(text).toContain('five-test');expect(text).toContain('model');expect(text).toContain('有限预算');expect(text).toContain('\n\n');
});
