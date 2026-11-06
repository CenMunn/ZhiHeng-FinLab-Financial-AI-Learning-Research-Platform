import { afterEach, expect, it, vi } from 'vitest';
import { api } from './api';
afterEach(()=>vi.unstubAllGlobals());
it('rejects comparison from another engine identity rather than leaving loading forever',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({current:{input_hash:'new'}}))));
  await expect(api.compare({snapshot_id:'case',expected_snapshot_sha256:'a'.repeat(64),assumptions:{credit_share:'0.8',delay_days:'15'}},undefined,'old')).rejects.toThrow('版本');
});
it('explains a stopped local service and preserves abort semantics',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
  await expect(api.cases()).rejects.toThrow('本地服务');
  const abort=new DOMException('Aborted','AbortError');
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(abort));
  await expect(api.cases()).rejects.toBe(abort);
});
it('handles a non-JSON proxy failure with an actionable message',async()=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('<html>Bad gateway</html>',{status:502})));
  await expect(api.scenarios()).rejects.toThrow('重试');
});
