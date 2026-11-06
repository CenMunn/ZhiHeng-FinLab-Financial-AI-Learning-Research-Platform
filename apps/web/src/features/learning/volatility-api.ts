export interface VolatilitySummary {run_id:string;created_at:string;market:'ashare'|'btc';instrument:string;horizon:1|5;rows:number;artifact_status:'verified'|'missing'}
export interface VolatilityMetrics {rows:number;qlike:number;variance_rmse:number;variance_mae:number;volatility_rmse_ann:number;calibration_ratio:number|null;prediction_floor_count:number}
export interface VolatilityComparison {delta_qlike:number;ci_low:number|null;ci_high:number|null;block:number;repeats:number}
export interface VolatilityModel {name:string;metrics:VolatilityMetrics|null;comparison:VolatilityComparison|null}
export interface VolatilityOverall extends VolatilityModel {metrics:VolatilityMetrics;comparison:VolatilityComparison;wins_vs_ewma:number;folds:number}
export interface VolatilityObservation {session:string;label_end:string;fold:string;regime:string;realized_variance:number;predictions:Record<string,number>}
export interface VolatilityFold {fold:string;bounds:Record<string,string[]>;counts:Record<string,number>;purged:Record<string,number>;regime_thresholds:Record<string,unknown>;models:Record<string,VolatilityModel>;training:Record<string,unknown>}
export interface VolatilityRecord {schema:string;run_id:string;created_at:string;market:'ashare'|'btc';instrument:string;currency:string;horizon:1|5;annualization:252|365;
  identity:Record<string,string>;dataset_sha256:string;dataset:Record<string,unknown>;protocol:Record<string,unknown>;folds:VolatilityFold[];
  overall:Record<string,VolatilityOverall>;regimes:Record<string,{name:string;rows:number;sufficient:boolean;models:Record<string,VolatilityModel>}>;
  observations:VolatilityObservation[];artifacts:Record<string,string>;limitations:string[];phase_receipts:Record<string,unknown>}
export interface VolatilityEnvelope {record:VolatilityRecord;record_sha256:string;artifact_status:'verified'|'missing';missing_artifacts:string[]}

async function read<T>(path:string,signal?:AbortSignal):Promise<T>{
  let response:Response;
  try{response=await fetch(`/api/v1/volatility/${path}`,{signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('波动实验服务暂不可用，请稍后重试。');}
  let payload;try{payload=await response.json();}catch{throw Error('波动实验响应无法读取，请重试。');}
  if(signal?.aborted)throw new DOMException('aborted','AbortError');
  if(!response.ok)throw Error(typeof payload?.message==='string'?payload.message:'波动实验读取失败。');
  return payload as T;
}
export const volatilityApi={
  async runs(signal?:AbortSignal){
    const rows=await read<VolatilitySummary[]>('runs',signal);
    if(!Array.isArray(rows)||rows.some(row=>!row||typeof row.run_id!=='string'||!['ashare','btc'].includes(row.market)||![1,5].includes(row.horizon)||!Number.isInteger(row.rows)))throw Error('波动实验目录格式不完整，请重试。');
    return rows;
  },
  async reopen(id:string,signal?:AbortSignal){
    const body=await read<VolatilityEnvelope>(`runs/${encodeURIComponent(id)}`,signal);
    if(body?.record?.run_id!==id)throw Error('波动记录身份与所选版本不符。');
    const r=body.record;
    if(r.schema!=='volatility-result-v1'||!Array.isArray(r.folds)||!r.folds.length||!Array.isArray(r.observations)||!r.observations.length||!r.overall?.ewma||!r.regimes||!Array.isArray(r.limitations)||!Array.isArray(body.missing_artifacts)||!['verified','missing'].includes(body.artifact_status))throw Error('波动结果格式不完整，请重试。');
    return body;
  }
};
export function latestVolatilityRuns(runs:VolatilitySummary[]){return runs.filter((run,i)=>runs.findIndex(other=>other.market===run.market&&other.horizon===run.horizon)===i);}
export function metricNumber(value:number|null|undefined,digits=3){return value==null?'—':value.toFixed(digits);}
export function volatilityPercent(variance:number,annualization:number){return `${(Math.sqrt(variance*annualization)*100).toFixed(2)}%`;}
export function volatilityReport(body:VolatilityEnvelope){
  const r=body.record;
  return [`# ${r.instrument} · 未来${r.horizon}个市场日波动代理`,
    '目标：未来收益平方的日均值，表示波动幅度，不预测涨跌，不等同高频实现方差或可交易收益。',
    `年化口径 ${r.annualization}；5日标签不再除以5。2024–2025八季度完整报告。`,
    '| 方法 | QLIKE | 相对EWMA损失差 | 95%探索性区间 | 胜出季度 |', '| --- | --- | --- | --- | --- |',
    ...Object.values(r.overall).map(m=>`| ${m.name} | ${metricNumber(m.metrics.qlike)} | ${metricNumber(m.comparison.delta_qlike)} | ${metricNumber(m.comparison.ci_low)} 至 ${metricNumber(m.comparison.ci_high)} | ${m.wins_vs_ewma}/${m.folds} |`),
    'QLIKE与损失差越低越好；绝对值允许为负，不跨市场排名。区间为逐比较探索性配对块bootstrap，不作多重检验确认。',
    '## 全部季度与市况',JSON.stringify({folds:r.folds,regimes:r.regimes},null,2),
    '## 来源与限制',...r.limitations.map(x=>`- ${x}`),`实验：${r.run_id}`,`数据SHA：${r.dataset_sha256}`,`记录SHA：${body.record_sha256}`,
    `产物状态：${body.artifact_status}；缺失项：${body.missing_artifacts.join('、')||'无'}`,
    '逐行预测、完整数据快照、协议、训练收据与产物指纹可另下载完整JSON。'].join('\n\n');
}
