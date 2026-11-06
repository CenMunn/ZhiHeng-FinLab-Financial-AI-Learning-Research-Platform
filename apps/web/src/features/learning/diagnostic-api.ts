import type {VolatilityMetrics,VolatilityComparison,VolatilityEnvelope} from './volatility-api';
export interface DiagnosticBin {lower:number|null;upper:number|null;rows:number;prediction_mean:number|null;realized_mean:number|null;ratio:number|null}
export interface DiagnosticWindow {fold:string;start:string;end:string;rows:number;raw_qlike:number;calibrated_qlike:number;ewma_qlike:number;raw_delta:number;calibrated_delta:number;underforecast_count:number;max_realized_variance:number}
export interface DiagnosticCoverage {regime:string;name:string;train_rows:number;validation_rows:number;evaluation_rows:number;nonoverlap_count:number;missing_to_30:number;train_share:number;evaluation_share:number;share_change:number}
export interface DiagnosticModel {name:string;raw:VolatilityMetrics;calibrated:VolatilityMetrics;comparison:VolatilityComparison;folds:{fold:string;raw_c:number;c:number;clipped:boolean;validation_rows:number;raw:VolatilityMetrics;calibrated:VolatilityMetrics;bins:DiagnosticBin[]}[];windows:DiagnosticWindow[];worst_windows:DiagnosticWindow[]}
export interface DiagnosticEnvelope {record:{schema:string;diagnostic_id:string;source_run_id:string;source_record_sha256:string;created_at:string;market:string;horizon:number;protocol:Record<string,unknown>;sources:Record<string,string>;artifacts:Record<string,string>;models:Record<string,DiagnosticModel>;coverage:DiagnosticCoverage[];coverage_folds:{fold:string;regimes:DiagnosticCoverage[]}[];limitations:string[]};record_sha256:string;artifact_status:'verified'|'missing';missing_artifacts:string[]}
export async function readDiagnostics(source:Pick<VolatilityEnvelope,'record'|'record_sha256'>,signal?:AbortSignal):Promise<DiagnosticEnvelope>{
 let response:Response;
 try{response=await fetch(`/api/v1/volatility/runs/${encodeURIComponent(source.record.run_id)}/diagnostics`,{signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('诊断服务暂不可用，请稍后重试。');}
 let body;try{body=await response.json();}catch{throw Error('诊断响应无法读取，请重试。');}
 if(signal?.aborted)throw new DOMException('aborted','AbortError');
 if(response.status===404)throw Error('尚无此版本的离线诊断；保留原始波动结果，可稍后重试。');
 if(!response.ok)throw Error(typeof body?.message==='string'?body.message:'诊断读取失败，请重试。');
 const r=body?.record;
 if(r?.source_run_id!==source.record.run_id||r?.source_record_sha256!==source.record_sha256||r?.market!==source.record.market||r?.horizon!==source.record.horizon)throw Error('诊断与当前波动版本不符，请重试。');
 if(r.schema!=='volatility-diagnostics-v1'||!/^vdiag-[a-f0-9]{64}$/.test(r.diagnostic_id)||!r.models||Object.keys(r.models).sort().join()!==Object.keys(source.record.overall).sort().join()||!Array.isArray(r.coverage)||!Array.isArray(r.coverage_folds)||!Array.isArray(r.limitations)||!Array.isArray(body.missing_artifacts)||!['verified','missing'].includes(body.artifact_status))throw Error('诊断结果格式不完整，请重试。');
 for(const model of Object.values(r.models) as DiagnosticModel[]){if(!model.raw||!model.calibrated||!model.comparison||!Array.isArray(model.folds)||model.folds.length!==source.record.folds.length||!Array.isArray(model.windows)||!Array.isArray(model.worst_windows)||model.folds.some(f=>!Array.isArray(f.bins)))throw Error('诊断模型格式不完整，请重试。');}
 return body as DiagnosticEnvelope;
}
export function diagnosticReport(body:DiagnosticEnvelope){const r=body.record;return [`# 波动诊断 · ${r.market} · 未来${r.horizon}日`,`来源实验：${r.source_run_id}`,`来源摘要：${r.source_record_sha256}`,`诊断摘要：${body.record_sha256}`,'QLIKE越低越好，校准减原始的负差值表示改善。验证段参与原模型早停，不是独立校准集。','| 方法 | 原始QLIKE | 校准QLIKE | 校准减原始 |','| --- | --- | --- | --- |',...Object.values(r.models).map(m=>`| ${m.name} | ${m.raw.qlike} | ${m.calibrated.qlike} | ${m.comparison.delta_qlike} |`),'## 限制',...r.limitations.map(s=>`- ${s}`),`产物核验：${body.artifact_status}；缺失：${body.missing_artifacts.join('、')||'无'}`,'## 全部季度、窗口、市况和来源','```json',JSON.stringify(r,null,2),'```'].join('\n\n');}
