export interface FoundationConfig {
  train_count:number;validation_count:number;window:number;horizon:number;as_of:string;seed:number;
  costs:{commission_bps:string;minimum_commission:string;sell_tax_bps:string;transfer_bps:string;slippage_bps:string;kind:'teaching_assumption'};
}
export interface FoundationSnapshot {
  snapshot_id:string;snapshot_sha256:string;market:'ashare'|'btc';instrument:string;venue:string;currency:string;
  source_kind:string;source_uri:string;calendar_source:string;row_count:number;start:string;end:string;default_config:FoundationConfig;limitations:string[];
}
export interface FoundationRequest {snapshot_id:string;expected_snapshot_sha256:string;config:FoundationConfig}
export interface FoundationHistory {run_id:string;created_at:string;snapshot_id:string;market:'ashare'|'btc';input_hash:string;window:number;source_kind:string}
export interface FoundationRecord {
  run_id:string;created_at:string;snapshot:{snapshot_id:string;source_kind:string};
  result:{market:'ashare'|'btc';input_hash:string;snapshot_sha256:string;engine_version:string;engine_sha256:string;config:FoundationConfig;
    quality:{total_rows:number;eligible_rows:number;excluded_as_of:number;unavailable_rows:number;halted_rows:number;complete_feature_rows:number;calendar_match:boolean};
    splits:{name:string;start:string;end:string;rows:number;label_count:number;purged_count:number}[];
    scaler:{fit_start:string;fit_end:string;fit_count:number;mean:string|null;std:string|null};
    features:{session:string;return_1d:string|null;sma:string|null;volatility:string|null;standardized_return:string|null}[];
    market_rules:{timezone:string;currency:string;buy_quantity_step:string;sell_delay_sessions:number;scope:string};
    cost_example:{notional:string;currency:string;kind:string;buy:{total:string};sell:{total:string}};limitations:string[]};
}
async function read<T>(path:string,options:RequestInit={}):Promise<T>{
  let response:Response;
  try{response=await fetch(`/api/v1/experiments/${path}`,options);}catch(error){if((error as Error).name==='AbortError')throw error;throw Error('无法连接实验服务，请检查本地服务后重试。');}
  let payload;
  try{payload=await response.json();}catch{throw Error('实验服务响应无法读取，请重试。');}
  if(options.signal?.aborted)throw new DOMException('aborted','AbortError');
  if(!response.ok)throw Error(typeof payload?.message==='string'?payload.message:'检查未成功，请检查输入范围后重试。');
  return payload as T;
}
export const foundationApi={
  snapshots:(signal?:AbortSignal)=>read<FoundationSnapshot[]>('snapshots',{signal}),
  runs:(signal?:AbortSignal)=>read<FoundationHistory[]>('runs',{signal}),
  reopen:(id:string,signal?:AbortSignal)=>read<FoundationRecord>(`runs/${encodeURIComponent(id)}`,{signal}),
  run:(body:FoundationRequest,signal?:AbortSignal)=>read<FoundationRecord>('foundation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal}),
};
