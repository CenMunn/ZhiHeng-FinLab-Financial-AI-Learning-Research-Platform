import type {VolatilityMetrics,VolatilityComparison} from './volatility-api';
export interface FiveSummary {run_id:string;created_at:string;symbol:string;name:string;market:'ashare'|'crypto';horizon:1|5;rows:number;artifact_status:'verified'|'missing'}
export interface FiveModel {name:string;raw:VolatilityMetrics|null;calibrated:VolatilityMetrics|null;raw_vs_ewma:VolatilityComparison|null;calibrated_vs_ewma:VolatilityComparison|null;calibrated_vs_raw:VolatilityComparison|null;wins_raw?:number;wins_calibrated?:number;folds?:number;c?:number;raw_c?:number;clipped?:boolean;calibration_rows?:number}
export interface FiveRecord extends Omit<FiveSummary,'rows'|'artifact_status'> {schema:string;annualization:number;identity:Record<string,string>;source_report_id:string;source_report_sha256:string;protocol:Record<string,unknown>;overall:Record<string,FiveModel>;folds:{fold:string;bounds:Record<string,string[]>;counts:Record<string,number>;models:Record<string,FiveModel>;training:Record<string,unknown>}[];regimes:Record<string,{name:string;rows:number;sufficient:boolean;models:Record<string,FiveModel>}>;observations:{session:string;label_end:string;fold:string;regime:string;realized_variance:number;raw:Record<string,number>;calibrated:Record<string,number>}[];artifacts:Record<string,string>;limitations:string[]}
export interface FiveEnvelope {record:FiveRecord;record_sha256:string;artifact_status:'verified'|'missing';missing_artifacts:string[]}
async function read<T>(path:string,signal?:AbortSignal):Promise<T>{
 let response:Response;try{response=await fetch(`/api/v1/five-asset/${path}`,{signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('五标的实验服务暂不可用，请重试。');}
 let body;try{body=await response.json();}catch{throw Error('五标的响应无法读取，请重试。');}
 if(signal?.aborted)throw new DOMException('aborted','AbortError');if(!response.ok)throw Error(body?.message||'五标的实验读取失败。');return body as T;
}
export const fiveAssetApi={
 async runs(signal?:AbortSignal){const rows=await read<FiveSummary[]>('runs',signal);if(!Array.isArray(rows)||rows.some(r=>!r||typeof r.run_id!=='string'||!['ashare','crypto'].includes(r.market)||typeof r.symbol!=='string'||![1,5].includes(r.horizon)||!Number.isInteger(r.rows)))throw Error('五标的目录格式不完整。');return rows;},
 async reopen(id:string,symbol:string,horizon:1|5,signal?:AbortSignal){const body=await read<FiveEnvelope>(`runs/${encodeURIComponent(id)}`,signal),r=body?.record;
 if(r?.run_id!==id||r?.symbol!==symbol||r?.horizon!==horizon)throw Error('五标的结果身份与所选标的、期限或版本不符。');
 if(r.schema!=='five-asset-result-v1'||r.folds?.length!==8||!r.overall?.ewma||!r.observations?.length||!r.regimes||!Array.isArray(r.limitations)||!Array.isArray(body.missing_artifacts)||!['verified','missing'].includes(body.artifact_status))throw Error('五标的结果格式不完整。');return body;
 }
};
export function fiveAssetReport(body:FiveEnvelope){const r=body.record;return [`# ${r.name} ${r.symbol} · 未来 ${r.horizon} 日波动幅度`,
 '逐标的重训：流程稳健性复现，不是零样本迁移。历史时期已研究；2026-11-06 前瞻仍 pending，无前瞻成绩。无仓位或实盘收益。',
 '|方法|原始 QLIKE|校准 QLIKE|原始 vs EWMA|校准 vs EWMA|校准 vs 原始|','|---|---|---|---|---|---|',...Object.values(r.overall).map(m=>`|${m.name}|${m.raw?.qlike??'—'}|${m.calibrated?.qlike??'—'}|${m.raw_vs_ewma?.delta_qlike??'—'}|${m.calibrated_vs_ewma?.delta_qlike??'—'}|${m.calibrated_vs_raw?.delta_qlike??'—'}|`),
 '## 全季度、市况、协议与训练收据',JSON.stringify({overall:r.overall,folds:r.folds,regimes:r.regimes,protocol:r.protocol},null,2),'## 来源与限制',...r.limitations,`实验 ${r.run_id}`,`原资格 ${r.source_report_id} / ${r.source_report_sha256}`,`记录 ${body.record_sha256}`,`产物 ${body.artifact_status}；缺失 ${body.missing_artifacts.join('、')||'无'}`,JSON.stringify(r.artifacts,null,2)].join('\n\n');}
