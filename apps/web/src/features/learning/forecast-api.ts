import type {CurvePoint} from './backtest-api';
export const FORECAST_METHODS=['zero','train_mean','last_return','ridge','lightgbm','dlinear_ensemble'];
export interface ForecastMetric {rows:number;mae:number;rmse:number;bias:number;mse_skill_vs_zero:number|null;direction_accuracy:number|null;temporal_correlation:number|null;zero_actual_rows:number;neutral_prediction_rows:number}
export interface ForecastPolicy {config:{initial_cash:string;costs:Record<string,string>};metrics:{return:string;max_drawdown:string;turnover:string|null;costs:string;trade_count:number;final_equity:string;final_quantity:string;dividend_receivable:string};curve:CurvePoint[];trades:Record<string,unknown>[];rejections:Record<string,unknown>[]}
export interface ForecastModel {name:string;evaluation:ForecastMetric;validation:ForecastMetric;annual:({year:string}&ForecastMetric)[];mse_difference_interval:{estimate:number;low:number;high:number;block_length:number;resamples:number};policy?:ForecastPolicy}
export interface ForecastSummary {run_id:string;created_at:string;market:'ashare'|'btc';instrument:string;currency:string;counts:Record<string,number>;evaluation:{rows:number;first_signal:string;last_signal:string;first_entry:string;last_exit:string};dataset_sha256:string;prediction_sha256:string;artifact_status:string;models:Record<string,{name:string;evaluation:ForecastMetric;validation:ForecastMetric}>}
export interface ForecastRecord extends ForecastSummary {schema:string;purged:Record<string,number>;config:{lookback:number;target:string;policy_threshold:string;dlinear:Record<string,unknown>;lightgbm:Record<string,unknown>};models:Record<string,ForecastModel>;benchmark:ForecastPolicy;
  observations:{signal_session:string;decision_at:string;entry_session:string;exit_session:string;actual_return:number;predictions:Record<string,number>}[];
  training:{models:Record<string,{best_epoch?:number;epochs?:number;updates?:number;best_iteration?:number;elapsed_seconds:number;device?:string;history?:{epoch:number;train_mse_standardized:number;validation_mse_standardized:number}[]}>;scaler:Record<string,number>;evaluation_labels_read:boolean};
  environment:Record<string,string>;code_sources:Record<string,string>;artifacts:Record<string,string>;artifact_directory:string;preparation_sha256:string;training_sha256:string;labels_sha256:string;limitations:string[];
  dataset:{snapshot:{source_uri:string;calendar_source:string};receipts:{url:string;sha256:string;retrieved_at:string}[]}}
export interface ForecastEnvelope {record:ForecastRecord;record_sha256:string;artifact_status:string;missing_artifacts:string[]}
async function read<T>(path:string,signal?:AbortSignal):Promise<T>{
  let response:Response;
  try{response=await fetch(`/api/v1/forecasts/${path}`,{signal});}catch(error){if((error as Error).name==='AbortError')throw error;throw Error('离线实验服务暂不可用，请稍后重新加载。');}
  let payload;
  try{payload=await response.json();}catch{throw Error('离线实验服务响应无法读取。');}
  if(signal?.aborted)throw new DOMException('aborted','AbortError');
  if(!response.ok)throw Error(typeof payload?.message==='string'?payload.message:'离线实验读取失败。');
  return payload as T;
}
export const forecastApi={runs:(signal?:AbortSignal)=>read<ForecastSummary[]>('runs',signal),reopen:(id:string,signal?:AbortSignal)=>read<ForecastEnvelope>(`runs/${encodeURIComponent(id)}`,signal)};
export function errorBps(value:number|null){return value===null?'—':`${(value*10000).toFixed(2)} bp`;}
export function ratio(value:number|null){return value===null?'—':`${(value*100).toFixed(2)}%`;}
export function forecastReport(r:ForecastRecord){return [`# ${r.instrument} 一步收益预测实验`,
  `信号 ${r.evaluation.first_signal}—${r.evaluation.last_signal}；可执行区间 ${r.evaluation.first_entry}—${r.evaluation.last_exit}；${r.evaluation.rows} 条评估。`,
  '训练2018–2021；验证2022–2023；历史评估2024–2025。每个模型使用过去60期已知收益；不是未知盲测。',
  '| 方法 | RMSE | MAE | 相对零收益MSE改善 | 策略累计收益 |','| --- | --- | --- | --- | --- |',
  ...FORECAST_METHODS.map(k=>{const m=r.models[k];return `| ${m.name} | ${errorBps(m.evaluation.rmse)} | ${errorBps(m.evaluation.mae)} | ${ratio(m.evaluation.mse_skill_vs_zero)} | ${m.policy?ratio(Number(m.policy.metrics.return)):'—'} |`;}),
  '## 口径与限制',...r.limitations.map(p=>'- '+p),'## 复现身份',`实验 ${r.run_id}`,`数据 ${r.dataset_sha256}`,`训练 ${r.training_sha256}`,`预测 ${r.prediction_sha256}`,`环境 ${JSON.stringify(r.environment)}`,
  '完整逐条预测、真实值、训练曲线、成交日志、模型权重指纹及来源请同时导出完整JSON。'].join('\n\n');}
