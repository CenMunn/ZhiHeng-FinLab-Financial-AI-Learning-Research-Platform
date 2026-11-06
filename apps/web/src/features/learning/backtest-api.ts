import type {FoundationConfig} from './foundation-api';
export interface BacktestConfig {start:string;end:string;window:number;initial_cash:string;costs:FoundationConfig['costs']}
export interface PublicData {dataset_id:string;dataset_sha256:string;market:'ashare'|'btc';instrument:string;currency:string;start:string;end:string;row_count:number;quality:Record<string,unknown>;limitations:string[];default_config:BacktestConfig}
export interface BacktestHistory {run_id:string;created_at:string;dataset_id:string;market:'ashare'|'btc';window:number;start:string;end:string;engine_sha256:string}
export interface CurvePoint {session:string;cash:string;quantity:string;close:string;dividend_receivable:string;equity:string;wealth:string;drawdown:string;signal_session:string;target:number;signal_close:string;sma:string|null;cycle:{height:number;index:string;phase:string}|null}
export interface Strategy {metrics:{return:string;annualized_return:string|null;max_drawdown:string;turnover:string|null;costs:string;trade_count:number;rejection_count:number;exposure_fraction:string;final_equity:string;final_cash:string;final_quantity:string;dividend_receivable:string;excess_return:string};
  curve:CurvePoint[];annual:{year:string;return:string|null}[];trades:{session:string;signal_session:string|null;decision_at:string;fill_at:string;side:string;quantity:string;price:string;costs:{total:string}}[];
  rejections:{session:string;side:string;reason:string}[];undefined_relative_windows?:number;worst_relative_window:{start:string;end:string;excess_return:string;strategy_return:string;benchmark_return:string;sessions:number}|null}
export interface BacktestRecord {run_id:string;created_at:string;dataset:{snapshot:{source_kind:string;calendar_source:string;source_uri:string;source_license:string};timing_assumption:string;receipts:{url:string;retrieved_at:string;sha256:string;publisher_checksum:string|null}[]};
  result:{market:'ashare'|'btc';instrument:string;currency:string;config:BacktestConfig;dataset_id:string;dataset_sha256:string;engine_sha256:string;input_sha256:string;evaluation:{start:string;end:string;rows:number;protocol:string};strategies:Record<string,Strategy>;quality:Record<string,unknown>;rules:string[];limitations:string[]}}
async function read<T>(path:string,options:RequestInit={}):Promise<T>{
  let response:Response;
  try{response=await fetch(`/api/v1/backtests/${path}`,options);}catch(error){if((error as Error).name==='AbortError')throw error;throw Error('无法连接回测服务，请检查本地服务后重试。');}
  let payload;
  try{payload=await response.json();}catch{throw Error('回测服务响应无法读取，请重试。');}
  if(options.signal?.aborted)throw new DOMException('aborted','AbortError');
  if(!response.ok)throw Error(typeof payload?.message==='string'?payload.message:'回测未成功，请检查参数后重试。');
  return payload as T;
}
export const backtestApi={
  datasets:(signal?:AbortSignal)=>read<{datasets:PublicData[];unavailable:{dataset_id:string;message:string}[]}>('datasets',{signal}),
  runs:(signal?:AbortSignal)=>read<BacktestHistory[]>('runs',{signal}),
  reopen:(id:string,signal?:AbortSignal)=>read<BacktestRecord>(`runs/${encodeURIComponent(id)}`,{signal}),
  run:(dataset:PublicData,config:BacktestConfig,signal?:AbortSignal)=>read<BacktestRecord>('compare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dataset_id:dataset.dataset_id,expected_dataset_sha256:dataset.dataset_sha256,config}),signal}),
};
export const STRATEGIES:Record<string,string>={buy_hold:'买入持有',trend:'均线趋势',halving_cycle:'减半周期假设'};
export function percent(value:string|null){return value===null?'—':`${(Number(value)*100).toFixed(2)}%`;}
export function money(value:string){return Number(value).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});}
export function decimalDisplay(value:string|null){return value===null?'—':Number(value).toFixed(2);}
export function percentagePoints(value:string){return `${(Number(value)*100).toFixed(2)} 个百分点`;}

export function reportText(record:BacktestRecord){
  const r=record.result;
  return [`# ${r.instrument} 入门历史对照`,`${r.evaluation.start} 至 ${r.evaluation.end}；${r.evaluation.rows}根日线；窗口${r.config.window}；起始现金${r.config.initial_cash} ${r.currency}`,
    r.evaluation.protocol,'费用：'+JSON.stringify(r.config.costs),
    '| 方法 | 累计收益 | 最大回撤 | 双边换手倍数 | 成本 | 成交次数 |','| --- | --- | --- | --- | --- | --- |',
    ...Object.entries(r.strategies).map(([key,s])=>`| ${STRATEGIES[key]} | ${percent(s.metrics.return)} | ${percent(s.metrics.max_drawdown)} | ${decimalDisplay(s.metrics.turnover)} | ${s.metrics.costs} ${r.currency} | ${s.metrics.trade_count} |`),
    '## 失败观察',...Object.entries(r.strategies).filter(([k])=>k!=='buy_hold').map(([k,s])=>s.worst_relative_window?`${STRATEGIES[k]}：最差${s.worst_relative_window.sessions}期相对区间 ${s.worst_relative_window.start}—${s.worst_relative_window.end}，策略减买入持有 ${percentagePoints(s.worst_relative_window.excess_return)}；另有${s.undefined_relative_windows||0}个零起点窗口无法定义。`:`${STRATEGIES[k]}：没有可定义的相对收益窗口。`),
    '## 口径与限制',...r.rules.map(x=>'- '+x),...r.limitations.map(x=>'- '+x),'## 追溯',
    '行情来源：'+record.dataset.snapshot.source_uri,'日历来源：'+record.dataset.snapshot.calendar_source,
    '数据SHA256：'+r.dataset_sha256,'代码SHA256：'+r.engine_sha256,'实验ID：'+record.run_id,
    `${record.dataset.receipts.length}份来源凭据；完整快照、费用、逐日账本和成交日志请同时导出完整JSON。`].join('\n\n');
}
