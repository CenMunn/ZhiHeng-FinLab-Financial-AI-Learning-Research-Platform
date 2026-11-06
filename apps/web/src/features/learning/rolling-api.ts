import type {ForecastMetric,ForecastPolicy} from './forecast-api';
export const ROLLING_METHODS=['zero','train_mean','last_return','ridge','lightgbm','dlinear_ensemble','enhanced'];
export const PRETRAINED_METHODS=[...ROLLING_METHODS,'random_encoder','chronos'];
export interface RollingSummary {run_id:string;created_at:string;market:'ashare'|'btc';instrument:string;currency:string;rows:number;folds:number;dataset_sha256:string;artifact_status:string}
export interface RollingModel {name:string;metrics:ForecastMetric;wins_vs_zero:number;folds:number}
export interface RollingFold {fold:string;bounds:{train:string[];validation:string[];evaluation:string[]};counts:Record<string,number>;purged:Record<string,number>;
  models:Record<string,{name:string;metrics:ForecastMetric;mse_difference_interval?:{low:number;high:number;estimate:number}}>;
  diagnostics:{validation_permutation:Record<string,{validation_delta_mse_mean:number;repeat_std:number;repeats:number;block:number}>;label_free_drift:Record<string,Record<string,{status:string;psi:number|null;train_mean:number;current_mean:number}>>};
  training:{lightgbm_best_iteration:number;dlinear:Record<string,{best_epoch:number;epochs:number;updates:number;device:string;elapsed_seconds:number}>}}
export interface RollingRecord {schema:string;run_id:string;created_at:string;market:'ashare'|'btc';instrument:string;currency:string;dataset_sha256:string;identity:Record<string,string>;protocol:Record<string,unknown>;
  overall:Record<string,RollingModel>;folds:RollingFold[];policies:Record<string,ForecastPolicy>;cost_sensitivity:Record<string,Record<string,ForecastPolicy['metrics']>>;
  observations:({fold:string;signal_session:string;actual_return:number;predictions:Record<string,number>})[];
  pretrained:{cohort:string;models:Record<string,RollingModel>;policies:Record<string,ForecastPolicy>;cost_sensitivity?:Record<string,Record<string,ForecastPolicy['metrics']>>;
    acquisition:{repo:string;revision:string;public_at:string;license:string;training_cutoff:string;mode:string;files:Record<string,{sha256:string;url:string}>};
    encoders:Record<string,{width:number;frozen_parameters:number;trainable_base_parameters:number;state_sha256:string;encoder_identity_sha256?:string;rows:number;device:string}>};
  phase_receipts:{base:{started_at:string;finished_at:string};pretrained:{started_at:string;finished_at:string}};artifacts:Record<string,string>;limitations:string[]}
export interface RollingEnvelope {record:RollingRecord;record_sha256:string;artifact_status:string;missing_artifacts:string[]}
async function read<T>(path:string,signal?:AbortSignal):Promise<T>{
  let response:Response;try{response=await fetch(`/api/v1/rolling/${path}`,{signal});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('滚动实验服务暂不可用，请稍后重试。');}
  let payload;try{payload=await response.json();}catch{throw Error('滚动实验响应无法读取。');}
  if(signal?.aborted)throw new DOMException('aborted','AbortError');
  if(!response.ok)throw Error(typeof payload?.message==='string'?payload.message:'滚动实验读取失败。');
  return payload as T;
}
export const rollingApi={runs:(signal?:AbortSignal)=>read<RollingSummary[]>('runs',signal),reopen:(id:string,signal?:AbortSignal)=>read<RollingEnvelope>(`runs/${encodeURIComponent(id)}`,signal)};
export function diagnosticNumber(value:number|null){return value===null?'—':value.toFixed(3);}
