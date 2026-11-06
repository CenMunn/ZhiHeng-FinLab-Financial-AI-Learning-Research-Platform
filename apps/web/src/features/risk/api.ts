export interface EvidenceLocator {
  source_id: string; source_url: string; source_sha256: string;
  value_page: number; header_pages: number[]; printed_page: number | null;
  excerpt: string; review_status: string; availability_status: string; version_status: string;
  file_status: 'verified_at_load' | 'missing' | 'changed' | 'synthetic'; audit_warning: string;
}
export interface CaseSnapshot {
  snapshot_id: string; snapshot_sha256: string; company_id: string; company_name: string;
  report_id: string; period_start: string; period_end: string; currency: 'CNY'; scope: 'consolidated';
  revenue: string; days: number; evidence: EvidenceLocator; limitations: string[]; source_kind: string;
}
export interface Assumptions { credit_share: string; delay_days: string }
export interface CalculationResult {
  schema_version: string; formula_version: string; engine_version: string; input_hash: string;
  snapshot: CaseSnapshot; assumptions: Assumptions; occupancy_change: string; cash_equivalent_change: string;
  unrounded_occupancy_change: string; formula: string; limitations: string[];
  sensitivity_curve: {delay_days: string; occupancy_change: string}[];
}
export interface SavedScenario { scenario_id: string; project_id: string; title: string; created_at: string; result: CalculationResult }
export interface ComparisonResult { current: CalculationResult; reference: CalculationResult; reference_title: string; difference: string }
export interface CalculationRequest { snapshot_id: string; expected_snapshot_sha256: string; assumptions: Assumptions }

async function read<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response:Response;
  try{response=await fetch(`/api/v1/${path}`,options);}
  catch(error){if((error as Error).name==='AbortError')throw error;throw new Error('无法连接本地服务，请检查服务是否运行后重试。');}
  let payload;
  try{payload=await response.json();}
  catch{throw new Error('服务响应暂时无法读取，请稍后重试。');}
  if (!response.ok) throw new Error(typeof payload?.message==='string'?payload.message:'请求失败，请重试。');
  return payload as T;
}
const post = (body: unknown): RequestInit => ({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const api = {
  cases: (signal?: AbortSignal) => read<CaseSnapshot[]>('cases',{signal}),
  scenarios: (signal?: AbortSignal) => read<SavedScenario[]>('scenarios',{signal}),
  calculate: (body: CalculationRequest) => read<CalculationResult>('risk/receivables-delay',post(body)),
  compare: async (body: CalculationRequest, reference: string|undefined, expectedHash: string) => {
    const value=await read<ComparisonResult>('risk/receivables-compare',post({...body,reference_scenario_id:reference || null}));
    if(value.current.input_hash!==expectedHash)throw new Error('计算版本不同，已保存结果保持原样；请重新计算后比较。');
    return value;
  },
  sourceStatus: (sourceId:string,sha:string) => read<{status:'available'|'missing'|'changed'}>(`sources/${encodeURIComponent(sourceId)}/status?expected_sha256=${sha}`),
  save: (body: CalculationRequest & {title:string;expected_input_hash:string}, key: string) => read<SavedScenario>('scenarios',{
    ...post(body),headers:{'Content-Type':'application/json','Idempotency-Key':key}}),
  reopen: (id: string) => read<SavedScenario>(`scenarios/${encodeURIComponent(id)}`),
};
