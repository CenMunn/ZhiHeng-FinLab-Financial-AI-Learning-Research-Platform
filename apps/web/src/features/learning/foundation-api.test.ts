import {afterEach,describe,expect,it,vi} from 'vitest';
import {foundationApi} from './foundation-api';
afterEach(()=>vi.unstubAllGlobals());
describe('foundation API contracts',()=>{
  it('sends versioned snapshot and exact string fee settings to the independent API',async()=>{
    const fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({run_id:'r'})});vi.stubGlobal('fetch',fetch);
    const body={snapshot_id:'ashare-synthetic-v1',expected_snapshot_sha256:'a'.repeat(64),config:{costs:{commission_bps:'3'}}};
    await foundationApi.run(body as never,new AbortController().signal);
    const [url,options]=fetch.mock.calls[0];expect(url).toBe('/api/v1/experiments/foundation');expect(JSON.parse(options.body)).toEqual(body);
  });
  it('surfaces structured server errors and never treats a failed save as success',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,json:async()=>({message:'快照版本变化'})}));
    await expect(foundationApi.runs()).rejects.toThrow('快照版本变化');
  });
  it('keeps request aborts identifiable for late response isolation',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new DOMException('aborted','AbortError')));
    await expect(foundationApi.runs(new AbortController().signal)).rejects.toMatchObject({name:'AbortError'});
  });
});
